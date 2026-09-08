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

Five cards need no credentials at all (coingecko, frankfurter, yahoo, sec_edgar, fred - the last
via its keyless graph CSV, not its keyed JSON api), which is what makes them the ones the test
suite can exercise honestly. Stooq is deliberately absent: its CSV endpoint now serves a
JavaScript proof-of-work challenge that a REST client cannot pass (checked 2026-09-08), so it is
PLANNED rather than quietly broken.
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


def _err_msg(j, raw_text):
    """The provider's own words, dug out of whichever envelope shape it used. Flat first - the
    common {"error": ...} / {"message": ...} shapes most providers use - then one level down, for
    a shape like yahoo's {"chart": {"error": {"description": ...}}}. Eight keyed providers copy
    this seam, so it stays this small: two passes, then the raw body as a last resort."""
    flat = (j.get('status', {}).get('error_message') if isinstance(j.get('status'), dict) else None) \
           or j.get('error') or j.get('message') or j.get('Note') or j.get('Information')
    if isinstance(flat, str) and flat.strip(): return flat
    for v in (j.values() if isinstance(j, dict) else ()):
        if not isinstance(v, dict): continue
        err = v.get('error') if isinstance(v.get('error'), dict) else v.get('Error')
        if isinstance(err, dict):
            nested = err.get('description') or err.get('message') or err.get('error_message')
            if nested: return str(nested)
    return raw_text[:200]


def _get(url, params=None, headers=None):
    r = requests.get(url, params=params or None, headers={'User-Agent': UA, **(headers or {})}, timeout=TIMEOUT)
    if r.status_code >= 300:
        try: j = r.json()
        except ValueError: j = {}
        raise MarketError(f'{r.status_code}: {_err_msg(j, r.text)[:300]}')
    try: return r.json()
    except ValueError: raise MarketError(f'{url} did not return JSON: {r.text[:200]}')


def _pct(v):
    try: return round(float(v), 2)
    except (TypeError, ValueError): return None


def _flt(v):
    """Every keyed provider below hands numbers back as strings (twelvedata, alphavantage) - this
    is the one coercion the row contract insists on, so a chart never has to parse "315.41" itself."""
    try: return float(str(v).rstrip('%'))
    except (TypeError, ValueError): return None


def _int(v):
    try: return int(float(v))
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


# ---- finnhub: quotes, company news and earnings, one key as a `token` query param -----------
# field mapping written from finnhub's documented shape 2026-09-08, NOT verified against a live
# response - report a mismatch rather than working around it. Its own error shape ({"error": ...})
# is already the flat case _err_msg checks first, so nothing there needed extending for this card.
FINNHUB_BASE = 'https://finnhub.io/api/v1'


def run_finnhub_quotes(cfg):
    """{"symbols": "AAPL,MSFT"} - price, change and day range per symbol.

    field mapping written from finnhub's documented shape 2026-09-08, NOT verified against a
    live response - report a mismatch rather than working around it. /quote answers bare-letter
    keys with no self-description at all: c current, d change, dp change percent, o/h/l open/
    high/low, pc previous close, t an epoch this card does not need."""
    key = _need(cfg, 'Finnhub', 'api_key', 'secret')
    rows = []
    for s in _syms(cfg, 'symbols', 'symbol') or ['AAPL']:
        j = _get(f'{FINNHUB_BASE}/quote', {'symbol': s, 'token': key})
        rows.append({'symbol': s, 'price': _flt(j.get('c')), 'change': _flt(j.get('d')), 'change_pct': _flt(j.get('dp')),
                     'open': _flt(j.get('o')), 'high': _flt(j.get('h')), 'low': _flt(j.get('l')), 'previous_close': _flt(j.get('pc'))})
    return _rows(cfg, rows, 'quotes')


