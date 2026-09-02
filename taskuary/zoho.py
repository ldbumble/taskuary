"""Zoho Invoice OAuth and the small, guarded surface used by monthly invoice workflows.

Creating an invoice always uses ``send=false``.  Sending is a separate call made only after
the associated Taskuary Review is approved.  ``reference_number`` is the upstream half of
the idempotency key, so retrying after a timeout reuses the draft instead of billing twice.
"""
import json, time
from datetime import date
from urllib.parse import urlencode

import requests

TIMEOUT = 30
SCOPES = 'ZohoInvoice.invoices.READ,ZohoInvoice.invoices.CREATE,ZohoInvoice.contacts.READ,ZohoInvoice.settings.READ'
_TOKENS = {}


class ZohoError(RuntimeError): pass


def connection(store, connector_id=None) -> dict:
    from .reports import _card, _connector
    cfg = _card(store, 'zoho_invoice', 'refresh_token', connector_id)
    c = _connector(store, 'zoho_invoice', connector_id)
    return {**cfg, '_store': store, '_cid': (c or {}).get('ConnectorId')}


def redirect_uri(server_cfg: dict) -> str:
    return f"http://localhost:{server_cfg.get('port') or 7787}/api/zoho/callback"


def accounts_url(cfg): return str(cfg.get('accounts_url') or 'https://accounts.zoho.com').rstrip('/')


def authorize_url(cfg: dict, redirect: str, state: str) -> str:
    if not cfg.get('client_id'):
        raise ZohoError('add the Client ID and Client Secret from api-console.zoho.com first')
    return accounts_url(cfg) + '/oauth/v2/auth?' + urlencode({
        'scope': SCOPES, 'client_id': cfg['client_id'], 'response_type': 'code',
        'access_type': 'offline', 'prompt': 'consent', 'redirect_uri': redirect, 'state': state})


def _save(cfg, refresh=None, **values):
    store, cid = cfg.get('_store'), cfg.get('_cid')
    if not (store and cid): return
    row = store.get_connector(cid) or {}
    conf = json.loads(row.get('ConfigJson') or '{}'); conf.update({k: v for k, v in values.items() if v})
    body = {'ConnectorId': cid, 'ConfigJson': json.dumps(conf)}
    if refresh: body['Secret'] = refresh; cfg['refresh_token'] = refresh
    store.save_connector(body, 'zoho')
    cfg.update(conf)


def exchange_code(cfg: dict, code: str, redirect: str) -> dict:
    r = requests.post(accounts_url(cfg) + '/oauth/v2/token', timeout=TIMEOUT, data={
        'grant_type': 'authorization_code', 'client_id': cfg.get('client_id'),
        'client_secret': cfg.get('client_secret'), 'redirect_uri': redirect, 'code': code})
    if r.status_code != 200: raise ZohoError(f'Zoho refused the code ({r.status_code}): {r.text[:240]}')
    j = r.json()
    if not j.get('refresh_token'): raise ZohoError('Zoho did not return a refresh token; reconnect with consent enabled')
    api_domain = j.get('api_domain') or cfg.get('api_domain') or 'https://www.zohoapis.com'
    _save(cfg, j['refresh_token'], api_domain=api_domain)
    _TOKENS[cfg.get('_cid') or id(cfg)] = (j['access_token'], time.time() + int(j.get('expires_in') or 3600))
    return j


def token(cfg: dict) -> str:
    if not (cfg.get('client_id') and cfg.get('client_secret')): raise ZohoError('the Zoho card needs its Client ID and Client Secret')
    if not cfg.get('refresh_token'): raise ZohoError('Zoho Invoice is not connected yet; press Connect on its card')
    key = cfg.get('_cid') or id(cfg); hit = _TOKENS.get(key)
    if hit and hit[1] > time.time() + 60: return hit[0]
    r = requests.post(accounts_url(cfg) + '/oauth/v2/token', timeout=TIMEOUT, data={
        'grant_type': 'refresh_token', 'client_id': cfg['client_id'],
        'client_secret': cfg['client_secret'], 'refresh_token': cfg['refresh_token']})
    if r.status_code != 200: raise ZohoError(f'Zoho refused the refresh token ({r.status_code}): {r.text[:180]}')
    j = r.json(); api_domain = j.get('api_domain') or cfg.get('api_domain') or 'https://www.zohoapis.com'
    if api_domain != cfg.get('api_domain'): _save(cfg, api_domain=api_domain)
    _TOKENS[key] = (j['access_token'], time.time() + int(j.get('expires_in') or 3600))
    return j['access_token']


def _call(cfg, method, path, *, organization=True, **kw):
    headers = {'Authorization': f'Zoho-oauthtoken {token(cfg)}', 'Accept': 'application/json'}
    if organization:
        if not cfg.get('organization_id'): raise ZohoError('choose a Zoho Invoice organization on the connector card')
        headers['X-com-zoho-invoice-organizationid'] = str(cfg['organization_id'])
    r = requests.request(method, f"{str(cfg.get('api_domain') or 'https://www.zohoapis.com').rstrip('/')}/invoice/v3/{path.lstrip('/')}",
                         timeout=TIMEOUT, headers=headers, **kw)
    if r.status_code == 401: _TOKENS.pop(cfg.get('_cid') or id(cfg), None)
    if r.status_code >= 300:
        try: msg = r.json().get('message') or r.text[:300]
        except Exception: msg = r.text[:300]
        raise ZohoError(f'Zoho Invoice {r.status_code}: {msg}')
    return r.json()


