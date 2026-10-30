"""Amazon Selling Partner API (SP-API) and the Amazon Business reconciliation API: a seller's own reports, and a
business buyer's purchases, as rows - for Reports, Dashboards and agents.

A DATA card, not a channel: nothing here polls for work or lands on the rail. It READS, and only reads:

  amazon_report         {"report_type": "GET_...", "days": 30, "options": {...}}   - any report type Amazon has
  amazon_sales_traffic  {"days": 30, "granularity": "DAY", "by": "date"}          - the Business Report
  amazon_orders         {"days": 7}                                                - every order, by order date
  amazon_inventory      {}                                                         - FBA inventory, now
  amazon_settlement     {"days": 60, "count": 1}                                   - the newest settlement report(s)
  amazon_marketplaces   {}                                                         - where this account sells
  amazon_business_transactions {"days": 7, "invoices": true, "pdfs": false}       - Amazon Business purchases, with invoice numbers
  amazon_invoice_pdf    {"invoice": "1111-2222-3333", "credit": false}             - one Amazon Business invoice (or credit memo) as a PDF

ONE LOGIN, SEVERAL APIS. The same Login-with-Amazon app can hold Selling Partner roles, Amazon Business roles or
both, and an app with only one of them gets a 403 from the other. So the card carries `apis` - which of APIS the
credentials reach - and Test fills it by probing each with one cheap read: a 403 from one is not a failed Test
while another answered (the owner, 2026-10-30: "maybe make little fillable dots which api you have access to").

A seller report is not a GET: Amazon makes you ASK for it (createReport), wait while it is built (getReport until
DONE), then fetch a short-lived link to the file (getReportDocument), which is usually gzipped TSV or JSON.
So the POSTs this card makes besides the token exchange are createReport - asking Amazon to prepare
something to read, a seller report or an Amazon Business invoice PDF - and Amazon Business's invoice lookup, a read that takes its order lines as a body. Nothing it can call changes a listing, a price, an order or a shipment: WRITES is the
whole list, and _call refuses anything else before it leaves the machine.

AUTH is Login with Amazon (LWA): the owner's self-authorized app gives a client id + secret, and pressing
Authorize on it in Seller Central gives a refresh token that does not rotate. That token buys an access
token for an hour (x-amz-access-token on every call). SigV4 signing is not needed - Amazon's connecting guide
sends requests "with a URI and headers but no signing information" - so there is no AWS key on this card.

THROTTLING: the documented usage plans are tiny (createReport 1 a minute), so a 429 is waited out against
the operation's own restore rate rather than a guess, and a finished document is kept for a few minutes so
a dashboard and a report reading the same window ask Amazon once.
"""
import csv, gzip, hashlib, io, json, re, time, zipfile
from datetime import datetime, timedelta, timezone

import requests
from loguru import logger

TOKEN_URL = 'https://api.amazon.com/auth/o2/token'
HOSTS = {'na': 'https://sellingpartnerapi-na.amazon.com', 'eu': 'https://sellingpartnerapi-eu.amazon.com',
         'fe': 'https://sellingpartnerapi-fe.amazon.com'}
