"""SimpleFIN: the bank and card feed anyone can actually sign up for.

Same job as teller.py - what left the account, as rows an agent can act on - and it exists because
Teller stopped being obtainable: teller.io still serves a login page and still advertises its free
developer tier, but /signup is a 404, there is no signup link anywhere, and dashboard.teller.io no
longer resolves (checked 2026-09-10). A card nobody new can connect is not a card.

WHAT THE OWNER DOES, and it is the whole reason this fits a local install: they link their banks at
their own SimpleFIN Bridge account ($1.50/month or $15/year, paid by them, not by whoever ships
Taskuary), press "Get a setup token", and paste it here. No application to register, no sales call,
no client certificate - Teller's mTLS PEM pair is simply gone. Read-only is not a promise we make
on the API's behalf either: the SimpleFIN protocol has no write verbs at all.

A SETUP TOKEN IS A BASE64 CLAIM URL, and claiming it is one POST whose body is the ACCESS URL -
`https://user:pass@bridge.simplefin.org/simplefin` - credentials inside the URL. That URL is the
card's write-only Secret, and it is the only credential there is. Claims are one-shot: a second
POST answers "Forbidden (was it already claimed?)", so a re-connect needs a fresh token rather
than the same one again.

ONE FETCH, FOUR TOOLS. `GET {access}/accounts` returns every account WITH its balance AND its
transactions, so accounts / transactions / balances / spend all read one response instead of
Teller's three calls per account. That is not only cheaper, it is required: the Bridge allows
**24 requests a day** and disables a token that keeps overrunning, so this module caches the
response (CACHE_TTL) and refuses past DAY_BUDGET rather than getting the owner's token switched
off. Nothing here retries.

WHAT IT DOES NOT HAVE, next to Teller, because the protocol does not carry it:
  - no account TYPE and no last four. An account is an id, a name, and the org it came from, so
    `pick_account` matches on name and org rather than digits on a card.
  - no per-transaction category or counterparty.
  - data refreshes about once a day (MX upstream), and history is 90 days per request. `days: 0`
    on the spend rollup therefore means "as of the last sync", not intraday.
Signs are the protocol's own and need no account type to read: positive is money INTO the account,
negative is money out, so a card purchase is negative and paying the card off is positive. `spend`
and `inflow` on each row say which, so nobody has to remember.
"""
import base64
import json
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

import requests
from loguru import logger

BRIDGE = 'https://bridge.simplefin.org'          # where the owner gets a token; never called with the Secret
TIMEOUT = 30
MAX_DAYS = 90                                    # the Bridge's own per-request window
CACHE_TTL = 900                                  # one /accounts response serves every tool for this long
DAY_BUDGET = 20                                  # of the Bridge's 24: it warns, then disables the token


class SimpleFinError(RuntimeError): pass


def connection(store, connector_id=None) -> dict:
    from .reports import _card
    return _card(store, 'simplefin', 'access_url', connector_id)


# ── the one-shot claim ───────────────────────────────────────────────────────────────────
def claim_url(setup_token: str) -> str:
    """The claim URL a setup token decodes to, or ValueError. A token is base64 and nothing else,
    so a pasted access URL (or a truncated copy) is caught here rather than at the POST."""
    raw = str(setup_token or '').strip()
    if not raw: raise ValueError('paste the setup token from your SimpleFIN account first')
    try: url = base64.b64decode(raw + '=' * (-len(raw) % 4), validate=True).decode('utf-8', 'replace').strip()
    except Exception: raise ValueError('that is not a SimpleFIN setup token - it is a long base64 string, copied whole') from None
    if not url.lower().startswith(('http://', 'https://')):
        raise ValueError('that token does not decode to a claim URL - copy the whole token, or press "Get a setup token" again')
    return url


def claim(setup_token: str) -> str:
    """Trade the setup token for the access URL. One shot, by design: the token is spent by this."""
    url = claim_url(setup_token)
    try: r = requests.post(url, timeout=TIMEOUT)
    except requests.RequestException as e: raise SimpleFinError(f'could not reach SimpleFIN to claim the token: {e}') from e
    body = (r.text or '').strip()
    # a spent token answers 200-or-403 with "Forbidden..." in the body, not a JSON error
    if body.lower().startswith('forbidden') or r.status_code == 403:
        raise SimpleFinError('SimpleFIN says that setup token was already claimed - generate a new one and paste that')
    if r.status_code >= 300 or not body.lower().startswith(('http://', 'https://')):
        raise SimpleFinError(f'SimpleFIN did not return an access URL ({r.status_code}): {body[:200]}')
    return body


