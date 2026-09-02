"""Teller: the bank and card feed - what actually left the account, as rows an agent can act on.

The other half of docs/beyond-code.md: QuickBooks is where a transaction ENDS UP; this is where it
COMES FROM. One card is one bank login (an "enrollment" in Teller's words - a Chase login holding a
checking account and two cards); Add another for a second bank. Three reads, no writes - a feed
cannot move money, and nothing here would let it:

  teller_accounts      {}                                             - every account under this login
  teller_transactions  {"account": "Amex ...1234", "days": 30}         - what posted, newest first
  teller_balances      {"account": "Operating"}                        - ledger and available

Why Teller and not an aggregator with a hosted dashboard: this is a local install, so the owner
does the enrolment themselves, in the card, with Teller Connect - a script from cdn.teller.io that
opens the bank's own login in a modal and hands back an ACCESS TOKEN for that login. The token is
the card's write-only Secret. Teller's development tier is free (up to 100 enrolments), which is
the whole company for a company this size; production is the same code with different keys.

AUTH is two things at once, and the second is the unusual one: the access token rides as HTTP
Basic (token as the user, no password), and development/production calls must ALSO present the
client CERTIFICATE Teller issued when the application was created (mTLS) - a PEM cert and key on
this machine, named on the card by path. Sandbox needs no certificate and accepts any login at its
fake institutions, which is how the loop can be exercised before a real bank is connected.

Amounts are Teller's own strings, signed from the account's point of view: a purchase on a card is
positive on a credit account, a debit is negative on a depository one. The rows keep the sign and
add `direction` so nobody has to remember which.
"""
import json
from datetime import date, timedelta

import requests
from loguru import logger

API = 'https://api.teller.io'
CONNECT_JS = 'https://cdn.teller.io/connect/connect.js'
ENVS = ('sandbox', 'development', 'production')
TIMEOUT = 30


class TellerError(RuntimeError): pass


def connection(store, connector_id=None) -> dict:
    from .reports import _card
    return _card(store, 'teller', 'access_token', connector_id)


def _auth(cfg) -> dict:
    """requests kwargs for one call: the token as Basic user, and the certificate outside sandbox."""
    tok = cfg.get('access_token')
    if not tok: raise TellerError('no bank connected on this card yet - press "Connect a bank" and sign in at your bank')
    kw = {'auth': (tok, ''), 'timeout': TIMEOUT}
    env = str(cfg.get('environment') or 'sandbox').lower()
    if env != 'sandbox':
        cert, key = cfg.get('cert_path'), cfg.get('key_path')
        if not (cert and key): raise TellerError(f'{env} calls need the client certificate Teller issued: set the certificate and private key paths on the card')
        kw['cert'] = (cert, key)
    return kw


def _get(cfg, path, **params):
    r = requests.get(f'{API}{path}', params=params or None, **_auth(cfg))
    if r.status_code == 401: raise TellerError('Teller refused the access token (401) - the bank login may need re-authorising: press Connect a bank again')
    if r.status_code == 403: raise TellerError('Teller refused (403): the certificate does not match this application, or the token is from another environment')
    if r.status_code >= 300:
        try: msg = r.json().get('error', {}).get('message') or r.text[:200]
        except ValueError: msg = r.text[:200]
        raise TellerError(f'Teller {r.status_code}: {msg}')
    return r.json()


# ── reads ────────────────────────────────────────────────────────────────────────────────
def _acct_row(a) -> dict:
    return {'id': a.get('id'), 'name': a.get('name'), 'type': a.get('type'), 'subtype': a.get('subtype'),
            'last_four': a.get('last_four'), 'institution': (a.get('institution') or {}).get('name'),
            'status': a.get('status'), 'currency': a.get('currency'), 'enrollment_id': a.get('enrollment_id')}


def accounts(cfg) -> list:
    return [_acct_row(a) for a in _get(cfg, '/accounts')]