# Amazon Business has its own hosts (docs: "Amazon Business API endpoints") for the same three regions; the Far East one is
# jp. and serves Japan and Australia
BUSINESS = {'na': 'https://na.business-api.amazon.com', 'eu': 'https://eu.business-api.amazon.com', 'fe': 'https://jp.business-api.amazon.com'}
# the APIs one set of LWA credentials may reach - the card's dots, in the order they are shown and probed
APIS = {'sp': 'Seller reports (SP-API)', 'business': 'Amazon Business reconciliation'}
REGION_WORDS = {'north america': 'na', 'america': 'na', 'us': 'na', 'europe': 'eu', 'eu': 'eu', 'far east': 'fe', 'asia': 'fe'}
# docs/marketplace-ids: id -> (country, region). Which endpoint serves a marketplace is fixed by Amazon.
MARKETPLACES = {'ATVPDKIKX0DER': ('US', 'na'), 'A2EUQ1WTGCTBG2': ('CA', 'na'), 'A1AM78C64UM0Y8': ('MX', 'na'), 'A2Q3Y263D00KWC': ('BR', 'na'),
                'A1F83G8C2ARO7P': ('UK', 'eu'), 'A1PA6795UKMFR9': ('DE', 'eu'), 'A13V1IB3VIYZZH': ('FR', 'eu'), 'APJ6JRA9NG5V4': ('IT', 'eu'),
                'A1RKKUPIHCS9HS': ('ES', 'eu'), 'A1805IZSGTT6HS': ('NL', 'eu'), 'A2NODRKZP88ZB9': ('SE', 'eu'), 'A1C3SOZRARQ6R3': ('PL', 'eu'),
                'A33AVAJ2PDY3EV': ('TR', 'eu'), 'A2VIGQ35RCS4UG': ('AE', 'eu'), 'A17E79C6D8DWNP': ('SA', 'eu'), 'ARBP9OOSHTCHU': ('EG', 'eu'),
                'A1VC38T7YXB528': ('JP', 'fe'), 'A39IBJ37TRP1C6': ('AU', 'fe'), 'A19VAU5U5O7RUS': ('SG', 'fe')}
REPORTS = '/reports/2021-06-30'
PARTICIPATIONS = '/sellers/v1/marketplaceParticipations'
RECON = '/reconciliation/2021-01-08'
BREPORTS = '/reports/2021-09-30'        # Amazon Business's own reports API (the invoice PDF) - a later version than SP-API's
# The documented usage plans, requests per second. A token returns to the bucket every 1/rate seconds, so that
# is how long a 429 is waited out - a fixed timer is what the docs say not to do.
RATE = {'createReport': 0.0167, 'getReport': 2.0, 'getReports': 0.0222, 'getReportDocument': 0.0167,
        'getMarketplaceParticipations': 0.016, 'getTransactions': 2.0, 'getInvoiceDetailsByOrderLineItems': 2.0}
# Every call this card makes that is not a GET. createReport asks Amazon to BUILD a report to read; the invoice lookup is a read
# that takes its order lines as a body. Neither moves anything.
WRITES = frozenset({('POST', f'{REPORTS}/reports'), ('POST', f'{RECON}/invoices'), ('POST', f'{BREPORTS}/reports')})
# Amazon builds these on its own schedule and refuses a createReport for them: they are found with getReports instead.
LISTED_ONLY = re.compile(r'^GET_V2_SETTLEMENT_REPORT_DATA')
NAMED = {'sales_traffic': 'GET_SALES_AND_TRAFFIC_REPORT', 'orders': 'GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL',
         'inventory': 'GET_FBA_MYI_UNSUPPRESSED_INVENTORY_DATA', 'settlement': 'GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE_V2'}
TIMEOUT, TRIES, MAX_BACKOFF, DOC_TTL = 30, 4, 120, 900
INVOICE_BATCH, MAX_PAGES = 25, 1000        # getInvoiceDetailsByOrderLineItems takes 25 order lines at most
# a 403 means a missing role, and the role has a different name in each API's console
ROLE_HINT = {'sp': "the app may lack the role this report needs (Develop Apps → Edit App → roles), or the marketplace is not this account's",
             'business': 'the app may lack the Business Purchase Reconciliation role, or these credentials are not an Amazon Business account'}
_TOK = {}        # hash of (client id, refresh token) -> (access token, expiry)
_DOCS = {}       # (report type, window, marketplaces, options) -> (fetched at, rows)
_sleep, _clock = time.sleep, time.monotonic


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


