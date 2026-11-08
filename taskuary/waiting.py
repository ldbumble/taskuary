"""WORK THAT WAITS ON YOU IN SOMEONE ELSE'S SYSTEM (the owner, 2026-11-08: "yes do all of them") - on the inboxes.py road, not beside it.

Shared inboxes (Front, Help Scout, Gorgias), phones (RingCentral, Aircall, Dialpad: missed calls, voicemails, texts), forms you
pick (Typeform, Jotform, SurveyMonkey, Tally, Google Forms) and candidates assigned to you (Lever). The vendors whose own MCP server
does the rest (Xero, BILL, Ramp, Greenhouse, Ashby ...) are catalogue rows on remotemcp.py's road, no code here.
Each source is the same two functions as inboxes.py - a Test that learns who you are and seeds the source row, and an `items`
reader that answers only what points at you - and inboxes.poll files every item, so dedupe, revisions and triage are that road's.

WHO WROTE IT (H2): a customer, a caller, a form respondent, a candidate is a stranger's words - no item here says member=True
unless the vendor's own data says the author is one of the workspace (a Front teammate, a Help Scout user). A system's own notice
(a candidate assigned to you) carries no author and waits for the owner's Trust everyone from ... press.

Read-only, like inboxes.py: nothing is answered, approved or paid from here. Every call goes through inboxes._req, so the tests'
fake HTTP sees all of it.
"""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from loguru import logger

from .inboxes import item, _req, _need, _site, _host, _keep, _me, _utc, _when, _text, _cfg, _seed_source, CAP
from .timewords import plural

NAMES = {'front': 'Front', 'helpscout': 'Help Scout', 'gorgias': 'Gorgias', 'ringcentral': 'RingCentral', 'aircall': 'Aircall', 'dialpad': 'Dialpad',
         'typeform': 'Typeform', 'jotform': 'Jotform', 'surveymonkey': 'SurveyMonkey', 'tally': 'Tally', 'google_forms': 'Google Forms', 'lever': 'Lever'}


def _mint(c, key, url, hint, **kw) -> str:
    "A client-credentials (or JWT-grant) token, kept until a minute before it expires (net.token)."
    from . import net
    def mint():
        j = _req(c, 'post', url, hint, **kw)
        return j['access_token'], j.get('expires_in')
    return net.token((c['Type'], key), mint)