def _split(access: str):
    """(base url without credentials, (user, password)). The Secret carries both in one string, and
    the credentials must not be logged or put in a URL anyone can see."""
    s = urlsplit(str(access or '').strip())
    if not s.scheme or not s.netloc: raise SimpleFinError('the saved SimpleFIN access URL is not a URL - re-connect the card with a fresh setup token')
    host = s.hostname or ''
    if s.port: host = f'{host}:{s.port}'
    return urlunsplit((s.scheme, host, s.path.rstrip('/'), '', '')), (s.username or '', s.password or '')


def _access(cfg) -> str:
    a = cfg.get('access_url')
    if not a: raise SimpleFinError('no bank connected on this card yet - press "Connect with a setup token" and paste the token from your SimpleFIN account')
    return a


# ── one cached fetch, and a budget so the token survives the day ─────────────────────────
_CACHE = {}                                      # key -> (fetched_at, payload)
_CALLS = {'day': '', 'n': 0}


def reset_budget(day: str = '') -> None:
    _CALLS.update(day=day, n=0); _CACHE.clear()


def budget() -> dict:
    return {'day': _CALLS['day'], 'used': _CALLS['n'], 'of': DAY_BUDGET}


def _spend_call() -> None:
    today = date.today().isoformat()
    if _CALLS['day'] != today: _CALLS.update(day=today, n=0)
    if _CALLS['n'] >= DAY_BUDGET:
        raise SimpleFinError(f'SimpleFIN allows 24 reads a day and this card has used {_CALLS["n"]} - it refuses here rather than '
                             'letting the Bridge disable your token. The data refreshes about once a day; try again tomorrow, '
                             'or space the scheduled reports further apart.')
    _CALLS['n'] += 1


def fetch(cfg, days: int = 30, which: str = '', balances_only: bool = False, fresh: bool = False) -> dict:
    """The account set, cached. Every read in this module comes through here."""
    access = _access(cfg)
    days = max(1, min(int(days or 30), MAX_DAYS))
    params = [('pending', '1')] if not balances_only else [('balances-only', '1')]
    if not balances_only:
        start = datetime.now(timezone.utc) - timedelta(days=days)
        params.append(('start-date', str(int(start.timestamp()))))
    key = (access, days if not balances_only else 0, balances_only)
    hit = _CACHE.get(key)
    if hit and not fresh and time.time() - hit[0] < CACHE_TTL: return hit[1]
    base, auth = _split(access)
    _spend_call()
    try: r = requests.get(f'{base}/accounts', params=params, auth=auth, timeout=TIMEOUT)
    except requests.RequestException as e: raise SimpleFinError(f'could not reach SimpleFIN: {e}') from e
    if r.status_code == 403: raise SimpleFinError('SimpleFIN refused the access URL (403) - re-connect the card with a fresh setup token')
    if r.status_code == 402: raise SimpleFinError('SimpleFIN says payment is required (402) - the Bridge subscription lapsed; renew it at bridge.simplefin.org')
    if r.status_code >= 300: raise SimpleFinError(f'SimpleFIN {r.status_code}: {(r.text or "")[:200]}')
    try: payload = r.json()
    except ValueError: raise SimpleFinError(f'SimpleFIN sent something that is not JSON: {(r.text or "")[:200]}') from None
    if not isinstance(payload, dict) or not isinstance(payload.get('accounts'), list):
        raise SimpleFinError('SimpleFIN sent no account list - the access URL may point at something else')
    for e in errors_of(payload): logger.warning(f'simplefin: {e}')
    _CACHE[key] = (time.time(), payload)
    return payload


def errors_of(payload) -> list:
    """The Bridge's own per-connection complaints. v1 sends strings in `errors`; the v2 spec sends
    objects in `errlist`. A bank that needs re-authorising says so HERE, with everything else 200,
    so this is not decoration - it is the only way the owner hears about it."""
    out = []
    for e in (payload or {}).get('errors') or (payload or {}).get('errlist') or []:
        out.append(e if isinstance(e, str) else str((e or {}).get('msg') or e))
    return [o for o in out if o]