def _call(cfg, op, method, path, api='sp', **kw) -> dict:
    """One SP-API call (or Amazon Business, api='business'), read-only by construction: any verb but GET that is not in
    WRITES never leaves here."""
    if method != 'GET' and (method, path) not in WRITES: raise AmazonError(f'{method} {path} is not a call this card makes - it is read-only')
    url, renewed = (BUSINESS if api == 'business' else HOSTS)[region(cfg)] + path, False
    for n in range(TRIES):
        r = requests.request(method, url, timeout=TIMEOUT, headers={'x-amz-access-token': token(cfg), 'user-agent': _ua(),
                                                                    'accept': 'application/json', 'content-type': 'application/json'}, **kw)
        if r.status_code == 429 and n < TRIES - 1:
            w = _wait(op, r, n); logger.info(f'amazon_sp: {op} throttled - waiting {w:.0f}s'); _sleep(w); continue
        # an access token Amazon has stopped honouring before its hour is up: drop it and buy one more, once
        if r.status_code in (401, 403) and not renewed and 'expired' in r.text.lower(): _TOK.pop(_key(cfg), None); renewed = True; continue
        break
    if r.status_code == 429: raise AmazonError(f'Amazon is still throttling {op} after {TRIES} tries - its quota is small; run it again in a few minutes')
    if r.status_code == 403: raise AmazonError(f'Amazon refused {op} (403): {_why(r)} - {ROLE_HINT[api]}')
    if r.status_code >= 300: raise AmazonError(f'Amazon {op} {r.status_code}: {_why(r)}')
    j = r.json() if r.text else {}
    # Amazon Business can answer 200 and still carry an errors list: a refusal is not an empty page of rows
    if api == 'business' and isinstance(j, dict) and j.get('errors'): raise AmazonError(f'Amazon {op}: {_why(r)}')
    return j


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
def _probe_sp(cfg) -> str:
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


def _probe_business(cfg) -> str:
    start, end = feed_window({'days': 1})
    _call(cfg, 'getTransactions', 'GET', f'{RECON}/transactions', api='business', params={'feedStartDate': start, 'feedEndDate': end, 'pageSize': 1})
    return f'reconciliation answered ({region(cfg).upper()})'


PROBES = {'sp': _probe_sp, 'business': _probe_business}


def probe_apis(cfg) -> tuple:
    """(detail, apis): one cheap read against each of APIS, and the keys of the ones that answered - what the card's dots show.
    The Test passes while ANY answered; only when none did is it a failure, and then it says why for each."""
    token(cfg)          # refused credentials are the same answer from every API - said once, not once per API
    ok, no = {}, {}
    for k, f in PROBES.items():
        try: ok[k] = f(cfg)
        except (AmazonError, requests.RequestException) as e: no[k] = str(e)
    if not ok: raise AmazonError(' · '.join(f'{APIS[k]}: {v}' for k, v in no.items()))
    return ' · '.join([f'{APIS[k]} ✓ {v}' for k, v in ok.items()] + [f'{APIS[k]} ✗ {v[:200]}' for k, v in no.items()]), list(ok)


def probe(cfg) -> str: return probe_apis(cfg)[0]


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


# ── Amazon Business: purchases as reconciliation sees them ───────────────────────────────
def feed_window(cfg, default_days=7, now=None) -> tuple:
    """(feedStartDate, feedEndDate) for getTransactions: `start`/`end` dates, else the last `days` days. A missing side is 7 days
    from the other, a start is that day's midnight, and an end of today is now less two minutes - any other end is that day's
    last second. Those are the rules of the owner's working reconciliation code (2026-10-30): today's 23:59:59 is in the future."""
    now = now or datetime.now(timezone.utc); today = now.date()
    def day(v):
        try: return datetime.fromisoformat(str(v).strip()[:10]).date()
        except ValueError: raise AmazonError(f'{v!r} is not a date - write it as 2026-10-01')
    s, e = (day(cfg[k]) if cfg.get(k) else None for k in ('start', 'end'))
    if not (s or e):
        try: n = max(1, int(cfg.get('days') or default_days))
        except (TypeError, ValueError): n = default_days
        s, e = today - timedelta(days=n), today
    elif not s: s = e - timedelta(days=7)
    elif not e: e = s + timedelta(days=7)
    e = min(e, today)
    if s > e: raise AmazonError(f'the window starts {s} but ends {e} - the start must come first')
    return f'{s.isoformat()}T00:00:00Z', _iso(now - timedelta(minutes=2)) if e == today else f'{e.isoformat()}T23:59:59Z'


