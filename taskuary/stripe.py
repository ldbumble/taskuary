"""Stripe: a business's payments, as rows - for Reports, Dashboards and agents.

A DATA card, not a channel: nothing here polls for work or lands on the rail (the owner, 2026-11-01: "just for
reports/connectors for now"). It READS, and only reads:

  stripe_balance               {}                                     - what is available and pending, per currency
  stripe_balance_transactions  {"days": 30, "kind": "charge"}        - every movement on the balance, fees and net
  stripe_charges               {"days": 30, "status": "succeeded"}   - charges
  stripe_payments              {"days": 30, "status": "succeeded"}   - PaymentIntents
  stripe_payouts               {"days": 30, "status": "paid"}        - money sent to the bank
  stripe_refunds               {"days": 30}                           - refunds
  stripe_disputes              {"days": 90, "status": "needs_response"} - chargebacks
  stripe_customers             {"email": "...", "days": 30}           - customers (all of them unless a window is given)
  stripe_subscriptions         {"status": "active"}                   - subscriptions, each with its MRR
  stripe_invoices              {"days": 30, "status": "open"}         - invoices

READ-ONLY BY CONSTRUCTION. Stripe's API moves money with a POST, so _call refuses every verb but GET and every host but
api.stripe.com before anything leaves the machine - not a promise in a docstring but the only road out of this file. The
key should be a RESTRICTED key with Read on what is listed above and None on everything else; that makes Stripe itself the
second wall. A full secret key (sk_) works too and is accepted, because some owners have nothing else - the card says a
restricted one is better, and why.

AUTH is the key as a Bearer token, kept as the card's write-only Secret. Amounts arrive in the currency's MINOR unit
(cents) - except the zero-decimal currencies, where 500 JPY is 500, and the three-decimal ones - and every row here carries
them already turned into money (minor()). Lists page with starting_after up to MAX_ITEMS, windows are created[gte]/[lte],
and a 429 is waited out (Retry-After when Stripe sends one, else a doubling wait) rather than failed.
"""
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests
from loguru import logger

API = 'https://api.stripe.com'
TIMEOUT, TRIES, MAX_BACKOFF, PAGE, MAX_ITEMS = 30, 5, 30, 100, 5000
# stripe.com/docs/currencies#zero-decimal and #three-decimal: every other currency has two decimals
ZERO_DECIMAL = frozenset('bif clp djf gnf jpy kmf krw mga pyg rwf ugx vnd vuv xaf xof xpf'.split())
THREE_DECIMAL = frozenset('bhd jod kwd omr tnd'.split())
# the field shapes the rows below read (subscription.current_period_end moved onto its items in later versions) - pinned so a
# Stripe upgrade of the account's default version cannot quietly empty a column
VERSION = '2024-06-20'
PREFIXES = ('rk_live_', 'rk_test_', 'sk_live_', 'sk_test_')
# what the headline calls the sum of each list's money column
SAID = {'amount': 'total', 'total': 'total', 'net': 'net', 'amount_received': 'received', 'mrr': 'MRR'}
# a subscription item's price per one interval -> per month
PER_MONTH = {'day': 365 / 12, 'week': 52 / 12, 'month': 1, 'year': 1 / 12}
_sleep = time.sleep


class StripeError(RuntimeError): pass


# ── the card ─────────────────────────────────────────────────────────────────────────────
def connection(store, connector_id=None) -> dict:
    """The card's config with its write-only Secret, the API key, as `api_key`."""
    from .reports import _card
    return _card(store, 'stripe', 'api_key', connector_id)


def key_of(cfg) -> str:
    k = str(cfg.get('api_key') or '').strip()
    if not k: raise StripeError('no Stripe key on the card yet - make a restricted key (Developers → API keys → Create restricted key) and paste it')
    if k.startswith(('pk_live_', 'pk_test_')): raise StripeError('that is a publishable key (pk_) - it cannot read anything; paste a restricted key (rk_) instead')
    if not k.startswith(PREFIXES): raise StripeError('a Stripe key starts rk_live_ / rk_test_ (restricted, preferred) or sk_live_ / sk_test_')
    return k


