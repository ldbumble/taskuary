"""Amazon Selling Partner API (SP-API): a seller's own reports as rows - for Reports, Dashboards and agents.

A DATA card, not a channel: nothing here polls for work or lands on the rail. It READS, and only reads:

  amazon_report         {"report_type": "GET_...", "days": 30, "options": {...}}   - any report type Amazon has
  amazon_sales_traffic  {"days": 30, "granularity": "DAY", "by": "date"}          - the Business Report
  amazon_orders         {"days": 7}                                                - every order, by order date
  amazon_inventory      {}                                                         - FBA inventory, now
  amazon_settlement     {"days": 60, "count": 1}                                   - the newest settlement report(s)
  amazon_marketplaces   {}                                                         - where this account sells

A report is not a GET: Amazon makes you ASK for it (createReport), wait while it is built (getReport until
DONE), then fetch a short-lived link to the file (getReportDocument), which is usually gzipped TSV or JSON.
So the one POST this card makes besides the token exchange is createReport - asking Amazon to prepare
something to read. Nothing it can call changes a listing, a price, an order or a shipment: WRITES is the
whole list, and _call refuses anything else before it leaves the machine.

AUTH is Login with Amazon (LWA): the owner's self-authorized app gives a client id + secret, and pressing
Authorize on it in Seller Central gives a refresh token that does not rotate. That token buys an access
token for an hour (x-amz-access-token on every call). SigV4 signing is not needed - Amazon's connecting guide
sends requests "with a URI and headers but no signing information" - so there is no AWS key on this card.

THROTTLING: the documented usage plans are tiny (createReport 1 a minute), so a 429 is waited out against
the operation's own restore rate rather than a guess, and a finished document is kept for a few minutes so
a dashboard and a report reading the same window ask Amazon once.
"""
import csv, gzip, hashlib, io, json, re, time
from datetime import datetime, timedelta, timezone

import requests
from loguru import logger

TOKEN_URL = 'https://api.amazon.com/auth/o2/token'
HOSTS = {'na': 'https://sellingpartnerapi-na.amazon.com', 'eu': 'https://sellingpartnerapi-eu.amazon.com',
         'fe': 'https://sellingpartnerapi-fe.amazon.com'}
REGION_WORDS = {'north america': 'na', 'america': 'na', 'us': 'na', 'europe': 'eu', 'eu': 'eu', 'far east': 'fe', 'asia': 'fe'}
# docs/marketplace-ids: id -> (country, region). Which endpoint serves a marketplace is fixed by Amazon.
MARKETPLACES = {'ATVPDKIKX0DER': ('US', 'na'), 'A2EUQ1WTGCTBG2': ('CA', 'na'), 'A1AM78C64UM0Y8': ('MX', 'na'), 'A2Q3Y263D00KWC': ('BR', 'na'),
                'A1F83G8C2ARO7P': ('UK', 'eu'), 'A1PA6795UKMFR9': ('DE', 'eu'), 'A13V1IB3VIYZZH': ('FR', 'eu'), 'APJ6JRA9NG5V4': ('IT', 'eu'),
                'A1RKKUPIHCS9HS': ('ES', 'eu'), 'A1805IZSGTT6HS': ('NL', 'eu'), 'A2NODRKZP88ZB9': ('SE', 'eu'), 'A1C3SOZRARQ6R3': ('PL', 'eu'),
                'A33AVAJ2PDY3EV': ('TR', 'eu'), 'A2VIGQ35RCS4UG': ('AE', 'eu'), 'A17E79C6D8DWNP': ('SA', 'eu'), 'ARBP9OOSHTCHU': ('EG', 'eu'),
                'A1VC38T7YXB528': ('JP', 'fe'), 'A39IBJ37TRP1C6': ('AU', 'fe'), 'A19VAU5U5O7RUS': ('SG', 'fe')}
REPORTS = '/reports/2021-06-30'
PARTICIPATIONS = '/sellers/v1/marketplaceParticipations'
# The documented usage plans, requests per second. A token returns to the bucket every 1/rate seconds, so that
# is how long a 429 is waited out - a fixed timer is what the docs say not to do.
RATE = {'createReport': 0.0167, 'getReport': 2.0, 'getReports': 0.0222, 'getReportDocument': 0.0167,
        'getMarketplaceParticipations': 0.016}
