# Market data connectors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `taskuary/markets.py` — twelve market-data provider cards and a deterministic strategy screen, so a watchlist or a portfolio can be a scheduled report on the Timeline and a match can become work.

**Architecture:** One module holding every provider, following `taskuary/research.py`: each executor is plain REST with a key on a card, no SDK, nothing new frozen into the single-exe build, and each returns `(headline, body)` through `reports.rows_out` so a market source drops into a report pipeline beside a SQL query. Wiring is additive registry entries only. Phase A is the four cards that need no credentials — they are the ones CI can actually exercise. Phase B is the keyed cards, each of which begins by capturing a real response rather than assuming its shape. Phase C is the screen.

**Tech Stack:** Python 3.10, `requests` (already a dependency; mocked at the HTTP edge in tests, per `tests/test_teller.py`), pytest with `unittest` style under `tests/`, React/JSX + vite for the cards, loguru.

**Spec:** `docs/superpowers/specs/2026-09-08-finance-agent-design.md` — Part 1 (the provider tables) and Part 3 layer 1 (`markets_screen`).

## Global Constraints

- **Connectors only.** New module plus additive registry entries. Do not edit `alert_fires`, `result_count`, `resolve_cfg`, `rows_out`, `proposals.py`, `terminal.py`, `playbooks.py`, or the seed. If a task appears to need one, stop and report.
- **Every numeric executor's headline LEADS WITH ITS NUMBER.** `reports.result_count` parses a leading number and strips commas, so this is the only way an owner can write a threshold (`alert {"when": "more_than", "count": 500}`) without a new alert condition. This is the module's idiom, established by `teller_spend`; it is not optional per-provider taste.
- **Spec corrections verified live 2026-09-08, already applied below — do not restore the spec's versions:**
  - `stooq` is **dropped**. Its CSV endpoint now serves a JavaScript proof-of-work bot challenge; a browser User-Agent does not defeat it. It moves to `reports.PLANNED`. The spec's claim that it is "officially free, no signup" is false as of today.
  - `frankfurter` is `https://api.frankfurter.dev/v1/latest`, not `api.frankfurter.app/latest` (which 301s).
  - `yahoo`'s `v8/finance/chart` path serves keyless with no cookie and no crumb — verified. Do **not** implement the crumb handshake; do not use `v7/finance/quote`.
- Dense fast.ai code style; no formatters. New files LF.
- Never write a backslash line-continuation or a Windows path through a heredoc; patch by line index.
- Tests from the repo root: `python -m pytest <files> -q -p no:cacheprovider`. "no tests ran" is a failure.
- **No live network in tests.** `tests/conftest.py` fences I/O boundaries; every executor test mocks `requests` at the edge the way `tests/test_teller.py` does. Captured real responses are pasted in as literals, never fetched during a test run.
- The packaged UI in `taskuary/web/assets/` is committed. A JSX change is not done until `npm run build` runs (Task 13).
- Shared checkout, shared git index: build every commit **off-index** (`GIT_INDEX_FILE=$(mktemp -u) git read-tree HEAD` → `hash-object -w` → `update-index --cacheinfo` → `write-tree` → `commit-tree -p HEAD` → guarded `update-ref <ref> <new> <old>`). Never `git add` here.
- **After every off-index commit, repair the shared index.** With `GIT_INDEX_FILE` unset, run
  `git update-index --add -- <the files you committed>`. Without this the shared index stays blind to
  new files, `git status` reports them as staged deletions, and another agent running `git commit -am`
  commits their removal. Found live on 2026-09-08. Use `--add` on named paths only — never
  `git read-tree HEAD` against the real index, which would discard another agent's staged work.
- **Nothing is pushed.** Stops at a review gate; the whole suite runs from the repo root before any later push.
- Card copy stays plain and unexcited. No emoji. A card that can break says so plainly rather than being quietly optimistic.

---

## Phase A — the cards that need no credentials

### Task 1: The module, its helpers, and crypto prices

**Files:**
- Create: `taskuary/markets.py`
- Create: `tests/test_markets.py`

**Interfaces:**
- Produces, and every later task consumes:
  - `markets._rows(cfg, rows: list, unit: str) -> (str, str)` — the `rows_out` wrapper, identical in role to `research._rows`.
  - `markets._num(cfg, total, words: str, rows: list) -> (str, str)` — the numeric-headline builder that puts `total` first so `result_count` reads it. Returns `(f'{total:,.2f} {words}', body)`.
  - `markets._key(cfg, *names) -> str` — first non-empty of the named config keys, `''` if none.
  - `markets._get(url, params=None, headers=None) -> dict` — a guarded GET returning parsed JSON, raising `MarketError` with the provider's own message on a non-2xx.
  - `markets.MarketError(RuntimeError)`.
  - `markets.run_coingecko_prices(cfg) -> (headline, body)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_markets.py`:

```python
"""Market data: plain REST with a key on a card, mocked at the HTTP edge. What is under test is
the SHAPE - the row keys a report and a chart consume, the headline that leads with its number so
a threshold compares the number and not the row count, and the refusal when no key is saved."""
import json
import unittest
from unittest import mock

from taskuary import markets

# captured live 2026-09-08 from api.coingecko.com/api/v3/simple/price
CG = {'bitcoin': {'usd': 78624, 'usd_24h_change': -0.6056038333762712}}


def _resp(status, body, text=None):
    r = mock.Mock(); r.status_code = status; r.text = text if text is not None else json.dumps(body)
    r.json = lambda: body
    return r


class TheHelpers(unittest.TestCase):
    def test_a_numeric_headline_leads_with_the_number_so_a_threshold_reads_dollars(self):
        from taskuary.reports import alert_fires, result_count
        head, body = markets._num({}, 1518.2, 'spent across 2 accounts', [{'a': 1}])
        self.assertTrue(head.startswith('1,518.20 '), head)
        self.assertEqual(result_count(head, body), 1518)
        self.assertIn('more than the 500', alert_fires({'alert': {'when': 'more_than', 'count': 500, 'to': 'x'}}, head, body))

    def test_a_missing_key_names_the_card_rather_than_failing_at_the_provider(self):
        with self.assertRaisesRegex(markets.MarketError, 'Finnhub'):
            markets.run_finnhub_quotes({'symbols': 'AAPL'})


class TheCrypto(unittest.TestCase):
    def test_prices_carry_the_symbol_price_and_day_change(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, CG)) as g:
            head, body = markets.run_coingecko_prices({'ids': 'bitcoin', 'vs': 'usd'})
        rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        self.assertEqual(rows, [{'id': 'bitcoin', 'currency': 'usd', 'price': 78624, 'change_pct': -0.61}])
        self.assertEqual(head, '1 prices')   # rows_out substitutes the unit word; it does not singularise
        self.assertNotIn('x-cg-demo-api-key', g.call_args.kwargs.get('headers') or {})

    def test_a_demo_key_rides_as_a_header_when_one_is_saved(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, CG)) as g:
            markets.run_coingecko_prices({'ids': 'bitcoin', 'api_key': 'demo_abc'})
        self.assertEqual(g.call_args.kwargs['headers']['x-cg-demo-api-key'], 'demo_abc')

    def test_the_providers_own_error_reaches_the_owner(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(429, {'status': {'error_message': 'rate limited'}})):
            with self.assertRaisesRegex(markets.MarketError, 'rate limited'):
                markets.run_coingecko_prices({'ids': 'bitcoin'})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_markets.py -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'taskuary.markets'`.