def mode(cfg) -> str: return 'test' if '_test_' in key_of(cfg)[:8] else 'live'


def _why(r) -> str:
    try: e = r.json().get('error') or {}; return e.get('message') or e.get('code') or r.text[:300]
    except Exception: return r.text[:300]


def _wait(r, n) -> float:
    try: base = float((getattr(r, 'headers', None) or {}).get('Retry-After'))
    except (TypeError, ValueError): base = 2.0 ** n
    return min(MAX_BACKOFF, base)


def _call(cfg, method, path, params=None) -> dict:
    """One Stripe call, and the only one there is. GET to api.stripe.com or nothing: a POST is how Stripe refunds, pays out
    and cancels, so any other verb - or a path that would leave the host - is refused before a request is built."""
    if method != 'GET': raise StripeError(f'{method} {path} is not a call this card makes - it is read-only')
    url = API + path
    if urlparse(url).hostname != 'api.stripe.com' or not path.startswith('/v1/'): raise StripeError(f'{path!r} is not a Stripe read')
    hdr = {'Authorization': f'Bearer {key_of(cfg)}', 'Stripe-Version': VERSION}
    for n in range(TRIES):
        r = requests.get(url, params=params or {}, headers=hdr, timeout=TIMEOUT)
        if r.status_code == 429 and n < TRIES - 1:
            w = _wait(r, n); logger.info(f'stripe: {path} rate-limited - waiting {w:.0f}s'); _sleep(w); continue
        break
    if r.status_code == 401: raise StripeError(f'Stripe refused the key (401): {_why(r)} - check it was copied whole, or roll a new one')
    if r.status_code == 403: raise StripeError(f'Stripe refused {path} (403): {_why(r)} - the restricted key needs Read on this resource')
    if r.status_code == 429: raise StripeError(f'Stripe is still rate-limiting {path} after {TRIES} tries - run it again in a minute')
    if r.status_code >= 300: raise StripeError(f'Stripe {path} {r.status_code}: {_why(r)}')
    return r.json()


def items(cfg, path, params=None, cap=MAX_ITEMS) -> list:
    """Every object of a list endpoint, PAGE at a time with starting_after, up to `cap` - a capped list says so in its
    headline (rows_out), so the cap is a ceiling on cost, never a silent cut."""
    out, p = [], {**(params or {}), 'limit': PAGE}
    while len(out) < cap:
        j = _call(cfg, 'GET', path, p)
        page = j.get('data') or []
        out += page
        if not (j.get('has_more') and page): break
        p = {**p, 'starting_after': page[-1]['id']}
    return out[:cap]


# ── money and time ───────────────────────────────────────────────────────────────────────
def minor(amount, currency):
    """Stripe's integer amount in the currency's minor unit -> money: 1999 usd is 19.99, 500 jpy is 500, 1500 kwd is 1.5."""
    if amount is None: return None
    c = str(currency or '').lower()
    d = 0 if c in ZERO_DECIMAL else 3 if c in THREE_DECIMAL else 2
    return round(amount / 10 ** d, d) if d else amount


def _day(s):
    try: d = datetime.fromisoformat(str(s).strip().replace('Z', '+00:00'))
    except ValueError: raise StripeError(f'{s!r} is not a date - write it as 2026-10-01')
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def window(cfg, default_days=30):
    """(gte, lte) as unix seconds: `start`/`end` dates if given (an end date is that whole day), else the last `days`
    days. default_days=None means no window unless one was asked for - customers and subscriptions are wanted whole."""
    if not (cfg.get('start') or cfg.get('end') or cfg.get('days') or default_days): return None, None
    end = _day(cfg['end']) + timedelta(days=1) - timedelta(seconds=1) if cfg.get('end') else datetime.now(timezone.utc)
    if cfg.get('start'): start = _day(cfg['start'])
    else:
        try: n = max(1, int(cfg.get('days') or default_days or 30))
        except (TypeError, ValueError): n = default_days or 30
        start = (end - timedelta(days=n)).replace(hour=0, minute=0, second=0, microsecond=0)
    if start > end: raise StripeError(f'the window starts {start:%Y-%m-%d} but ends {end:%Y-%m-%d} - the start must come first')
    return int(start.timestamp()), int(end.timestamp())