# Every call this card makes that is not a GET. createReport asks Amazon to BUILD a report to read; it moves nothing.
WRITES = frozenset({('POST', f'{REPORTS}/reports')})
# Amazon builds these on its own schedule and refuses a createReport for them: they are found with getReports instead.
LISTED_ONLY = re.compile(r'^GET_V2_SETTLEMENT_REPORT_DATA')
NAMED = {'sales_traffic': 'GET_SALES_AND_TRAFFIC_REPORT', 'orders': 'GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL',
         'inventory': 'GET_FBA_MYI_UNSUPPRESSED_INVENTORY_DATA', 'settlement': 'GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE_V2'}
TIMEOUT, TRIES, MAX_BACKOFF, DOC_TTL = 30, 4, 120, 900
_TOK = {}        # hash of (client id, refresh token) -> (access token, expiry)
_DOCS = {}       # (report type, window, marketplaces, options) -> (fetched at, rows)
_sleep = time.sleep


class AmazonError(RuntimeError): pass


# ── the card ─────────────────────────────────────────────────────────────────────────────
def connection(store, connector_id=None) -> dict:
    """The card's config with the refresh token (its write-only Secret) as `refresh_token`. The client secret
    is in the config too, write-only (guard.WRITE_ONLY_CONFIG)."""
    from .reports import _card
    return _card(store, 'amazon_sp', 'refresh_token', connector_id)


def region(cfg) -> str:
    r = str(cfg.get('region') or '').strip().lower()
    if r in HOSTS: return r
    if r in REGION_WORDS: return REGION_WORDS[r]
    if r: raise AmazonError(f'region {r!r} is not one of na (North America), eu (Europe) or fe (Far East)')
    ids = ids_of(cfg.get('marketplace_ids'))
    return MARKETPLACES.get(ids[0], ('', 'na'))[1] if ids else 'na'


def ids_of(v) -> list:
    if isinstance(v, (list, tuple)): v = ','.join(map(str, v))
    return [s for s in re.split(r'[\s,;]+', str(v or '').strip()) if s]


def _key(cfg) -> str: return hashlib.sha256(f"{cfg.get('client_id')}\0{cfg.get('refresh_token')}".encode()).hexdigest()[:24]


def token(cfg) -> str:
    """An LWA access token, cached for its hour less a minute. The refresh token does not rotate, so nothing is saved back."""
    if not (cfg.get('client_id') and cfg.get('client_secret')):
        raise AmazonError("the Amazon card needs the app's LWA client id and client secret (Seller Central → Apps and Services → Develop Apps → View)")
    if not cfg.get('refresh_token'):
        raise AmazonError('no refresh token on the Amazon card yet - press Authorize on the app in Develop Apps and paste the token it shows')
    k = _key(cfg)
    hit = _TOK.get(k)
    if hit and hit[1] > time.time() + 60: return hit[0]
    r = requests.post(TOKEN_URL, timeout=TIMEOUT, headers={'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'},
                      data={'grant_type': 'refresh_token', 'refresh_token': cfg['refresh_token'],
                            'client_id': cfg['client_id'], 'client_secret': cfg['client_secret']})
    if r.status_code != 200:
        try: why = r.json(); why = f"{why.get('error')}: {why.get('error_description')}"
        except Exception: why = r.text[:200]
        raise AmazonError(f'Login with Amazon refused the credentials ({r.status_code}) - {why}. Check the client id/secret, '
                          'or authorize the app again for a fresh refresh token')
    j = r.json()
    _TOK[k] = (j['access_token'], time.time() + int(j.get('expires_in') or 3600))
    return j['access_token']


def _ua() -> str:
    from . import __version__
    return f'Taskuary/{__version__} (Language=Python)'


def _wait(op, r, n) -> float:
    ra = (getattr(r, 'headers', None) or {}).get('Retry-After')
    try: base = float(ra)
    except (TypeError, ValueError): base = 1 / RATE.get(op, 1.0)
    return min(MAX_BACKOFF, base * 1.5 ** n)


def _why(r) -> str:
    try: return '; '.join(f"{e.get('code')}: {e.get('message')}" for e in r.json().get('errors') or []) or r.text[:300]
    except Exception: return r.text[:300]


