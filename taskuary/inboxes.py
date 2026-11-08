"""More places work comes in: helpdesks (Zendesk, Freshdesk, Intercom, ServiceNow) and project tools (Shortcut, Wrike,
Smartsheet, Airtable, GitHub Projects, Bitbucket, Microsoft Planner) - the same deal as pm.py and devtools.py, on ONE road.

Each source is two small functions: a Test (who this token is, remembered on the card so the poller never guesses, plus the
source row the poller walks) and an `items` reader that answers only the work POINTED AT YOU - assigned, asked of you as a
reviewer, new in your group - as plain dicts. `poll` files every one through ingest_tracker, so an item that changes is a
revision of the same conversation, never a second task.

WHO WROTE IT (senders._item_known, H2): every item says its author and whether the VENDOR'S OWN DATA calls them one of the
workspace - a Zendesk agent, an Intercom teammate, a member of the Bitbucket workspace. A customer's ticket, a portal caller,
an outside collaborator is a stranger's words; a source that cannot say (Airtable) carries no author, and its items wait for
the owner's Trust everyone from ... press. Membership lookups are cached per process, like devtools.gitlab_member.

The same road carries the people who write from OUTSIDE (Zulip, Signal, Twilio texts, Discourse, Reddit, YouTube) and the business
systems where something waits on you (Calendly bookings, ShipStation and Shopify orders, Square and PayPal disputes) - see below.

And the ones that sign in by OAuth (oauth.py - their Secret is the tokens Sign in left, spent through oauth.access): Webex and Zoom Team
Chat (direct messages, @mentions), Threads (replies, mentions - always strangers), HubSpot and Salesforce (tickets, cases and tasks
assigned to you), DocuSign (envelopes waiting on your signature), Basecamp (assigned to-dos, Pings, @mentions). Mailgun's stored mail is
polled; LINE and SendGrid Inbound Parse only push (pushin.py), and their items are the queue the webhook filled.

Read-only: nothing is posted back to any of these (trackers.py writes Jira, Monday and Linear only).
"""
import json, re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
import requests
from loguru import logger

from .pm import CAP, _cfg, _seed_source, _stamp, author_meta
from .devtools import _new
from .timewords import plural

NAMES = {'zendesk': 'Zendesk', 'freshdesk': 'Freshdesk', 'intercom': 'Intercom', 'servicenow': 'ServiceNow',
         'shortcut': 'Shortcut', 'wrike': 'Wrike', 'smartsheet': 'Smartsheet', 'airtable': 'Airtable',
         'github_projects': 'GitHub Projects', 'bitbucket': 'Bitbucket', 'ms_planner': 'Microsoft Planner',
         'zulip': 'Zulip', 'signal': 'Signal', 'twilio': 'Twilio', 'discourse': 'Discourse', 'reddit': 'Reddit', 'youtube': 'YouTube',
         'calendly': 'Calendly', 'shipstation': 'ShipStation', 'shopify': 'Shopify', 'square': 'Square', 'paypal': 'PayPal',
         'webex': 'Webex', 'zoom_chat': 'Zoom Team Chat', 'threads': 'Threads', 'hubspot': 'HubSpot', 'salesforce': 'Salesforce',
         'docusign': 'DocuSign', 'basecamp_todos': 'Basecamp to-dos', 'mailgun': 'Mailgun', 'line': 'LINE', 'sendgrid': 'SendGrid Inbound Parse',
         'woocommerce': 'WooCommerce', 'bigcommerce': 'BigCommerce'}
_MEMO = {}       # (type, scope, who) -> membership, read once per process


def _req(c, method, url, hint, ok404=False, **kw):
    who = NAMES[c['Type']]
    r = requests.request(method, url, timeout=30, **kw)
    if r.status_code in (401, 403): raise RuntimeError(f'{who} said {r.status_code} - {hint}')
    if r.status_code == 429: raise RuntimeError(f'{who} rate-limited the poll - it will catch up next sync')
    if ok404 and r.status_code == 404: return None
    r.raise_for_status()
    return r.json()


def _need(c, what, where):
    if not c.get('Secret'): raise RuntimeError(f'no {what} saved - {where}')


def _site(c, key, fmt, hint) -> str:
    "'acme' -> https://acme.zendesk.com; a whole host or URL is kept as typed."
    v = str(_cfg(c).get(key) or '').strip().rstrip('/')
    if not v: raise RuntimeError(hint)
    v = v if '.' in v or v.startswith('http') else fmt.format(v)
    return v if v.startswith('http') else f'https://{v}'


def _host(url: str) -> str: return url.split('//', 1)[-1]
def _keep(store, c, **kv): store.merge_connector_config(c['ConnectorId'], kv)
def _me(c, key='me_id'):
    v = _cfg(c).get(key)
    if not v: raise RuntimeError(f'who you are on {NAMES[c["Type"]]} is not known yet - run Test on the card once')
    return v