- [ ] **Step 3: Write the module**

Create `taskuary/markets.py`:

```python
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
```

Then add the Finnhub stub the helper test reaches for — the full executor lands in Task 6, but the
key refusal is part of this task's contract:

```python
def run_finnhub_quotes(cfg):
    """{"symbols": "AAPL,MSFT"} - last, change and day range per symbol. Filled in at Task 6."""
    _need(cfg, 'Finnhub', 'api_key', 'secret')
    raise MarketError('finnhub quotes not implemented yet')
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_markets.py -q -p no:cacheprovider`
Expected: PASS. `test_prices_carry_the_symbol_price_and_day_change` pins `'1 price'` — `rows_out` singularises by replacing `'rows'` once, so confirm the unit word it produces and match the assertion to the real behaviour rather than editing `rows_out`.

- [ ] **Step 5: Commit**

Off-index recipe, `taskuary/markets.py tests/test_markets.py`, message:

```
feat: markets.py, and crypto prices as its first keyless source

research.py's shape for market data: plain REST, a key on a card, (headline, body) out. Two rules
the module holds to - a numeric headline leads with its number so result_count reads the measure
and an owner's "more than 500" means dollars, and a missing key names the CARD rather than
relaying a provider's 401 to someone who has not signed up yet.
```

---

### Task 2: FX rates

**Files:** Modify `taskuary/markets.py`, `tests/test_markets.py`

**Interfaces:** Consumes `_rows`, `_get`. Produces `markets.run_fx_rates(cfg)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_markets.py`:

```python
# captured live 2026-09-08 from api.frankfurter.dev/v1/latest
FX = {'amount': 1.0, 'base': 'USD', 'date': '2026-09-08', 'rates': {'EUR': 0.86103, 'GBP': 0.73825}}


class TheFx(unittest.TestCase):
    def test_one_row_per_currency_with_the_base_and_the_date(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, FX)) as g:
            head, body = markets.run_fx_rates({'base': 'USD', 'symbols': 'EUR,GBP'})
        rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        self.assertEqual(rows, [{'base': 'USD', 'currency': 'EUR', 'rate': 0.86103, 'date': '2026-09-08'},
                                {'base': 'USD', 'currency': 'GBP', 'rate': 0.73825, 'date': '2026-09-08'}])
        self.assertEqual(g.call_args.args[0], 'https://api.frankfurter.dev/v1/latest')
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_markets.py::TheFx -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: run_fx_rates`.

- [ ] **Step 3: Implement**

```python
# ---- frankfurter: FX, keyless. api.frankfurter.app 301s now; .dev/v1 is the live host --------
def run_fx_rates(cfg):
    """{"base": "USD", "symbols": "EUR,GBP" (blank = every currency)} - reference rates, no key."""
    p = {'base': str(cfg.get('base') or 'USD').strip().upper()}
    if str(cfg.get('symbols') or '').strip(): p['symbols'] = str(cfg['symbols']).replace(' ', '')
    j = _get('https://api.frankfurter.dev/v1/latest', p)
    rows = [{'base': j.get('base'), 'currency': k, 'rate': v, 'date': j.get('date')}
            for k, v in sorted((j.get('rates') or {}).items())]
    return _rows(cfg, rows, 'rates')
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_markets.py -q -p no:cacheprovider` — Expected: PASS.

- [ ] **Step 5: Commit** — off-index, message: `feat: FX rates, keyless, on frankfurter's live .dev host`

---

### Task 3: Yahoo quotes and history

**Files:** Modify `taskuary/markets.py`, `tests/test_markets.py`

**Interfaces:** Consumes `_rows`, `_num`, `_get`, `_pct`. Produces `markets.run_yahoo_quotes(cfg)`, `markets.run_yahoo_history(cfg)`.

**Read before implementing:** the `v8/finance/chart` path serves keyless — verified 2026-09-08, no cookie and no crumb. Do not implement a crumb handshake and do not reach for `v7/finance/quote`, which is the endpoint that needs one. One symbol per request; loop the list.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_markets.py`:

```python
# captured live 2026-09-08 from query1.finance.yahoo.com/v8/finance/chart/AAPL (meta trimmed)
YQ = {'chart': {'result': [{'meta': {'currency': 'USD', 'symbol': 'AAPL', 'fullExchangeName': 'NasdaqGS',
                                     'instrumentType': 'EQUITY', 'regularMarketPrice': 316.195,
                                     'regularMarketChangePercent': -1.18, 'regularMarketTime': 1788889085,
                                     'regularMarketDayHigh': 319.4, 'regularMarketDayLow': 314.0,
                                     'previousClose': 319.97, 'exchangeTimezoneName': 'America/New_York'},
                            'timestamp': [1788800000, 1788886400],
                            'indicators': {'quote': [{'close': [318.1, 316.195], 'volume': [41000000, 38000000]}]}}],
                'error': None}}