def run_finnhub_news(cfg):
    """{"symbol": "AAPL", "from": "2026-09-01" (blank = 7 days back), "to": "" (blank = today)} -
    company news, whatever order the provider answers in: headline, source, url, published (an
    ISO date, converted here from finnhub's epoch).

    field mapping written from finnhub's documented shape 2026-09-08, NOT verified against a
    live response - report a mismatch rather than working around it. /company-news is a bare
    ARRAY of {headline, source, url, datetime, summary, ...}; datetime is epoch SECONDS."""
    from datetime import datetime, timedelta, timezone
    key = _need(cfg, 'Finnhub', 'api_key', 'secret')
    sym = (_syms(cfg, 'symbol', 'symbols') or ['AAPL'])[0]
    frm = str(cfg.get('from') or '').strip() or (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
    to = str(cfg.get('to') or '').strip() or datetime.now(timezone.utc).date().isoformat()
    j = _get(f'{FINNHUB_BASE}/company-news', {'symbol': sym, 'from': frm, 'to': to, 'token': key})
    rows = [{'symbol': sym, 'headline': n.get('headline'), 'source': n.get('source'), 'url': n.get('url'),
             'published': datetime.utcfromtimestamp(n['datetime']).isoformat() if n.get('datetime') else None}
            for n in (j or [])]
    return _rows(cfg, rows, 'articles')


def run_finnhub_earnings(cfg):
    """{"from": "2026-09-08" (blank = today), "to": "" (blank = 30 days out)} - upcoming earnings,
    one row per company: date, hour, eps_estimate, eps_actual, revenue_estimate.

    field mapping written from finnhub's documented shape 2026-09-08, NOT verified against a
    live response - report a mismatch rather than working around it. /calendar/earnings answers
    {"earningsCalendar": [{symbol, date, hour, epsEstimate, epsActual, revenueEstimate, ...}]}."""
    from datetime import datetime, timedelta, timezone
    key = _need(cfg, 'Finnhub', 'api_key', 'secret')
    frm = str(cfg.get('from') or '').strip() or datetime.now(timezone.utc).date().isoformat()
    to = str(cfg.get('to') or '').strip() or (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
    j = _get(f'{FINNHUB_BASE}/calendar/earnings', {'from': frm, 'to': to, 'token': key})
    rows = [{'symbol': e.get('symbol'), 'date': e.get('date'), 'hour': e.get('hour'),
             'eps_estimate': _flt(e.get('epsEstimate')), 'eps_actual': _flt(e.get('epsActual')),
             'revenue_estimate': _flt(e.get('revenueEstimate'))}
            for e in (j.get('earningsCalendar') or [])]
    return _rows(cfg, rows, 'earnings')


def run_finnhub_insiders(cfg):
    """{"symbol": "AAPL"} - insider transactions, newest first: name, date, shares, change, price.

    field mapping written from finnhub's documented shape 2026-09-08, NOT verified against a
    live response - report a mismatch rather than working around it. /stock/insider-transactions
    answers {"data": [{name, share, change, transactionDate, transactionPrice, ...}]} - "share"
    singular, and transactionPrice is the trade's own price, not a market quote."""
    key = _need(cfg, 'Finnhub', 'api_key', 'secret')
    sym = (_syms(cfg, 'symbol', 'symbols') or ['AAPL'])[0]
    j = _get(f'{FINNHUB_BASE}/stock/insider-transactions', {'symbol': sym, 'token': key})
    rows = [{'symbol': sym, 'name': d.get('name'), 'date': d.get('transactionDate'),
             'shares': _int(d.get('share')), 'change': _int(d.get('change')), 'price': _flt(d.get('transactionPrice'))}
            for d in (j.get('data') or [])]
    rows.sort(key=lambda r: str(r.get('date') or ''), reverse=True)
    return _rows(cfg, rows, 'transactions')


# ---- polygon: prev-day bar and a live snapshot, one key as an `apiKey` query param -----------
POLYGON_BASE = 'https://api.polygon.io'


def _polygon(url, params):
    """polygon can answer {"status": "ERROR", "error": ...} at HTTP 200 - _get's status-code
    check never sees that case, only the 4xx one, so a 200 carrying an error must be caught here
    or it would return zero rows instead of raising, the same trap twelvedata sets."""
    j = _get(url, params)
    if isinstance(j, dict) and j.get('status') == 'ERROR':
        raise MarketError(str(j.get('error') or 'polygon error'))
    return j


def run_polygon_bars(cfg):
    """{"symbol": "AAPL"} - the previous trading day's bar, one row: open, high, low, close, volume.

    field mapping written from polygon's documented shape 2026-09-08, NOT verified against a
    live response - report a mismatch rather than working around it. /v2/aggs/ticker/<SYM>/prev
    answers {"results": [{T,o,h,l,c,v,t}]}; t is epoch MILLISECONDS - divided by 1000 here before
    conversion, or the date would land in 1970."""
    from datetime import datetime
    key = _need(cfg, 'Polygon', 'api_key', 'secret')
    sym = (_syms(cfg, 'symbol', 'symbols') or ['AAPL'])[0]
    j = _polygon(f'{POLYGON_BASE}/v2/aggs/ticker/{sym}/prev', {'apiKey': key})
    rows = [{'symbol': r.get('T') or sym, 'date': datetime.utcfromtimestamp(r['t'] / 1000).date().isoformat(),
             'open': _flt(r.get('o')), 'high': _flt(r.get('h')), 'low': _flt(r.get('l')),
             'close': _flt(r.get('c')), 'volume': _int(r.get('v'))}
            for r in (j.get('results') or []) if r.get('t') is not None]
    rows.sort(key=lambda r: r['date'])
    return _rows(cfg, rows, 'bars')


def run_polygon_snapshot(cfg):
    """{"symbol": "AAPL"} - one row: last price, day change %, volume, updated.

    field mapping written from polygon's documented shape 2026-09-08, NOT verified against a
    live response - report a mismatch rather than working around it. /v2/snapshot/locale/us/
    markets/stocks/tickers/<SYM> answers {"ticker": {"day": {c,v}, "todaysChangePerc", "updated"}}
    - "updated" is documented as epoch NANOSECONDS on this endpoint, unlike the millisecond `t`
    the aggs endpoint above uses; unverified either way."""
    from datetime import datetime
    key = _need(cfg, 'Polygon', 'api_key', 'secret')
    sym = (_syms(cfg, 'symbol', 'symbols') or ['AAPL'])[0]
    j = _polygon(f'{POLYGON_BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{sym}', {'apiKey': key})
    t = j.get('ticker') or {}
    day = t.get('day') or {}
    upd = t.get('updated')
    rows = [{'symbol': t.get('ticker') or sym, 'price': _flt(day.get('c')), 'change_pct': _pct(t.get('todaysChangePerc')),
             'volume': _int(day.get('v')), 'updated': datetime.utcfromtimestamp(upd / 1e9).isoformat() if upd else None}]
    return _rows(cfg, rows, 'quotes')


# ---- tiingo: daily history and news - the only provider here keyed by a HEADER, not a param --
TIINGO_BASE = 'https://api.tiingo.com'


def run_tiingo_history(cfg):
    """{"symbol": "AAPL", "from": "2026-08-01" (blank = 30 days back)} - one row per day, oldest
    first: close, adj_close, volume.

    field mapping written from tiingo's documented shape 2026-09-08, NOT verified against a
    live response - report a mismatch rather than working around it. /tiingo/daily/<sym>/prices
    is a bare ARRAY of {date, close, adjClose, volume, ...}. The key rides as an
    `Authorization: Token <key>` HEADER, not a query param - _get already accepts headers for
    exactly this shape."""
    from datetime import datetime, timedelta, timezone
    key = _need(cfg, 'Tiingo', 'api_key', 'secret')
    sym = (_syms(cfg, 'symbol', 'symbols') or ['AAPL'])[0].lower()
    frm = str(cfg.get('from') or '').strip() or (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    j = _get(f'{TIINGO_BASE}/tiingo/daily/{sym}/prices', {'startDate': frm}, {'Authorization': f'Token {key}'})
    rows = [{'symbol': sym.upper(), 'date': str(r.get('date') or '')[:10], 'close': _flt(r.get('close')),
             'adj_close': _flt(r.get('adjClose')), 'volume': _int(r.get('volume'))}
            for r in (j or [])]
    return _rows(cfg, rows, 'bars')


def run_tiingo_news(cfg):
    """{"symbols": "AAPL,MSFT" (blank = every ticker tiingo has news for)} - headline, source,
    url, published; symbol carries every ticker the article is tagged with, joined.

    field mapping written from tiingo's documented shape 2026-09-08, NOT verified against a
    live response - report a mismatch rather than working around it. /tiingo/news is a bare
    ARRAY of {title, url, source, publishedDate, tickers, ...}."""
    key = _need(cfg, 'Tiingo', 'api_key', 'secret')
    syms = _syms(cfg, 'symbols', 'symbol')
    params = {'tickers': ','.join(s.lower() for s in syms)} if syms else {}
    j = _get(f'{TIINGO_BASE}/tiingo/news', params, {'Authorization': f'Token {key}'})
    rows = [{'symbol': ','.join(n.get('tickers') or []).upper(), 'headline': n.get('title'),
             'source': n.get('source'), 'url': n.get('url'), 'published': n.get('publishedDate')}
            for n in (j or [])]
    return _rows(cfg, rows, 'articles')





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


# ---- SEC EDGAR: official, free, keyless - and the only source here that hands back the 8-K ----
def _cik(cfg) -> str:
    c = str(cfg.get('cik') or '').strip().lstrip('Cc').lstrip('IiKk').strip()
    if not c.isdigit(): raise MarketError(f'{cfg.get("cik")!r} is not a CIK - use the number from sec.gov (Apple is 320193)')
    return c.zfill(10)


def run_edgar_filings(cfg):
    """{"cik": "320193", "forms": "8-K,10-Q" (blank = every form)} - what this company has filed,
    newest first, each row linking to the document itself. Schedule it with "can become work" and
    a new 8-K is a message triage judges."""
    cik = _cik(cfg)
    j = _get(f'https://data.sec.gov/submissions/CIK{cik}.json')
    r = ((j.get('filings') or {}).get('recent') or {})
    want = {f.strip().upper() for f in str(cfg.get('forms') or '').replace(';', ',').split(',') if f.strip()}
    bare, rows = cik.lstrip('0'), []
    for i, form in enumerate(r.get('form') or []):
        if want and str(form).upper() not in want: continue
        acc = (r.get('accessionNumber') or [''])[i].replace('-', '')
        doc = (r.get('primaryDocument') or [''])[i]
        rows.append({'company': j.get('name'), 'form': form, 'filed': (r.get('filingDate') or [''])[i],
                     'description': (r.get('primaryDocDescription') or [''])[i],
                     'url': f'https://www.sec.gov/Archives/edgar/data/{bare}/{acc}/{doc}'})
    return _rows(cfg, rows, 'filings')


def run_edgar_facts(cfg):
    """{"cik": "320193", "tag": "Revenues", "unit": "USD"} - one reported XBRL fact over time,
    newest first: the number as the company itself filed it, with the form it came from."""
    j = _get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{_cik(cfg)}.json')
    tag = str(cfg.get('tag') or 'Revenues').strip()
    facts = (j.get('facts') or {})
    for taxonomy in ('us-gaap', 'ifrs-full', 'dei'):
        got = (facts.get(taxonomy) or {}).get(tag)
        # a tag present but reporting zero observations must not shadow a populated taxonomy below it
        if got and any((got.get('units') or {}).values()): break
    else:
        raise MarketError(f'{j.get("entityName") or "this company"} reports no observations for XBRL tag {tag!r}')
    units = got.get('units') or {}
    want = str(cfg.get('unit') or '').strip()
    if want:
        if want not in units:
            raise MarketError(f'{tag} has no unit {want!r} on {j.get("entityName") or "this company"} '
                               f'- it reports {", ".join(sorted(units))}')
        unit = want
    else:
        # USD when the company reports it; otherwise the unit with the most observations, tied
        # alphabetically - dict order is a serialization artifact, never the thing that picks a series
        unit = 'USD' if 'USD' in units else sorted(units, key=lambda u: (-len(units[u]), u))[0]
    rows = [{'company': j.get('entityName'), 'tag': tag, 'unit': unit, 'end': f.get('end'),
             'value': f.get('val'), 'fy': f.get('fy'), 'fp': f.get('fp'), 'form': f.get('form')}
            for f in units.get(unit) or []]
    rows.sort(key=lambda r: str(r.get('end') or ''), reverse=True)
    return _rows(cfg, rows, 'facts')


# ---- twelvedata: quotes and technical indicators, one key on the card ------------------------
TD_BASE = 'https://api.twelvedata.com'
TD_INDICATORS = ('rsi', 'macd', 'sma', 'ema', 'bbands')


def _td(url, params):
    """twelvedata answers an error at HTTP 200 - {"code":.., "message":.., "status":"error"} -
    so _get's status-code check never sees it. A 200 that reports zero rows because of an error
    is a report that lies, so this is checked on every call before a row is ever built."""
    j = _get(url, params)
    if isinstance(j, dict) and j.get('status') == 'error':
        raise MarketError(str(j.get('message') or 'twelvedata error'))
    return j


def run_td_quotes(cfg):
    """{"symbol": "AAPL" or "symbols": "AAPL,MSFT"} - price, change % and day range per symbol.
    Every value in twelvedata's /quote response is a string; each is coerced to a number here."""
    key = _need(cfg, 'Twelve Data', 'api_key', 'secret')
    rows = []
    for s in _syms(cfg, 'symbols', 'symbol') or ['AAPL']:
        j = _td(f'{TD_BASE}/quote', {'symbol': s, 'apikey': key})
        rows.append({'symbol': j.get('symbol') or s, 'name': j.get('name'), 'exchange': j.get('exchange'),
                     'currency': j.get('currency'), 'price': _flt(j.get('close')), 'change_pct': _flt(j.get('percent_change')),
                     'open': _flt(j.get('open')), 'high': _flt(j.get('high')), 'low': _flt(j.get('low')),
                     'previous_close': _flt(j.get('previous_close')), 'volume': _int(j.get('volume'))})
    return _rows(cfg, rows, 'quotes')


def run_td_indicator(cfg):
    """{"symbol": "AAPL", "indicator": "rsi|macd|sma|ema|bbands", "interval": "1day", "time_period": 14, ...}
    - one row per bar, newest first: {symbol, indicator, date} plus every non-datetime numeric key
    the indicator returns. RSI hands back one value (rsi); MACD hands back several - both come
    through the same values-object unpack, which is the point of screening on either."""
    key = _need(cfg, 'Twelve Data', 'api_key', 'secret')
    ind = str(cfg.get('indicator') or 'rsi').strip().lower()
    if ind not in TD_INDICATORS:
        raise MarketError(f'{ind!r} is not a twelvedata indicator this card knows - one of: {", ".join(TD_INDICATORS)}')
    sym = (_syms(cfg, 'symbol', 'symbols') or ['AAPL'])[0]
    params = {'symbol': sym, 'apikey': key, 'interval': str(cfg.get('interval') or '1day')}
    for k in ('time_period', 'series_type', 'fast_period', 'slow_period', 'signal_period'):
        if cfg.get(k) not in (None, ''): params[k] = cfg[k]
    j = _td(f'{TD_BASE}/{ind}', params)
    rows = [{'symbol': sym, 'indicator': ind, 'date': v.get('datetime'),
             **{k: _flt(x) for k, x in v.items() if k != 'datetime'}}
            for v in j.get('values') or []]
    rows.sort(key=lambda r: str(r.get('date') or ''), reverse=True)
    return _rows(cfg, rows, 'values')


# ---- alphavantage: one quote, GLOBAL_QUOTE only - the demo key blocks every indicator ---------
AV_BASE = 'https://www.alphavantage.co/query'


def _av_err(j):
    """A rate limit or a refused call answers at HTTP 200 with Note/Information/Error Message
    and NO data - _get's status-code check never sees this either. Captured live: a demo key
    hitting RSI comes back exactly this way."""
    m = j.get('Note') or j.get('Information') or j.get('Error Message')
    if m: raise MarketError(str(m))


def run_av_quotes(cfg):
    """{"symbol": "IBM"} - one quote row: price, day range, volume and change % since the previous
    close. GLOBAL_QUOTE's fields live under a "Global Quote" key, every one a string, and change
    percent carries a literal "%" - both stripped before a chart or a screen sees them.

    av_indicator is deliberately not built: the demo key blocks every technical-indicator
    endpoint, so its shape is unverified - guessing it would be exactly the fail-open pattern
    this module has already fixed four times."""
    key = _need(cfg, 'Alpha Vantage', 'api_key', 'secret')
    sym = (_syms(cfg, 'symbol', 'symbols') or ['IBM'])[0]
    j = _get(AV_BASE, {'function': 'GLOBAL_QUOTE', 'symbol': sym, 'apikey': key})
    _av_err(j)
    gq = j.get('Global Quote') or {}
    if not gq: raise MarketError(f'alphavantage has no quote for {sym!r}')
    rows = [{'symbol': gq.get('01. symbol') or sym, 'price': _flt(gq.get('05. price')),
             'change_pct': _flt(gq.get('10. change percent')), 'volume': _int(gq.get('06. volume')),
             'previous_close': _flt(gq.get('08. previous close')), 'open': _flt(gq.get('02. open')),
             'high': _flt(gq.get('03. high')), 'low': _flt(gq.get('04. low')),
             'latest_day': gq.get('07. latest trading day')}]
    return _rows(cfg, rows, 'quotes')


# ---- FRED: macro series, keyless - fredgraph.csv needs no api_key at all (the JSON api does) --
FRED_CSV = 'https://fred.stlouisfed.org/graph/fredgraph.csv'


def _fred_csv(params):
    r = requests.get(FRED_CSV, params=params, headers={'User-Agent': UA}, timeout=TIMEOUT)
    if r.status_code >= 300: raise MarketError(f'{r.status_code}: fred did not return data')
    return r.text


def run_fred_series(cfg):
    """{"series": "DGS10", "from": "2026-08-01" (cosd), "to": "" (coed, blank = through today)}
    - one row per observation, newest first. Keyless - fredgraph.csv is the graph endpoint, not
    the JSON api, and it answers with no api_key at all.

    An unknown series id answers with an HTML error page, not CSV - parsing that as CSV would
    produce garbage rows, so it is detected and refused before a single line is split. A missing
    observation (a market holiday, a series not yet reported) is a lone "." in FRED's CSV; it
    becomes None here, never a string a chart would have to choke on."""
    series = str(cfg.get('series') or '').strip().upper()
    if not series: raise MarketError('no FRED series id given - e.g. DGS10, CPIAUCSL')
    params = {'id': series}
    if str(cfg.get('from') or '').strip(): params['cosd'] = str(cfg['from']).strip()
    if str(cfg.get('to') or '').strip(): params['coed'] = str(cfg['to']).strip()
    text = _fred_csv(params)
    if text.lstrip().lower().startswith(('<!doctype', '<html')):
        raise MarketError(f'{series!r} is not a FRED series id - fredgraph.csv answered an error page, not data')
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) < 2: raise MarketError(f'{series!r} returned no observations from FRED')
    rows = [{'series': series, 'date': cols[0], 'value': None if cols[1] == '.' else _flt(cols[1])}
            for l in lines[1:] for cols in [l.split(',')] if len(cols) >= 2]
    rows.sort(key=lambda r: r['date'], reverse=True)
    return _rows(cfg, rows, 'observations')


# ---- the screen: conditions in CONFIG, matches out ------------------------------------------
# The threshold lives here and not in a playbook. A playbook is prose flattened onto a command
# line; a number living in prose is a number re-judged by a model every run, and it will drift.
OPS = {'<': lambda a, b: a < b, '<=': lambda a, b: a <= b, '>': lambda a, b: a > b,
       '>=': lambda a, b: a >= b, '==': lambda a, b: a == b, '!=': lambda a, b: a != b}
# Only the quote-shaped providers - screening wants comparable numbers on every row, which is what
# a quote (price/change_pct/...) gives and a filing or an FX table does not. A provider must be
# ADDED HERE when it is built: naming one that does not exist yet would raise KeyError, not an
# error an owner can read (see run_markets_screen below). td_indicator belongs here too, even
# though it is not a quote: it is what lets a screen match a real strategy (["rsi", "<", 30])
# instead of only price moves. fred_series does NOT belong here - a macro series has no symbol
# to screen per-row.
SCREENABLE = ('yahoo_quotes', 'coingecko_prices', 'td_quotes', 'td_indicator', 'av_quotes')


def screen_connection(store, connector_id=None) -> dict:
    """The screen has no credentials of its own. CONNECTION_OF only ever hands this function
    (store, connector_id) - never the screen's own config - so connector_id IS the borrow: the
    owner points a markets_screen report at whichever provider's card it should read through
    (their coingecko card, say, if it carries a saved key), and that card's id is what
    connector_id names. There is no reverse lookup to do because the id already picks the card -
    but the id is owner input, and a wrong one must not hand an unrelated card's secret to
    whichever provider the screen calls (reports._connector refuses this same way for every
    other borrow; this is that same check, done here because CONNECTION_OF passes no cfg to
    check it against upstream)."""
    if not connector_id: return {}
    from .reports import card_of
    c = store.get_connector(int(connector_id), with_secret=True)
    if not c: return {}
    allowed = {card_of(p) for p in SCREENABLE}
    if c.get('Type') not in allowed:
        raise MarketError(f'connector {connector_id} is a {c.get("Type")!r} card - a screen may only borrow '
                           f'one of: {", ".join(sorted(allowed))}')
    cfg = json.loads(c.get('ConfigJson') or '{}')
    if c.get('Secret'): cfg.setdefault('api_key', c['Secret'])
    return {k: v for k, v in cfg.items() if v}


def run_markets_screen(cfg):
    """{"provider": "yahoo_quotes", "symbols": "AAPL,NVDA", "conditions": [["change_pct", "<=", -5]]}
    - the provider's rows, filtered to the ones where EVERY condition holds, and nothing else.

    Silence is the normal outcome, which is what makes alert "something came back" the right rule:
    a report that files a row every run is a report that stops being read - which is exactly why
    every ambiguity below refuses loudly instead of matching everything. A screen that fails OPEN
    (a dropped condition, an empty condition list, a config error read as "no match") turns the
    alert into one that fires every run, and an alarm that always fires is one nobody reads - a
    worse outcome than a crash."""
    prov = str(cfg.get('provider') or '').strip()
    if prov not in SCREENABLE:
        raise MarketError(f'{prov!r} is not a market source a screen can read - one of: {", ".join(SCREENABLE)}')
    raw_conds = cfg.get('conditions') or []
    for c in raw_conds:
        if not (isinstance(c, (list, tuple)) and len(c) == 3):
            raise MarketError(f'{c!r} is not a condition - each one is [field, operator, value]')
    if not raw_conds:
        raise MarketError('a screen needs at least one condition - conditions: [] would match every row, every run')
    for f, op, _ in raw_conds:
        if op not in OPS: raise MarketError(f'{op!r} is not a comparison operator - one of: {", ".join(OPS)}')
    _, body = globals()[f'run_{prov}']({k: v for k, v in cfg.items() if k not in ('provider', 'conditions')})
    rows = [json.loads(l) for l in str(body or '').splitlines() if l.strip()]
    fields_present = {k for r in rows for k in r}
    for f, op, _ in raw_conds:
        # a field missing from EVERY row is a misconfigured condition; missing from just THIS row
        # (a degraded row - see run_yahoo_quotes) is handled per-row below, as a non-match, not an error
        if rows and f not in fields_present:
            raise MarketError(f'{prov} returns no field {f!r} to screen on - it has: {", ".join(sorted(fields_present))}')
    out = []
    for r in rows:
        for f, op, want in raw_conds:
            if f not in r: break            # this row does not carry the field - it does not match, it is not a config error
            v = r.get(f)
            if v is None: break
            try: ok = OPS[op](v, want)
            except TypeError:
                raise MarketError(f'cannot compare {f} ({v!r}) {op} {want!r} - check the condition\'s value type')
            if not ok: break
        else: out.append(r)
    return _rows(cfg, out, 'matches')
