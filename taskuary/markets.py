"""Market data: the watchlist, the portfolio and the macro series as report sources.

Every executor here is plain REST with a key on a card - no SDK, no browser, nothing new frozen
into the single-exe build - which is the same boundary research.py draws and for the same reason.
Each returns (headline, body) like every other executor, so a quote source drops into a report
pipeline beside a SQL query and feeds the same prompt.

TWO RULES hold across the module and are not per-provider taste:

1. A numeric headline LEADS WITH ITS NUMBER (_num below). reports.result_count parses a leading
   number and strips its commas, so this is the only way an owner can write "tell me if it goes
   over 500" without teaching alert_fires a new condition. Cents are ignored by that comparison.
2. A missing key names THE CARD, not the provider's 401. An owner who has not signed up yet needs
   to be told where to go, and a provider's own auth error does not say "Connections -> Finnhub".

Four cards need no credentials at all (coingecko, frankfurter, yahoo, sec_edgar), which is what
makes them the ones the test suite can exercise honestly. Stooq is deliberately absent: its CSV
endpoint now serves a JavaScript proof-of-work challenge that a REST client cannot pass (checked
2026-09-08), so it is PLANNED rather than quietly broken.
"""
import json

import requests

TIMEOUT = 30
UA = 'Taskuary/1.0 (+https://github.com/ldbumble/taskuary)'    # sec.gov requires a contactable agent; others are happy with it


class MarketError(RuntimeError): pass


def _rows(cfg, rows, unit):
    from .reports import row_limit, rows_out
    lim, mine = row_limit(cfg)
    return rows_out(rows, lim, unit=unit, mine=mine)


def _num(cfg, total, words: str, rows) -> tuple:
    """A headline whose first token is the measure, so reports.result_count reads the MEASURE and
    an alert of "more than 500" means five hundred - not five hundred rows. See rule 1 above."""
    from .reports import BODY_CHARS
    body = '\n'.join(json.dumps(r, default=str) for r in rows)[:BODY_CHARS]
    return f'{float(total):,.2f} {words}', body


def _key(cfg, *names) -> str:
    for n in names:
        if str(cfg.get(n) or '').strip(): return str(cfg[n]).strip()
    return ''


def _need(cfg, card: str, *names) -> str:
    k = _key(cfg, *names)
    if not k: raise MarketError(f'no {card} API key saved - Connections -> {card}')
    return k


def _get(url, params=None, headers=None):
    r = requests.get(url, params=params or None, headers={'User-Agent': UA, **(headers or {})}, timeout=TIMEOUT)
    if r.status_code >= 300:
        try: j = r.json()
        except ValueError: j = {}
        msg = (j.get('status', {}).get('error_message') if isinstance(j.get('status'), dict) else None) \
              or j.get('error') or j.get('message') or j.get('Note') or j.get('Information') or r.text[:200]
        raise MarketError(f'{r.status_code}: {str(msg)[:300]}')
    try: return r.json()
    except ValueError: raise MarketError(f'{url} did not return JSON: {r.text[:200]}')


def _pct(v):
    try: return round(float(v), 2)
    except (TypeError, ValueError): return None


# ---- coingecko: crypto spot, keyless (a demo key only raises the limit) -----------------
def run_coingecko_prices(cfg):
    """{"ids": "bitcoin,ethereum", "vs": "usd"} - spot price and 24h change per coin. Works with
    no key at all; a demo key raises the rate limit, which is run_reader's precedent."""
    ids = str(cfg.get('ids') or 'bitcoin').strip()
    vs = str(cfg.get('vs') or 'usd').strip().lower()
    key = _key(cfg, 'api_key', 'secret')
    j = _get('https://api.coingecko.com/api/v3/simple/price',
             {'ids': ids, 'vs_currencies': vs, 'include_24hr_change': 'true'},
             {'x-cg-demo-api-key': key} if key else None)
    rows = [{'id': k, 'currency': vs, 'price': v.get(vs), 'change_pct': _pct(v.get(f'{vs}_24h_change'))}
            for k, v in (j or {}).items()]
    return _rows(cfg, rows, 'prices')