class TheYahoo(unittest.TestCase):
    def test_a_quote_row_carries_last_change_and_the_day_range(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, YQ)) as g:
            head, body = markets.run_yahoo_quotes({'symbols': 'AAPL'})
        row = json.loads(body.splitlines()[0])
        self.assertEqual(row['symbol'], 'AAPL')
        self.assertEqual((row['price'], row['change_pct'], row['currency']), (316.195, -1.18, 'USD'))
        self.assertEqual((row['day_low'], row['day_high'], row['previous_close']), (314.0, 319.4, 319.97))
        self.assertEqual(row['exchange'], 'NasdaqGS')
        self.assertIn('/v8/finance/chart/AAPL', g.call_args.args[0])
        self.assertNotIn('crumb', json.dumps(g.call_args.kwargs))

    def test_several_symbols_are_several_calls_and_one_table(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, YQ)) as g:
            head, body = markets.run_yahoo_quotes({'symbols': 'AAPL, MSFT'})
        self.assertEqual(g.call_count, 2)
        self.assertEqual(len([l for l in body.splitlines() if l.strip()]), 2)

    def test_a_symbol_yahoo_does_not_know_is_named_and_the_rest_still_come_back(self):
        def side(url, **kw):
            return _resp(200, YQ) if '/AAPL' in url else _resp(404, {'chart': {'error': {'description': 'No data found, symbol may be delisted'}}})
        with mock.patch.object(markets.requests, 'get', side_effect=side):
            head, body = markets.run_yahoo_quotes({'symbols': 'AAPL,NOPE'})
        rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]['symbol'], 'NOPE')
        self.assertIn('delisted', rows[1]['error'])

    def test_history_is_one_row_per_bar_newest_last(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, YQ)):
            head, body = markets.run_yahoo_history({'symbol': 'AAPL', 'range': '5d', 'interval': '1d'})
        rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        self.assertEqual([r['close'] for r in rows], [318.1, 316.195])
        self.assertEqual(rows[0]['date'], '2026-09-07')
```

> Implementer note on the last assertion: `1788800000` is a real epoch second from the captured
> response. Compute the expected date with `datetime.utcfromtimestamp(1788800000).date().isoformat()`
> and assert that value rather than the literal above if they differ — the row must carry a
> UTC-derived ISO date, and the point of the assertion is the derivation, not the string.

- [ ] **Step 2: Run to verify it fails** — `python -m pytest tests/test_markets.py::TheYahoo -q -p no:cacheprovider`, expected `AttributeError: run_yahoo_quotes`.

- [ ] **Step 3: Implement**

```python
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
```

- [ ] **Step 4: Run to verify it passes** — `python -m pytest tests/test_markets.py -q -p no:cacheprovider`, expected PASS.

- [ ] **Step 5: Commit** — off-index, message:

```
feat: Yahoo quotes and bars, keyless, on the one path that needs no crumb

v8/finance/chart serves without a cookie (checked 2026-09-08); v7/finance/quote is the one that
wants a crumb and is deliberately unused. A ticker Yahoo cannot resolve becomes a row with its
error, because a watchlist with one bad symbol is still a watchlist.
```

---

### Task 4: SEC filings and company facts

**Files:** Modify `taskuary/markets.py`, `tests/test_markets.py`

**Interfaces:** Consumes `_rows`, `_get`. Produces `markets.run_edgar_filings(cfg)`, `markets.run_edgar_facts(cfg)`.

**Read before implementing:** `data.sec.gov` refuses a request without a contactable `User-Agent` — the module's `UA` constant already supplies one, which is why `_get` sets it on every call. A CIK is zero-padded to ten digits in the path.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_markets.py`:

```python
# captured live 2026-09-08 from data.sec.gov/submissions/CIK0000320193.json (trimmed)
EDGAR = {'cik': '0000320193', 'entityType': 'operating', 'sic': '3571', 'sicDescription': 'Electronic Computers',
         'name': 'Apple Inc.', 'tickers': ['AAPL'],
         'filings': {'recent': {'accessionNumber': ['0000320193-26-000081', '0000320193-26-000075'],
                                'filingDate': ['2026-08-01', '2026-07-15'], 'form': ['10-Q', '8-K'],
                                'primaryDocument': ['aapl-20260627.htm', 'ex991.htm'],
                                'primaryDocDescription': ['10-Q', 'EX-99.1']}}}


class TheEdgar(unittest.TestCase):
    def test_filings_are_rows_newest_first_with_a_link_to_the_document(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, EDGAR)) as g:
            head, body = markets.run_edgar_filings({'cik': '320193'})
        rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        self.assertEqual(rows[0]['form'], '10-Q')
        self.assertEqual(rows[0]['filed'], '2026-08-01')
        self.assertEqual(rows[0]['company'], 'Apple Inc.')
        self.assertIn('320193/000032019326000081/aapl-20260627.htm', rows[0]['url'])
        self.assertIn('CIK0000320193.json', g.call_args.args[0])          # zero-padded to ten
        self.assertIn('Taskuary', g.call_args.kwargs['headers']['User-Agent'])

    def test_only_the_forms_asked_for_come_back(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, EDGAR)):
            _, body = markets.run_edgar_filings({'cik': '320193', 'forms': '8-K'})
        rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        self.assertEqual([r['form'] for r in rows], ['8-K'])
```

- [ ] **Step 2: Run to verify it fails** — expected `AttributeError: run_edgar_filings`.

- [ ] **Step 3: Implement**

```python
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
        if got: break
    else:
        raise MarketError(f'{j.get("entityName") or "this company"} reports no XBRL tag {tag!r}')
    unit = str(cfg.get('unit') or '').strip() or next(iter(got.get('units') or {}), 'USD')
    rows = [{'company': j.get('entityName'), 'tag': tag, 'unit': unit, 'end': f.get('end'),
             'value': f.get('val'), 'fy': f.get('fy'), 'fp': f.get('fp'), 'form': f.get('form')}
            for f in (got.get('units') or {}).get(unit) or []]
    rows.sort(key=lambda r: str(r.get('end') or ''), reverse=True)
    return _rows(cfg, rows, 'facts')
```

- [ ] **Step 4: Run to verify it passes** — `python -m pytest tests/test_markets.py -q -p no:cacheprovider`, expected PASS.

- [ ] **Step 5: Commit** — off-index, message: `feat: SEC filings and XBRL facts - official, keyless, and the only source that hands back the 8-K`

---

### Task 5: Wire the keyless four so they are usable

**Files:**
- Modify: `taskuary/reports.py` — `REGISTRY` (after the teller block, ~line 611), `CARD_OF` (~654), `PLANNED` (line 15)
- Modify: `taskuary/scopes.py` — `ACTIONS` (after the teller line, ~44), `DEFAULT_SCOPE` (~87)
- Modify: `taskuary/docsync.py:69` — the type list an agent is shown
- Modify: `taskuary/store.py:673` — the connector catalog rows so the cards exist to configure
- Test: `tests/test_markets.py` (append)

**Interfaces:** Consumes every `run_*` from Tasks 1-4. Produces the types `coingecko_prices`, `fx_rates`, `yahoo_quotes`, `yahoo_history`, `edgar_filings`, `edgar_facts` resolvable through `reports.executor_for`, each at scope `read`.