# ── reads ────────────────────────────────────────────────────────────────────────────────
def _org(a) -> str:
    o = a.get('org') if isinstance(a.get('org'), dict) else {}
    return str(o.get('name') or o.get('domain') or '')


def _stamp(epoch) -> str:
    try: return datetime.fromtimestamp(int(epoch), timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError, OverflowError): return ''


def _acct_row(a) -> dict:
    return {'id': a.get('id'), 'name': a.get('name'), 'org': _org(a), 'currency': a.get('currency'),
            'balance': a.get('balance'), 'available': a.get('available-balance'), 'as_of': _stamp(a.get('balance-date'))}


def accounts(cfg, days: int = 1) -> list:
    return [_acct_row(a) for a in fetch(cfg, days=days, balances_only=True).get('accounts') or []]


def pick(rows: list, which: str) -> list:
    """One account out of several, by id or by a word of its name or its bank - and a word matching
    two is refused, because "which account" is the whole question. There is no last-four to match
    on: the protocol carries neither the account type nor the digits, so a name like
    "Platinum Card x1234" is matched as text like any other."""
    w = str(which or '').strip().lower()
    if not w: return rows
    hit = [a for a in rows if str(a.get('id')) == str(which)]
    if not hit: hit = [a for a in rows if w in str(a.get('name') or '').lower() or w in str(a.get('org') or '').lower()]
    if not hit:
        named = ', '.join(f"{a.get('name')} ({a['org']})" if a.get('org') else str(a.get('name')) for a in rows)
        raise SimpleFinError(f'no account matching "{which}" - this token carries: {named}')
    if len(hit) > 1: raise SimpleFinError(f'"{which}" matches {len(hit)} accounts - use the account id or a word only one of them has')
    return hit


def _txn_row(t, acct) -> dict:
    amt = t.get('amount')
    try: f = float(amt)
    except (TypeError, ValueError): f = None
    # the protocol's own convention: positive INTO the account, so a card purchase is negative
    direction = None if f is None else 'zero' if f == 0 else 'spend' if f < 0 else 'inflow'
    return {'id': t.get('id'), 'date': _stamp(t.get('posted') or t.get('transacted_at')), 'description': t.get('description'),
            'amount': amt, 'direction': direction, 'payee': t.get('payee'), 'memo': t.get('memo'),
            'pending': bool(t.get('pending')) or not t.get('posted'), 'account': (acct or {}).get('name'), 'org': (acct or {}).get('org')}


def _posted(t) -> int:
    try: return int(t.get('posted') or t.get('transacted_at') or 0)
    except (TypeError, ValueError): return 0


def transactions(cfg, which: str = '', days: int = 30) -> list:
    """Newest first, across the picked account or every account this token carries.

    Sorted on the EPOCH, not on the row's date: several transactions a day is the normal case, and
    a date string ties them all together so the order falls back to whatever the ids sort like."""
    payload = fetch(cfg, days=days)
    rows, out = [_acct_row(a) for a in payload.get('accounts') or []], []
    keep = {a['id'] for a in pick(rows, which)}
    for a in payload.get('accounts') or []:
        if a.get('id') not in keep: continue
        acct = _acct_row(a)
        out += [(_posted(t), _txn_row(t, acct)) for t in a.get('transactions') or []]
    out.sort(key=lambda p: (p[0], str(p[1].get('id') or '')), reverse=True)
    return [r for _, r in out]


def balances(cfg, which: str = '') -> list:
    return [{'account': a['name'], 'org': a['org'], 'balance': a['balance'], 'available': a['available'], 'as_of': a['as_of']}
            for a in pick(accounts(cfg), which)]


def _window(days: int) -> str:
    return 'today' if days <= 0 else 'since yesterday' if days == 1 else f'over the last {days + 1} days'