def run_finnhub_quotes(cfg):
    """{"symbols": "AAPL,MSFT"} - last, change and day range per symbol. Filled in at Task 6."""
    _need(cfg, 'Finnhub', 'api_key', 'secret')
    raise MarketError('finnhub quotes not implemented yet')


# ---- frankfurter: FX, keyless. api.frankfurter.app 301s now; .dev/v1 is the live host --------
def run_fx_rates(cfg):
    """{"base": "USD", "symbols": "EUR,GBP" (blank = every currency)} - reference rates, no key."""
    p = {'base': str(cfg.get('base') or 'USD').strip().upper()}
    if str(cfg.get('symbols') or '').strip(): p['symbols'] = str(cfg['symbols']).replace(' ', '')
    j = _get('https://api.frankfurter.dev/v1/latest', p)
    rows = [{'base': j.get('base'), 'currency': k, 'rate': v, 'date': j.get('date')}
            for k, v in sorted((j.get('rates') or {}).items())]
    return _rows(cfg, rows, 'rates')


# ---- yahoo: keyless, and the only card here that is not a supported API ---------------------
# v8/finance/chart serves without a cookie or a crumb (checked 2026-09-08). v7/finance/quote is
# the endpoint that wants one - it is deliberately not used. Yahoo retired its official API in
# 2017, so this card is BEST-EFFORT and its copy says so: if it breaks, that is the deal, not a
# bug to be fixed under pressure.
CHART = 'https://query1.finance.yahoo.com/v8/finance/chart/'


def _yahoo_chart(sym, rng, interval):
    return _get(f'{CHART}{sym}', {'range': rng, 'interval': interval})


def _syms(cfg, *names):
    raw = _key(cfg, *names) or ''
    return [s.strip().upper() for s in raw.replace(';', ',').split(',') if s.strip()]


def run_yahoo_quotes(cfg):
    """{"symbols": "AAPL,MSFT"} - last, day change %, day range and previous close per symbol.

    A symbol Yahoo cannot resolve becomes a row carrying its error rather than taking the whole
    report down: a watchlist with one bad ticker is still a watchlist."""
    rows = []
    for s in _syms(cfg, 'symbols', 'symbol') or ['AAPL']:
        try:
            m = (((_yahoo_chart(s, '1d', '1d').get('chart') or {}).get('result') or [{}])[0] or {}).get('meta') or {}
            rows.append({'symbol': m.get('symbol') or s, 'price': m.get('regularMarketPrice'),
                         'change_pct': _pct(m.get('regularMarketChangePercent')), 'currency': m.get('currency'),
                         'day_low': m.get('regularMarketDayLow'), 'day_high': m.get('regularMarketDayHigh'),
                         'previous_close': m.get('previousClose'), 'exchange': m.get('fullExchangeName')})
        except MarketError as e:
            rows.append({'symbol': s, 'price': None, 'error': str(e)[:200]})
    return _rows(cfg, rows, 'quotes')


def run_yahoo_history(cfg):
    """{"symbol": "AAPL", "range": "5d|1mo|1y", "interval": "1d|1h"} - one row per bar, oldest first."""
    from datetime import datetime
    s = (_syms(cfg, 'symbol', 'symbols') or ['AAPL'])[0]
    res = (((_yahoo_chart(s, cfg.get('range') or '1mo', cfg.get('interval') or '1d').get('chart') or {}).get('result') or [{}])[0]) or {}
    q = ((res.get('indicators') or {}).get('quote') or [{}])[0] or {}
    closes, vols, ts = q.get('close') or [], q.get('volume') or [], res.get('timestamp') or []
    rows = [{'symbol': s, 'date': datetime.utcfromtimestamp(t).date().isoformat(),
             'close': closes[i] if i < len(closes) else None, 'volume': vols[i] if i < len(vols) else None}
            for i, t in enumerate(ts)]
    return _rows(cfg, rows, 'bars')