def transactions(cfg, start, end, page_size=100) -> list:
    """Every transaction whose feed date falls in the window, page by page. Amazon's reference says a next page is asked for
    with nextPageToken as the ONLY parameter."""
    out, params, seen = [], {'feedStartDate': start, 'feedEndDate': end, 'pageSize': max(1, min(int(page_size), 100))}, set()
    for _ in range(MAX_PAGES):
        j = _call(cfg, 'getTransactions', 'GET', f'{RECON}/transactions', api='business', params=params)
        out += j.get('transactions') or []
        tok = j.get('nextPageToken')
        if not tok or tok in seen: break           # a token handed back twice would page forever
        seen.add(tok); params = {'nextPageToken': tok}
    return out


def _line_key(li): return tuple(str(li.get(k) or '') for k in ('orderId', 'orderLineItemId', 'shipmentId'))


def invoices(cfg, lines) -> dict:
    """(orderId, orderLineItemId, shipmentId) -> its invoiceDetails, asked INVOICE_BATCH lines at a time. A line missing any of
    the three cannot be asked about and is left out."""
    keys, out = list(dict.fromkeys(k for k in map(_line_key, lines) if all(k))), {}
    for i in range(0, len(keys), INVOICE_BATCH):
        body = {'orderLineItems': [dict(zip(('orderId', 'orderLineItemId', 'shipmentId'), k)) for k in keys[i:i + INVOICE_BATCH]]}
        j = _call(cfg, 'getInvoiceDetailsByOrderLineItems', 'POST', f'{RECON}/invoices', api='business', data=json.dumps(body))
        for d in j.get('invoiceDetailsByOrderLineItems') or []: out[_line_key(d.get('orderLineItem') or {})] = d.get('invoiceDetails') or []
    return out


def _when(v):
    try: d = datetime.fromisoformat(str(v).strip().replace('Z', '+00:00'))
    except ValueError: return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def pick_invoice(kind, details, tx_date=None) -> dict:
    """The invoice a transaction line answers to: a CHARGE its STANDARD invoice; a REFUND or OVERREFUND the CREDIT_MEMO nearest
    its own date (a line refunded twice has two), with the STANDARD one kept as originalInvoiceNumber."""
    std = next((d for d in details if str(d.get('invoiceType') or 'STANDARD').upper() == 'STANDARD'), None)
    if str(kind or '').upper() not in ('REFUND', 'OVERREFUND'):
        return {'invoiceNumber': std['invoiceNumber'], 'invoiceDate': std.get('invoiceDate')} if std else {}
    memos, t = [d for d in details if str(d.get('invoiceType') or '').upper() == 'CREDIT_MEMO'], _when(tx_date)
    if t: memos.sort(key=lambda d: abs((_when(d.get('invoiceDate')) or t) - t))
    out = {'invoiceNumber': memos[0]['invoiceNumber'], 'invoiceDate': memos[0].get('invoiceDate')} if memos else {}
    return {**out, 'originalInvoiceNumber': std['invoiceNumber']} if std else out


def enrich(cfg, txs) -> list:
    """Each transaction line given the invoice it answers to (pick_invoice), in place; a line Amazon has no invoice for keeps its own."""
    got = invoices(cfg, [li for t in txs for li in t.get('transactionLineItems') or []])
    for t in txs:
        for li in t.get('transactionLineItems') or []: li.update(pick_invoice(t.get('transactionType'), got.get(_line_key(li)) or [], t.get('transactionDate')))
    return txs