def organizations(cfg):
    return _call(cfg, 'GET', 'organizations', organization=False).get('organizations') or []


def customers(cfg):
    rows = _call(cfg, 'GET', 'contacts', params={'contact_type': 'customer', 'status': 'active', 'per_page': 200}).get('contacts') or []
    def email_of(x):
        people = x.get('contact_persons') or []
        primary = next((p for p in people if p.get('is_primary_contact')), None) or (people[0] if people else {})
        return x.get('email') or primary.get('email') or ''
    return [{'customer_id': str(x.get('contact_id') or ''),
             'customer_name': x.get('contact_name') or x.get('company_name') or 'Unnamed customer',
             'recipient': email_of(x), 'currency': x.get('currency_code') or 'USD'} for x in rows]


def invoices(cfg, **params):
    return _call(cfg, 'GET', 'invoices', params={'per_page': 200, **params}).get('invoices') or []


def invoice(cfg, invoice_id): return _call(cfg, 'GET', f'invoices/{invoice_id}').get('invoice') or {}


def latest_invoice(cfg, customer_id, before_period):
    cutoff = f'{before_period}-01'
    rows = [x for x in invoices(cfg, customer_id=customer_id, sort_column='date')
            if str(x.get('date') or '') < cutoff and str(x.get('status') or '').lower() not in ('void', 'draft')]
    rows.sort(key=lambda x: (str(x.get('date') or ''), str(x.get('created_time') or '')), reverse=True)
    return rows[0] if rows else None


def by_reference(cfg, reference):
    return next((x for x in invoices(cfg, reference_number=reference)
                 if str(x.get('reference_number') or '') == str(reference)), None)


def _money(value):
    try: amount = round(float(str(value).replace(',', '').replace('$', '')), 2)
    except (TypeError, ValueError): raise ZohoError(f'amount {value!r} is not a number')
    if amount <= 0: raise ZohoError('amount must be greater than zero')
    return amount


def create_draft_from(cfg, template_id, amount, reference, period):
    existing = by_reference(cfg, reference)
    if existing:
        status = str(existing.get('status') or '').lower()
        if status != 'draft': raise ZohoError(f'{reference} already exists in Zoho with status {status}; no duplicate was created')
        return {**existing, 'existing': True}
    old = invoice(cfg, template_id); lines = old.get('line_items') or []
    if not lines: raise ZohoError('the prior invoice has no line items to duplicate')
    wanted, previous = _money(amount), round(float(old.get('total') or 0), 2)
    if len(lines) > 1 and abs(wanted - previous) > .009:
        raise ZohoError('the prior invoice has multiple line items; edit the draft in Zoho or keep the same total so Taskuary does not guess how to split it')
    clean = []
    for line in lines:
        keep = {k: line[k] for k in ('item_id','name','description','quantity','rate','unit','tax_id','discount') if line.get(k) not in (None, '')}
        clean.append(keep)
    if len(clean) == 1:
        qty = float(clean[0].get('quantity') or 1); clean[0]['rate'] = round(wanted / qty, 6)
    body = {'customer_id': old.get('customer_id'), 'date': str(date.today()),
            'reference_number': reference, 'line_items': clean}
    for k in ('payment_terms','payment_terms_label','notes','terms','template_id','salesperson_id','tax_id'):
        if old.get(k) not in (None, ''): body[k] = old[k]
    out = _call(cfg, 'POST', 'invoices', params={'send': 'false'}, json=body).get('invoice') or {}
    return out


def email_content(cfg, invoice_id):
    j = _call(cfg, 'GET', f'invoices/{invoice_id}/email')
    return {'to': j.get('to_mail_ids') or [], 'subject': j.get('subject') or '',
            'body': j.get('body') or j.get('body_text') or ''}


def send_invoice(cfg, invoice_id, to, subject, body):
    recipients = to if isinstance(to, list) else [x.strip() for x in str(to or '').split(',') if x.strip()]
    if not recipients: raise ZohoError('this invoice has no recipient')
    j = _call(cfg, 'POST', f'invoices/{invoice_id}/email', json={
        'to_mail_ids': recipients, 'cc_mail_ids': [], 'subject': subject, 'body': body})
    return {'channel': 'zoho_invoice', 'to': recipients, 'invoice_id': invoice_id,
            'message': j.get('message') or 'sent'}


def probe(cfg):
    orgs = organizations(cfg)
    if not cfg.get('organization_id') and orgs:
        first = orgs[0]; _save(cfg, organization_id=str(first.get('organization_id')), organization_name=first.get('name'))
    n = len(customers(cfg)) if (cfg.get('organization_id') or orgs) else 0
    org = cfg.get('organization_name') or next((o.get('name') for o in orgs if str(o.get('organization_id')) == str(cfg.get('organization_id'))), '')
    return f'connected to {org or "Zoho Invoice"} - read {n} active customers'