def _call(cfg, op, method, path, **kw) -> dict:
    """One SP-API call, read-only by construction: any verb but GET that is not in WRITES never leaves here."""
    if method != 'GET' and (method, path) not in WRITES: raise AmazonError(f'{method} {path} is not a call this card makes - it is read-only')
    url, renewed = HOSTS[region(cfg)] + path, False
    for n in range(TRIES):
        r = requests.request(method, url, timeout=TIMEOUT, headers={'x-amz-access-token': token(cfg), 'user-agent': _ua(),
                                                                    'accept': 'application/json', 'content-type': 'application/json'}, **kw)
        if r.status_code == 429 and n < TRIES - 1:
            w = _wait(op, r, n); logger.info(f'amazon_sp: {op} throttled - waiting {w:.0f}s'); _sleep(w); continue
        # an access token Amazon has stopped honouring before its hour is up: drop it and buy one more, once
        if r.status_code in (401, 403) and not renewed and 'expired' in r.text.lower(): _TOK.pop(_key(cfg), None); renewed = True; continue
        break
    if r.status_code == 429: raise AmazonError(f'Amazon is still throttling {op} after {TRIES} tries - its quota is small; run it again in a few minutes')
    if r.status_code == 403:
        raise AmazonError(f'Amazon refused {op} (403): {_why(r)} - the app may lack the role this report needs '
                          '(Develop Apps → Edit App → roles), or the marketplace is not this account\'s')
    if r.status_code >= 300: raise AmazonError(f'Amazon {op} {r.status_code}: {_why(r)}')
    return r.json() if r.text else {}


# ── reads ────────────────────────────────────────────────────────────────────────────────
def participations(cfg) -> list:
    """Where this account sells: one row per marketplace, the ones it actively participates in first."""
    out = [{'id': (p.get('marketplace') or {}).get('id'), 'name': (p.get('marketplace') or {}).get('name'),
            'country': (p.get('marketplace') or {}).get('countryCode'), 'currency': (p.get('marketplace') or {}).get('defaultCurrencyCode'),
            'store': p.get('storeName'), 'participating': bool((p.get('participation') or {}).get('isParticipating')),
            'suspended_listings': bool((p.get('participation') or {}).get('hasSuspendedListings'))}
           for p in _call(cfg, 'getMarketplaceParticipations', 'GET', PARTICIPATIONS).get('payload') or []]
    return sorted(out, key=lambda m: not m['participating'])


def marketplaces(cfg) -> list:
    """The report's marketplace ids, else the card's, else every marketplace this account participates in."""
    ids = ids_of(cfg.get('marketplace_ids'))
    return ids or [m['id'] for m in participations(cfg) if m['participating'] and m['id']]


def _iso(d) -> str: return d.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def window(cfg, default_days=30):
    """(start, end) as SP-API wants them: `start`/`end` dates if given, else the last `days` days up to now."""
    def day(s):
        try: d = datetime.fromisoformat(str(s).strip().replace('Z', '+00:00'))
        except ValueError: raise AmazonError(f'{s!r} is not a date - write it as 2026-10-01')
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    end = day(cfg['end']) if cfg.get('end') else datetime.now(timezone.utc)
    if cfg.get('start'): return _iso(day(cfg['start'])), _iso(end)
    try: n = max(1, int(cfg.get('days') or default_days))
    except (TypeError, ValueError): n = default_days
    return _iso((end - timedelta(days=n)).replace(hour=0, minute=0, second=0, microsecond=0)), _iso(end)


def flatten(d, prefix='') -> dict:
    out = {}
    for k, v in (d or {}).items():
        if isinstance(v, dict): out.update(flatten(v, f'{prefix}{k}.'))
        elif isinstance(v, list): out[f'{prefix}{k}'] = json.dumps(v)[:400]
        else: out[f'{prefix}{k}'] = v
    return out


def json_rows(j, by='') -> list:
    """Rows out of a JSON report. Sales & traffic carries two tables - by date and by ASIN - and `by` picks one;
    anything else gives its first list of records."""
    if isinstance(j, list): return [flatten(x) if isinstance(x, dict) else {'value': x} for x in j]
    if not isinstance(j, dict): return [{'value': j}]
    want = {'asin': 'salesAndTrafficByAsin', 'date': 'salesAndTrafficByDate'}.get(str(by or 'date').lower())
    if want and isinstance(j.get(want), list): return json_rows(j[want])
    lst = next((v for v in j.values() if isinstance(v, list) and v and isinstance(v[0], dict)), None)
    return json_rows(lst) if lst is not None else [flatten(j)]


def _text(raw: bytes, fallback='cp1252') -> str:
    # flat files are UTF-8 in most marketplaces, Windows-1252 in some European ones and Shift-JIS in Japan - a report never fails on decoding
    for enc in ('utf-8-sig', fallback):
        try: return raw.decode(enc)
        except UnicodeDecodeError: pass
    return raw.decode('utf-8', 'replace')