def _amt(m): return m.get('amount') if isinstance(m, dict) else m


def tx_rows(txs) -> list:
    """One row per transaction line (a transaction without lines is one row), the transaction's own fields on each."""
    out = []
    for t in txs:
        amt = t.get('amount') if isinstance(t.get('amount'), dict) else {}
        head = {'transactionId': t.get('transactionId'), 'transactionDate': t.get('transactionDate'), 'transactionType': t.get('transactionType'),
                'amount': _amt(t.get('amount')), 'currency': amt.get('currencyCode'), 'legalEntityName': t.get('legalEntityName')}
        for li in t.get('transactionLineItems') or [{}]:
            out.append({**head, 'asin': li.get('asin'), 'productTitle': li.get('productTitle'), 'itemQuantity': li.get('itemQuantity'),
                        'unitPrice': _amt(li.get('unitPrice')), 'totalAmount': _amt(li.get('totalAmount')), 'tax': _amt(li.get('tax')),
                        'orderId': li.get('orderId'), 'purchaseOrderNumber': li.get('purchaseOrderNumber'),
                        'invoiceNumber': li.get('invoiceNumber') or t.get('invoiceNumber'), 'invoiceDate': li.get('invoiceDate'),
                        'originalInvoiceNumber': li.get('originalInvoiceNumber')})
    return out


def _yes(v) -> bool: return v is None or v == '' or str(v).strip().lower() not in ('0', 'false', 'no', 'off', 'none')
def _on(v) -> bool: return str(v or '').strip().lower() in ('1', 'true', 'yes', 'on', 'y')     # off unless said


# ── Amazon Business: an invoice or credit memo as its PDF ───────────────────────────────
# The owner's working flow (2026-10-30): createReport GET_AB_INVOICE_PDF, poll every 15s up to 120s, then the document - which
# Amazon's "Downloading invoices" guide says is "compressed twice: first with zip, then with gzip", and a zip may hold several PDFs.
INVOICE_PDF, PDF_POLL, PDF_WAIT, PDF_CAP = 'GET_AB_INVOICE_PDF', 15, 120, 25
_FILE = re.compile(r'[^A-Za-z0-9._ -]+')


def _bare(s) -> str: return re.sub(r'\W+', '', str(s or '')).lower()


def _pdf_text(data, pages=2) -> str:
    # pypdf is an optional extra (docs/bundle), never a requirement of this card: without it a zip of several PDFs is matched on
    # filenames alone
    try: from pypdf import PdfReader
    except ImportError: return ''
    try: return ' '.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(data)).pages[:pages])
    except Exception: return ''


def pick_pdf(raw: bytes, number) -> tuple:
    """(filename, pdf bytes) out of a downloaded invoice document: a plain PDF as it is; a zip's PDF whose filename carries the
    invoice number (punctuation and case ignored), else the one whose first two pages say it, else its only PDF."""
    if raw[:2] == b'\x1f\x8b': raw = gzip.decompress(raw)
    if raw[:5] == b'%PDF-': return f'{number}.pdf', raw
    if not zipfile.is_zipfile(io.BytesIO(raw)): raise AmazonError(f'the invoice document for {number} is neither a PDF nor a zip of them')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        pdfs = [(i.filename.rsplit('/', 1)[-1], z.read(i)) for i in z.infolist() if not i.is_dir() and i.filename.lower().endswith('.pdf')]
    if not pdfs: raise AmazonError(f'the invoice document for {number} held no PDF')
    k = _bare(number)
    hit = (next((p for p in pdfs if k and k in _bare(p[0])), None) or (pdfs[0] if len(pdfs) == 1 else None)
           or next((p for p in pdfs if k and k in _bare(_pdf_text(p[1]))), None))
    if not hit: raise AmazonError(f"none of the {len(pdfs)} PDFs Amazon sent for {number} names it ({', '.join(n for n, _ in pdfs[:5])})")
    return hit