def _bearer(tok, **h): return {'Authorization': f'Bearer {tok}', 'Accept': 'application/json', **h}
def _picked(c) -> list: return [x for x in re.split(r'[\s,]+', str(_cfg(c).get('forms') or '')) if x]
def _qa(pairs) -> str: return '\n'.join(f'{q}: {a}' for q, a in pairs if a not in (None, '', [], {}))
def _email_in(vals): return next((v for v in vals if isinstance(v, str) and re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', v)), None)


def _forms_said(store, c, who, forms: dict) -> str:
    "What a form card's Test says: the forms it watches, or the ones it could watch when none is picked yet."
    _seed_source(store, c, who or NAMES[c['Type']])
    mine = _picked(c)
    if not mine:
        some = ', '.join(f'{t} ({i})' for i, t in list(forms.items())[:8]) or 'none found'
        return f"authenticated as {who} - pick the forms to watch on the card (their ids): {some}"
    return f"authenticated as {who} - new responses to {plural(len(mine), 'form')} flow in on the next sync"


# ── Typeform ─────────────────────────────────────────────────────────────────────────────
TF, TF_HINT = 'https://api.typeform.com', 'check the personal access token (your account, then Personal tokens; scopes forms:read and responses:read)'
def _tf(c, path, **params): return _req(c, 'get', f'{TF}{path}', TF_HINT, params=params, headers=_bearer(c.get('Secret') or ''))


def test_typeform(store, c) -> str:
    _need(c, 'personal access token', 'Typeform: your account, then Personal tokens - Generate a new token')
    me = _tf(c, '/me')
    return _forms_said(store, c, me.get('alias') or me.get('email'), {f['id']: f.get('title') for f in _tf(c, '/forms', page_size=20).get('items') or []})


def _tf_answer(a):
    v = a.get(a.get('type')) if a.get('type') else None
    return v.get('label') if isinstance(v, dict) and 'label' in v else ', '.join(v.get('labels') or []) if isinstance(v, dict) else v


def items_typeform(store, c, since) -> list:
    out = []
    for f in _picked(c):
        d = _tf(c, f'/forms/{quote(f)}')
        q = {x['id']: x.get('title') for x in d.get('fields') or []}
        for r in _tf(c, f'/forms/{quote(f)}/responses', since=_utc(since), page_size=CAP, completed='true').get('items') or []:
            pairs = [(q.get((a.get('field') or {}).get('id'), 'Answer'), _tf_answer(a)) for a in r.get('answers') or []]
            out.append(item(r['response_id'], f"New response to {d.get('title') or f}", 'Typeform response', _qa(pairs), None,
                            _email_in(v for _, v in pairs), None, None, r.get('submitted_at'),
                            f"https://admin.typeform.com/form/{f}/results#responses", d.get('title') or 'Typeform'))
    return out


# ── Jotform ──────────────────────────────────────────────────────────────────────────────
JF_HINT = 'check the API key (your avatar, then API - Create new key, read access)'
def _jf(c, path, **params):
    base = 'https://eu-api.jotform.com' if _cfg(c).get('eu') in (True, 'true', '1', 'yes') else 'https://api.jotform.com'
    return _req(c, 'get', f'{base}{path}', JF_HINT, params={**params, 'apiKey': c.get('Secret') or ''})['content']


def test_jotform(store, c) -> str:
    _need(c, 'API key', 'Jotform: your avatar, then API - Create new key')
    me = _jf(c, '/user')
    return _forms_said(store, c, me.get('name') or me.get('username'), {f['id']: f.get('title') for f in _jf(c, '/user/forms', limit=20) or []})


def items_jotform(store, c, since) -> list:
    import json
    out = []
    # Jotform keeps the account's own clock and no offset: the filter reaches a day back and the poll keeps only what is new
    flt = json.dumps({'created_at:gt': f'{since - timedelta(days=1):%Y-%m-%d %H:%M:%S}'})
    for f in _picked(c):
        for s in _jf(c, f'/form/{quote(f)}/submissions', filter=flt, limit=CAP, orderby='created_at') or []:
            ans = sorted((s.get('answers') or {}).values(), key=lambda a: int(a.get('order') or 0))
            pairs = [(a.get('text') or a.get('name'), a.get('prettyFormat') or a.get('answer')) for a in ans if a.get('answer') not in (None, '')]
            out.append(item(s['id'], 'New Jotform submission', 'Jotform submission', _qa(pairs), None, _email_in(v for _, v in pairs), None, None,
                            None, f"https://www.jotform.com/submission/{s['id']}", f'Jotform form {f}'))
    return out


# ── SurveyMonkey ─────────────────────────────────────────────────────────────────────────
SM, SM_HINT = 'https://api.surveymonkey.com/v3', 'check the access token (developer.surveymonkey.com, then My Apps - your private app - Settings)'
def _sm(c, path, **params): return _req(c, 'get', f'{SM}{path}', SM_HINT, params=params, headers=_bearer(c.get('Secret') or ''))


def test_surveymonkey(store, c) -> str:
    _need(c, 'access token', 'SurveyMonkey: developer.surveymonkey.com, then My Apps - a private app shows its access token')
    me = _sm(c, '/users/me')
    return _forms_said(store, c, me.get('username') or me.get('email'), {s['id']: s.get('title') for s in _sm(c, '/surveys', per_page=20).get('data') or []})


def items_surveymonkey(store, c, since) -> list:
    out = []
    for f in _picked(c):
        for r in _sm(c, f'/surveys/{quote(f)}/responses/bulk', start_modified_at=_utc(since)[:19], per_page=CAP, simple='true', status='completed').get('data') or []:
            pairs = [(q.get('heading') or 'Answer', '; '.join(str(a.get('simple_text') or a.get('text') or '') for a in q.get('answers') or []))
                     for p in r.get('pages') or [] for q in p.get('questions') or []]
            out.append(item(r['id'], 'New SurveyMonkey response', 'SurveyMonkey response', _qa(pairs), None, _email_in(v for _, v in pairs), None, None,
                            r.get('date_created'), r.get('analyze_url') or 'https://www.surveymonkey.com/', f'SurveyMonkey survey {f}'))
    return out


# ── Google Forms (the Google Sheets card's sign-in) ──────────────────────────────────────────
GF = 'https://forms.googleapis.com/v1'
GF_HINT = 'the Google Sheets card\'s refresh token needs the forms.responses.readonly scope (and forms.body.readonly for the questions) - mint it again with them'
def _gf(store, c, path, **params):
    from . import sheets
    return _req(c, 'get', f'{GF}{path}', GF_HINT, params=params, headers=_bearer(sheets._token(sheets.google_sheets_connection(store))))


def test_google_forms(store, c) -> str:
    mine = _picked(c)
    if not mine: raise RuntimeError('name the forms to watch on the card - the id in a form\'s edit address, docs.google.com/forms/d/<id>/edit')
    t = (_gf(store, c, f'/forms/{quote(mine[0])}').get('info') or {}).get('title')
    _seed_source(store, c, 'Google Forms')
    return f"read {t or mine[0]} - new responses to {plural(len(mine), 'form')} flow in on the next sync"


def items_google_forms(store, c, since) -> list:
    out = []
    for f in _picked(c):
        d = _gf(store, c, f'/forms/{quote(f)}')
        q = {(x.get('questionItem') or {}).get('question', {}).get('questionId'): x.get('title') for x in d.get('items') or []}
        for r in _gf(store, c, f'/forms/{quote(f)}/responses', filter=f'timestamp > {_utc(since)}').get('responses') or []:
            pairs = [(q.get(k) or 'Answer', ', '.join(a.get('value', '') for a in (v.get('textAnswers') or {}).get('answers') or []))
                     for k, v in (r.get('answers') or {}).items()]
            out.append(item(r['responseId'], f"New response to {(d.get('info') or {}).get('title') or f}", 'Google Forms response', _qa(pairs), None,
                            r.get('respondentEmail') or _email_in(v for _, v in pairs), None, None, r.get('lastSubmittedTime') or r.get('createTime'),
                            f'https://docs.google.com/forms/d/{f}/edit#responses', (d.get('info') or {}).get('title') or 'Google Forms'))
    return out


# ── Help Scout (conversations assigned to you) ───────────────────────────────────────────────
HS, HS_HINT = 'https://api.helpscout.net/v2', 'check the app id and secret (your profile, then My Apps - Create My App)'
def _hs(c, path, **params):
    cid = str(_cfg(c).get('app_id') or '').strip()
    if not cid: raise RuntimeError('no app id set - Help Scout: your profile, then My Apps')
    tok = _mint(c, cid, f'{HS}/oauth2/token', HS_HINT, data={'grant_type': 'client_credentials', 'client_id': cid, 'client_secret': c.get('Secret') or ''})
    return _req(c, 'get', f'{HS}{path}', HS_HINT, params=params, headers=_bearer(tok))


def test_helpscout(store, c) -> str:
    _need(c, 'app secret', 'Help Scout: your profile, then My Apps - Create My App shows the app id and secret')
    me = _hs(c, '/users/me')
    _keep(store, c, me_id=str(me['id']))
    _seed_source(store, c, 'Help Scout')
    return f"authenticated as {me.get('firstName')} {me.get('lastName')} - active conversations assigned to you flow in on the next sync"


def items_helpscout(store, c, since) -> list:
    out = []
    for v in (_hs(c, '/conversations', assigned_to=_me(c), status='active', modifiedSince=_utc(since), sortField='modifiedAt', sortOrder='desc')
              .get('_embedded') or {}).get('conversations') or []:
        p, by = v.get('primaryCustomer') or {}, v.get('createdBy') or {}
        name = ' '.join(x for x in (p.get('first'), p.get('last')) if x) or p.get('email')
        out.append(item(v['id'], f"#{v.get('number')} {v.get('subject') or ''}".strip(), f"Help Scout conversation - {v.get('status')} · assigned to you",
                        v.get('preview'), name, p.get('email'), p.get('id') and f"c:{p['id']}",
                        by.get('type') == 'user' if by.get('type') else None,                 # a customer is a stranger; one of your users is not
                        v.get('userUpdatedAt') or v.get('createdAt'), f"https://secure.helpscout.net/conversation/{v['id']}", 'Help Scout'))
    return out


# ── RingCentral (voicemails, texts and missed calls to your extension) ──────────────────────
RC, RC_HINT = 'https://platform.ringcentral.com', 'check the app\'s client id and secret and the JWT credential (developers.ringcentral.com, then Credentials)'
def _rc(c, path, raw=False, **params):
    cfg = _cfg(c)
    cid, sec = str(cfg.get('client_id') or '').strip(), str(cfg.get('client_secret') or '').strip()
    if not cid: raise RuntimeError('no client id set - your app on developers.ringcentral.com, JWT auth flow')
    tok = _mint(c, cid, f'{RC}/restapi/oauth/token', RC_HINT, auth=(cid, sec),
                data={'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer', 'assertion': c.get('Secret') or ''})
    return _req(c, 'get', path if path.startswith('http') else f'{RC}/restapi/v1.0{path}', RC_HINT, params=params, headers=_bearer(tok))


def test_ringcentral(store, c) -> str:
    _need(c, 'JWT credential', 'RingCentral developer console: your profile, then Credentials - Create JWT')
    me = _rc(c, '/account/~/extension/~')
    _seed_source(store, c, f"{me.get('name')} (ext {me.get('extensionNumber')})")
    return f"authenticated as {me.get('name')}, extension {me.get('extensionNumber')} - voicemails, texts and missed calls flow in on the next sync"


def _rc_said(c, m) -> str:
    "A voicemail's words where RingCentral transcribed it, else where to hear it."
    t = next((a for a in m.get('attachments') or [] if a.get('type') == 'AudioTranscription'), None)
    if t:
        try: return str(_rc(c, t['uri']) or '')
        except Exception as e: logger.debug(f'ringcentral: transcription unread ({e})')
    return 'A voicemail - play it in RingCentral.'


def items_ringcentral(store, c, since) -> list:
    out, frm = [], _utc(since)
    for m in _rc(c, '/account/~/extension/~/message-store', messageType=['VoiceMail', 'SMS'], direction='Inbound', dateFrom=frm, perPage=CAP).get('records') or []:
        f, vm = m.get('from') or {}, m.get('type') == 'VoiceMail'
        who = f.get('name') or f.get('phoneNumber') or f.get('extensionNumber')
        out.append(item(m['id'], f"{'Voicemail' if vm else 'Text'} from {who}", f"RingCentral {'voicemail' if vm else 'text message'} to you",
                        _rc_said(c, m) if vm else m.get('subject'), who, None, f.get('phoneNumber') and f"tel:{f['phoneNumber']}",
                        None, m.get('creationTime'), 'https://app.ringcentral.com/', 'RingCentral',
                        conv=None if vm else (m.get('conversation') or {}).get('id') and f"sms:{m['conversation']['id']}"))
    for r in _rc(c, '/account/~/extension/~/call-log', type='Voice', direction='Inbound', dateFrom=frm, perPage=CAP).get('records') or []:
        if r.get('result') != 'Missed': continue                               # the call log takes no result filter: a voicemail is its own record above
        f = r.get('from') or {}
        who = f.get('name') or f.get('phoneNumber')
        out.append(item(r['id'], f'Missed call from {who}', 'RingCentral missed call', f"Call {who} back: {f.get('phoneNumber') or 'number withheld'}",
                        who, None, f.get('phoneNumber') and f"tel:{f['phoneNumber']}", None, r.get('startTime'), 'https://app.ringcentral.com/', 'RingCentral'))
    return out


# ── Front (conversations assigned to you) ────────────────────────────────────────────────────
FR, FR_HINT = 'https://api2.frontapp.com', 'check the API token (Front: your company settings, then Developers - API tokens; scope Shared resources, read)'
def _fr(c, path, **params): return _req(c, 'get', path if path.startswith('http') else f'{FR}{path}', FR_HINT, params=params, headers=_bearer(c.get('Secret') or ''))


def test_front(store, c) -> str:
    _need(c, 'API token', 'Front: your company settings, then Developers - API tokens - Create API token')
    em = str(_cfg(c).get('email') or '').strip()
    if not em: raise RuntimeError('no email set - the one you sign in to Front with')
    me = _fr(c, f"/teammates/alt:email:{quote(em, safe='@.')}")
    _keep(store, c, me_id=me['id'])
    _seed_source(store, c, 'Front')
    return f"found {me.get('first_name')} {me.get('last_name')} - open conversations assigned to you flow in on the next sync"


def items_front(store, c, since) -> list:
    out = []
    for v in _fr(c, f'/teammates/{quote(_me(c))}/conversations', **{'q[statuses][]': 'assigned', 'limit': CAP}).get('_results') or []:
        m = next(iter(_fr(c, f"/conversations/{v['id']}/messages", limit=1).get('_results') or []), {})      # newest first
        a, frm = m.get('author') or {}, next((r for r in m.get('recipients') or [] if r.get('role') == 'from'), {})
        who = ' '.join(x for x in (a.get('first_name'), a.get('last_name')) if x) or frm.get('name') or frm.get('handle')
        out.append(item(v['id'], v.get('subject') or '(no subject)', f"Front conversation - assigned to you{' · ' + ', '.join(t.get('name') for t in v.get('tags') or []) if v.get('tags') else ''}",
                        m.get('text') or m.get('blurb') or _text(m.get('body')), who, None if a else frm.get('handle'),
                        a.get('id') and f"tm:{a['id']}" or frm.get('handle') and f"h:{frm['handle']}",
                        bool(a) if (a or frm) else None,                                   # a teammate wrote it, or a contact did
                        m.get('created_at') or v.get('created_at'), f"https://app.frontapp.com/open/{v['id']}", 'Front'))
    return out


# ── Aircall (missed calls and voicemails on your lines) ──────────────────────────────────────
AC, AC_HINT = 'https://api.aircall.io/v1', 'check the API ID and token (Aircall dashboard: Integrations & API, then API Keys)'
def _ac(c, path, **params): return _req(c, 'get', f'{AC}{path}', AC_HINT, params=params, auth=(str(_cfg(c).get('api_id') or ''), c.get('Secret') or ''))


def test_aircall(store, c) -> str:
    _need(c, 'API token', 'Aircall dashboard: Integrations & API, then API Keys - Generate an API key (shows an API ID and token)')
    em = str(_cfg(c).get('email') or '').strip().lower()
    if not em: raise RuntimeError('no email set - the one you sign in to Aircall with')
    _ac(c, '/ping')
    u = next((u for u in _ac(c, '/users', per_page=50).get('users') or [] if str(u.get('email') or '').lower() == em), None)
    if not u: raise RuntimeError(f'Aircall has no user {em} on this account')
    nums = [n['id'] for n in (_ac(c, f"/users/{u['id']}").get('user') or {}).get('numbers') or []]
    _keep(store, c, me_id=str(u['id']), number_ids=nums)
    _seed_source(store, c, f"{u.get('name')} on Aircall")
    return f"authenticated - {u.get('name')}, {plural(len(nums), 'line')}: missed calls and voicemails flow in on the next sync"


def items_aircall(store, c, since) -> list:
    cfg, out = _cfg(c), []
    me, lines = str(_me(c)), set(cfg.get('number_ids') or [])
    for v in _ac(c, '/calls', **{'from': int(since.timestamp()), 'order': 'desc', 'per_page': 50, 'fetch_contact': 'true'}).get('calls') or []:
        if v.get('direction') != 'inbound' or not (v.get('missed_call_reason') or v.get('voicemail')): continue
        if str((v.get('user') or {}).get('id')) != me and (v.get('number') or {}).get('id') not in lines: continue
        k = v.get('contact') or {}
        who = ' '.join(x for x in (k.get('first_name'), k.get('last_name')) if x) or v.get('raw_digits')
        vm = bool(v.get('voicemail'))
        said = ''
        if vm:
            try: said = '\n'.join(str(u.get('text') or '') for u in ((_ac(c, f"/calls/{v['id']}/transcription").get('transcription') or {}).get('content') or {}).get('utterances') or [])
            except Exception as e: logger.debug(f'aircall: transcription unread ({e})')
        out.append(item(v['id'], f"{'Voicemail' if vm else 'Missed call'} from {who}",
                        f"Aircall {'voicemail' if vm else 'missed call'} on {(v.get('number') or {}).get('name') or 'your line'}",
                        said or (f"Voicemail: {v['voicemail']}" if vm else f"Call back {v.get('raw_digits')} - {str(v.get('missed_call_reason')).replace('_', ' ')}"),
                        who, None, v.get('raw_digits') and f"tel:{v['raw_digits']}", None, v.get('started_at'),
                        'https://dashboard.aircall.io/conversations', 'Aircall'))
    return out


# ── Gorgias (tickets assigned to you) ────────────────────────────────────────────────────────
GG_HINT = 'check the email and API key (Gorgias: your settings, then REST API - the username, password and base address it shows)'
def _gg_base(c): return _site(c, 'domain', '{}.gorgias.com', 'no Gorgias domain set - the "yourstore" in yourstore.gorgias.com')
def _gg(c, path, **params): return _req(c, 'get', f'{_gg_base(c)}/api{path}', GG_HINT, params=params, auth=(str(_cfg(c).get('email') or ''), c.get('Secret') or ''))


def test_gorgias(store, c) -> str:
    _need(c, 'API key', 'Gorgias: your settings, then REST API - Create API key')
    if not _cfg(c).get('email'): raise RuntimeError('no email set - the one your Gorgias key belongs to')
    a = _gg(c, '/account')
    _seed_source(store, c, a.get('domain') or _host(_gg_base(c)))
    return f"connected to {a.get('domain') or 'your helpdesk'} - open tickets assigned to you flow in on the next sync"


def items_gorgias(store, c, since) -> list:
    me, base, out = str(_cfg(c).get('email') or '').lower(), _gg_base(c), []
    # the ticket list takes no assignee: it is read newest first and the poll keeps yours (and only what changed - inboxes.poll)
    for t in _gg(c, '/tickets', order_by='updated_datetime:desc', limit=100).get('data') or []:
        u = t.get('assignee_user') or {}
        if str(u.get('email') or '').lower() != me or t.get('status') == 'closed': continue
        k = t.get('customer') or {}
        out.append(item(t['id'], t.get('subject') or f"Ticket {t['id']}", f"Gorgias ticket - {t.get('status')} · {t.get('channel') or 'email'} · assigned to you",
                        t.get('excerpt'), k.get('name') or k.get('email'), k.get('email'), k.get('id') and f"cu:{k['id']}", False,   # a shopper is a stranger
                        t.get('updated_datetime'), f"{base}/app/ticket/{t['id']}", _host(base)))
    return out


# ── Dialpad (missed calls and voicemails, with Dialpad's transcript) ──────────────────────────
DP, DP_HINT = 'https://dialpad.com/api/v2', 'check the API key (Dialpad admin: My Company, then Authentication - API keys)'
def _dp(c, path, **params): return _req(c, 'get', f'{DP}{path}', DP_HINT, params=params, headers=_bearer(c.get('Secret') or ''))


def test_dialpad(store, c) -> str:
    _need(c, 'API key', 'Dialpad admin: My Company, then Authentication - API keys - Add a key')
    co, em = _dp(c, '/company'), str(_cfg(c).get('email') or '').strip()
    if not em: raise RuntimeError('no email set - the one you sign in to Dialpad with')
    u = next(iter(_dp(c, '/users', email=em).get('items') or []), None)
    if not u: raise RuntimeError(f'Dialpad has no user {em} in {co.get("name") or "this company"}')
    _keep(store, c, me_id=str(u['id']))
    _seed_source(store, c, co.get('name') or 'Dialpad')
    return f"connected to {co.get('name')} as {em} - missed calls and voicemails flow in on the next sync"


def items_dialpad(store, c, since) -> list:
    out = []
    for v in _dp(c, '/call', started_after=int(since.timestamp() * 1000), target_id=_me(c), target_type='user', limit=CAP).get('items') or []:
        vm = bool(v.get('voicemail_link'))
        if v.get('direction') != 'inbound' or not (vm or v.get('state') == 'missed'): continue
        k = v.get('contact') or {}
        who = k.get('name') or k.get('phone') or v.get('external_number')
        out.append(item(v.get('call_id') or v.get('id'), f"{'Voicemail' if vm else 'Missed call'} from {who}", f"Dialpad {'voicemail' if vm else 'missed call'}",
                        v.get('transcription_text') or (f"Voicemail: {v['voicemail_link']}" if vm else f'Call back {who}'), who, k.get('email'),
                        (k.get('phone') or v.get('external_number')) and f"tel:{k.get('phone') or v.get('external_number')}", None,
                        v.get('date_started'), 'https://dialpad.com/app', 'Dialpad'))
    return out


# ── Tally (new submissions on the forms you pick) ─────────────────────────────────────────────
TL, TL_HINT = 'https://api.tally.so', 'check the API key (Tally: your settings, then API keys)'
def _tl(c, path, **params): return _req(c, 'get', f'{TL}{path}', TL_HINT, params=params, headers=_bearer(c.get('Secret') or ''))


def test_tally(store, c) -> str:
    _need(c, 'API key', 'Tally: your settings, then API keys - Create API key')
    mine = _picked(c)
    if mine: _tl(c, f'/forms/{quote(mine[0])}/submissions', limit=1)
    j = {} if mine else _tl(c, '/forms')
    rows = j if isinstance(j, list) else j.get('items') or j.get('forms') or []
    return _forms_said(store, c, 'your Tally key', {f.get('id'): f.get('name') or f.get('title') for f in rows})


def items_tally(store, c, since) -> list:
    out = []
    for f in _picked(c):
        j = _tl(c, f'/forms/{quote(f)}/submissions', startDate=_utc(since), limit=CAP)
        q = {x['id']: x.get('title') for x in j.get('questions') or []}
        for s in j.get('submissions') or []:
            if s.get('isCompleted') is False: continue
            pairs = [(q.get(r.get('questionId')) or 'Answer', r.get('formattedAnswer') or r.get('answer')) for r in s.get('responses') or []]
            out.append(item(s['id'], 'New Tally submission', 'Tally submission', _qa(pairs), None, _email_in(v for _, v in pairs), None, None,
                            s.get('submittedAt'), f'https://tally.so/forms/{f}/submissions', f'Tally form {f}'))
    return out


# ── Lever (candidates you own) ────────────────────────────────────────────────────────────────
LV, LV_HINT = 'https://api.lever.co/v1', 'check the API key (Lever: its settings, then Integrations and API - API credentials; read Opportunities and Users)'
def _lv(c, path, **params): return _req(c, 'get', f'{LV}{path}', LV_HINT, params=params, auth=(c.get('Secret') or '', ''))


def test_lever(store, c) -> str:
    _need(c, 'API key', 'Lever: its settings, then Integrations and API - API credentials - Generate new key')
    em = str(_cfg(c).get('email') or '').strip().lower()
    if not em: raise RuntimeError('no email set - the one you sign in to Lever with')
    u = next((u for u in _lv(c, '/users', email=em, limit=100).get('data') or [] if str(u.get('email') or '').lower() == em), None)
    if not u: raise RuntimeError(f'Lever has no user {em}')
    _keep(store, c, me_id=u['id'])
    _seed_source(store, c, 'Lever')
    return f"authenticated - {u.get('name')}: candidates you own flow in when they change"


def items_lever(store, c, since) -> list:
    me, out = _me(c), []
    # no owner filter on the list: read what changed since and keep the ones you own
    for o in _lv(c, '/opportunities', updated_at_start=int(since.timestamp() * 1000), limit=100).get('data') or []:
        own = o.get('owner')
        if (own.get('id') if isinstance(own, dict) else own) != me or o.get('archived'): continue
        out.append(item(o['id'], f"{o.get('name') or 'A candidate'} - {o.get('headline') or 'candidate'}", 'Lever candidate you own - changed',
                        f"Stage: {(o.get('stage') or {}).get('text') if isinstance(o.get('stage'), dict) else o.get('stage')}", None, None, None, None,
                        o.get('updatedAt') or o.get('lastInteractionAt'), (o.get('urls') or {}).get('show') or 'https://hire.lever.co/', 'Lever'))
    return out


TYPES = tuple(NAMES)
TESTS = {t: globals()[f'test_{t}'] for t in TYPES}
ITEMS = {t: globals()[f'items_{t}'] for t in TYPES}