- [ ] **Step 1: Write the failing test**

```python
class TheWiring(unittest.TestCase):
    KEYLESS = ('coingecko_prices', 'fx_rates', 'yahoo_quotes', 'yahoo_history', 'edgar_filings', 'edgar_facts')

    def test_every_type_is_registered_a_read_and_owned_by_a_card(self):
        from taskuary import reports, scopes
        for t in self.KEYLESS:
            self.assertIn(t, reports.REGISTRY, t)
            self.assertIs(reports.executor_for(t), reports.REGISTRY[t], t)
            self.assertEqual(scopes.needs(t), 'read', t)
            self.assertIn(reports.card_of(t), ('coingecko', 'frankfurter', 'yahoo', 'sec_edgar'), t)

    def test_a_keyless_card_needs_no_connection_entry_and_resolve_cfg_passes_the_config_through(self):
        from taskuary import reports
        from taskuary.store import MemoryStore
        cfg = reports.resolve_cfg(MemoryStore(), {'type': 'yahoo_quotes', 'symbols': 'AAPL'})
        self.assertEqual(cfg['symbols'], 'AAPL')

    def test_stooq_is_planned_and_fails_loudly_rather_than_being_absent(self):
        from taskuary import reports
        self.assertIn('stooq', reports.PLANNED)
        with self.assertRaises(Exception):
            reports.REGISTRY['stooq']({})

    def test_the_cards_are_in_the_catalog_so_they_can_be_configured(self):
        from taskuary.store import MemoryStore
        types = {c['Type'] for c in MemoryStore().list_connectors()}
        for card in ('coingecko', 'frankfurter', 'yahoo', 'sec_edgar'): self.assertIn(card, types, card)
```

- [ ] **Step 2: Run to verify it fails** — expected `AssertionError: 'coingecko_prices' not found in REGISTRY`.

- [ ] **Step 3: Add the registry lines**

`taskuary/reports.py`, in `REGISTRY` after the teller block:

```python
            # market data (markets.py): the watchlist, the filing and the FX rate as report sources.
            # These four cards need no credentials at all, which is why they are the ones CI exercises.
            'coingecko_prices': _lazy('markets', 'run_coingecko_prices'), 'fx_rates': _lazy('markets', 'run_fx_rates'),
            'yahoo_quotes': _lazy('markets', 'run_yahoo_quotes'), 'yahoo_history': _lazy('markets', 'run_yahoo_history'),
            'edgar_filings': _lazy('markets', 'run_edgar_filings'), 'edgar_facts': _lazy('markets', 'run_edgar_facts'),
```

`taskuary/reports.py`, in `CARD_OF`:

```python
           'coingecko_prices': 'coingecko', 'fx_rates': 'frankfurter',
           'yahoo_quotes': 'yahoo', 'yahoo_history': 'yahoo',
           'edgar_filings': 'sec_edgar', 'edgar_facts': 'sec_edgar',
```

`taskuary/reports.py:15`, in `PLANNED` — add `'stooq'` with the reason, since a planned entry with no
explanation invites someone to "just implement it":

```python
           'stooq',    # its CSV endpoint serves a JS proof-of-work challenge now (2026-09-08) - not reachable from REST
```

`taskuary/scopes.py`, in `ACTIONS` after the teller line:

```python
    # market data: every one of these is a window on a public market. Nothing upstream moves.
    'coingecko_prices': 'read', 'fx_rates': 'read', 'yahoo_quotes': 'read', 'yahoo_history': 'read',
    'edgar_filings': 'read', 'edgar_facts': 'read',
```

`taskuary/scopes.py`, in `DEFAULT_SCOPE`:

```python
    'coingecko': 'read', 'frankfurter': 'read', 'yahoo': 'read', 'sec_edgar': 'read',
```

- [ ] **Step 4: Add the catalog rows**

`taskuary/store.py:673` — extend the tuple list so the cards exist to be configured. Follow the exact
shape of the neighbouring entries:

```python
                         ('coingecko', 'Crypto prices (CoinGecko)'), ('frankfurter', 'FX rates'),
                         ('yahoo', 'Yahoo Finance (best-effort)'), ('sec_edgar', 'SEC filings (EDGAR)'),
```

Read the surrounding lines first: if that catalog also carries a `Roles` default per type (as
`store.py:455` does for `teller`), give each of these `'report,tool'` — they are report sources and
agent tools, and neither is a trigger or a notifier.

- [ ] **Step 5: Name them in the list an agent is shown**

`taskuary/docsync.py:69` — append to the pipe-separated string after `teller_spend`:

```
|yahoo_quotes|yahoo_history|edgar_filings|edgar_facts|coingecko_prices|fx_rates
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_markets.py tests/test_teller.py tests/test_seeded_reports.py tests/test_agent_identity.py -q -p no:cacheprovider`
Expected: PASS. `test_seeded_reports` and `test_agent_identity` are here because both assert over the
connector catalog and will catch a malformed row.

- [ ] **Step 7: Commit** — off-index, message:

```
feat: the four keyless market cards are registered, read-only, and in the catalog

Additive registry lines only. stooq joins PLANNED with its reason recorded - its CSV endpoint
serves a JS proof-of-work challenge a REST client cannot pass - so nobody re-implements it from
the spec's out-of-date claim that it is a clean free source.
```

---

## Phase B — the keyed providers

Each task in this phase follows the same discipline and it matters: **capture the real response
first, then write the test against what came back.** Guessing a provider's JSON shape produces a
parser that passes its own invented fixture and fails on contact. The row contract below is fully
specified for each provider; the provider's own JSON is evidence to be gathered, not assumed.

Each task's Step 1 is a `curl` the implementer runs with the owner's key. If no key is available,
**stop and report** rather than inventing a shape — an unbuilt card is honest, a wrong one is not.

### Task 6: Finnhub — quotes, company news, earnings calendar, insider transactions

**Files:** Modify `taskuary/markets.py` (replace the Task 1 stub), `tests/test_markets.py`

**Interfaces:** Produces `run_finnhub_quotes`, `run_finnhub_news`, `run_finnhub_earnings`, `run_finnhub_insiders`. Base `https://finnhub.io/api/v1`, key as the `token` query parameter.