def _params(cfg, default_days=30, **extra) -> dict:
    gte, lte = window(cfg, default_days)
    p = {'created[gte]': gte, 'created[lte]': lte} if gte else {}
    return {**p, **{k: v for k, v in extra.items() if v not in (None, '')}}


def _ts(t): return datetime.fromtimestamp(t, timezone.utc).strftime('%Y-%m-%d %H:%M') if t else None


def _span(gte, lte): return f"{_ts(gte)[:10]} → {_ts(lte)[:10]}" if gte else ''


def _name(o, k):
    v = o.get(k)
    return v if isinstance(v, str) or v is None else v.get('id')      # an expanded object, or the id Stripe sends by default


# ── rows: each object's handful of fields a person reads, amounts already money ──────────
def _money(o, cur, *keys): return {k: minor(o.get(k), cur) for k in keys}


def balance_rows(b) -> list:
    return [{'state': state, 'currency': x.get('currency'), 'amount': minor(x.get('amount'), x.get('currency'))}
            for state in ('available', 'pending', 'instant_available') for x in b.get(state) or []]


def bt_row(o):
    c = o.get('currency')
    return {'id': o['id'], 'created': _ts(o.get('created')), 'available_on': _ts(o.get('available_on')), 'type': o.get('type'),
            'reporting_category': o.get('reporting_category'), 'currency': c, **_money(o, c, 'amount', 'fee', 'net'),
            'status': o.get('status'), 'description': o.get('description'), 'source': _name(o, 'source')}


def charge_row(o):
    c, bd = o.get('currency'), o.get('billing_details') or {}
    return {'id': o['id'], 'created': _ts(o.get('created')), 'currency': c, **_money(o, c, 'amount', 'amount_captured', 'amount_refunded'),
            'status': o.get('status'), 'paid': o.get('paid'), 'refunded': o.get('refunded'), 'disputed': o.get('disputed'),
            'customer': _name(o, 'customer'), 'email': bd.get('email') or o.get('receipt_email'), 'description': o.get('description'),
            'payment_intent': _name(o, 'payment_intent'), 'failure_message': o.get('failure_message')}


def payment_row(o):
    c = o.get('currency')
    return {'id': o['id'], 'created': _ts(o.get('created')), 'currency': c, **_money(o, c, 'amount', 'amount_received'),
            'status': o.get('status'), 'customer': _name(o, 'customer'), 'description': o.get('description'),
            'latest_charge': _name(o, 'latest_charge'), 'canceled_at': _ts(o.get('canceled_at'))}


def payout_row(o):
    c = o.get('currency')
    return {'id': o['id'], 'created': _ts(o.get('created')), 'arrival_date': _ts(o.get('arrival_date')), 'currency': c,
            'amount': minor(o.get('amount'), c), 'status': o.get('status'), 'method': o.get('method'), 'type': o.get('type'),
            'description': o.get('description'), 'failure_message': o.get('failure_message')}


def refund_row(o):
    c = o.get('currency')
    return {'id': o['id'], 'created': _ts(o.get('created')), 'currency': c, 'amount': minor(o.get('amount'), c), 'status': o.get('status'),
            'reason': o.get('reason'), 'charge': _name(o, 'charge'), 'payment_intent': _name(o, 'payment_intent')}


def dispute_row(o):
    c, ev = o.get('currency'), o.get('evidence_details') or {}
    return {'id': o['id'], 'created': _ts(o.get('created')), 'currency': c, 'amount': minor(o.get('amount'), c), 'status': o.get('status'),
            'reason': o.get('reason'), 'charge': _name(o, 'charge'), 'evidence_due_by': _ts(ev.get('due_by')),
            'is_charge_refundable': o.get('is_charge_refundable')}


def customer_row(o):
    c = o.get('currency')
    return {'id': o['id'], 'created': _ts(o.get('created')), 'name': o.get('name'), 'email': o.get('email'), 'currency': c,
            'balance': minor(o.get('balance'), c), 'delinquent': o.get('delinquent')}


