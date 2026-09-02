"""QuickBooks Online: the books, as a connection an agent can read - and, on approval, post to.

The first Corporate system that WRITES. Intacct is read-only here on purpose; QuickBooks is where
the "beyond code" work lands (docs/beyond-code.md): a card transaction becomes a bill, an expense
gets posted. So the card carries five verbs, split the way the scope ladder wants them:

  quickbooks           read   {"query": "SELECT * FROM Bill WHERE TxnDate > '2026-08-01'"}  - QBO's own SQL
  quickbooks_vendors   read   {"name": "amex"}                                              - vendors, by name
  quickbooks_accounts  read   {"type": "Expense"}                                           - the chart of accounts
  quickbooks_bill      WRITE  {"vendor", "amount", "account", "date", "memo", "doc_number"}  - an AP bill
  quickbooks_expense   WRITE  {"vendor", "amount", "account", "paid_from", "date", "memo"}   - a card/bank purchase

The card ships at scope `read`, so an agent cannot post directly: it proposes (TASKUARY-PROPOSE
{"action": "run_tool", "type": "quickbooks_bill", ...}), the proposal lands in Review with the
vendor, the amount and the account on it, and approving RUNS it. Raise the card to `write` and a
routing policy can let small, known bills through without the click - that is the owner's choice
to make once, not the agent's to make each time.

AUTH is OAuth2 against Intuit, and the shape is the awkward part: Intuit hands out a refresh
token that ROTATES on every use (each refresh returns a new one, the old one dies), and the pair
is good for 100 days of disuse. So the refresh token is the card's write-only Secret, and every
refresh writes the new one back - a connector that kept the first token would work for exactly
one hour. The client id + secret are the owner's own Intuit app (developer.intuit.com, one-time);
the redirect URI it must carry is this server's /api/quickbooks/callback, shown on the card.

Sandbox and production are different hosts and different app keys; `env` on the card picks.
"""
import base64, json, time
from datetime import date
from urllib.parse import urlencode

import requests
from loguru import logger

AUTH_URL = 'https://appcenter.intuit.com/connect/oauth2'
TOKEN_URL = 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer'
SCOPE = 'com.intuit.quickbooks.accounting'
HOSTS = {'sandbox': 'https://sandbox-quickbooks.api.intuit.com', 'production': 'https://quickbooks.api.intuit.com'}
MINOR = 75
TIMEOUT = 30
_TOK = {}        # realm id -> (access token, expiry): access tokens live an hour, refresh only when needed


class QuickBooksError(RuntimeError): pass


# ── the card ─────────────────────────────────────────────────────────────────────────────
def connection(store, connector_id=None) -> dict:
    """The card's config with the refresh token as `refresh_token`, plus a handle back to the store
    so a rotated token can be written where it came from."""
    from .reports import _card, _connector
    cfg = _card(store, 'quickbooks', 'refresh_token', connector_id)
    c = _connector(store, 'quickbooks', connector_id)
    return {**cfg, '_store': store, '_cid': (c or {}).get('ConnectorId')}


def redirect_uri(cfg_server: dict) -> str:
    """What the Intuit app must have registered, exactly. localhost, because that is where this
    server listens and the one origin Intuit accepts over plain http."""
    return f"http://localhost:{cfg_server.get('port') or 7787}/api/quickbooks/callback"


def authorize_url(cfg: dict, redirect: str, state: str) -> str:
    if not cfg.get('client_id'): raise QuickBooksError('no Intuit client id on the card yet - create the app at developer.intuit.com and paste its keys')
    return AUTH_URL + '?' + urlencode({'client_id': cfg['client_id'], 'redirect_uri': redirect, 'response_type': 'code',
                                       'scope': SCOPE, 'state': state})


def _basic(cfg) -> str:
    return 'Basic ' + base64.b64encode(f"{cfg.get('client_id', '')}:{cfg.get('client_secret', '')}".encode()).decode()


def _save_refresh(cfg, refresh: str, realm: str = None):
    """The rotated token goes back on the card the moment it exists. Losing it is losing the
    connection: the previous token is dead the instant Intuit issues the next."""
    store, cid = cfg.get('_store'), cfg.get('_cid')
    if not (store and cid): return
    body = {'ConnectorId': cid, 'Secret': refresh}
    if realm:
        c = store.get_connector(cid) or {}
        conf = json.loads(c.get('ConfigJson') or '{}'); conf['realm_id'] = realm
        body['ConfigJson'] = json.dumps(conf)
    store.save_connector(body, 'quickbooks')
    cfg['refresh_token'] = refresh