def parse(raw: bytes, gzipped=False, by='', fallback='cp1252') -> list:
    """A downloaded report document -> rows: gzip off, then JSON, tab-separated or comma-separated, whichever it is."""
    if gzipped or raw[:2] == b'\x1f\x8b': raw = gzip.decompress(raw)
    s = _text(raw, fallback).strip()
    if not s: return []
    if s[0] in '{[': return json_rows(json.loads(s), by)
    delim = '\t' if '\t' in s.split('\n', 1)[0] else ','
    return [{k.strip(): v for k, v in r.items() if k is not None} for r in csv.DictReader(io.StringIO(s), delimiter=delim)]


def document(cfg, doc_id, by='') -> list:
    """getReportDocument, then the file itself - a presigned link good for five minutes, fetched WITHOUT the access token."""
    d = _call(cfg, 'getReportDocument', 'GET', f'{REPORTS}/documents/{doc_id}')
    r = requests.get(d['url'], timeout=120)
    if r.status_code != 200: raise AmazonError(f'the report file would not download ({r.status_code}) - run it again; the link lives five minutes')
    return parse(r.content, str(d.get('compressionAlgorithm') or '').upper() == 'GZIP', by, 'cp932' if region(cfg) == 'fe' else 'cp1252')


def request_report(cfg, report_type, start=None, end=None, options=None, wait_minutes=None) -> dict:
    """createReport, then getReport until Amazon says DONE. Returns the finished report record."""
    body = {'reportType': report_type, 'marketplaceIds': marketplaces(cfg)[:25]}
    if not body['marketplaceIds']: raise AmazonError('no marketplace to report on - put a marketplace id on the card (ATVPDKIKX0DER is amazon.com)')
    if start: body['dataStartTime'] = start
    if end: body['dataEndTime'] = end
    if options: body['reportOptions'] = {k: str(v) for k, v in options.items()}
    rid = _call(cfg, 'createReport', 'POST', f'{REPORTS}/reports', data=json.dumps(body))['reportId']
    deadline, pause = time.time() + 60 * float(wait_minutes or cfg.get('wait_minutes') or 10), 5.0
    while True:
        rep = _call(cfg, 'getReport', 'GET', f'{REPORTS}/reports/{rid}')
        st = rep.get('processingStatus')
        if st == 'DONE': return rep
        if st == 'CANCELLED': return {**rep, 'reportDocumentId': None}      # Amazon cancels a report that has no data to return
        if st == 'FATAL':
            why = ''
            if rep.get('reportDocumentId'):
                try: why = ' - ' + json.dumps(document(cfg, rep['reportDocumentId']))[:300]
                except Exception: pass
            raise AmazonError(f'Amazon could not build {report_type} (FATAL){why}')
        if time.time() > deadline:
            raise AmazonError(f'{report_type} was still {st} after {wait_minutes or cfg.get("wait_minutes") or 10} minutes - '
                              f'report {rid} keeps building at Amazon; run this again later')
        _sleep(pause); pause = min(30.0, pause * 1.5)


def listed(cfg, report_type, days=90, count=1) -> list:
    """The newest finished reports of a type Amazon schedules itself (settlements), newest first."""
    since = _iso(datetime.now(timezone.utc) - timedelta(days=max(1, min(int(days or 90), 90))))
    reps = _call(cfg, 'getReports', 'GET', f'{REPORTS}/reports', params={'reportTypes': report_type, 'processingStatuses': 'DONE',
                                                                         'createdSince': since, 'pageSize': 100}).get('reports') or []
    return sorted(reps, key=lambda r: r.get('createdTime') or '', reverse=True)[:max(1, int(count or 1))]


def report(cfg, report_type, start=None, end=None, options=None, by='') -> tuple:
    """(rows, note) for one report type - requested and waited for, or for a listed-only type its newest copies."""
    if not report_type: raise AmazonError('no report type - e.g. GET_SALES_AND_TRAFFIC_REPORT, or use one of the named Amazon reports')
    mk = tuple(marketplaces(cfg)) if not LISTED_ONLY.match(report_type) else ()
    key = (report_type, start, end, mk, json.dumps(options or {}, sort_keys=True), by, cfg.get('days'), cfg.get('count'), _key(cfg))
    hit = _DOCS.get(key)
    if hit and hit[0] > time.time() - DOC_TTL: return hit[1], hit[2]
    if LISTED_ONLY.match(report_type):
        reps = listed(cfg, report_type, cfg.get('days') or 90, cfg.get('count') or 1)
        rows = [r for rep in reps for r in document(cfg, rep['reportDocumentId'], by)]
        note = f"{len(reps)} settlement report(s), newest {(reps[0].get('createdTime') or '')[:10]}" if reps else 'no settlement report in that window'
    else:
        rep = request_report(cfg, report_type, start, end, options)
        rows = document(cfg, rep['reportDocumentId'], by) if rep.get('reportDocumentId') else []
        note = '' if rep.get('reportDocumentId') else 'Amazon had no data for that window (report cancelled)'
    _DOCS[key] = (time.time(), rows, note)
    return rows, note