def mrr(sub) -> float:
    """What one subscription brings in a month, in money: each item's price normalised from its interval. A metered or
    tiered price has no fixed unit amount and counts 0 here - its revenue is in the invoices."""
    tot = 0
    for it in (sub.get('items') or {}).get('data') or []:
        p = it.get('price') or {}; rec = p.get('recurring') or {}
        if p.get('unit_amount') is None or rec.get('usage_type') == 'metered': continue
        f = PER_MONTH.get(rec.get('interval'), 0) / max(1, int(rec.get('interval_count') or 1))
        tot += minor(p['unit_amount'], p.get('currency') or sub.get('currency')) * (it.get('quantity') or 1) * f
    return round(tot, 2)


def subscription_row(o):
    its = (o.get('items') or {}).get('data') or []
    return {'id': o['id'], 'created': _ts(o.get('created')), 'status': o.get('status'), 'customer': _name(o, 'customer'),
            'currency': o.get('currency'), 'mrr': mrr(o), 'items': ', '.join(str(((i.get('price') or {}).get('nickname')
                                                                                  or _name(i.get('price') or {}, 'product') or '')) for i in its),
            'current_period_end': _ts(o.get('current_period_end')), 'cancel_at_period_end': o.get('cancel_at_period_end'),
            'canceled_at': _ts(o.get('canceled_at')), 'trial_end': _ts(o.get('trial_end'))}


def invoice_row(o):
    c = o.get('currency')
    return {'id': o['id'], 'number': o.get('number'), 'created': _ts(o.get('created')), 'status': o.get('status'), 'currency': c,
            **_money(o, c, 'total', 'amount_due', 'amount_paid', 'amount_remaining'), 'customer': _name(o, 'customer'),
            'customer_email': o.get('customer_email'), 'due_date': _ts(o.get('due_date')), 'subscription': _name(o, 'subscription')}


# ── the card's test, and the report/tool surface (reports.REGISTRY) ─────────────────────
def account(cfg) -> dict:
    """The account's own record, for its name. A restricted key needs no permission it would not otherwise want for the
    Test to pass, so a refusal here is answered with the balance alone rather than failed."""
    try: a = _call(cfg, 'GET', '/v1/account')
    except StripeError: return {}
    bp = a.get('business_profile') or {}
    return {'id': a.get('id'), 'name': bp.get('name') or (a.get('settings') or {}).get('dashboard', {}).get('display_name') or a.get('email')}


def probe(cfg) -> str:
    """One cheap read for the Test button - the balance - plus the account's name where the key may read it."""
    m, b = mode(cfg), _call(cfg, 'GET', '/v1/balance')
    a = account(cfg)
    avail = ', '.join(f"{r['amount']:,} {r['currency'].upper()}" for r in balance_rows(b) if r['state'] == 'available') or 'nothing'
    kind = 'restricted key' if key_of(cfg).startswith('rk_') else 'full secret key - a restricted read-only key is safer'
    who = f"{a['name']} ({a['id']})" if a.get('name') else a.get('id') or 'the account'
    return f"connected to {who} in {m.upper()} mode with a {kind} · balance read: {avail} available"


def _out(cfg, rows, label, span='', note=''):
    from .reports import rows_out, row_limit
    lim, mine = row_limit(cfg)
    head, body = rows_out(rows, lim, mine=mine)
    return ' · '.join(x for x in (head, label, span, note) if x), body


def _cap(cfg):
    from .reports import row_limit
    return min(MAX_ITEMS, row_limit(cfg)[0] + 1)


def _totals(rows, key='amount') -> str:
    """'1,234.50 USD · 80 EUR' - one total per currency; Stripe never adds two currencies and neither should a headline."""
    by = {}
    for r in rows:
        if r.get(key) is not None: by[r.get('currency') or ''] = by.get(r.get('currency') or '', 0) + r[key]
    return ' · '.join(f'{round(v, 2):,} {c.upper()}' for c, v in sorted(by.items()))