**Row contracts — these are the assertions, whatever the provider's field names turn out to be:**
- `finnhub_quotes` → `{symbol, price, change_pct, day_low, day_high, previous_close}` from `/quote?symbol=`
- `finnhub_news` → `{symbol, headline, source, url, published}` (ISO date) from `/company-news?symbol=&from=&to=`
- `finnhub_earnings` → `{symbol, date, hour, eps_estimate, revenue_estimate}` from `/calendar/earnings?from=&to=`
- `finnhub_insiders` → `{symbol, name, date, shares, change, price}` from `/stock/insider-transactions?symbol=`

- [ ] **Step 1: Capture the real shapes**

```bash
K=<the owner's finnhub key>
curl -s "https://finnhub.io/api/v1/quote?symbol=AAPL&token=$K"
curl -s "https://finnhub.io/api/v1/company-news?symbol=AAPL&from=2026-09-01&to=2026-09-08&token=$K" | head -c 800
curl -s "https://finnhub.io/api/v1/calendar/earnings?from=2026-09-08&to=2026-09-30&token=$K" | head -c 800
curl -s "https://finnhub.io/api/v1/stock/insider-transactions?symbol=AAPL&token=$K" | head -c 800
```

Paste each response into `tests/test_markets.py` as a module-level literal named `FH_QUOTE`,
`FH_NEWS`, `FH_EARN`, `FH_INSIDE`, each with a `# captured live <date> from <url>` comment — the
convention Tasks 1-4 established.

- [ ] **Step 2: Write the failing test**