def exchange_code(cfg: dict, code: str, redirect: str, realm: str) -> dict:
    """The callback's half of OAuth: the one-time code for the token pair. Saves both the refresh
    token and the company (realm) id the callback names - a QBO token is for one company."""
    r = requests.post(TOKEN_URL, timeout=TIMEOUT, headers={'Authorization': _basic(cfg), 'Accept': 'application/json'},
                      data={'grant_type': 'authorization_code', 'code': code, 'redirect_uri': redirect})
    if r.status_code != 200: raise QuickBooksError(f'Intuit refused the code ({r.status_code}): {r.text[:200]}')
    j = r.json()
    _save_refresh(cfg, j['refresh_token'], realm)
    _TOK[realm] = (j['access_token'], time.time() + int(j.get('expires_in') or 3600))
    return {'realm_id': realm}


def token(cfg: dict) -> str:
    """An access token, refreshed when the hour is up - and the rotated refresh token saved."""
    realm = str(cfg.get('realm_id') or '')
    if not (cfg.get('client_id') and cfg.get('client_secret')): raise QuickBooksError('the QuickBooks card needs the Intuit app\'s client id and secret')
    if not cfg.get('refresh_token'): raise QuickBooksError('QuickBooks is not connected yet - press "Connect to QuickBooks" on its card')
    if not realm: raise QuickBooksError('no company (realm) id on the card - connecting fills it in')
    hit = _TOK.get(realm)
    if hit and hit[1] > time.time() + 60: return hit[0]
    r = requests.post(TOKEN_URL, timeout=TIMEOUT, headers={'Authorization': _basic(cfg), 'Accept': 'application/json'},
                      data={'grant_type': 'refresh_token', 'refresh_token': cfg['refresh_token']})
    if r.status_code != 200:
        raise QuickBooksError(f'Intuit refused the refresh token ({r.status_code}) - reconnect from the card: {r.text[:160]}')
    j = r.json()
    if j.get('refresh_token') and j['refresh_token'] != cfg.get('refresh_token'): _save_refresh(cfg, j['refresh_token'])
    _TOK[realm] = (j['access_token'], time.time() + int(j.get('expires_in') or 3600))
    return j['access_token']


def _base(cfg) -> str:
    env = str(cfg.get('env') or 'production').lower()
    return f"{HOSTS.get(env, HOSTS['production'])}/v3/company/{cfg.get('realm_id')}"


def _call(cfg, method, path, **kw):
    tok = token(cfg)
    r = requests.request(method, f'{_base(cfg)}/{path}', timeout=TIMEOUT, params={'minorversion': MINOR, **kw.pop('params', {})},
                         headers={'Authorization': f'Bearer {tok}', 'Accept': 'application/json', 'Content-Type': 'application/json'}, **kw)
    if r.status_code == 401: _TOK.pop(str(cfg.get('realm_id')), None); raise QuickBooksError('QuickBooks refused the token (401) - reconnect from the card')
    if r.status_code >= 300:
        try: why = r.json()['Fault']['Error'][0]; msg = f"{why.get('Message')}: {why.get('Detail')}"
        except Exception: msg = r.text[:300]
        raise QuickBooksError(f'QuickBooks {r.status_code}: {msg}')
    return r.json()


# ── reads ────────────────────────────────────────────────────────────────────────────────
def query(cfg, sql: str, limit: int = 200) -> list:
    """QBO's query language: SELECT * FROM <Entity> [WHERE ...] [ORDERBY ...]. One entity per query,
    which is how Intuit built it. Rows come back as flat dicts - nested refs collapse to their
    name and id, so a Bill row has VendorRef.name beside its total."""
    q = str(sql or '').strip().rstrip(';')
    if not q.lower().startswith('select'): raise QuickBooksError('a QuickBooks query starts with SELECT - e.g. SELECT * FROM Vendor WHERE Active = true')
    if ' maxresults ' not in q.lower(): q += f' MAXRESULTS {max(1, min(int(limit), 1000))}'
    j = _call(cfg, 'GET', 'query', params={'query': q})
    resp = j.get('QueryResponse') or {}
    ent = next((k for k in resp if isinstance(resp[k], list)), None)
    return [flatten(x) for x in (resp.get(ent) or [])] if ent else []