def _list(cfg, path, row, label, default_days=30, total='amount', local_status=False, **extra):
    """Rows of one list endpoint in the window. `status` is a filter Stripe takes on some lists and not others: where it
    does not (local_status), the whole window is read and filtered here, so the cap counts matching rows, not fetched ones."""
    st = str(cfg.get('status') or '').strip().lower()
    p = _params(cfg, default_days, **({} if local_status else {'status': st}), **extra)
    rows = [row(o) for o in items(cfg, path, p, MAX_ITEMS if st and local_status else _cap(cfg))]
    if st and local_status: rows = [r for r in rows if r.get('status') == st]
    t = _totals(rows, total) if total else ''
    return _out(cfg, rows, f"{st + ' ' if st and st != 'all' else ''}{label}", _span(p.get('created[gte]'), p.get('created[lte]')),
                f"{SAID.get(total, total)} {t}" if t else '')


def run_stripe_balance(cfg):
    """{} - the Stripe balance now: available and pending, per currency. Cash on hand at Stripe, before the next payout."""
    return _out(cfg, balance_rows(_call(cfg, 'GET', '/v1/balance')), f'Stripe balance ({mode(cfg)})')


def run_stripe_balance_transactions(cfg):
    """{"days": 30 (or "start"/"end"), "kind": "charge|refund|payout|stripe_fee|adjustment"} - every movement on the
    Stripe balance with amount, fee and net: revenue, fees and payouts reconciled. Read-only."""
    return _list(cfg, '/v1/balance_transactions', bt_row, 'balance transactions', total='net', type=cfg.get('kind'))      # `type` is the report's own key


def run_stripe_charges(cfg):
    """{"days": 30, "status": "succeeded|failed|pending", "customer": "cus_..."} - card and bank charges: sales revenue,
    refunded and disputed flags, failures. Read-only."""
    return _list(cfg, '/v1/charges', charge_row, 'charges', local_status=True, customer=cfg.get('customer'))


def run_stripe_payments(cfg):
    """{"days": 30, "status": "succeeded|requires_payment_method|canceled|processing", "customer": "cus_..."} - payments
    (PaymentIntents): revenue taken, payments that failed or were abandoned. Read-only."""
    return _list(cfg, '/v1/payment_intents', payment_row, 'payments', total='amount_received', local_status=True, customer=cfg.get('customer'))


def run_stripe_payouts(cfg):
    """{"days": 30, "status": "paid|pending|in_transit|failed|canceled"} - payouts from Stripe to the bank: when money
    arrived and how much. Read-only."""
    return _list(cfg, '/v1/payouts', payout_row, 'payouts')


def run_stripe_refunds(cfg):
    """{"days": 30, "charge": "ch_..."} - refunds given back to customers, with reason. Read-only."""
    return _list(cfg, '/v1/refunds', refund_row, 'refunds', charge=cfg.get('charge'))


def run_stripe_disputes(cfg):
    """{"days": 90, "status": "needs_response|under_review|won|lost"} - disputes and chargebacks, with the evidence due
    date. Read-only."""
    return _list(cfg, '/v1/disputes', dispute_row, 'disputes', 90, local_status=True)


def run_stripe_customers(cfg):
    """{"email": "someone@example.com", "days": blank = every customer} - customers with name, email and balance; the count
    of customers, or the new ones in a window. Read-only."""
    return _list(cfg, '/v1/customers', customer_row, 'customers', None, total=None, email=cfg.get('email'))


def run_stripe_subscriptions(cfg):
    """{"status": "active|trialing|past_due|canceled|all", "price": "price_..."} - subscriptions with each one's MRR
    (monthly recurring revenue) and the total MRR per currency; active ones by default. Read-only."""
    return _list({**cfg, 'status': cfg.get('status') or 'active'}, '/v1/subscriptions', subscription_row, 'subscriptions', None,
                 total='mrr', price=cfg.get('price'))


def run_stripe_invoices(cfg):
    """{"days": 30, "status": "draft|open|paid|uncollectible|void", "customer": "cus_..."} - invoices with totals, what is
    paid and what is still owed. Read-only."""
    return _list(cfg, '/v1/invoices', invoice_row, 'invoices', total='total', customer=cfg.get('customer'))