# ── the card's test, and the report/tool surface (reports.REGISTRY) ─────────────────────
def probe(cfg) -> str:
    ms = participations(cfg)
    mine = [m for m in ms if m['participating']]
    if not mine: return f"connected ({region(cfg).upper()}) - but this account participates in no marketplace in that region"
    want, have = ids_of(cfg.get('marketplace_ids')), {m['id'] for m in ms}
    store = next((m['store'] for m in mine if m.get('store')), '')
    out = (f"connected{' as ' + store if store else ''} ({region(cfg).upper()}) - selling in "
           + ', '.join(f"{m['name']} ({m['id']})" for m in mine))
    if miss := [w for w in want if w not in have]: out += f" · not this account's in this region: {', '.join(miss)}"
    if not want: out += ' · no marketplace ids on the card, so reports cover all of these'
    return out


def _out(cfg, rows, note, label, span=''):
    from .reports import rows_out, row_limit
    lim, mine = row_limit(cfg)
    head, body = rows_out(rows, lim, mine=mine)
    return ' · '.join(x for x in (head, label, span, note) if x), body


def _span(start, end): return f'{start[:10]} → {end[:10]}' if start else ''


def run_amazon_report(cfg):
    """{"report_type": "GET_MERCHANT_LISTINGS_ALL_DATA", "days": 30 (or "start"/"end" dates), "options": {"k": "v"},
    "marketplace_ids": "ATVPDKIKX0DER"} - ANY SP-API report type: requested, waited for, downloaded and parsed to rows.
    Settlement types are found among the reports Amazon already built. Read-only."""
    t = str(cfg.get('report_type') or '').strip().upper()
    opts = cfg.get('options')
    if isinstance(opts, str):
        try: opts = json.loads(opts) if opts.strip() else None
        except ValueError: raise AmazonError(f'report options {opts!r} are not JSON - e.g. {{"reportPeriod": "WEEK"}}')
    start, end = window(cfg) if (cfg.get('days') or cfg.get('start')) and not LISTED_ONLY.match(t) else (None, None)
    rows, note = report(cfg, t, start, end, opts, cfg.get('by'))
    return _out(cfg, rows, note, t, _span(start, end) if start else '')


def run_amazon_sales_traffic(cfg):
    """{"days": 30, "granularity": "DAY|WEEK|MONTH", "by": "date|asin", "asin_granularity": "PARENT|CHILD|SKU"} -
    the Business Report: ordered sales, units, sessions and page views, per day (or per ASIN)."""
    start, end = window(cfg)
    opts = {'dateGranularity': str(cfg.get('granularity') or 'DAY').upper(), 'asinGranularity': str(cfg.get('asin_granularity') or 'PARENT').upper()}
    rows, note = report(cfg, NAMED['sales_traffic'], start, end, opts, cfg.get('by') or 'date')
    return _out(cfg, rows, note, 'sales & traffic', _span(start, end))


def run_amazon_orders(cfg):
    """{"days": 7} - every order placed in the window (all statuses, all channels), one row per item."""
    start, end = window(cfg, 7)
    rows, note = report(cfg, NAMED['orders'], start, end)
    return _out(cfg, rows, note, 'orders by order date', _span(start, end))


def run_amazon_inventory(cfg):
    """{} - FBA inventory as it stands: every SKU in Amazon's warehouses, fulfillable, inbound, reserved."""
    rows, note = report(cfg, NAMED['inventory'])
    return _out(cfg, rows, note, 'FBA inventory')


def run_amazon_settlement(cfg):
    """{"days": 60, "count": 1} - the newest settlement report(s) Amazon published in the last `days` (90 at most):
    every fee, charge and payout line. Amazon schedules these itself; they cannot be requested."""
    rows, note = report(cfg, NAMED['settlement'])
    return _out(cfg, rows, note, 'settlement')


def run_amazon_marketplaces(cfg):
    """{} - the marketplaces this seller account is registered in, with currency and store name."""
    ms = participations(cfg)
    return _out(cfg, ms, '', f"{sum(m['participating'] for m in ms)} participating")