One `class TheFinnhub(unittest.TestCase)` with one test per executor. Each mocks
`markets.requests.get` to return the captured literal, calls the executor with
`{'symbols': 'AAPL', 'api_key': 'k'}`, parses `body` line by line as JSON, and asserts the **row
contract above** — every key present, `change_pct` rounded to 2 places, `published` an ISO date
string. Add one test asserting the key rides as `params['token']` and never appears in the
headline or body, and one asserting `{'symbols': 'AAPL'}` with no key raises `MarketError` matching
`Finnhub` (already written in Task 1's `TheHelpers`; extend it if the message changes).

- [ ] **Step 3: Run to verify it fails** — `python -m pytest tests/test_markets.py::TheFinnhub -q -p no:cacheprovider`.

- [ ] **Step 4: Implement the four executors**

Each is the shape Task 1's helpers make available:

```python
# ---- finnhub: the widest single free key here - quotes, news, earnings, insiders ------------
FINNHUB = 'https://finnhub.io/api/v1'


def _finnhub(cfg, path, **params):
    return _get(f'{FINNHUB}{path}', {**params, 'token': _need(cfg, 'Finnhub', 'api_key', 'secret')})
```

Then one `run_finnhub_*` per row contract, each mapping the captured response's fields onto the
contract's keys and returning `_rows(cfg, rows, '<unit>')`. Use `_pct` for every percentage and
`_syms` for every symbol list. `finnhub_news` and `finnhub_earnings` default their window to the
last / next 7 days when `from`/`to` are absent.

- [ ] **Step 5: Run to verify it passes** — `python -m pytest tests/test_markets.py -q -p no:cacheprovider`.

- [ ] **Step 6: Commit** — off-index, message: `feat: Finnhub - quotes, company news, the earnings calendar and insider transactions on one key`

---

### Task 7: Alpha Vantage — quotes, technical indicators, news sentiment

**Interfaces:** Produces `run_av_quotes`, `run_av_indicator`, `run_av_news`. Base `https://www.alphavantage.co/query`, key as `apikey`.

**Why this card matters more than its rate limit suggests:** its indicator endpoints (`RSI`, `MACD`,
`SMA`, `EMA`, `BBANDS`) are computed server-side, which is what lets Task 12's screen match a
strategy without this codebase implementing indicator math.

**Row contracts:**
- `av_quotes` → `{symbol, price, change_pct, volume, previous_close, latest_day}` from `function=GLOBAL_QUOTE`
- `av_indicator` → `{symbol, indicator, date, value}` newest first, from `function=<RSI|MACD|SMA|EMA|BBANDS>&interval=&time_period=&series_type=`
- `av_news` → `{symbol, headline, source, url, published, sentiment, sentiment_label}` from `function=NEWS_SENTIMENT&tickers=`

**Two traps to handle explicitly, both of which return HTTP 200:**
- The free tier answers a rate-limited call with `{"Note": "..."}` or `{"Information": "..."}` and **no data**. `_get` already surfaces those keys in its error message, but a 200 does not reach that branch — so each executor must check for `Note` / `Information` in the parsed body and raise `MarketError` with that text. A report that silently returns zero rows on a rate limit is a report that lies.
- `GLOBAL_QUOTE` returns its fields under a `"Global Quote"` key with names like `"10. change percent"` and a value of `"-1.1800%"` — a string with a `%`. Strip it before `_pct`.

- [ ] **Step 1: Capture the real shapes**

```bash
K=<the owner's alphavantage key>
curl -s "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=AAPL&apikey=$K"
curl -s "https://www.alphavantage.co/query?function=RSI&symbol=AAPL&interval=daily&time_period=14&series_type=close&apikey=$K" | head -c 700
curl -s "https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers=AAPL&apikey=$K" | head -c 900
```

Paste as `AV_QUOTE`, `AV_RSI`, `AV_NEWS` with the captured-live comment.

- [ ] **Step 2: Write the failing test** — `class TheAlphaVantage`, one test per executor asserting the row contracts, plus:

```python
    def test_a_rate_limited_answer_raises_rather_than_reporting_no_rows(self):
        note = {'Note': 'Thank you for using Alpha Vantage! Our standard API rate limit is 25 requests per day'}
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, note)):
            with self.assertRaisesRegex(markets.MarketError, 'rate limit'):
                markets.run_av_quotes({'symbols': 'AAPL', 'api_key': 'k'})

    def test_the_percent_string_becomes_a_number(self):
        with mock.patch.object(markets.requests, 'get', return_value=_resp(200, AV_QUOTE)):
            _, body = markets.run_av_quotes({'symbols': 'AAPL', 'api_key': 'k'})
        self.assertIsInstance(json.loads(body.splitlines()[0])['change_pct'], float)
```

- [ ] **Step 3: Run to verify it fails.**
- [ ] **Step 4: Implement**, including a shared guard used by all three:

```python
def _av(cfg, **params):
    j = _get('https://www.alphavantage.co/query', {**params, 'apikey': _need(cfg, 'Alpha Vantage', 'api_key', 'secret')})
    # a 200 carrying Note/Information is a rate limit or a bad call with no data behind it, and a
    # report that turns that into "0 rows" is a report that lies about what it looked at
    for k in ('Note', 'Information', 'Error Message'):
        if j.get(k): raise MarketError(str(j[k])[:300])
    return j
```

- [ ] **Step 5: Run to verify it passes.**
- [ ] **Step 6: Commit** — message: `feat: Alpha Vantage - quotes, server-side indicators, news sentiment; a rate limit raises instead of reporting nothing`

---

### Task 8: Twelve Data — quotes and indicators

**Interfaces:** Produces `run_td_quotes`, `run_td_indicator`. Base `https://api.twelvedata.com`, key as `apikey`.

Here because Alpha Vantage's free tier is a daily cap and this one is per-minute — the same
indicators at a limit an intraday schedule can live with. Its error shape is
`{"code": 400, "message": "...", "status": "error"}` **at HTTP 200**, so it needs the same
lie-prevention guard as Task 7: check `status == 'error'` and raise with `message`.

**Row contracts:** `td_quotes` → `{symbol, price, change_pct, day_low, day_high, previous_close}` from `/quote?symbol=`. `td_indicator` → `{symbol, indicator, date, value}` newest first, from `/rsi|/macd|/sma|/ema|/bbands?symbol=&interval=`.

- [ ] **Step 1: Capture** — `curl -s "https://api.twelvedata.com/quote?symbol=AAPL&apikey=$K"` and `curl -s "https://api.twelvedata.com/rsi?symbol=AAPL&interval=1day&apikey=$K"`, pasted as `TD_QUOTE`, `TD_RSI`.
- [ ] **Step 2: Write the failing test** — `class TheTwelveData`, row contracts plus `test_a_status_error_at_200_raises`.
- [ ] **Step 3: Run to verify it fails.**
- [ ] **Step 4: Implement** with a `_td(cfg, path, **params)` helper carrying the guard.
- [ ] **Step 5: Run to verify it passes.**
- [ ] **Step 6: Commit** — `feat: Twelve Data - the same indicators at a per-minute limit`

---

### Task 9: Tiingo — end-of-day prices and news

**Interfaces:** Produces `run_tiingo_history`, `run_tiingo_news`. Base `https://api.tiingo.com`, key as `Authorization: Token <key>` (a **header**, unlike every other card in this phase — `_get` already accepts headers).

**Row contracts:** `tiingo_history` → `{symbol, date, close, adj_close, volume}` oldest first, from `/tiingo/daily/<sym>/prices?startDate=`. `tiingo_news` → `{symbol, headline, source, url, published}` from `/tiingo/news?tickers=`.

- [ ] **Step 1: Capture** — `curl -s -H "Authorization: Token $K" "https://api.tiingo.com/tiingo/daily/aapl/prices?startDate=2026-09-01"` and the news equivalent; paste as `TII_EOD`, `TII_NEWS`.
- [ ] **Step 2: Write the failing test** — `class TheTiingo`, row contracts plus one asserting the key rides in `headers['Authorization']` as `Token <key>` and never as a query parameter.
- [ ] **Step 3: Run to verify it fails.**
- [ ] **Step 4: Implement.**
- [ ] **Step 5: Run to verify it passes.**
- [ ] **Step 6: Commit** — `feat: Tiingo - end-of-day prices and news, keyed by header`

---

### Task 10: Financial Modeling Prep — fundamentals, ratios, screener

**Interfaces:** Produces `run_fmp_fundamentals`, `run_fmp_ratios`, `run_fmp_screener`. Key as `apikey`.

**Row contracts:** `fmp_fundamentals` → `{symbol, period, date, revenue, net_income, eps}`. `fmp_ratios` → `{symbol, period, pe, price_to_book, debt_to_equity, return_on_equity}`. `fmp_screener` → `{symbol, company, sector, market_cap, price}`.

**Before implementing:** FMP has moved endpoints between `/api/v3/` and a newer `/stable/` base. **Do not guess.** Capture from whichever base the owner's key answers on and pin the working base as a module constant with a comment naming the date it was verified.

- [ ] **Step 1: Capture** — try `curl -s "https://financialmodelingprep.com/api/v3/income-statement/AAPL?limit=2&apikey=$K"`; if it 403s or returns a "legacy endpoint" message, retry under `/stable/`. Record which worked. Paste as `FMP_INC`, `FMP_RATIO`, `FMP_SCREEN`.
- [ ] **Step 2: Write the failing test** — `class TheFmp`, row contracts, plus one asserting the pinned base constant is the one actually called.
- [ ] **Step 3: Run to verify it fails.**
- [ ] **Step 4: Implement.**
- [ ] **Step 5: Run to verify it passes.**
- [ ] **Step 6: Commit** — `feat: FMP fundamentals, ratios and screener, on the base its key actually answers`

---

### Task 11: Polygon snapshots and bars, FRED series, Alpaca quotes and bars

Three cards in one task because each is a single small executor pair and none of them shares a trap
with the others. Split it if any one turns out to need more than a screenful.

**Interfaces:**
- `run_polygon_snapshot` → `{symbol, price, change_pct, volume, updated}`; `run_polygon_bars` → `{symbol, date, open, high, low, close, volume}` oldest first. Key as `apiKey`. Free tier is end-of-day and heavily rate-limited — a `{"status": "ERROR"}` or `NOT_AUTHORIZED` body at 200 must raise, same discipline as Tasks 7 and 8.
- `run_fred_series` → `{series, date, value}` newest first, from `https://api.stlouisfed.org/fred/series/observations?series_id=&api_key=&file_type=json`. FRED writes a missing observation as the string `"."` — map it to `None` rather than letting it reach a chart as text.
- `run_alpaca_quotes` → `{symbol, price, bid, ask, updated}`; `run_alpaca_bars` → `{symbol, date, open, high, low, close, volume}`. Base `https://data.alpaca.markets/v2`. **Two credentials, not one** — headers `APCA-API-KEY-ID` and `APCA-API-SECRET-KEY`, so it uses `_need(cfg, 'Alpaca', 'key_id')` and `_need(cfg, 'Alpaca', 'secret_key', 'api_key')`, never `_apikey_card`'s single `api_key`. Its free feed is IEX; a SIP request without a subscription returns delayed data or an error, so the executor passes `feed=iex` unless the config names another.

- [ ] **Step 1: Capture all five shapes** with the owner's keys, pasted as `POLY_SNAP`, `POLY_BARS`, `FRED_OBS`, `ALP_QUOTE`, `ALP_BARS`.
- [ ] **Step 2: Write the failing tests** — `class ThePolygon`, `class TheFred`, `class TheAlpacaData`. Include `test_a_missing_observation_is_none_not_a_dot` for FRED and `test_both_credentials_ride_as_headers_and_neither_reaches_the_body` for Alpaca.
- [ ] **Step 3: Run to verify they fail.**
- [ ] **Step 4: Implement.**
- [ ] **Step 5: Run to verify they pass.**
- [ ] **Step 6: Commit** — `feat: Polygon, FRED and Alpaca market data - the paid road, the macro series, and the card that becomes the broker`

---

## Phase C — the screen, the cards, the docs

### Task 12: `markets_screen` — conditions in config, matches out

**Files:** Modify `taskuary/markets.py`, `taskuary/reports.py` (`REGISTRY`, `CARD_OF`, `CONNECTION_OF`), `taskuary/scopes.py`, `tests/test_markets.py`

**Interfaces:** Produces `markets.run_markets_screen(cfg)` and `markets.screen_connection(store, connector_id=None)`.

**Design, decided in the spec — implement it, do not redesign it:** the screen reads through whichever
provider supplies the data, and `CONNECTION_OF` is keyed by executor type, so it **borrows** the named
provider's card the way `azure_connection` borrows the Outlook app (`reports.py:706`). Config:

```json
{"provider": "yahoo_quotes", "connector_id": 7, "symbols": "AAPL,NVDA",
 "conditions": [["change_pct", "<=", -5], ["price", "<", 200]]}
```

It returns **only the rows where every condition holds**, which is what makes
`alert {"when": "something_came_back"}` the right rule and silence the normal outcome.

- [ ] **Step 1: Write the failing test**

```python
class TheScreen(unittest.TestCase):
    def test_only_the_rows_where_every_condition_holds_come_back(self):
        with mock.patch.object(markets, 'run_yahoo_quotes', return_value=('2 quotes', '\n'.join([
                json.dumps({'symbol': 'AAPL', 'price': 316.19, 'change_pct': -1.18}),
                json.dumps({'symbol': 'NVDA', 'price': 118.0, 'change_pct': -6.4})]))):
            head, body = markets.run_markets_screen({'provider': 'yahoo_quotes', 'symbols': 'AAPL,NVDA',
                                                     'conditions': [['change_pct', '<=', -5]]})
        rows = [json.loads(l) for l in body.splitlines() if l.strip()]
        self.assertEqual([r['symbol'] for r in rows], ['NVDA'])
        self.assertIn('1 match', head)

    def test_nothing_matching_is_quiet_and_an_alert_stays_silent(self):
        from taskuary.reports import alert_fires
        with mock.patch.object(markets, 'run_yahoo_quotes', return_value=('1 quotes', json.dumps({'symbol': 'AAPL', 'change_pct': -1.0}))):
            head, body = markets.run_markets_screen({'provider': 'yahoo_quotes', 'conditions': [['change_pct', '<=', -5]]})
        self.assertEqual(alert_fires({'alert': {'when': 'something_came_back', 'to': 'x'}}, head, body), '')

    def test_an_unknown_provider_or_operator_is_refused_before_any_call(self):
        with self.assertRaisesRegex(markets.MarketError, 'not a market source'):
            markets.run_markets_screen({'provider': 'sqlite', 'conditions': []})
        with self.assertRaisesRegex(markets.MarketError, 'operator'):
            markets.run_markets_screen({'provider': 'yahoo_quotes', 'conditions': [['price', 'DROP TABLE', 1]]})

    def test_a_condition_on_a_field_the_provider_does_not_return_says_so(self):
        with mock.patch.object(markets, 'run_yahoo_quotes', return_value=('1 quotes', json.dumps({'symbol': 'AAPL'}))):
            with self.assertRaisesRegex(markets.MarketError, 'rsi'):
                markets.run_markets_screen({'provider': 'yahoo_quotes', 'conditions': [['rsi', '<', 30]]})

    def test_the_screen_borrows_the_named_providers_card(self):
        from taskuary import reports
        self.assertIs(reports.CONNECTION_OF['markets_screen'], markets.screen_connection)
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement**

```python
# ---- the screen: conditions in CONFIG, matches out ------------------------------------------
# The threshold lives here and not in a playbook. A playbook is prose flattened onto a command
# line; a number living in prose is a number re-judged by a model every run, and it will drift.
OPS = {'<': lambda a, b: a < b, '<=': lambda a, b: a <= b, '>': lambda a, b: a > b,
       '>=': lambda a, b: a >= b, '==': lambda a, b: a == b, '!=': lambda a, b: a != b}
SCREENABLE = ('yahoo_quotes', 'finnhub_quotes', 'av_quotes', 'av_indicator', 'td_quotes',
              'td_indicator', 'alpaca_quotes', 'polygon_snapshot', 'coingecko_prices')


def screen_connection(store, connector_id=None) -> dict:
    """The screen has no credentials of its own: it BORROWS the card of the provider it names,
    the way azure_connection borrows the Outlook app. Without this the screen could only ever
    read the keyless providers."""
    from .reports import CONNECTION_OF
    c = store.get_connector(int(connector_id), with_secret=True) if connector_id else None
    if not c: return {}
    conn = CONNECTION_OF.get(f"{c.get('Type')}_") or None
    fn = next((f for t, f in CONNECTION_OF.items() if card_for(t) == c.get('Type') and f), None)
    return fn(store, c.get('ConnectorId')) if fn else {}


def card_for(t):
    from .reports import card_of
    return card_of(t)


def run_markets_screen(cfg):
    """{"provider": "yahoo_quotes", "symbols": "AAPL,NVDA", "conditions": [["change_pct", "<=", -5]]}
    - the provider's rows, filtered to the ones where EVERY condition holds, and nothing else.

    Silence is the normal outcome, which is what makes alert "something came back" the right rule:
    a report that files a row every run is a report that stops being read."""
    prov = str(cfg.get('provider') or '').strip()
    if prov not in SCREENABLE:
        raise MarketError(f'{prov!r} is not a market source a screen can read - one of: {", ".join(SCREENABLE)}')
    conds = [c for c in (cfg.get('conditions') or []) if isinstance(c, (list, tuple)) and len(c) == 3]
    for f, op, _ in conds:
        if op not in OPS: raise MarketError(f'{op!r} is not a comparison operator - one of: {", ".join(OPS)}')
    _, body = globals()[f'run_{prov}']({k: v for k, v in cfg.items() if k not in ('provider', 'conditions')})
    rows, out = [json.loads(l) for l in str(body or '').splitlines() if l.strip()], []
    for r in rows:
        for f, op, want in conds:
            if f not in r: raise MarketError(f'{prov} returns no field {f!r} to screen on - it has: {", ".join(sorted(r))}')
            v = r.get(f)
            if v is None or not OPS[op](v, want): break
        else: out.append(r)
    return _rows({**cfg, 'max_rows': cfg.get('max_rows')}, out, 'matches')
```

> Implementer note: `screen_connection` above is the one function in this plan written without a
> verified call path — `CONNECTION_OF` is a flat `type -> fn` map and the reverse lookup from a card
> type back to its connection function may be cleaner written as an explicit dict. Read
> `reports.CONNECTION_OF` and `reports.CARD_OF` before implementing, keep the borrow behaviour and
> the test above, and simplify the lookup if a direct mapping reads better. Do not change
> `reports.py`'s own structures to make it easier.

- [ ] **Step 4: Wire it** — `REGISTRY['markets_screen'] = _lazy('markets', 'run_markets_screen')`, `CARD_OF['markets_screen'] = 'screen'`, `CONNECTION_OF['markets_screen'] = markets.screen_connection` (imported the way `_teller_connection` is), `scopes.ACTIONS['markets_screen'] = 'read'`, `scopes.DEFAULT_SCOPE['screen'] = 'read'`, and a `('screen', 'Strategy screen')` catalog row.

- [ ] **Step 5: Run the tests** — `python -m pytest tests/test_markets.py -q -p no:cacheprovider`, expected PASS.

- [ ] **Step 6: Commit** — `feat: markets_screen - conditions in config, only the matches out, silence as the normal outcome`

---

### Task 13: The cards, the catalog group, the docs, the bundle

**Files:** Modify `website/src/ConnectorsView.jsx`, `website/src/logos.jsx`, `docs/integrations.md`; rebuild `taskuary/web/assets/`

- [ ] **Step 1: Add a card entry per provider**

Model each on the `teller` entry (`ConnectorsView.jsx:537`): `title`, `types`, `fields`,
`secretLabel`, `desc`, `howto`, `agent`. For the keyed cards the only field is the key, so
`secretLabel` carries it — except **Alpaca**, which needs `fields: [["key id", "key_id"], ["environment — paper or live", "env", "paper"]]` with the secret as the write-only half.

Three copy requirements, none of them decoration:
- **Yahoo's `desc` says it is best-effort**, in plain words: Yahoo retired its official API in 2017, this reads an undocumented endpoint, and it may break without notice. An owner choosing it should know.
- **Alpha Vantage's and Polygon's `howto`** state the free-tier limit as found today, next to the link where it is authoritative — the spec deliberately does not tabulate limits because they go stale.
- **Every numeric card's `howto`** repeats the threshold idiom: the headline leads with the number, so an alert of "more than 500" compares the measure and not the row count.

- [ ] **Step 2: Add a "Markets & finance" group**

In the `groups` array (`ConnectorsView.jsx:1035-1057`), after "Corporate systems":

```jsx
    { title: "Markets & finance", cards: [
      ...dataCards(["yahoo", "alpaca", "finnhub", "alphavantage", "twelvedata", "tiingo", "fmp",
                    "polygon", "fred", "sec_edgar", "coingecko", "frankfurter", "screen"]),
      ...plannedCards(["stooq", "plaid", "ibkr", "schwab", "tradier", "robinhood", "eodhd",
                       "marketstack", "intrinio", "benzinga"]),
      ...catalogCards("Markets & finance"),
    ]},
```

- [ ] **Step 3: Add a logo tile per card** in `logos.jsx`, following the `teller` line's `<T>` shape.

- [ ] **Step 4: Add the rows to `docs/integrations.md`**, one per card, in the format of the existing Teller and QuickBooks rows. `stooq` gets a **Planned** row naming its reason, so nobody implements it from the spec's out-of-date claim.

- [ ] **Step 5: Check the JSX and rebuild**

From `website/`: `npm run lint:undef` (expected: no errors), then `npm run build` (expected: a successful vite build writing into the committed `taskuary/web/assets/`). Use `npm exec` at Node 22 if the global Node is older.

- [ ] **Step 6: Commit source and bundle together** — off-index, listing the JSX, `logos.jsx`, `docs/integrations.md` and every file `git status --porcelain taskuary/web` reports. Message:

```
feat: a Markets & finance group, one card per provider, and Yahoo says what it is

The card copy carries three things the code cannot: that Yahoo reads an undocumented endpoint and
may break, what each free tier costs today next to the link that is authoritative, and why a
numeric headline starts with its number - an owner setting "more than 500" against a row count
would be setting the wrong threshold entirely.
```

---

### Task 14: Reconcile the spec, then stop

**Files:** Modify `docs/superpowers/specs/2026-09-08-finance-agent-design.md`

- [ ] **Step 1: Confirm the three corrections are still in place** — they were applied to the spec on 2026-09-08 before this plan was committed, so this is a check, not an edit: `stooq` in the planned list with its reason, `frankfurter` on `api.frankfurter.dev/v1/latest`, and Yahoo's entry recording that `v8/finance/chart` was verified keyless so the crumb handshake is not built. If any has been reverted, restore it.
- [ ] **Step 2: Mark Part 1 and Part 3 layer 1 built** — `— *built 2026-09-08*`. Add one line under Part 1 naming which providers actually landed, since Phase B tasks stop rather than guess when a key is unavailable, and "built" must not overstate what exists.
- [ ] **Step 3: Commit** — `docs: the market cards are built, and the spec's free-no-key tier corrected against what the endpoints actually serve`
- [ ] **Step 4: Run the whole suite from the repo root**

Run: `python -m pytest -q -p no:cacheprovider`
Expected: PASS with a non-zero collection count.

Then **stop and report**. Nothing is pushed by this plan.

---

## What follows this plan

- **Plan 3 — the Alpaca broker card:** `alpaca_positions` / `alpaca_orders` at `read`, then `alpaca_order` / `alpaca_cancel` at `write` with the card shipping at `read`, plus the hand-written `propose-a-trade.md`. Depends on Task 11 landing the `alpaca` card's two-credential connection.
- **Not in any plan, by the owner's constraint:** numeric alert conditions in `alert_fires`, re-quote-at-approval in `proposals.execute`, `playbooks.draft` declining broker playbooks, and `if rules and repo_tag(t) != NO_REPO` in the seed. **Do not raise the Alpaca card to `write` scope while the re-quote hole is open.**
- **`docs/agent-profiles.md`** — the profile/playbook redesign, deliberately deferred until these cards give it real profiles to design against.