def _marketplace(cfg, marketplace=None) -> str:
    ids = ids_of(marketplace) or ids_of(cfg.get('marketplace_ids'))
    if ids: return ids[0]
    if region(cfg) == 'na': return 'ATVPDKIKX0DER'          # the owner's default: amazon.com
    raise AmazonError('which marketplace is the invoice from? Put its id on the card or pass "marketplace_id" (e.g. A1PA6795UKMFR9 for Germany)')


def invoice_pdf(cfg, number, credit=False, marketplace=None) -> tuple:
    """(filename, pdf bytes) for ONE Amazon Business invoice - or, with `credit`, credit memo: createReport GET_AB_INVOICE_PDF on
    the business host, getReport every PDF_POLL seconds until DONE (CANCELLED or FATAL, or PDF_WAIT seconds, is a failure), then
    the document. `number` is the invoiceNumber the invoice lookup gave - for a refund, the credit memo's own number: Amazon's guide
    says the invoiceId is that invoiceNumber and "the correct invoice or credit memo document will be vended" from it."""
    n, kind = str(number or '').strip(), 'credit memo' if credit else 'invoice'
    if not n: raise AmazonError('no invoice number - give the invoiceNumber an Amazon Business transaction carries')
    body = {'reportType': INVOICE_PDF, 'reportOptions': {'invoiceId': n, 'documentType': 'Credits' if credit else 'Invoice'},
            'marketplaceIds': [_marketplace(cfg, marketplace)]}
    rid = _call(cfg, 'createReport', 'POST', f'{BREPORTS}/reports', api='business', data=json.dumps(body))['reportId']
    deadline = _clock() + PDF_WAIT
    while True:
        rep = _call(cfg, 'getReport', 'GET', f'{BREPORTS}/reports/{rid}', api='business')
        st = rep.get('processingStatus')
        if st == 'DONE' and rep.get('reportDocumentId'): break
        if st in ('CANCELLED', 'FATAL', 'DONE'):
            raise AmazonError(f"Amazon would not build the PDF of {kind} {n} ({st}) - check the number{' and that it is a credit memo' if credit else ''}")
        if _clock() >= deadline: raise AmazonError(f'the PDF of {kind} {n} was still {st} after {PDF_WAIT}s - report {rid}; ask again in a minute')
        _sleep(PDF_POLL)
    d = _call(cfg, 'getReportDocument', 'GET', f"{BREPORTS}/documents/{rep['reportDocumentId']}", api='business')
    r = requests.get(d['url'], timeout=120)
    if r.status_code != 200: raise AmazonError(f'the PDF of {kind} {n} would not download ({r.status_code}) - the link lives five minutes; ask again')
    raw = gzip.decompress(r.content) if str(d.get('compressionAlgorithm') or '').upper() == 'GZIP' else r.content
    return pick_pdf(raw, n)


def pdf_dir():
    from . import config
    p = config.home() / 'amazon' / 'invoices'; p.mkdir(parents=True, exist_ok=True)
    return p


def pdf_path(number, credit=False): return pdf_dir() / (_FILE.sub('', f"Amazon {'credit memo' if credit else 'invoice'} {number}").strip()[:120] + '.pdf')


def staged_pdf(cfg, number, credit=False, marketplace=None):
    """The invoice's PDF on disk (pdf_dir), fetched once: an issued invoice never changes, and every fetch spends a createReport
    from a quota of about one a minute. Returns (path, fetched now)."""
    p = pdf_path(number, credit)
    if p.exists() and p.stat().st_size: return p, False
    p.write_bytes(invoice_pdf(cfg, number, credit, marketplace)[1])
    return p, True