def _utc(since) -> str: return since.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _when(v) -> str:
    "A vendor time - ISO, ServiceNow's UTC 'YYYY-MM-DD HH:MM:SS', or unix seconds/ms - as a local wall-clock stamp."
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
        v = int(v); return datetime.fromtimestamp(v / 1000 if v > 1e11 else v).strftime('%Y-%m-%d %H:%M:%S')
    v = str(v or '')
    return _stamp(v + 'Z' if re.fullmatch(r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d', v) else v)


def _text(html) -> str:
    from .channels import _clean
    return _clean(html) if '<' in str(html or '') else str(html or '')


def _member(key, ask):
    "Membership as the vendor says it, once per (source, scope, person); None when it cannot be read - and None is a stranger."
    if key[-1] in (None, ''): return None
    if key not in _MEMO:
        try: _MEMO[key] = ask()
        except Exception as e: logger.debug(f'{key[0]}: membership unread ({e})'); return None
        if _MEMO[key] is None: return _MEMO.pop(key)
    return _MEMO[key]


def item(id, subject, head, body='', who=None, email=None, uid=None, member=None, at=None, link=None, place=None, conv=None, drained=False) -> dict:
    """One piece of work as every source hands it over. `conv`: the conversation it continues (a chat's room, a texter) when that is not
    the item itself; `drained`: the source handed it over once and keeps no copy (signal-cli's queue), so no time floor may drop it."""
    return dict(id=id, subject=subject, head=head, body=body, who=who, email=email, uid=uid, member=member, at=at, link=link, place=place,
                conv=conv, drained=drained)


# ── Zendesk ──────────────────────────────────────────────────────────────────────────────
ZD_HINT = 'check the agent email and API token (Admin Center → Apps and integrations → APIs → Zendesk API)'
def _zd_base(c): return _site(c, 'subdomain', '{}.zendesk.com', 'no Zendesk subdomain set - the "yourco" in yourco.zendesk.com')
def _zd(c, path, **params):
    return _req(c, 'get', f'{_zd_base(c)}/api/v2{path}', ZD_HINT, params=params,
                auth=(f"{_cfg(c).get('email') or ''}/token", c.get('Secret') or ''))


def test_zendesk(store, c) -> str:
    _need(c, 'API token', 'Zendesk Admin Center → Apps and integrations → APIs → Zendesk API → Add API token')
    u = _zd(c, '/users/me.json').get('user') or {}
    # wrong credentials are not a 401 here: Zendesk answers as the anonymous user, id null
    if not u.get('id') or u.get('role') == 'end-user':
        raise RuntimeError(f'Zendesk did not sign you in as an agent - {ZD_HINT}')
    gids = [g['group_id'] for g in _zd(c, f"/users/{u['id']}/group_memberships.json").get('group_memberships') or []][:5]
    _keep(store, c, me_id=str(u['id']), group_ids=gids)
    _seed_source(store, c, _host(_zd_base(c)))
    return (f"authenticated as {u.get('name')} ({u.get('role')}) - tickets assigned to you"
            f"{' and new ones in your ' + plural(len(gids), 'group') if gids else ''} flow in on the next sync")


def items_zendesk(store, c, since) -> list:
    cfg, base = _cfg(c), _zd_base(c)
    j = _zd(c, f"/users/{_me(c)}/tickets/assigned.json", sort_by='updated_at', sort_order='desc', per_page=CAP, include='users')
    rows, users = {t['id']: (t, 'assigned to you') for t in j.get('tickets') or []}, {u['id']: u for u in j.get('users') or []}
    for g in cfg.get('group_ids') or []:
        s = _zd(c, '/search.json', query=f'type:ticket status:new assignee:none group:{int(g)} updated>{_utc(since)}',
                sort_by='updated_at', sort_order='desc', per_page=CAP, include='tickets(users)')
        rows |= {t['id']: (t, 'new in your group') for t in s.get('results') or [] if t['id'] not in rows}
        users |= {u['id']: u for u in s.get('users') or []}
    out = []
    for t, why in rows.values():
        if t.get('status') in ('solved', 'closed'): continue
        u = users.get(t.get('requester_id')) or {}
        out.append(item(t['id'], f"#{t['id']} {t.get('subject') or ''}".strip(),
                        f"Zendesk ticket - {t.get('status')} · priority {t.get('priority') or 'none'} · {why}", t.get('description'),
                        u.get('name'), u.get('email'), t.get('requester_id'),
                        (u['role'] in ('agent', 'admin')) if u.get('role') else None,     # an end-user is a customer: a stranger
                        t.get('updated_at'), f"{base}/agent/tickets/{t['id']}", _host(base)))
    return out


# ── Freshdesk ────────────────────────────────────────────────────────────────────────────
FD_HINT = 'check the API key (your avatar → Profile settings → View API key)'
FD_STATUS, FD_PRIORITY = {2: 'open', 3: 'pending', 4: 'resolved', 5: 'closed'}, {1: 'low', 2: 'medium', 3: 'high', 4: 'urgent'}
def _fd_base(c): return _site(c, 'domain', '{}.freshdesk.com', 'no Freshdesk domain set - the "yourco" in yourco.freshdesk.com')
def _fd(c, path, **params): return _req(c, 'get', f'{_fd_base(c)}/api/v2{path}', FD_HINT, params=params, auth=(c.get('Secret') or '', 'X'))


def test_freshdesk(store, c) -> str:
    _need(c, 'API key', 'Freshdesk: your avatar → Profile settings → View API key')
    a = _fd(c, '/agents/me')
    _keep(store, c, me_id=str(a['id']), group_ids=[int(g) for g in a.get('group_ids') or []][:20])
    _seed_source(store, c, _host(_fd_base(c)))
    return f"authenticated as {(a.get('contact') or {}).get('name') or a['id']} - tickets assigned to you, and new ones in your groups, flow in on the next sync"


def items_freshdesk(store, c, since) -> list:
    cfg, base, me = _cfg(c), _fd_base(c), int(_me(c))
    groups = set(cfg.get('group_ids') or [])
    ts = _fd(c, '/tickets', updated_since=_utc(since), order_by='updated_at', order_type='asc', per_page=100, include='requester')
    # a requester is a contact; only the helpdesk's own agents are of the workspace (read once a poll, None when it cannot be read)
    try: agents = {a['id'] for a in _fd(c, '/agents', per_page=100)}
    except Exception as e: agents = None; logger.debug(f'freshdesk: agents unread ({e})')
    out = []
    for t in ts or []:
        why = 'assigned to you' if t.get('responder_id') == me else \
              'new in your group' if t.get('responder_id') is None and t.get('group_id') in groups and t.get('status') == 2 else None
        if not why or t.get('status') in (4, 5): continue
        r = t.get('requester') or {}
        out.append(item(t['id'], f"#{t['id']} {t.get('subject') or ''}".strip(),
                        f"Freshdesk ticket - {FD_STATUS.get(t.get('status'), t.get('status'))} · priority {FD_PRIORITY.get(t.get('priority'), '?')} · {why}",
                        t.get('description_text') or _text(t.get('description')), r.get('name'), r.get('email'), t.get('requester_id'),
                        None if agents is None else t.get('requester_id') in agents, t.get('updated_at'), f"{base}/a/tickets/{t['id']}", _host(base)))
    return out[:CAP]


# ── Intercom ─────────────────────────────────────────────────────────────────────────────
IC, IC_HINT = 'https://api.intercom.io', 'check the access token (Developer Hub → your app → Authentication)'
def _ic(c, method, path, **kw):
    return _req(c, method, f'{IC}{path}', IC_HINT, headers={'Authorization': f"Bearer {c.get('Secret') or ''}",
                                                             'Intercom-Version': '2.11', 'Accept': 'application/json'}, **kw)


def test_intercom(store, c) -> str:
    _need(c, 'access token', 'Intercom Developer Hub → New app → Authentication → Access token')
    me = _ic(c, 'get', '/me')
    app = me.get('app') or {}
    _keep(store, c, me_id=str(me['id']), app_id=app.get('id_code') or '', app_name=app.get('name') or 'Intercom')
    _seed_source(store, c, app.get('name') or 'Intercom')
    return f"authenticated as {me.get('name')} in {app.get('name') or 'your workspace'} - open conversations assigned to you flow in on the next sync"


def items_intercom(store, c, since) -> list:
    cfg = _cfg(c)
    q = {'query': {'operator': 'AND', 'value': [{'field': 'admin_assignee_id', 'operator': '=', 'value': _me(c)},
                                                 {'field': 'open', 'operator': '=', 'value': True},
                                                 {'field': 'updated_at', 'operator': '>', 'value': int(since.timestamp())}]},
         'pagination': {'per_page': CAP}}
    out = []
    for v in _ic(c, 'post', '/conversations/search', json=q).get('conversations') or []:
        src = v.get('source') or {}
        a = src.get('author') or {}
        out.append(item(v['id'], (v.get('title') or src.get('subject') or f"Conversation with {a.get('name') or a.get('email') or 'a customer'}").strip(),
                        f"Intercom conversation - {v.get('state')}{' · priority' if v.get('priority') == 'priority' else ''} · assigned to you",
                        _text(src.get('body')), a.get('name'), a.get('email'), a.get('id'),
                        a.get('type') == 'admin' if a.get('type') else None,          # a teammate; a user, lead or bot is not
                        v.get('updated_at'), f"https://app.intercom.com/a/inbox/{cfg.get('app_id')}/inbox/conversation/{v['id']}",
                        cfg.get('app_name') or 'Intercom'))
    return out


# ── ServiceNow ───────────────────────────────────────────────────────────────────────────
SN_HINT = 'check the user name and password (the user needs the itil role, or rest_api_explorer to read tables)'
def _sn_base(c): return _site(c, 'instance', '{}.service-now.com', 'no ServiceNow instance set - the "yourco" in yourco.service-now.com')
def _sn(c, path, **params):
    return _req(c, 'get', f'{_sn_base(c)}/api/now{path}', SN_HINT, params=params,
                auth=(_cfg(c).get('username') or '', c.get('Secret') or ''), headers={'Accept': 'application/json'})
def _sn_tables(c) -> list:
    ts = [t.strip() for t in str(_cfg(c).get('tables') or 'incident').split(',') if t.strip()]
    if bad := [t for t in ts if not re.fullmatch(r'[a-z][a-z0-9_]*', t)]: raise RuntimeError(f'not a ServiceNow table name: {bad[0]!r}')
    return ts


def test_servicenow(store, c) -> str:
    _need(c, 'password', 'the ServiceNow user\'s password goes under Credentials')
    user = str(_cfg(c).get('username') or '').strip()
    if not user: raise RuntimeError('no user name set - the ServiceNow user these tickets are assigned to')
    u = (_sn(c, '/table/sys_user', sysparm_query=f'user_name={user}', sysparm_fields='sys_id,name', sysparm_limit=1).get('result') or [None])[0]
    if not u: raise RuntimeError(f'ServiceNow knows no user {user!r}')
    _keep(store, c, me_id=u['sys_id'])
    _seed_source(store, c, _host(_sn_base(c)))
    return f"authenticated as {u.get('name')} - {', '.join(_sn_tables(c))} records assigned to you flow in on the next sync"


def _sn_internal(c, uid):
    "A caller in sys_user ITSELF is the company's directory; customer_contact and csm_consumer extend it for outsiders."
    return _member(('servicenow', _sn_base(c), uid), lambda: (_sn(c, f'/table/sys_user/{uid}', sysparm_fields='sys_class_name')
                                                             .get('result') or {}).get('sys_class_name') == 'sys_user')


def items_servicenow(store, c, since) -> list:
    base, me, out = _sn_base(c), _me(c), []
    dv = lambda f, k='display_value': (f or {}).get(k) if isinstance(f, dict) else f
    floor = (since.astimezone(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')    # its zone is the user's: over-fetch a day
    for t in _sn_tables(c):
        rows = _sn(c, f'/table/{t}', sysparm_query=f'assigned_to={me}^active=true^sys_updated_on>={floor}^ORDERBYDESCsys_updated_on',
                   sysparm_limit=CAP, sysparm_display_value='all',
                   sysparm_fields='sys_id,number,short_description,description,priority,state,sys_updated_on,caller_id,opened_by').get('result') or []
        for r in rows:
            who = r.get('caller_id') if dv(r.get('caller_id'), 'value') else r.get('opened_by')
            uid, sid = dv(who, 'value'), dv(r.get('sys_id'), 'value')
            out.append(item(f"{t}:{sid}", f"{dv(r.get('number'))} {dv(r.get('short_description')) or ''}".strip(),
                            f"ServiceNow {t.replace('_', ' ')} - {dv(r.get('state'))} · priority {dv(r.get('priority'))} · assigned to you",
                            dv(r.get('description')), dv(who), None, uid, _sn_internal(c, uid), dv(r.get('sys_updated_on'), 'value'),
                            f"{base}/nav_to.do?uri={quote(f'{t}.do?sys_id={sid}', safe='')}",
                            _host(base)))
    return out


# ── Shortcut ─────────────────────────────────────────────────────────────────────────────
SC = 'https://api.app.shortcut.com/api/v3'
def _sc(c, path, **params):
    return _req(c, 'get', f'{SC}{path}', 'check the API token (Settings, then Your account → API Tokens)', params=params,
                headers={'Shortcut-Token': c.get('Secret') or '', 'Content-Type': 'application/json'})


def test_shortcut(store, c) -> str:
    _need(c, 'API token', 'Shortcut: Settings, then Your account → API Tokens → Generate token')
    m = _sc(c, '/member')
    p, ws = m.get('profile') or {}, (m.get('workspace2') or {}).get('url_slug') or 'Shortcut'
    _keep(store, c, me_id=m['id'], mention=p.get('mention_name') or '', workspace=ws)
    _seed_source(store, c, ws)
    return f"authenticated as {p.get('name') or p.get('mention_name')} in {ws} - stories you own flow in on the next sync"


def items_shortcut(store, c, since) -> list:
    cfg = _cfg(c)
    if not cfg.get('mention'): _me(c, 'mention')
    j = _sc(c, '/search/stories', query=f"owner:{cfg['mention']} !is:done !is:archived updated:{since:%Y-%m-%d}..*", page_size=CAP, detail='full')
    # requested_by is a workspace member when the members list says so - and still active there
    people = {m['id']: m for m in _sc(c, '/members') or [] if not m.get('disabled')}
    out = []
    for s in j.get('data') or []:
        p = (people.get(s.get('requested_by_id')) or {}).get('profile') or {}
        out.append(item(s['id'], f"sc-{s['id']} {s.get('name') or ''}".strip(), f"Shortcut {s.get('story_type') or 'story'} - you own it",
                        s.get('description'), p.get('name'), p.get('email_address'), s.get('requested_by_id'),
                        s.get('requested_by_id') in people if s.get('requested_by_id') else None,
                        s.get('updated_at'), s.get('app_url'), cfg.get('workspace') or 'Shortcut'))
    return out


# ── Wrike ────────────────────────────────────────────────────────────────────────────────
def _wr(c, path, **params):
    host = str(_cfg(c).get('host') or 'www.wrike.com').strip().split('//')[-1].strip('/')
    return _req(c, 'get', f'https://{host}/api/v4{path}', 'check the permanent access token (Apps & Integrations → API)', params=params,
                headers={'Authorization': f"Bearer {c.get('Secret') or ''}"}).get('data') or []


def test_wrike(store, c) -> str:
    _need(c, 'permanent access token', 'Wrike: your avatar → Apps & Integrations → API → create a permanent access token')
    me = (_wr(c, '/contacts', me='true') or [{}])[0]
    _keep(store, c, me_id=me['id'])
    _seed_source(store, c, 'Wrike')
    return f"authenticated as {me.get('firstName')} {me.get('lastName')} - active tasks assigned to you flow in on the next sync"


def items_wrike(store, c, since) -> list:
    ts = _wr(c, '/tasks', responsibles=json.dumps([_me(c)]), status='Active', updatedDate=json.dumps({'start': _utc(since)}),
             sortField='UpdatedDate', sortOrder='Desc', pageSize=CAP, fields=json.dumps(['description', 'authorIds']))
    ids = sorted({a for t in ts for a in (t.get('authorIds') or [])})
    # an author whose profile in this account is External is a collaborator from outside it
    who = {p['id']: p for p in (_wr(c, f"/contacts/{','.join(ids)}") if ids else [])}
    out = []
    for t in ts:
        a = who.get((t.get('authorIds') or [None])[0]) or {}
        out.append(item(t['id'], t.get('title') or 'Wrike task', f"Wrike task - {t.get('status')} · importance {t.get('importance') or 'normal'} · assigned to you",
                        _text(t.get('description')), ' '.join(x for x in (a.get('firstName'), a.get('lastName')) if x) or None,
                        next((p.get('email') for p in a.get('profiles') or [] if p.get('email')), None), a.get('id'),
                        (a.get('type') == 'Person' and not any(p.get('external') for p in a.get('profiles') or [])) if a else None,
                        t.get('updatedDate'), t.get('permalink'), 'Wrike'))
    return out


# ── Smartsheet ───────────────────────────────────────────────────────────────────────────
SS = 'https://api.smartsheet.com/2.0'
def _ss(c, path, **params):
    return _req(c, 'get', f'{SS}{path}', 'check the API access token (Account → Personal settings → API Access)', params=params,
                headers={'Authorization': f"Bearer {c.get('Secret') or ''}"})


def test_smartsheet(store, c) -> str:
    _need(c, 'API access token', 'Smartsheet: Account → Personal settings → API Access → Generate new access token')
    me = _ss(c, '/users/me')
    _keep(store, c, me_email=str(me.get('email') or '').lower())
    _seed_source(store, c, 'Smartsheet')
    return f"authenticated as {me.get('email')} - rows whose contact column names you flow in on the next sync"


def _ss_mine(cell, me) -> bool:
    o = cell.get('objectValue') or {}
    return me in {str(x).lower() for x in [cell.get('value'), o.get('email'), *[v.get('email') for v in o.get('values') or []]] if x}


def items_smartsheet(store, c, since) -> list:
    cfg, me, out = _cfg(c), _me(c, 'me_email'), []
    ids = [s.strip() for s in str(cfg.get('sheet_ids') or '').split(',') if s.strip()]
    if not ids: ids = [s['id'] for s in (_ss(c, '/sheets', modifiedSince=_utc(since), includeAll='true').get('data') or [])][:10]
    for sid in ids:
        sh = _ss(c, f'/sheets/{sid}', rowsModifiedSince=_utc(since), include='objectValue,rowPermalink,writerInfo', level=2)
        cols = {k['id']: k for k in sh.get('columns') or []}
        contact = {k for k, v in cols.items() if v.get('type') in ('CONTACT_LIST', 'MULTI_CONTACT_LIST')}
        shared = None
        for r in sh.get('rows') or []:
            cells = r.get('cells') or []
            if not any(x.get('columnId') in contact and _ss_mine(x, me) for x in cells): continue
            # a member of the sheet is someone it is shared with - read once a sheet, and only when a row is ours
            if shared is None:
                try: shared = {str(s.get('email') or '').lower() for s in _ss(c, f'/sheets/{sid}/shares', includeAll='true').get('data') or []} - {''}
                except Exception as e: shared = set(); logger.debug(f'smartsheet {sid}: shares unread ({e})')
            title = next((x.get('displayValue') or x.get('value') for x in cells if cols.get(x.get('columnId'), {}).get('primary')), None)
            by = r.get('createdBy') or {}
            out.append(item(f"{sid}:{r['id']}", str(title or f"Row {r.get('rowNumber')}"), f'Smartsheet row on "{sh.get("name")}" - assigned to you',
                            '\n'.join(f"{cols[x['columnId']]['title']}: {x.get('displayValue') or x.get('value')}" for x in cells
                                      if x.get('columnId') in cols and (x.get('displayValue') or x.get('value')) not in (None, '')),
                            by.get('name'), by.get('email'), by.get('email'),
                            (str(by['email']).lower() in shared) if by.get('email') and shared else None,
                            r.get('modifiedAt'), r.get('permalink') or sh.get('permalink'), sh.get('name') or 'Smartsheet'))
    return out[:CAP]


# ── Airtable ─────────────────────────────────────────────────────────────────────────────
AT = 'https://api.airtable.com/v0'
def _at(c, path, **params):
    return _req(c, 'get', f'{AT}{path}', 'check the personal access token (scope data.records:read, with this base added)', params=params,
                headers={'Authorization': f"Bearer {c.get('Secret') or ''}"})
def _at_where(c) -> tuple:
    cfg = _cfg(c)
    base, table = str(cfg.get('base_id') or '').strip(), str(cfg.get('table') or '').strip()
    if not (base and table): raise RuntimeError('need the base id (appXXXX, from the base URL) and the table name or id')
    return base, table, str(cfg.get('view') or '').strip()


def test_airtable(store, c) -> str:
    _need(c, 'personal access token', 'airtable.com/create/tokens - scope data.records:read, and add this base')
    base, table, view = _at_where(c)
    me = _at(c, '/meta/whoami')
    _at(c, f'/{base}/{quote(table, safe="")}', maxRecords=1, **({'view': view} if view else {}))
    _seed_source(store, c, table)
    return f"authenticated as {me.get('email') or me.get('id')} - rows {f'in the view {view!r}' if view else 'of ' + table} flow in as they change"


def items_airtable(store, c, since) -> list:
    base, table, view = _at_where(c)
    cfg = _cfg(c)
    j = _at(c, f'/{base}/{quote(table, safe="")}', pageSize=CAP, filterByFormula=f"IS_AFTER(LAST_MODIFIED_TIME(), '{_utc(since)}')",
            **({'view': view} if view else {}))
    out = []
    for r in j.get('records') or []:
        f = r.get('fields') or {}
        title = f.get(cfg.get('title_field')) if cfg.get('title_field') else next((v for v in f.values() if isinstance(v, str) and v.strip()), None)
        # no author: Airtable's API never says who in a base is a collaborator, so a row waits for Trust everyone from this table
        out.append(item(r['id'], str(title or 'Airtable row')[:200], f"Airtable row in {table}{f' · view {view}' if view else ''}",
                        '\n'.join(f'{k}: {v if isinstance(v, (str, int, float)) else json.dumps(v)[:300]}' for k, v in f.items()),
                        at=None, link=f'https://airtable.com/{base}/{table}/{r["id"]}' if table.startswith('tbl') else f'https://airtable.com/{base}',
                        place=table))
    return out


# ── GitHub Projects ──────────────────────────────────────────────────────────────────────
_GHP_ITEMS = ('items(first: 50) { nodes { id updatedAt content { __typename '
              '... on Issue { number title url body state authorAssociation author { login } assignees(first: 10) { nodes { login } } repository { nameWithOwner } } '
              '... on PullRequest { number title url body state authorAssociation author { login } assignees(first: 10) { nodes { login } } repository { nameWithOwner } } '
              '... on DraftIssue { title body creator { login } assignees(first: 10) { nodes { login } } } } } }')
def _gql(c, query, **variables):
    j = _req(c, 'post', 'https://api.github.com/graphql', 'check the token (classic: read:project + repo; fine-grained: Projects read)',
             json={'query': query, 'variables': variables}, headers={'Authorization': f"Bearer {c.get('Secret') or ''}"})
    if j.get('errors'): raise RuntimeError(f"GitHub Projects: {(j['errors'][0] or {}).get('message') or j['errors']}")
    return j['data']


def test_github_projects(store, c) -> str:
    _need(c, 'token', 'GitHub → Settings, then Developer settings → a token with read:project (and repo for private repos)')
    v = _gql(c, '{ viewer { login projectsV2(first: 20) { totalCount } } }')['viewer']
    _keep(store, c, me_id=v['login'])
    _seed_source(store, c, v['login'])
    return f"authenticated as {v['login']} ({plural(v['projectsV2']['totalCount'], 'project')} of your own) - project items assigned to you flow in on the next sync"


def items_github_projects(store, c, since) -> list:
    me, cfg = _me(c), _cfg(c)
    boards = _gql(c, '{ viewer { projectsV2(first: 10) { nodes { title url %s } } } }' % _GHP_ITEMS)['viewer']['projectsV2']['nodes']
    for org in [o.strip() for o in str(cfg.get('owners') or '').split(',') if o.strip()][:5]:
        boards += (_gql(c, 'query($o: String!) { organization(login: $o) { projectsV2(first: 10) { nodes { title url %s } } } }' % _GHP_ITEMS, o=org)
                   .get('organization') or {}).get('projectsV2', {}).get('nodes') or []
    # an issue in a repo the GitHub card already watches is that card's to file - the same issue twice is two tasks
    watched = {s['Address'].lower() for s in store.list_sources() if s['Channel'] == 'github'}
    out = []
    for b in boards:
        for i in (b.get('items') or {}).get('nodes') or []:
            x = i.get('content') or {}
            if me not in {a['login'] for a in (x.get('assignees') or {}).get('nodes') or []}: continue
            if x.get('state') in ('CLOSED', 'MERGED') or _when(i.get('updatedAt')) < _new(since): continue
            repo = (x.get('repository') or {}).get('nameWithOwner')
            if repo and repo.lower() in watched: continue
            by = x.get('author') or x.get('creator') or {}
            kind = {'Issue': 'issue', 'PullRequest': 'pull request'}.get(x['__typename'], 'draft item')
            out.append(item(i['id'], f"{f'{repo}#' + str(x['number']) + ' ' if repo else ''}{x.get('title') or ''}".strip(),
                            f"GitHub Projects {kind} on {b['title']} - assigned to you", x.get('body'), by.get('login'), None, by.get('login'),
                            x.get('authorAssociation') in ('OWNER', 'MEMBER', 'COLLABORATOR') if repo else True,   # a draft lives only on the board
                            i.get('updatedAt'), x.get('url') or b.get('url'), b['title']))
    return out[:CAP]


# ── Bitbucket ────────────────────────────────────────────────────────────────────────────
BB = 'https://api.bitbucket.org/2.0'
def _bb(c, path, ok404=False, **params):
    return _req(c, 'get', f'{BB}{path}', 'check the user name / email and the API token or app password (scopes: repository, pull request, issue read)',
                ok404=ok404, params=params, auth=(_cfg(c).get('username') or '', c.get('Secret') or ''))
def _bb_ws(c) -> str:
    ws = str(_cfg(c).get('workspace') or '').strip()
    if not re.fullmatch(r'[\w.-]+', ws): raise RuntimeError('no workspace set - the first path segment of your Bitbucket URLs')
    return ws


def test_bitbucket(store, c) -> str:
    _need(c, 'API token or app password', 'Bitbucket: Personal settings → API tokens (or App passwords)')
    me, ws = _bb(c, '/user'), _bb_ws(c)
    w = _bb(c, f'/workspaces/{ws}')
    _keep(store, c, me_id=me['uuid'])
    _seed_source(store, c, ws)
    return f"authenticated as {me.get('display_name')} in {w.get('name') or ws} - PRs asking your review and issues assigned to you flow in on the next sync"


def _bb_member(c, ws, uid):
    return _member(('bitbucket', ws, uid), lambda: _bb(c, f'/workspaces/{ws}/members/{quote(uid, safe="")}', ok404=True) is not None)


def items_bitbucket(store, c, since) -> list:
    ws, me, iso = _bb_ws(c), _me(c), _utc(since)
    repos = [r.strip() for r in str(_cfg(c).get('repos') or '').split(',') if re.fullmatch(r'[\w.-]+', r.strip())]
    if not repos: repos = [r['slug'] for r in _bb(c, f'/repositories/{ws}', sort='-updated_on', pagelen=10).get('values') or []]
    out = []
    for slug in repos[:10]:
        prs = _bb(c, f'/repositories/{ws}/{slug}/pullrequests', pagelen=CAP,
                  q=f'state="OPEN" AND reviewers.uuid="{me}" AND updated_on>{iso}').get('values') or []
        iss = (_bb(c, f'/repositories/{ws}/{slug}/issues', ok404=True, pagelen=CAP,           # 404: this repo keeps no issue tracker
                   q=f'assignee.uuid="{me}" AND (state="new" OR state="open") AND updated_on>{iso}') or {}).get('values') or []
        for kind, x, by in [('pull request', p, p.get('author') or {}) for p in prs] + [('issue', i, i.get('reporter') or {}) for i in iss]:
            out.append(item(f"{slug}:{kind[0]}{x['id']}", f"{slug}{'!' if kind[0] == 'p' else '#'}{x['id']} {x.get('title') or ''}".strip(),
                            f"Bitbucket {kind} in {ws}/{slug} - {'review requested from you' if kind[0] == 'p' else 'assigned to you'}",
                            x.get('description') if kind[0] == 'p' else (x.get('content') or {}).get('raw'), by.get('display_name'), None,
                            by.get('uuid'), _bb_member(c, ws, by.get('uuid')), x.get('updated_on'),
                            ((x.get('links') or {}).get('html') or {}).get('href'), f'{ws}/{slug}'))
    return out[:CAP]


# ── Microsoft Planner (Graph, through the Microsoft sign-in this app already has) ───────────────────────────────────────────────
def _pl_token(store, c) -> tuple:
    from .channels import graph_creds, graph_token
    cfg, sec, _ = graph_creds(store, c)
    if cfg.get('auth') != 'user' and not str(_cfg(c).get('user') or '').strip():
        raise RuntimeError("a company app reads someone's plans: enter whose (their sign-in address) under Credentials")
    return graph_token(cfg, sec), cfg


def _graph(tok, path, **params):
    r = requests.get(f'https://graph.microsoft.com/v1.0{path}', params=params, timeout=30, headers={'Authorization': f'Bearer {tok}'})
    if r.status_code in (401, 403):
        raise RuntimeError(f'Microsoft said {r.status_code} - the app needs the Tasks.Read permission (or Tasks.Read.All for a company app), granted by IT')
    r.raise_for_status()
    return r.json()


def _pl_who(c, cfg) -> str: return '/me' if cfg.get('auth') == 'user' else f"/users/{quote(str(_cfg(c).get('user')).strip(), safe='@.')}"


def test_ms_planner(store, c) -> str:
    tok, cfg = _pl_token(store, c)
    ts = _graph(tok, f'{_pl_who(c, cfg)}/planner/tasks', **{'$top': 1})
    _seed_source(store, c, 'Planner')
    return f"Planner read OK ({'tasks found' if ts.get('value') else 'no tasks yet'}) - tasks assigned to you flow in on the next sync"


def items_ms_planner(store, c, since) -> list:
    # a Planner task carries no modified time, so every open one is offered and ingest_tracker keeps only what changed
    tok, cfg = _pl_token(store, c)
    ts = [t for t in _graph(tok, f'{_pl_who(c, cfg)}/planner/tasks').get('value') or [] if (t.get('percentComplete') or 0) < 100]
    ts.sort(key=lambda t: t.get('createdDateTime') or '', reverse=True)
    plans, out = {}, []
    for t in ts[:CAP]:
        if t['planId'] not in plans:
            try: plans[t['planId']] = _graph(tok, f"/planner/plans/{t['planId']}").get('title') or 'Planner'
            except Exception: plans[t['planId']] = 'Planner'
        by = ((t.get('createdBy') or {}).get('user') or {})
        # a guest in the tenant is an outsider; only the directory's own Member is of the workspace
        member = _member(('ms_planner', cfg.get('tenant_id') or '', by.get('id')),
                         lambda: {'Member': True, 'Guest': False}.get(_graph(tok, f"/users/{by['id']}", **{'$select': 'userType'}).get('userType')))
        desc = ''
        if t.get('hasDescription') and not store.message_exists(f"ms_planner:{t['id']}"):
            try: desc = _graph(tok, f"/planner/tasks/{t['id']}/details").get('description') or ''
            except Exception as e: logger.debug(f'planner {t["id"]}: details unread ({e})')
        due = f" · due {str(t['dueDateTime'])[:10]}" if t.get('dueDateTime') else ''
        out.append(item(t['id'], t.get('title') or 'Planner task', f"Planner task on {plans[t['planId']]} - {t.get('percentComplete') or 0}% done{due} · assigned to you",
                        desc, by.get('displayName'), None, by.get('id'), member, None,
                        f"https://planner.cloud.microsoft/webui/plan/{t['planId']}/view/board/task/{t['id']}", plans[t['planId']]))
    return out


# ═══ PEOPLE WHO WRITE TO YOU FROM OUTSIDE: chat, community, social, texts ════════════════════════════════════════════════════
# The same road - but here almost every author is an outsider by nature (a forum member, a Redditor, a commenter, a texter), so
# a member is only who the platform itself says belongs: a Zulip organisation's non-guest, a Discourse forum's staff. Everyone
# else is a stranger, vouched for one by one (senders.vouch keys on their id here).

# ── Zulip ────────────────────────────────────────────────────────────────────────────────
def _zu_base(c): return _site(c, 'site', '{}.zulipchat.com', 'no Zulip site set - e.g. https://yourco.zulipchat.com')
def _zu(c, path, **params):
    return _req(c, 'get', f'{_zu_base(c)}/api/v1{path}', 'check the bot or account email and its API key (Personal settings → Account & privacy → API key)',
                params=params, auth=(_cfg(c).get('email') or '', c.get('Secret') or ''))


def test_zulip(store, c) -> str:
    _need(c, 'API key', 'Zulip: Personal settings → Account & privacy → Manage your API key')
    me = _zu(c, '/users/me')
    _keep(store, c, me_id=me['user_id'])
    _seed_source(store, c, _host(_zu_base(c)))
    return f"authenticated as {me.get('full_name')} - messages that mention you and direct messages flow in on the next sync"


def items_zulip(store, c, since) -> list:
    base, me, seen, out = _zu_base(c), int(_me(c)), set(), []
    for why, narrow in (('mentions you', 'mentioned'), ('a direct message', 'dm')):
        for m in _zu(c, '/messages', anchor='newest', num_before=CAP, num_after=0, apply_markdown='false',
                     narrow=json.dumps([{'operator': 'is', 'operand': narrow}])).get('messages') or []:
            if m['id'] in seen or m.get('sender_id') == me: continue
            seen.add(m['id'])
            # Zulip's own role: owner 100 ... member 400, guest 600 - a guest or a bot is not of the organisation
            role = lambda u=m['sender_id']: (lambda x: x.get('role', 600) <= 400 and not x.get('is_bot'))(_zu(c, f'/users/{u}').get('user') or {})
            dm = m.get('type') == 'private'
            where = f"dm/{m['sender_id']}" if dm else f"channel/{m.get('stream_id')}/topic/{quote(str(m.get('subject') or ''))}"
            out.append(item(m['id'], None if dm else f"#{m.get('display_recipient')} > {m.get('subject')}",
                            f"Zulip message - {why}", m.get('content'), m.get('sender_full_name'), m.get('sender_email'), m['sender_id'],
                            _member(('zulip', base, m['sender_id']), role), m.get('timestamp'),
                            f"{base}/#narrow/{where}/near/{m['id']}",
                            _host(base), conv=f"dm:{m['sender_id']}" if dm else f"{m.get('stream_id')}:{m.get('subject')}"))
    return out


# ── Signal (signal-cli-rest-api running beside Taskuary) ──────────────────────────────────
def _sg_base(c) -> str: return str(_cfg(c).get('url') or 'http://127.0.0.1:8080').strip().rstrip('/')
def _sg_number(c) -> str:
    n = re.sub(r'[^\d+]', '', str(_cfg(c).get('number') or ''))
    if not n: raise RuntimeError("no number set - the Signal number signal-cli is registered or linked as, e.g. +15551234567")
    return n


def test_signal(store, c) -> str:
    about, n = _req(c, 'get', f'{_sg_base(c)}/v1/about', 'the signal-cli REST API refused us'), _sg_number(c)
    if n not in (_req(c, 'get', f'{_sg_base(c)}/v1/accounts', 'the signal-cli REST API refused us') or []):
        raise RuntimeError(f'signal-cli answers, but {n} is not registered or linked on it - link it first (its /v1/qrcodelink)')
    _seed_source(store, c, n)
    return f"signal-cli {about.get('version') or ''} answers for {n} - your messages flow in on the next sync"


def items_signal(store, c, since) -> list:
    # receive EMPTIES signal-cli's queue: what it hands over is this poll's to file, so nothing here may drop a message
    out = []
    for e in _req(c, 'get', f'{_sg_base(c)}/v1/receive/{quote(_sg_number(c))}', 'the signal-cli REST API refused us') or []:
        v = e.get('envelope') or {}
        d = v.get('dataMessage') or {}
        if not str(d.get('message') or '').strip(): continue        # receipts, typing, reactions
        who, g = v.get('sourceUuid') or v.get('sourceNumber') or v.get('source'), (d.get('groupInfo') or {}).get('groupId')
        out.append(item(f"{who}:{v.get('timestamp')}", None, f"Signal message{' in a group' if g else ''}", d['message'],
                        v.get('sourceName') or v.get('sourceNumber'), None, who, None, v.get('timestamp'), None, 'Signal',
                        conv=f"g:{g}" if g else f"dm:{who}", drained=True))
    return out


# ── Twilio (texts to your number) ────────────────────────────────────────────────────────
def _tw(c, path, **params):
    sid = str(_cfg(c).get('account_sid') or '').strip()
    if not re.fullmatch(r'AC[0-9a-fA-F]{32}', sid): raise RuntimeError('no Account SID set - it starts AC, on the Twilio console home')
    return _req(c, 'get', f'https://api.twilio.com/2010-04-01/Accounts/{sid}{path}', 'check the Account SID and the auth token', params=params,
                auth=(sid, c.get('Secret') or ''))


def test_twilio(store, c) -> str:
    _need(c, 'auth token', 'the Twilio console home shows the Account SID and the auth token')
    a, n = _tw(c, '.json'), str(_cfg(c).get('number') or '').strip()
    if not n: raise RuntimeError('no number set - the Twilio number texts arrive on, e.g. +15551234567')
    _seed_source(store, c, n)
    return f"authenticated to {a.get('friendly_name')} - texts to {n} flow in on the next sync"


def items_twilio(store, c, since) -> list:
    from email.utils import parsedate_to_datetime
    n = str(_cfg(c).get('number') or '').strip()
    ms = _tw(c, '/Messages.json', To=n, PageSize=CAP, **{'DateSent>': f'{since - timedelta(days=1):%Y-%m-%d}'}).get('messages') or []
    return [item(m['sid'], None, 'Text message to your Twilio number', m.get('body'), m.get('from'), None, m.get('from'), None,
                 parsedate_to_datetime(m['date_sent']).isoformat() if m.get('date_sent') else None,
                 f"https://console.twilio.com/us1/monitor/logs/sms/{m['sid']}", n, conv=f"from:{m.get('from')}")
            for m in ms if m.get('direction') == 'inbound']


# ── Discourse (mentions, replies, messages to you) ───────────────────────────────────────
DC_KINDS = {1: 'mentioned you', 2: 'replied to you', 3: 'quoted you', 6: 'sent you a message', 15: 'mentioned your group'}
def _dc_base(c): return _site(c, 'base_url', '{}', 'no forum URL set - e.g. https://forum.yourco.example')
def _dc(c, path, **params):
    return _req(c, 'get', f'{_dc_base(c)}{path}', 'check the API key and the user name it acts for (Admin → API → Keys)', params=params,
                headers={'Api-Key': c.get('Secret') or '', 'Api-Username': _cfg(c).get('username') or '', 'Accept': 'application/json'})


def test_discourse(store, c) -> str:
    _need(c, 'API key', 'Discourse: Admin → API → New API key (a single user: you)')
    u = _dc(c, f"/u/{quote(str(_cfg(c).get('username') or ''))}.json").get('user') or {}
    _seed_source(store, c, _host(_dc_base(c)))
    return f"authenticated as {u.get('username')} - mentions, replies and messages to you flow in on the next sync"


def _dc_staff(c, who):
    """Staff - or a member of the group the card names - is of the forum; anyone else can sign up, so is a stranger."""
    def ask():
        u = _dc(c, f'/u/{quote(who)}.json').get('user') or {}
        g = str(_cfg(c).get('member_group') or '').strip().lower()
        return bool(u.get('admin') or u.get('moderator') or (g and g in {str(x.get('name') or '').lower() for x in u.get('groups') or []}))
    return _member(('discourse', _dc_base(c), who), ask)


def items_discourse(store, c, since) -> list:
    base, out = _dc_base(c), []
    for n in _dc(c, '/notifications.json', username=_cfg(c).get('username') or '').get('notifications') or []:
        if n.get('notification_type') not in DC_KINDS or _when(n.get('created_at')) < _new(since): continue
        d = n.get('data') or {}
        who = d.get('original_username') or d.get('display_username')
        p = _dc(c, f"/posts/by_number/{n['topic_id']}/{n.get('post_number') or 1}.json") if n.get('topic_id') else {}
        out.append(item(n['id'], d.get('topic_title') or n.get('fancy_title') or 'Discourse', f"Discourse - {who} {DC_KINDS[n['notification_type']]}",
                        p.get('raw') or _text(p.get('cooked')), p.get('name') or who, None, who and f'u:{who}',
                        _dc_staff(c, who) if who else None, n.get('created_at'),
                        f"{base}/t/{n.get('slug') or '-'}/{n['topic_id']}/{n.get('post_number') or 1}", _host(base), conv=f"t{n.get('topic_id')}"))
    return out


# ── Reddit (your inbox: replies, mentions, messages) ─────────────────────────────────────
RD_UA = 'taskuary:inbox:1.0 (by your own script app)'
def _rd_token(c) -> str:
    cfg = _cfg(c)
    if not (cfg.get('client_id') and cfg.get('client_secret') and cfg.get('username')):
        raise RuntimeError('need the script app\'s client id and secret (reddit.com/prefs/apps) and your user name')
    from . import net
    def mint():
        r = requests.request('post', 'https://www.reddit.com/api/v1/access_token', timeout=30, auth=(cfg['client_id'], cfg['client_secret']),
                             data={'grant_type': 'password', 'username': cfg['username'], 'password': c.get('Secret') or ''}, headers={'User-Agent': RD_UA})
        j = r.json() if r.status_code == 200 else {}
        if not j.get('access_token'): raise RuntimeError('Reddit refused the sign-in - check the app id, its secret, your user name and password '
                                                         '(an account with two-factor sign-in cannot use a script app)')
        return j['access_token'], j.get('expires_in')
    return net.token(('reddit', cfg['client_id'], cfg['username']), mint)


def _rd(c, path, **params):
    return _req(c, 'get', f'https://oauth.reddit.com{path}', 'the sign-in was refused - Test the card again', params=params,
                headers={'Authorization': f'Bearer {_rd_token(c)}', 'User-Agent': RD_UA})


def test_reddit(store, c) -> str:
    _need(c, 'password', 'your Reddit password (the script app signs in as you)')
    me = _rd(c, '/api/v1/me')
    _seed_source(store, c, f"u/{me.get('name')}")
    return f"authenticated as u/{me.get('name')} - replies, mentions and messages in your inbox flow in on the next sync"


def items_reddit(store, c, since) -> list:
    out = []
    for k in (_rd(c, '/message/inbox', limit=CAP, raw_json=1).get('data') or {}).get('children') or []:
        m = k.get('data') or {}
        kind = 'a reply to you' if m.get('was_comment') else 'a message'
        out.append(item(m.get('name') or m['id'], m.get('link_title') or m.get('subject'), f"Reddit - {kind}{' in r/' + m['subreddit'] if m.get('subreddit') else ''}",
                        m.get('body'), f"u/{m.get('author')}", None, m.get('author') and f"u:{m['author']}", False,   # a Redditor is always an outsider
                        m.get('created_utc'), f"https://www.reddit.com{m['context']}" if m.get('context') else 'https://www.reddit.com/message/inbox',
                        f"u/{_cfg(c).get('username')}"))
    return out


# ── YouTube (comments on your channel's videos) ──────────────────────────────────────────
def _yt(c, path, **params):
    return _req(c, 'get', f'https://www.googleapis.com/youtube/v3{path}', 'check the API key (Google Cloud console, YouTube Data API v3 enabled)',
                params={**params, 'key': c.get('Secret') or ''})
def _yt_channel(c) -> str:
    ch = str(_cfg(c).get('channel_id') or '').strip()
    if not re.fullmatch(r'UC[\w-]{22}', ch): raise RuntimeError('no channel id set - it starts UC (YouTube Studio → Settings, then Channel → Advanced)')
    return ch


def test_youtube(store, c) -> str:
    _need(c, 'API key', 'Google Cloud console → APIs & Services → enable YouTube Data API v3 → Credentials → API key')
    ch = (_yt(c, '/channels', part='snippet', id=_yt_channel(c)).get('items') or [None])[0]
    if not ch: raise RuntimeError('YouTube knows no channel with that id')
    _seed_source(store, c, ch['snippet']['title'])
    return f"found {ch['snippet']['title']} - new comments on its videos flow in on the next sync"


def items_youtube(store, c, since) -> list:
    me, out = _yt_channel(c), []
    for t in _yt(c, '/commentThreads', part='snippet', allThreadsRelatedToChannelId=me, order='time', maxResults=CAP, textFormat='plainText').get('items') or []:
        s = (t['snippet'].get('topLevelComment') or {}).get('snippet') or {}
        who = (s.get('authorChannelId') or {}).get('value')
        if who == me: continue                                                  # the channel's own words are not work
        out.append(item(t['id'], f"Comment on your video {t['snippet'].get('videoId')}", 'YouTube comment on your channel', s.get('textOriginal'),
                        s.get('authorDisplayName'), None, who and f'ch:{who}', False, s.get('updatedAt') or s.get('publishedAt'),
                        f"https://www.youtube.com/watch?v={t['snippet'].get('videoId')}&lc={t['id']}", 'YouTube', conv=t['id']))
    return out


# ═══ THE BUSINESS SYSTEMS: something waits on you ═══════════════════════════════════════════════════════════════════════════
# A booking, an order to ship, a dispute to answer. Nobody inside wrote these - a customer did, or the system did - so no item
# here carries a member: each waits for the owner's press until they trust the source (Trust everyone from ...).

# ── Calendly (new bookings) ──────────────────────────────────────────────────────────────
CY = 'https://api.calendly.com'
def _cy(c, url, **params):
    return _req(c, 'get', url if url.startswith('http') else f'{CY}{url}', 'check the personal access token (Integrations → API & webhooks)',
                params=params, headers={'Authorization': f"Bearer {c.get('Secret') or ''}"})


def test_calendly(store, c) -> str:
    _need(c, 'personal access token', 'Calendly: Integrations & apps → API & webhooks → Generate new token')
    me = _cy(c, '/users/me')['resource']
    _keep(store, c, me_id=me['uri'])
    _seed_source(store, c, me.get('name') or 'Calendly')
    return f"authenticated as {me.get('name')} - new bookings flow in on the next sync"


def items_calendly(store, c, since) -> list:
    out = []
    for e in _cy(c, '/scheduled_events', user=_me(c), status='active', min_start_time=_utc(datetime.now()), sort='start_time:asc', count=CAP).get('collection') or []:
        if _when(e.get('created_at')) < _new(since): continue                  # a booking is news once: when it is made
        inv = (_cy(c, f"{e['uri']}/invitees").get('collection') or [{}])[0]
        qa = '\n'.join(f"{q.get('question')}: {q.get('answer')}" for q in inv.get('questions_and_answers') or [])
        out.append(item(e['uri'].rsplit('/', 1)[-1], f"{e.get('name')} with {inv.get('name') or 'someone'}",
                        f"Calendly booking - {_when(e.get('start_time'))[:16]} to {_when(e.get('end_time'))[11:16]}",
                        '\n'.join(x for x in (qa, (e.get('location') or {}).get('join_url')) if x), inv.get('name'), inv.get('email'), None, None,
                        e.get('created_at'), 'https://calendly.com/app/scheduled_events/user/me', 'Calendly'))
    return out


# ── ShipStation (orders waiting to ship) ─────────────────────────────────────────────────
def _st(c, path, **params):
    return _req(c, 'get', f'https://ssapi.shipstation.com{path}', 'check the API key and secret (Settings, then Account → API Settings)', params=params,
                auth=(_cfg(c).get('api_key') or '', c.get('Secret') or ''))


def test_shipstation(store, c) -> str:
    _need(c, 'API secret', 'ShipStation: Settings, then Account → API Settings shows the key and the secret')
    n = len(_st(c, '/stores') or [])
    _seed_source(store, c, 'ShipStation')
    return f"authenticated - {plural(n, 'store')} - orders awaiting shipment flow in on the next sync"


def items_shipstation(store, c, since) -> list:
    # ShipStation keeps its own clock (US Pacific, no offset): the query reaches a day back and ingest keeps only what changed
    j = _st(c, '/orders', orderStatus='awaiting_shipment', modifyDateStart=f'{since - timedelta(days=1):%Y-%m-%d %H:%M:%S}',
            sortBy='ModifyDate', sortDir='DESC', pageSize=CAP)
    by = lambda o: f" · ship by {str(o['shipByDate'])[:10]}" if o.get('shipByDate') else ''
    return [item(o['orderId'], f"Order {o.get('orderNumber')} to ship", f"ShipStation order - awaiting shipment{by(o)}",
                 '\n'.join([*(f"{i.get('quantity')} × {i.get('name')}" for i in o.get('items') or []),
                            *(f'{k}: {o[k]}' for k in ('customerNotes', 'internalNotes', 'orderTotal') if o.get(k))]),
                 (o.get('billTo') or {}).get('name'), o.get('customerEmail'), None, None, None,
                 f"https://ship.shipstation.com/orders/awaiting-shipment/order/{o['orderId']}", 'ShipStation') for o in j.get('orders') or []]


# ── Shopify (open orders not yet fulfilled) ──────────────────────────────────────────────
def _sh_base(c): return _site(c, 'shop', '{}.myshopify.com', 'no shop set - yourstore.myshopify.com')
def _sh(c, path, **params):
    return _req(c, 'get', f'{_sh_base(c)}/admin/api/2024-10{path}', 'check the Admin API access token (a custom app with read_orders)',
                params=params, headers={'X-Shopify-Access-Token': c.get('Secret') or ''})


def test_shopify(store, c) -> str:
    _need(c, 'Admin API access token', 'Shopify admin → Settings, then Apps and sales channels → Develop apps → your app → API credentials')
    sh = _sh(c, '/shop.json')['shop']
    _seed_source(store, c, sh.get('name') or _host(_sh_base(c)))
    return f"connected to {sh.get('name')} - open orders waiting to be fulfilled flow in on the next sync"


def items_shopify(store, c, since) -> list:
    base = _sh_base(c)
    return [item(o['id'], f"Order {o.get('name')} to fulfil", f"Shopify order - {o.get('financial_status')} · unfulfilled · {o.get('total_price')} {o.get('currency')}",
                 '\n'.join([*(f"{i.get('quantity')} × {i.get('title')}" for i in o.get('line_items') or []), *([f"Note: {o['note']}"] if o.get('note') else [])]),
                 ' '.join(x for x in ((o.get('customer') or {}).get('first_name'), (o.get('customer') or {}).get('last_name')) if x) or None,
                 o.get('email'), None, None, o.get('updated_at'), f"{base}/admin/orders/{o['id']}", _host(base))
            for o in _sh(c, '/orders.json', status='open', fulfillment_status='unfulfilled', updated_at_min=_utc(since), limit=CAP).get('orders') or []]


# ── Square (disputes waiting on your evidence) ───────────────────────────────────────────
def _sq(c, path, **params):
    return _req(c, 'get', f'https://connect.squareup.com/v2{path}', 'check the access token (Developer Console → your app → Credentials, Production)',
                params=params, headers={'Authorization': f"Bearer {c.get('Secret') or ''}", 'Square-Version': '2024-10-17'})
def _money(m, cents=True):
    m = m or {}
    v = m.get('amount') if cents else m.get('value')
    return f"{(v or 0) / 100 if cents else v} {m.get('currency') or m.get('currency_code') or ''}".strip()


def test_square(store, c) -> str:
    _need(c, 'access token', 'Square Developer Console → your app → Credentials → Production access token')
    m = _sq(c, '/merchants/me').get('merchant') or {}
    _seed_source(store, c, m.get('business_name') or 'Square')
    return f"connected to {m.get('business_name')} - disputes waiting on your evidence flow in on the next sync"


def items_square(store, c, since) -> list:
    return [item(d['id'], f"Dispute: {_money(d.get('amount_money'))} - {str(d.get('reason') or '').replace('_', ' ').lower()}",
                 f"Square dispute - evidence required{' by ' + str(d['due_at'])[:10] if d.get('due_at') else ''}",
                 f"Card: {d.get('card_brand')}\nPayment: {(d.get('disputed_payment') or {}).get('payment_id')}", 'Square', None, None, None,
                 d.get('updated_at'), 'https://app.squareup.com/dashboard/disputes', 'Square')
            for d in _sq(c, '/disputes', states='EVIDENCE_REQUIRED').get('disputes') or []]


# ── PayPal (disputes that need your action) ──────────────────────────────────────────────
def _pp_base(c) -> str: return 'https://api-m.sandbox.paypal.com' if _cfg(c).get('sandbox') in (True, 'true', '1', 'yes') else 'https://api-m.paypal.com'
def _pp(c, path, **params):
    from . import net
    cid = str(_cfg(c).get('client_id') or '').strip()
    if not cid: raise RuntimeError('no client id set - developer.paypal.com → Apps & Credentials → your app')
    def mint():
        r = requests.request('post', f'{_pp_base(c)}/v1/oauth2/token', timeout=30, auth=(cid, c.get('Secret') or ''), data={'grant_type': 'client_credentials'})
        if r.status_code != 200: raise RuntimeError(f'PayPal refused the app (said {r.status_code}) - check the client id and secret')
        j = r.json(); return j['access_token'], j.get('expires_in')
    tok = net.token(('paypal', _pp_base(c), cid), mint)
    return _req(c, 'get', f'{_pp_base(c)}{path}', 'the app needs the disputes permission (Apps & Credentials → your app → Features)', params=params,
                headers={'Authorization': f'Bearer {tok}'})


def test_paypal(store, c) -> str:
    _need(c, 'client secret', 'developer.paypal.com → Apps & Credentials → your app → Secret')
    _pp(c, '/v1/customer/disputes', page_size=1)
    _seed_source(store, c, 'PayPal')
    return 'connected - disputes that need your action flow in on the next sync'


def items_paypal(store, c, since) -> list:
    return [item(d['dispute_id'], f"Dispute: {_money(d.get('dispute_amount'), False)} - {str(d.get('reason') or '').replace('_', ' ').lower()}",
                 f"PayPal dispute - {str(d.get('dispute_life_cycle_stage') or '').lower()} · needs your action", f"Status: {d.get('status')}", 'PayPal',
                 None, None, None, d.get('update_time'), f"https://www.paypal.com/resolutioncenter/{d['dispute_id']}", 'PayPal')
            for d in _pp(c, '/v1/customer/disputes', dispute_state='REQUIRED_ACTION', page_size=CAP).get('items') or []]


# ── THE ONES THAT SIGN IN BY OAUTH (oauth.py): the card's Secret is its tokens, spent through oauth.access - renewed, never pasted ──
SIGN_IN = 'press Sign in on the card again'
def _bear(store, c, **h):
    from . import oauth
    return {'Authorization': f'Bearer {oauth.access(store, c)}', 'Accept': 'application/json', **h}
def _api(store, c, base, path, method='get', h=None, **kw): return _req(c, method, f'{base}{path}', SIGN_IN, headers=_bear(store, c, **(h or {})), **kw)
def _since_ms(since) -> int: return int(since.timestamp() * 1000)


# ── Webex (direct messages, and @mentions in spaces) ─────────────────────────────────────
WX = 'https://webexapis.com/v1'
def _wx(store, c, path, **params): return _api(store, c, WX, path, params=params)
def _wx_person(store, c, pid) -> dict:
    k = ('webex', 'person', pid)
    if k not in _MEMO: _MEMO[k] = _wx(store, c, f'/people/{quote(str(pid))}') or {}
    return _MEMO[k]


def test_webex(store, c) -> str:
    _need(c, 'sign-in', 'press Sign in with Webex on the card')
    me = _wx(store, c, '/people/me')
    _keep(store, c, me_id=me['id'], org_id=me.get('orgId') or '', me_name=me.get('displayName') or '')
    _seed_source(store, c, 'Webex')
    return f"signed in as {me.get('displayName')} - direct messages and the space messages that mention you flow in on the next sync"


def items_webex(store, c, since) -> list:
    me, org, out = _me(c), _cfg(c).get('org_id'), []
    for rm in _wx(store, c, '/rooms', sortBy='lastactivity', max=CAP).get('items') or []:
        if _when(rm.get('lastActivity')) < _new(since): break                       # newest first: the rest are older still
        dm = rm.get('type') == 'direct'
        for m in _wx(store, c, '/messages', roomId=rm['id'], max=10, **({} if dm else {'mentionedPeople': 'me'})).get('items') or []:
            if m.get('personId') == me: continue
            p = _wx_person(store, c, m['personId'])
            out.append(item(m['id'], rm.get('title') if not dm else f"Webex message from {p.get('displayName') or m.get('personEmail')}",
                            'Webex direct message' if dm else f"Webex - you were mentioned in {rm.get('title')}", m.get('text') or _text(m.get('html')),
                            p.get('displayName'), m.get('personEmail'), m['personId'],
                            _member(('webex', org, m['personId']), lambda: (p.get('orgId') == org) if org and p else None),
                            m.get('created'), None, 'Webex', conv=rm['id']))
    return out[:CAP]


# ── Zoom Team Chat (direct messages, and @mentions in channels) ──────────────────────────
ZM = 'https://api.zoom.us/v2'
def _zm(store, c, path, ok404=False, **params): return _req(c, 'get', f'{ZM}{path}', SIGN_IN, ok404=ok404, params=params, headers=_bear(store, c))


def test_zoom_chat(store, c) -> str:
    _need(c, 'sign-in', 'press Sign in with Zoom Team Chat on the card')
    me = _zm(store, c, '/users/me')
    name = me.get('display_name') or ' '.join(x for x in (me.get('first_name'), me.get('last_name')) if x)
    _keep(store, c, me_id=me['id'], me_email=me.get('email') or '', account_id=me.get('account_id') or '', me_name=name)
    _seed_source(store, c, 'Zoom Team Chat')
    return f"signed in as {name} - direct messages and the channel messages that mention you flow in on the next sync"


def items_zoom_chat(store, c, since) -> list:
    cfg, out = _cfg(c), []
    me, mail = _me(c), str(cfg.get('me_email') or '').lower()
    for se in (_zm(store, c, '/chat/users/me/sessions', page_size=CAP).get('sessions') or [])[:CAP]:
        dm = bool(se.get('peer_contact_email'))
        to = {'to_contact': se['peer_contact_email']} if dm else {'to_channel': se.get('channel_id')}
        if not (to.get('to_contact') or to.get('to_channel')): continue
        for m in _zm(store, c, '/chat/users/me/messages', page_size=10, **{'from': _utc(since)}, **to).get('messages') or []:
            who = str(m.get('sender') or '').lower()
            if who in (mail, me) or m.get('sender_member_id') == me: continue
            if not dm and not any(a.get('at_contact') in (me, mail) or a.get('at_type') == 2 for a in m.get('at_items') or []): continue
            out.append(item(m['id'], f"Zoom chat from {m.get('sender_display_name') or who}" if dm else se.get('name') or 'Zoom channel',
                            'Zoom Team Chat direct message' if dm else f"Zoom Team Chat - you were mentioned in {se.get('name') or 'a channel'}",
                            m.get('message'), m.get('sender_display_name') or who, who if '@' in who else None, who,
                            # one of the owner's own Zoom account answers /users/<email>; an outside contact is a 404 there
                            _member(('zoom_chat', cfg.get('account_id'), who), lambda: _zm(store, c, f'/users/{quote(who)}', ok404=True) is not None),
                            m.get('date_time') or m.get('timestamp'), None, 'Zoom Team Chat', conv=to.get('to_contact') or to.get('to_channel')))
    return out[:CAP]


# ── Threads (replies to your posts, and posts that mention you) ──────────────────────────
TH, TH_FIELDS = 'https://graph.threads.net/v1.0', 'id,text,username,timestamp,permalink'
def _th(store, c, path, **params): return _api(store, c, TH, path, params=params)


def test_threads(store, c) -> str:
    _need(c, 'sign-in', 'press Sign in with Threads on the card')
    me = _th(store, c, '/me', fields='id,username')
    _keep(store, c, me_id=me['id'], me_name=me.get('username') or '')
    _seed_source(store, c, f"@{me.get('username')}")
    return f"signed in as @{me.get('username')} - replies to your posts and posts that mention you flow in on the next sync"


def items_threads(store, c, since) -> list:
    me, mine = _me(c), _cfg(c).get('me_name')
    got = [(p, 'mention', p['id']) for p in _th(store, c, f'/{me}/mentions', fields=TH_FIELDS, since=int(since.timestamp())).get('data') or []]
    for post in _th(store, c, f'/{me}/threads', fields='id,timestamp', limit=10).get('data') or []:
        got += [(r, 'reply', post['id']) for r in _th(store, c, f"/{post['id']}/replies", fields=TH_FIELDS).get('data') or []]
    # Threads has no colleagues: every reply and mention is a stranger's, however often they write
    return [item(p['id'], f"@{p.get('username') or 'someone'} {'mentioned you' if how == 'mention' else 'replied'} on Threads",
                 f'Threads {how}', p.get('text'), p.get('username'), None, p.get('username'), False, p.get('timestamp'), p.get('permalink'),
                 'Threads', conv=post) for p, how, post in got if p.get('username') != mine][:CAP]


# ── HubSpot (tickets and tasks assigned to you) ──────────────────────────────────────────
HS = 'https://api.hubapi.com'
def _hs(store, c, path, method='get', **kw): return _api(store, c, HS, path, method, **kw)


def test_hubspot(store, c) -> str:
    from . import oauth
    _need(c, 'sign-in', 'press Sign in with HubSpot on the card')
    t = _hs(store, c, f'/oauth/v1/access-tokens/{quote(oauth.access(store, c))}')
    own = next((o for o in _hs(store, c, '/crm/v3/owners', params={'email': t.get('user'), 'limit': 1}).get('results') or []), None)
    if not own: raise RuntimeError(f"{t.get('user')} is not a HubSpot owner in this account, so nothing can be assigned to it")
    _keep(store, c, me_id=str(own['id']), hub_id=str(t.get('hub_id') or ''), me_name=t.get('user') or '')
    _seed_source(store, c, t.get('hub_domain') or 'HubSpot')
    return f"signed in as {t.get('user')} - tickets and open tasks assigned to you flow in on the next sync"


def _hs_find(store, c, kind, props, since, *more) -> list:
    f = [{'propertyName': 'hubspot_owner_id', 'operator': 'EQ', 'value': _me(c)},
         {'propertyName': 'hs_lastmodifieddate', 'operator': 'GT', 'value': str(_since_ms(since))}, *more]
    return _hs(store, c, f'/crm/v3/objects/{kind}/search', 'post', json={'filterGroups': [{'filters': f}], 'properties': props, 'limit': CAP,
               'sorts': [{'propertyName': 'hs_lastmodifieddate', 'direction': 'DESCENDING'}]}).get('results') or []


def items_hubspot(store, c, since) -> list:
    hub = _cfg(c).get('hub_id')
    link = lambda kind, i: f'https://app.hubspot.com/contacts/{hub}/record/{kind}/{i}'
    tix = [item(t['id'], (p := t.get('properties') or {}).get('subject') or f"Ticket {t['id']}",
                f"HubSpot ticket - priority {p.get('hs_ticket_priority') or 'none'} · assigned to you", p.get('content'),
                None, None, None, None, p.get('hs_lastmodifieddate'), link('0-5', t['id']), 'HubSpot')     # a ticket is a customer's words
           for t in _hs_find(store, c, 'tickets', ['subject', 'content', 'hs_ticket_priority', 'hs_lastmodifieddate'], since)]
    tasks = [item(t['id'], (p := t.get('properties') or {}).get('hs_task_subject') or f"Task {t['id']}",
                  f"HubSpot task - {str(p.get('hs_task_status') or '').lower().replace('_', ' ')} · priority {p.get('hs_task_priority') or 'none'}"
                  + (f" · due {str(p['hs_timestamp'])[:10]}" if p.get('hs_timestamp') else ''), _text(p.get('hs_task_body')),
                  None, None, p.get('hs_created_by_user_id'), True if p.get('hs_created_by_user_id') else None,   # a task is made by a user of the account
                  p.get('hs_lastmodifieddate'), link('0-27', t['id']), 'HubSpot')
             for t in _hs_find(store, c, 'tasks', ['hs_task_subject', 'hs_task_body', 'hs_task_status', 'hs_task_priority', 'hs_timestamp',
                                                   'hs_lastmodifieddate', 'hs_created_by_user_id'], since,
                               {'propertyName': 'hs_task_status', 'operator': 'NEQ', 'value': 'COMPLETED'})]
    return (tix + tasks)[:CAP]


# ── Salesforce (cases and tasks assigned to you) ─────────────────────────────────────────
SF_V = 'v62.0'
def _sf_base(c) -> str:
    h = str(_cfg(c).get('host') or '').rstrip('/')
    if not re.fullmatch(r'https://[a-z0-9.-]+\.(salesforce|force)\.com', h, re.I):
        raise RuntimeError('Salesforce has not named your instance yet - press Sign in on the card')
    return h
def _sf(store, c, path, **params): return _api(store, c, _sf_base(c), path, params=params)
def _sf_id(v) -> str:
    if not re.fullmatch(r'[A-Za-z0-9]{15,18}', str(v or '')): raise RuntimeError('who you are on Salesforce is not known yet - run Test on the card once')
    return str(v)


def test_salesforce(store, c) -> str:
    _need(c, 'sign-in', 'press Sign in with Salesforce on the card')
    me = _sf(store, c, '/services/oauth2/userinfo')
    _keep(store, c, me_id=_sf_id(me.get('user_id')), org_id=me.get('organization_id') or '', me_name=me.get('name') or '')
    _seed_source(store, c, _host(_sf_base(c)))
    return f"signed in as {me.get('name')} - open cases and tasks assigned to you flow in on the next sync"


def items_salesforce(store, c, since) -> list:
    base, me, at = _sf_base(c), _sf_id(_me(c)), _utc(since)
    q = lambda soql: _sf(store, c, f'/services/data/{SF_V}/query', q=soql).get('records') or []
    who = 'CreatedById, CreatedBy.Name, CreatedBy.Email, CreatedBy.UserType'
    std = lambda r: (r.get('CreatedBy') or {}).get('UserType') == 'Standard' if (r.get('CreatedBy') or {}).get('UserType') else None
    out = []
    for r in q(f"SELECT Id, CaseNumber, Subject, Description, Status, Priority, LastModifiedDate, ContactId, Contact.Name, Contact.Email, {who} "
               f"FROM Case WHERE OwnerId = '{me}' AND IsClosed = false AND LastModifiedDate > {at} ORDER BY LastModifiedDate DESC LIMIT {CAP}"):
        k, b = r.get('Contact') or {}, r.get('CreatedBy') or {}
        # a case with a contact is the customer's words; one a colleague opened is theirs
        out.append(item(r['Id'], f"Case {r.get('CaseNumber')}: {r.get('Subject') or ''}".strip(),
                        f"Salesforce case - {r.get('Status')} · priority {r.get('Priority')}",
                        r.get('Description'), k.get('Name') or b.get('Name'), k.get('Email') or b.get('Email'), r.get('ContactId') or r.get('CreatedById'),
                        False if r.get('ContactId') else std(r), r.get('LastModifiedDate'), f"{base}/{r['Id']}", _host(base)))
    for r in q(f"SELECT Id, Subject, Description, Status, Priority, ActivityDate, LastModifiedDate, {who} "
               f"FROM Task WHERE OwnerId = '{me}' AND IsClosed = false AND LastModifiedDate > {at} ORDER BY LastModifiedDate DESC LIMIT {CAP}"):
        b = r.get('CreatedBy') or {}
        out.append(item(r['Id'], r.get('Subject') or 'Salesforce task', f"Salesforce task - {r.get('Status')} · priority {r.get('Priority')}"
                        + (f" · due {r['ActivityDate']}" if r.get('ActivityDate') else ''), r.get('Description'), b.get('Name'), b.get('Email'),
                        r.get('CreatedById'), std(r), r.get('LastModifiedDate'), f"{base}/{r['Id']}", _host(base)))
    return out[:CAP]


# ── DocuSign (envelopes waiting on your signature) ───────────────────────────────────────
def _ds_auth(c) -> str: return 'account-d.docusign.com' if str(_cfg(c).get('auth_host') or '').startswith('account-d') else 'account.docusign.com'
def _ds_base(c) -> str:
    h = str(_cfg(c).get('host') or '')
    if not re.fullmatch(r'https://[a-z0-9.-]+\.docusign\.(net|com)/restapi/v2\.1/accounts/[0-9a-f-]+', h, re.I):
        raise RuntimeError('which DocuSign account to read is not known yet - run Test on the card once')
    return h


def test_docusign(store, c) -> str:
    _need(c, 'sign-in', 'press Sign in with DocuSign on the card')
    me = _api(store, c, f'https://{_ds_auth(c)}', '/oauth/userinfo')
    a = next((a for a in me.get('accounts') or [] if a.get('is_default')), (me.get('accounts') or [None])[0])
    if not a: raise RuntimeError('DocuSign signed you in, but names no account')
    _keep(store, c, host=f"{str(a['base_uri']).rstrip('/')}/restapi/v2.1/accounts/{a['account_id']}", account_id=a['account_id'],
          me_name=me.get('name') or '', me_email=me.get('email') or '')
    _ds_base(again := store.get_connector(c['ConnectorId'], with_secret=True))
    _seed_source(store, again, a.get('account_name') or 'DocuSign')
    return f"signed in as {me.get('name')} on {a.get('account_name')} - envelopes waiting on your signature flow in on the next sync"


def items_docusign(store, c, since) -> list:
    cfg, base = _cfg(c), _ds_base(c)
    app = 'https://appdemo.docusign.com' if _ds_auth(c).startswith('account-d') else 'https://app.docusign.com'
    j = _api(store, c, base, '/envelopes', params={'folder_ids': 'awaiting_my_signature', 'from_date': _utc(since - timedelta(days=30)), 'count': CAP})
    return [item(e['envelopeId'], e.get('emailSubject') or 'An envelope to sign',
                 f"DocuSign envelope - waiting on your signature · sent {str(e.get('sentDateTime') or '')[:10]}", e.get('emailBlurb'),
                 (s := e.get('sender') or {}).get('userName'), s.get('email'), s.get('userId') or s.get('email'),
                 (s.get('accountId') == cfg.get('account_id')) if s.get('accountId') else None,     # your own DocuSign account is your company
                 e.get('statusChangedDateTime') or e.get('sentDateTime'), f"{app}/documents/details/{e['envelopeId']}", 'DocuSign')
            for e in j.get('envelopes') or []]


# ── Basecamp (to-dos assigned to you; Pings and @mentions in your Hey! menu) ──────────────
BC_UA = {'User-Agent': 'Taskuary (https://github.com/ldbumble/taskuary)'}       # Basecamp refuses a call that does not say who makes it
def _bc_base(c) -> str:
    h = str(_cfg(c).get('host') or '').rstrip('/')
    if not re.fullmatch(r'https://[0-9]+\.basecampapi\.com/[0-9]+', h):
        raise RuntimeError('which Basecamp account to read is not known yet - run Test on the card once')
    return h
def _bc(store, c, path, **params): return _api(store, c, _bc_base(c), path, h=BC_UA, params=params)
def _bc_member(p) -> bool | None:
    "Basecamp's own word: a client (or an outsider) is a stranger; a User of the account who is no client is the team."
    if not p: return None
    return not p.get('client') and p.get('personable_type') in ('User', None)


def test_basecamp_todos(store, c) -> str:
    _need(c, 'sign-in', 'press Sign in with Basecamp on the card')
    who = _api(store, c, 'https://launchpad.37signals.com', '/authorization.json', h=BC_UA)
    a = next((a for a in who.get('accounts') or [] if a.get('product') in ('bc3', 'bc4')), None)
    if not a: raise RuntimeError('this Basecamp sign-in has no Basecamp account on it')
    _keep(store, c, host=a['href'], account_name=a.get('name') or '')
    me = _bc(store, again := store.get_connector(c['ConnectorId'], with_secret=True), '/my/profile.json')
    _keep(store, c, me_id=str(me['id']), me_name=me.get('name') or '')
    _seed_source(store, again, a.get('name') or 'Basecamp')
    return f"signed in as {me.get('name')} on {a.get('name')} - to-dos assigned to you, Pings and @mentions flow in on the next sync"


def items_basecamp_todos(store, c, since) -> list:
    base, out = _bc_base(c), []
    j = _bc(store, c, '/my/assignments.json')
    for t in [*(j.get('priorities') or []), *(j.get('non_priorities') or [])][:CAP]:
        if t.get('completed'): continue
        b = t.get('bucket') or {}
        d = _bc(store, c, f"/buckets/{int(b['id'])}/todos/{int(t['id'])}.json") if b.get('id') else {}      # its creator, and when it changed
        p = d.get('creator') or {}
        out.append(item(t['id'], t.get('content') or 'A to-do', f"Basecamp to-do in {b.get('name') or 'a project'} · assigned to you"
                        + (f" · due {t['due_on']}" if t.get('due_on') else ''), _text(d.get('description')), p.get('name'), p.get('email_address'),
                        p.get('id'), _bc_member(p), d.get('updated_at'), t.get('app_url'), b.get('name') or 'Basecamp'))
    for r in _bc(store, c, '/my/readings.json').get('unreads') or []:
        if r.get('section') not in ('pings', 'mentions'): continue
        p = r.get('creator') or {}
        if str(p.get('id')) == str(_cfg(c).get('me_id')): continue
        out.append(item(f"r{r['id']}", r.get('title') or 'Basecamp', f"Basecamp {'Ping' if r['section'] == 'pings' else 'mention'}"
                        + (f" in {r['bucket_name']}" if r.get('bucket_name') else ''), r.get('content_excerpt'), p.get('name'), p.get('email_address'),
                        p.get('id'), _bc_member(p), r.get('unread_at') or r.get('created_at'), r.get('app_url'), r.get('bucket_name') or 'Basecamp',
                        conv=r.get('readable_sgid') if r['section'] == 'pings' else None))
    return out[:CAP]


# ── Mailgun (stored mail, polled - no public address) ────────────────────────────────────
def _mg_base(c) -> str:
    h = str(_cfg(c).get('host') or 'https://api.mailgun.net').rstrip('/')
    if h not in ('https://api.mailgun.net', 'https://api.eu.mailgun.net'):
        raise RuntimeError('the Mailgun address is https://api.mailgun.net, or https://api.eu.mailgun.net for an EU account')
    return h
def _mg_domain(c) -> str:
    d = str(_cfg(c).get('domain') or '').strip().lower()
    if not re.fullmatch(r'[a-z0-9.-]+\.[a-z]{2,}', d): raise RuntimeError('no receiving domain set - the domain your Mailgun route stores mail for')
    return d
def _mg(c, path, **params):
    return _req(c, 'get', f'{_mg_base(c)}{path}', 'check the private API key (app.mailgun.com, the API Security page of your account menu)',
                params=params, auth=('api', c.get('Secret') or ''))


def test_mailgun(store, c) -> str:
    _need(c, 'private API key', 'app.mailgun.com, in the API Security page of your account menu')
    d = _mg_domain(c)
    _mg(c, f'/v3/{d}/events', event='stored', limit=1)
    _seed_source(store, c, d)
    return f"connected to {d} - mail a route stores (its action store()) flows in on the next sync"


def items_mailgun(store, c, since) -> list:
    d, out = _mg_domain(c), []
    for e in _mg(c, f'/v3/{d}/events', event='stored', begin=int(since.timestamp()), ascending='yes', limit=CAP).get('items') or []:
        k = (e.get('storage') or {}).get('key')
        if not k or not re.fullmatch(r'[A-Za-z0-9=_-]+', k): continue
        m = _mg(c, f'/v3/domains/{d}/messages/{k}')
        h = (e.get('message') or {}).get('headers') or {}
        name, mail = _parse_from(m.get('from') or h.get('from'))
        out.append(item(h.get('message-id') or k, m.get('subject') or h.get('subject') or '(no subject)', f"Mail to {m.get('recipient') or d} (Mailgun)",
                        m.get('stripped-text') or m.get('body-plain') or _text(m.get('body-html')), name, mail, mail, None,
                        _epoch(e.get('timestamp')), 'https://app.mailgun.com/', d))
    return out


def _epoch(v):
    "Mailgun's event time: seconds as its events say, or nanoseconds as its reference shows - unix seconds either way."
    try: t = float(v)
    except (TypeError, ValueError): return None
    return int(t / 1e9 if t > 1e14 else t / 1e3 if t > 1e11 else t)


def _parse_from(v):
    from email.utils import parseaddr
    n, a = parseaddr(str(v or ''))
    return (n or a or None), (a.lower() or None)


# ── the ones that only PUSH (pushin.py): LINE, SendGrid Inbound Parse - the queue the webhook filled, drained once ──
def _hook(c) -> str:
    return f"point it at https://<your public address>/api/inbound/{c['Type']}/{c['ConnectorId']}" + ('/<the key the card shows>' if c['Type'] == 'sendgrid' else '')
LN = 'https://api.line.me'
def _ln(c, path): return _req(c, 'get', f'{LN}{path}', 'check the channel access token (the LINE Developers Console, your channel\'s Messaging API tab)',
                              headers={'Authorization': f"Bearer {c.get('Secret') or ''}"})


def test_line(store, c) -> str:
    _need(c, 'channel access token', "the LINE Developers Console, on your channel's Messaging API tab")
    if not _cfg(c).get('channel_secret'): raise RuntimeError("no channel secret saved - the Basic settings tab of your channel; without it no push can be checked")
    b = _ln(c, '/v2/bot/info')
    _keep(store, c, me_id=b.get('userId') or '', me_name=b.get('displayName') or '')
    _seed_source(store, c, b.get('displayName') or 'LINE')
    return f"connected as {b.get('displayName')} ({b.get('basicId')}) - set the channel's Webhook URL ({_hook(c)}) and turn Use webhook on"


def items_line(store, c, since) -> list:
    from . import pushin
    out = []
    for e in pushin.drain(store, c):
        s, m = e.get('source') or {}, e.get('message') or {}
        uid = s.get('userId')
        k = ('line', 'name', uid)
        if uid and k not in _MEMO:
            try: _MEMO[k] = (_ln(c, f'/v2/bot/profile/{quote(uid)}') or {}).get('displayName')
            except Exception as x: _MEMO[k] = None; logger.debug(f'line: profile unread ({x})')
        who = _MEMO.get(k) or 'someone on LINE'
        out.append(item(m.get('id') or e.get('webhookEventId'), f"LINE message from {who}", f"LINE {s.get('type') or 'user'} message",
                        m.get('text') if m.get('type') == 'text' else f"(a {m.get('type') or 'message'} - open LINE to see it)", who, None, uid,
                        False, e.get('timestamp'), None, 'LINE', conv=s.get('groupId') or s.get('roomId') or uid, drained=True))   # a customer: a stranger
    return out


def test_sendgrid(store, c) -> str:
    _need(c, 'API key', 'app.sendgrid.com, in the API Keys page under Settings')
    _req(c, 'get', 'https://api.sendgrid.com/v3/scopes', 'check the API key', headers={'Authorization': f"Bearer {c.get('Secret') or ''}"})
    _seed_source(store, c, 'SendGrid Inbound Parse')
    return f"the key works - add an Inbound Parse host and {_hook(c)}"


def items_sendgrid(store, c, since) -> list:
    from . import pushin
    out = []
    for m in pushin.drain(store, c):
        name, mail = _parse_from(m.get('from'))
        out.append(item(m.get('message_id') or f"{mail}:{m.get('at')}", m.get('subject') or '(no subject)', f"Mail to {m.get('to')} (SendGrid Inbound Parse)",
                        m.get('text') or _text(m.get('html')), name, mail, mail, None, int(m['at']) if m.get('at') else None, None, 'SendGrid', drained=True))
    return out


# ═══ CARDS THAT ARE ALSO KEYED READS (apireads.json) ═════════════════════════════════════════════════════════════════════════
# The same card is a report and agent read (`<type>_read`) and a source: one key, one request road (apireads.get - no redirect, nothing
# but reads), so the poll and a report can never disagree on where the card's key goes.
def _kapi(c, path, **params):
    from . import apireads
    return apireads.get(c['Type'], _cfg(c), c.get('Secret') or '', path, params or None)
def _api_base(c) -> str:
    from . import apireads
    return apireads.base_of(c['Type'], _cfg(c), c.get('Secret') or '')
def _lines(xs, qty='quantity', name='name') -> list: return [f"{x.get(qty)} × {x.get(name)}" for x in xs or []]
def _person(a) -> str | None: return ' '.join(x for x in ((a or {}).get('first_name'), (a or {}).get('last_name')) if x) or None


# ── WooCommerce (orders paid and waiting to ship) ────────────────────────────────────────
def test_woocommerce(store, c) -> str:
    _need(c, 'consumer secret', 'WooCommerce: Settings, then Advanced, then REST API - add a Read key')
    _kapi(c, '/orders', per_page=1)
    _seed_source(store, c, _host(_cfg(c).get('host') or 'WooCommerce'))
    return 'connected - orders paid and waiting to ship (processing) flow in on the next sync'


def items_woocommerce(store, c, since) -> list:
    site = str(_cfg(c).get('host') or '').rstrip('/')
    site = site if site.startswith('http') else f'https://{site}'
    return [item(o['id'], f"Order #{o.get('number') or o['id']} to ship", f"WooCommerce order - processing · {o.get('total')} {o.get('currency')}",
                 '\n'.join([*_lines(o.get('line_items')), *([f"Customer note: {o['customer_note']}"] if o.get('customer_note') else [])]),
                 _person(o.get('billing')), (o.get('billing') or {}).get('email'), None, None,    # a customer wrote nothing: no author
                 f"{o['date_modified_gmt']}Z" if o.get('date_modified_gmt') else o.get('date_modified'),
                 f"{site}/wp-admin/post.php?post={o['id']}&action=edit", _host(site))
            for o in _kapi(c, '/orders', status='processing', modified_after=_utc(since), per_page=CAP, orderby='modified') or []]


# ── BigCommerce (orders awaiting fulfillment) ────────────────────────────────────────────
def test_bigcommerce(store, c) -> str:
    _need(c, 'API account access token', 'BigCommerce: Settings, then Store-level API accounts - Orders read-only')
    st = _kapi(c, '/v2/store')
    _seed_source(store, c, st.get('name') or 'BigCommerce')
    return f"connected to {st.get('name')} - orders awaiting fulfillment flow in on the next sync"


def items_bigcommerce(store, c, since) -> list:
    from email.utils import parsedate_to_datetime
    when = lambda v: parsedate_to_datetime(v).isoformat() if v else None              # v2 orders keep RFC 2822 dates
    js = _kapi(c, '/v2/orders', status_id=11, min_date_modified=_utc(since), sort='date_modified:desc', limit=CAP)
    hsh = _cfg(c).get('store_hash')
    return [item(o['id'], f"Order {o['id']} to fulfil", f"BigCommerce order - {o.get('status')} · {o.get('total_inc_tax')} {o.get('currency_code')}",
                 '\n'.join(x for x in (f"{o.get('items_total')} items", o.get('customer_message') and f"Customer message: {o['customer_message']}",
                                        o.get('staff_notes') and f"Staff notes: {o['staff_notes']}") if x),
                 _person(o.get('billing_address')), (o.get('billing_address') or {}).get('email'), None, None, when(o.get('date_modified')),
                 f"https://store-{hsh}.mybigcommerce.com/manage/orders/{o['id']}", 'BigCommerce')
            for o in (js if isinstance(js, list) else [])]                          # no orders: an empty 204, not a list


TESTS = {t: globals()[f'test_{t}'] for t in NAMES}
ITEMS = {t: globals()[f'items_{t}'] for t in NAMES}
# ...and the shared inboxes, phones, forms, hiring and money that wait on you (waiting.py): the same road, one module of their own
from . import waiting
NAMES |= waiting.NAMES; TESTS |= waiting.TESTS; ITEMS |= waiting.ITEMS
TYPES = tuple(NAMES)

def test(store, c) -> str: return TESTS[c['Type']](store, c)


def poll(store, c, since, llm=None, file_only=False) -> int:
    from .ingest import ingest_tracker
    t, n = c['Type'], 0
    try: xs = ITEMS[t](store, c, since)
    except requests.RequestException as e: raise RuntimeError(f'{NAMES[t]} poll failed: {e}') from e
    for x in xs:
        if x['at'] and not x['drained'] and _when(x['at']) < _new(since): continue
        n += ingest_tracker(store, file_only=file_only, llm=llm, msg={
            'external_id': f"{t}:{x['id']}", 'channel': t, 'conversation_id': f"{t}:{x['conv'] or x['id']}",
            'subject': str(x['subject'] or NAMES[t])[:300], 'body': f"[{x['head']}]\n{str(x['body'] or '(no description)')[:20000]}",
            'from_name': x['who'] or NAMES[t], 'from_email': x['email'], 'sent_at': _when(x['at']) if x['at'] else datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source_link': x['link'], 'source_name': x['place'] or NAMES[t], **author_meta(t, x['uid'], x['member'])})
    return n
