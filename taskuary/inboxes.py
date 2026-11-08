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
         'calendly': 'Calendly', 'shipstation': 'ShipStation', 'shopify': 'Shopify', 'square': 'Square', 'paypal': 'PayPal'}
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
    return _req(c, 'get', f'{SC}{path}', 'check the API token (Settings → Your account → API Tokens)', params=params,
                headers={'Shortcut-Token': c.get('Secret') or '', 'Content-Type': 'application/json'})


def test_shortcut(store, c) -> str:
    _need(c, 'API token', 'Shortcut: Settings → Your account → API Tokens → Generate token')
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
    _need(c, 'token', 'GitHub → Settings → Developer settings → a token with read:project (and repo for private repos)')
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
    if not re.fullmatch(r'UC[\w-]{22}', ch): raise RuntimeError('no channel id set - it starts UC (YouTube Studio → Settings → Channel → Advanced)')
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
    return _req(c, 'get', f'https://ssapi.shipstation.com{path}', 'check the API key and secret (Settings → Account → API Settings)', params=params,
                auth=(_cfg(c).get('api_key') or '', c.get('Secret') or ''))


def test_shipstation(store, c) -> str:
    _need(c, 'API secret', 'ShipStation: Settings → Account → API Settings shows the key and the secret')
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
    _need(c, 'Admin API access token', 'Shopify admin → Settings → Apps and sales channels → Develop apps → your app → API credentials')
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


TYPES = tuple(NAMES)
TESTS = {t: globals()[f'test_{t}'] for t in TYPES}
ITEMS = {t: globals()[f'items_{t}'] for t in TYPES}

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