def pick_account(cfg, which: str):
    """One account out of the login's several, by id, by the digits on the card, or by a word of its
    name - and a word matching two is refused, because "which card" is the whole question."""
    rows = accounts(cfg)
    w = str(which or '').strip().lower()
    if not w: return rows
    hit = [a for a in rows if a['id'] == which]
    if not hit: hit = [a for a in rows if w.isdigit() and str(a.get('last_four') or '') == w]
    if not hit: hit = [a for a in rows if w in str(a.get('name') or '').lower() or w in str(a.get('institution') or '').lower()]
    if not hit: raise TellerError(f'no account matching "{which}" - this login has: ' + ', '.join(f"{a['name']} ...{a['last_four']}" for a in rows))
    if len(hit) > 1: raise TellerError(f'"{which}" matches {len(hit)} accounts - use the last four digits or the id')
    return hit


def _txn_row(t, acct) -> dict:
    amt = t.get('amount')
    try: f = float(amt)
    except (TypeError, ValueError): f = None
    credit = (acct or {}).get('type') == 'credit'
    # spend is what people want to see as spend, whichever way the bank signs it
    direction = None if f is None else ('spend' if (f > 0) == credit else 'inflow') if f != 0 else 'zero'
    d = t.get('details') or {}
    return {'id': t.get('id'), 'date': t.get('date'), 'description': t.get('description'), 'amount': amt, 'direction': direction,
            'status': t.get('status'), 'category': d.get('category'), 'counterparty': (d.get('counterparty') or {}).get('name'),
            'account': (acct or {}).get('name'), 'account_last_four': (acct or {}).get('last_four'), 'running_balance': t.get('running_balance')}


def transactions(cfg, which: str = '', days: int = 30, count: int = 200) -> list:
    """Newest first, across the picked account or every account under the login, since `days` ago."""
    since = (date.today() - timedelta(days=max(1, int(days or 30)))).isoformat()
    out = []
    for a in pick_account(cfg, which):
        rows = _get(cfg, f"/accounts/{a['id']}/transactions", count=max(1, min(int(count or 200), 500)))
        out += [_txn_row(t, a) for t in rows if str(t.get('date') or '') >= since]
    out.sort(key=lambda r: (r.get('date') or '', r.get('id') or ''), reverse=True)
    return out


def balances(cfg, which: str = '') -> list:
    out = []
    for a in pick_account(cfg, which):
        b = _get(cfg, f"/accounts/{a['id']}/balances")
        out.append({'account': a['name'], 'last_four': a['last_four'], 'type': a['type'], 'ledger': b.get('ledger'), 'available': b.get('available')})
    return out


def probe(cfg) -> str:
    rows = accounts(cfg)
    if not rows: return 'connected, but the login shows no accounts'
    inst = rows[0].get('institution') or 'the bank'
    return f"connected to {inst} ({cfg.get('environment') or 'sandbox'}) - {len(rows)} account{'s' if len(rows) != 1 else ''}: " + \
           ', '.join(f"{a['name']} ...{a['last_four']}" for a in rows[:6])


# ── the report/tool surface (reports.REGISTRY) ───────────────────────────────────────────
def run_teller_accounts(cfg):
    """{} - every account under this bank login: name, type, last four, institution."""
    from .reports import rows_out, row_limit
    lim, mine = row_limit(cfg)
    return rows_out(accounts(cfg), lim, unit='accounts', mine=mine)


def run_teller_transactions(cfg):
    """{"account": "1234" | "Amex" | "<id>" (blank = every account), "days": 30} - what posted,
    newest first, with `direction` (spend / inflow) so the sign needs no decoding. Schedule it with
    "can become work" on and each new transaction is a message triage judges - the front door of the
    card-to-books playbook."""
    from .reports import rows_out, row_limit
    lim, mine = row_limit(cfg)
    return rows_out(transactions(cfg, cfg.get('account'), cfg.get('days') or 30, lim + 1), lim, unit='transactions', mine=mine)


def run_teller_balances(cfg):
    """{"account": "Operating" (blank = every account)} - ledger and available balance."""
    from .reports import rows_out, row_limit
    lim, mine = row_limit(cfg)
    return rows_out(balances(cfg, cfg.get('account')), lim, unit='balances', mine=mine)