def spend(cfg, which: str = '', days: int = 0) -> list:
    """Per-account spend over the window, biggest spender first, and a TOTAL row.

    Same shape as teller.spend, deliberately - the reports and alerts built on that one keep
    working - so the window is INCLUSIVE and counted in days back from today, and inflow is
    carried beside spend and never subtracted from it: a card payment is not negative spending.

    Pending rows COUNT. On a daily feed the alternative is a rollup that ignores this morning.
    """
    days = max(0, int(days or 0))
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = [r for r in transactions(cfg, which, days=days or 1) if (r.get('date') or '') >= since]
    seen = {}
    for r in rows:
        a = seen.setdefault(r.get('account') or '?', {'account': r.get('account') or '?', 'org': r.get('org'),
                                                      'charges': 0, 'spend': 0.0, 'largest': 0.0, 'inflow': 0.0})
        try: amt = abs(float(r.get('amount')))
        except (TypeError, ValueError): continue
        if r.get('direction') == 'spend': a['charges'], a['spend'], a['largest'] = a['charges'] + 1, a['spend'] + amt, max(a['largest'], amt)
        elif r.get('direction') == 'inflow': a['inflow'] += amt
    out = sorted(seen.values(), key=lambda a: -a['spend'])
    for a in out: a['spend'], a['largest'], a['inflow'] = round(a['spend'], 2), round(a['largest'], 2), round(a['inflow'], 2)
    return out + [{'account': 'TOTAL', 'org': None, 'charges': sum(a['charges'] for a in out),
                   'spend': round(sum(a['spend'] for a in out), 2), 'largest': max([a['largest'] for a in out] or [0.0]),
                   'inflow': round(sum(a['inflow'] for a in out), 2)}]


def probe(cfg) -> str:
    payload = fetch(cfg, balances_only=True, fresh=True)
    rows = [_acct_row(a) for a in payload.get('accounts') or []]
    errs = errors_of(payload)
    if not rows:
        return 'connected, but this token carries no accounts yet - link a bank at bridge.simplefin.org' + (f' ({errs[0]})' if errs else '')
    orgs = sorted({a['org'] for a in rows if a['org']})
    said = f"connected - {len(rows)} account{'s' if len(rows) != 1 else ''}" + (f" at {', '.join(orgs[:4])}" if orgs else '') + \
           ': ' + ', '.join(a['name'] for a in rows[:6])
    # a bank needing re-authorisation is a 200 with a sentence in `errors`, so Test must say it
    return said + (f" - SimpleFIN also reports: {errs[0]}" if errs else '')


# ── the report/tool surface (reports.REGISTRY) ───────────────────────────────────────────
def run_simplefin_accounts(cfg):
    """{} - every account this token carries: name, bank, balance and the date it is as of."""
    from .reports import row_limit, rows_out
    lim, mine = row_limit(cfg)
    return rows_out(accounts(cfg), lim, unit='accounts', mine=mine)


def run_simplefin_transactions(cfg):
    """{"account": "Operating" | "<id>" (blank = every account), "days": 30} - what posted, newest
    first, with `direction` (spend / inflow) so the sign needs no decoding and `pending` flagged.
    Schedule it with "can become work" on and each new transaction is a message triage judges -
    the front door of the card-to-books playbook."""
    from .reports import row_limit, rows_out
    lim, mine = row_limit(cfg)
    return rows_out(transactions(cfg, cfg.get('account'), cfg.get('days') or 30), lim, unit='transactions', mine=mine)


def run_simplefin_balances(cfg):
    """{"account": "Operating" (blank = every account)} - balance, available, and its as-of date."""
    from .reports import row_limit, rows_out
    lim, mine = row_limit(cfg)
    return rows_out(balances(cfg, cfg.get('account')), lim, unit='balances', mine=mine)


def run_simplefin_spend(cfg):
    """{"days": 0 (today) | 7, "account": "Operating" (blank = every account)} - what actually left
    each account, per account and in total, with the largest single charge beside each.

    The headline LEADS WITH THE TOTAL deliberately, exactly as teller_spend does: reports.result_count
    parses a leading number and strips its commas, so alert {"when": "more_than", "count": 500} on
    this report compares DOLLARS rather than row count. Cents are ignored by that comparison.
    """
    from .reports import BODY_CHARS
    days = max(0, int(cfg.get('days') or 0))
    rows = spend(cfg, cfg.get('account') or '', days)
    n = len(rows) - 1
    head = f"{rows[-1]['spend']:,.2f} spent {_window(days)} across {n} account{'' if n == 1 else 's'}"
    return head, '\n'.join(json.dumps(r, default=str) for r in rows)[:BODY_CHARS]