def flatten(d, prefix=''):
    out = {}
    for k, v in (d or {}).items():
        key = f'{prefix}{k}'
        if isinstance(v, dict) and set(v) <= {'value', 'name', 'type'}:      # a Ref
            out[key] = v.get('name') or v.get('value'); out[f'{key}.id'] = v.get('value')
        elif isinstance(v, dict): out.update(flatten(v, key + '.'))
        elif isinstance(v, list): out[key] = json.dumps(v)[:400] if k != 'Line' else f'{len(v)} lines'
        else: out[key] = v
    return out


def vendors(cfg, name: str = None, limit: int = 200) -> list:
    where = f" WHERE DisplayName LIKE '%{name.replace(chr(39), '')}%'" if name else ' WHERE Active = true'
    return query(cfg, f'SELECT Id, DisplayName, CompanyName, Active, Balance, PrimaryEmailAddr FROM Vendor{where}', limit)


def accounts(cfg, kind: str = None, limit: int = 500) -> list:
    where = f" WHERE AccountType = '{kind}'" if kind else ' WHERE Active = true'
    return query(cfg, f'SELECT Id, Name, FullyQualifiedName, AccountType, AccountSubType, Active, CurrentBalance FROM Account{where}', limit)


def company(cfg) -> dict:
    j = _call(cfg, 'GET', f"companyinfo/{cfg.get('realm_id')}")
    c = j.get('CompanyInfo') or {}
    return {'name': c.get('CompanyName'), 'country': c.get('Country'), 'realm_id': cfg.get('realm_id')}


def _ref(cfg, entity, name_field, name, kind='') -> dict:
    """An exact id, or a NAME resolved to one - and a name that matches nothing is refused, never
    guessed: a bill posted to the wrong vendor is the failure this whole file exists to prevent."""
    s = str(name or '').strip()
    if not s: raise QuickBooksError(f'no {kind or entity.lower()} given')
    if s.isdigit(): return {'value': s}
    rows = query(cfg, f"SELECT Id, {name_field} FROM {entity} WHERE {name_field} = '{s.replace(chr(39), '')}'", 5)
    if len(rows) == 1: return {'value': str(rows[0]['Id']), 'name': rows[0][name_field]}
    if not rows:
        near = query(cfg, f"SELECT Id, {name_field} FROM {entity} WHERE {name_field} LIKE '%{s.replace(chr(39), '')}%'", 5)
        hint = f" Close: {', '.join(str(r[name_field]) for r in near)}." if near else ''
        raise QuickBooksError(f'no {kind or entity.lower()} named "{s}" in QuickBooks - it is not created for you.{hint}')
    raise QuickBooksError(f'"{s}" matches {len(rows)} {entity}s - use the id')


# ── writes: never called without an approved proposal, unless the owner raised the card ─
def _money(x):
    try: v = round(float(str(x).replace(',', '').replace('$', '')), 2)
    except (TypeError, ValueError): raise QuickBooksError(f'amount {x!r} is not a number')
    if v <= 0: raise QuickBooksError('amount must be positive')
    return v


def create_bill(cfg, vendor, amount, account, when=None, memo='', doc_number='', description='') -> dict:
    """One AP bill: one line, one expense account. The vendor and account are looked up by name
    and must exist. `doc_number` is the dedupe key a card transaction id belongs in."""
    body = {'VendorRef': _ref(cfg, 'Vendor', 'DisplayName', vendor, 'vendor'),
            'TxnDate': str(when or date.today()), 'PrivateNote': str(memo or '')[:4000],
            'Line': [{'Amount': _money(amount), 'DetailType': 'AccountBasedExpenseLineDetail', 'Description': str(description or memo or '')[:4000],
                      'AccountBasedExpenseLineDetail': {'AccountRef': _ref(cfg, 'Account', 'Name', account, 'expense account')}}]}
    if doc_number: body['DocNumber'] = str(doc_number)[:21]
    b = _call(cfg, 'POST', 'bill', data=json.dumps(body)).get('Bill') or {}
    logger.info(f"quickbooks: bill {b.get('Id')} {b.get('DocNumber') or ''} {b.get('TotalAmt')} to {vendor}")
    return {'id': b.get('Id'), 'doc_number': b.get('DocNumber'), 'total': b.get('TotalAmt'), 'vendor': (b.get('VendorRef') or {}).get('name'),
            'date': b.get('TxnDate'), 'due': b.get('DueDate')}