def run_amazon_invoice_pdf(cfg):
    """{"invoice": "1111-2222-3333", "credit": false, "marketplace_id": "ATVPDKIKX0DER"} - ONE Amazon Business invoice, or with
    credit the credit memo of that number, fetched as a PDF to a local folder; answers with its path. Like sftp_get it writes a file
    here and is still a read: nothing upstream moves."""
    n = str(cfg.get('invoice') or cfg.get('invoice_number') or '').strip()
    if not n: raise AmazonError('which invoice? Pass "invoice": the invoiceNumber an Amazon Business transaction carries')
    p, fresh = staged_pdf(cfg, n, _on(cfg.get('credit')), cfg.get('marketplace_id'))
    return f"{p.stat().st_size} bytes · {'credit memo' if _on(cfg.get('credit')) else 'invoice'} {n}{'' if fresh else ' (already fetched)'}", str(p)


def attach_pdfs(cfg, rows, sink) -> str:
    """Each row's invoice PDF staged and added to `sink` (the run's files, which land on the report's message), at most `pdf_cap`
    (PDF_CAP) NEW fetches a run - one already on disk costs Amazon nothing, so the next run picks up where this one stopped. A row
    gets `invoicePdf`, the file's name. Returns the note for the headline."""
    try: cap = max(0, min(int(cfg.get('pdf_cap') or PDF_CAP), PDF_CAP))
    except (TypeError, ValueError): cap = PDF_CAP
    want = list(dict.fromkeys((r['invoiceNumber'], str(r.get('transactionType') or '').upper() in ('REFUND', 'OVERREFUND'))
                              for r in rows if r.get('invoiceNumber')))
    got, bad, left, fetched = {}, [], 0, 0
    for n, credit in want:
        if not pdf_path(n, credit).exists() and fetched >= cap: left += 1; continue
        try: p, fresh = staged_pdf(cfg, n, credit); fetched += fresh
        except (AmazonError, requests.RequestException) as e:
            fetched += 1; bad.append(f'{n}: {e}')
            if '(403)' in str(e): break             # a role the app lacks refuses every one the same way - said once
            continue
        got[(n, credit)] = p.name; sink.append({'path': str(p), 'name': p.name, 'type': 'application/pdf'})
    for r in rows:
        if (k := (r.get('invoiceNumber'), str(r.get('transactionType') or '').upper() in ('REFUND', 'OVERREFUND'))) in got: r['invoicePdf'] = got[k]
    return ' · '.join(x for x in (f'{len(got)} invoice PDF(s) attached' if want else '', f'{left} more next run (at most {cap} new a run)' if left else '',
                                  f"{len(bad)} PDF(s) not fetched - {bad[0][:200]}" if bad else '') if x)


def run_amazon_business_transactions(cfg):
    """{"days": 7 (or "start"/"end" dates), "invoices": true, "pdfs": false, "pdf_cap": 25} - Amazon Business purchases as the
    reconciliation API sees them: one row per transaction line (charges, refunds) with ASIN, quantity, amounts, tax, order and PO
    number. With invoices on, each line is matched to its invoice number - a charge its invoice, a refund its credit memo. With
    pdfs on, a RUN also attaches each invoice's PDF to the report (attach_pdfs). Read-only."""
    start, end = feed_window(cfg)
    txs = transactions(cfg, start, end)
    if txs and _yes(cfg.get('invoices')): enrich(cfg, txs)
    rows, note = tx_rows(txs), f'{len(txs)} transaction(s)'
    if rows and _on(cfg.get('pdfs')):
        # only a run has somewhere to put a file (reports._run_report_source hands it `_files`); a preview or a dashboard does not,
        # and fetching up to 25 PDFs at a minute's quota each would make a preview take a quarter of an hour
        sink = cfg.get('_files')
        note += ' · ' + (attach_pdfs(cfg, rows, sink) if isinstance(sink, list) else 'invoice PDFs are attached when the report runs, not on a preview')
    return _out(cfg, rows, note, 'Amazon Business transactions', _span(start, end))