def create_expense(cfg, vendor, amount, account, paid_from, when=None, memo='', description='') -> dict:
    """A purchase already paid - the card-transaction shape: money left `paid_from` (a credit card
    or bank account) for `account` (the expense), payee `vendor`."""
    pay = _ref(cfg, 'Account', 'Name', paid_from, 'credit card / bank account')
    kind = query(cfg, f"SELECT AccountType FROM Account WHERE Id = '{pay['value']}'", 1)
    ptype = 'CreditCard' if kind and kind[0].get('AccountType') == 'Credit Card' else 'Cash'
    body = {'PaymentType': ptype, 'AccountRef': pay, 'TxnDate': str(when or date.today()), 'PrivateNote': str(memo or '')[:4000],
            'EntityRef': {**_ref(cfg, 'Vendor', 'DisplayName', vendor, 'vendor'), 'type': 'Vendor'},
            'Line': [{'Amount': _money(amount), 'DetailType': 'AccountBasedExpenseLineDetail', 'Description': str(description or memo or '')[:4000],
                      'AccountBasedExpenseLineDetail': {'AccountRef': _ref(cfg, 'Account', 'Name', account, 'expense account')}}]}
    p = _call(cfg, 'POST', 'purchase', data=json.dumps(body)).get('Purchase') or {}
    logger.info(f"quickbooks: expense {p.get('Id')} {p.get('TotalAmt')} {vendor} from {paid_from}")
    return {'id': p.get('Id'), 'total': p.get('TotalAmt'), 'vendor': vendor, 'paid_from': (p.get('AccountRef') or {}).get('name'), 'date': p.get('TxnDate')}


# ── the card's test, and the report/tool surface (reports.REGISTRY) ─────────────────────
def probe(cfg) -> str:
    c = company(cfg)
    n = len(vendors(cfg, limit=5))
    return f"connected to {c.get('name') or 'the company'} (realm {c.get('realm_id')}, {cfg.get('env') or 'production'}) - read a vendor list ({n}+ vendors)"


def run_quickbooks(cfg):
    """{"query": "SELECT * FROM Bill WHERE TxnDate >= '2026-08-01'"} - QBO's own query language,
    one entity per query. Bill, Purchase, Vendor, Account, Invoice, Customer, Payment, JournalEntry."""
    from .reports import rows_out, row_limit
    lim, mine = row_limit(cfg)
    if not str(cfg.get('query') or '').strip(): raise QuickBooksError('no query set - e.g. SELECT * FROM Bill WHERE TxnDate >= \'2026-08-01\'')
    return rows_out(query(cfg, cfg['query'], lim + 1), lim, mine=mine)


def run_quickbooks_vendors(cfg):
    """{"name": "amex"} - vendors whose display name contains it; blank = every active vendor."""
    from .reports import rows_out, row_limit
    lim, mine = row_limit(cfg)
    return rows_out(vendors(cfg, cfg.get('name'), lim + 1), lim, unit='vendors', mine=mine)


def run_quickbooks_accounts(cfg):
    """{"type": "Expense"} - the chart of accounts, optionally one AccountType (Expense, Bank,
    Credit Card, Accounts Payable...)."""
    from .reports import rows_out, row_limit
    lim, mine = row_limit(cfg)
    return rows_out(accounts(cfg, cfg.get('type'), lim + 1), lim, unit='accounts', mine=mine)


def run_quickbooks_bill(cfg):
    """{"vendor": "Acme Supply", "amount": 412.50, "account": "Office Supplies", "date": "2026-09-01",
    "memo": "card ****1234 txn 88213", "doc_number": "88213"} - create ONE AP bill. A WRITE: below
    scope write on the card it can only run as an approved proposal."""
    b = create_bill(cfg, cfg.get('vendor'), cfg.get('amount'), cfg.get('account'), cfg.get('date'), cfg.get('memo'), cfg.get('doc_number'), cfg.get('description'))
    return f"bill {b.get('doc_number') or b.get('id')} for {b.get('total')} to {b.get('vendor')} created", json.dumps(b, indent=1)


def run_quickbooks_expense(cfg):
    """{"vendor": "Delta", "amount": 318.20, "account": "Travel", "paid_from": "Amex 1234", "date":
    "2026-09-01", "memo": "txn 77a1"} - post a purchase already paid from a card or bank account."""
    p = create_expense(cfg, cfg.get('vendor'), cfg.get('amount'), cfg.get('account'), cfg.get('paid_from'), cfg.get('date'), cfg.get('memo'), cfg.get('description'))
    return f"expense of {p.get('total')} to {p.get('vendor')} from {p.get('paid_from')} posted", json.dumps(p, indent=1)
