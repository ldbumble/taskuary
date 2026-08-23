"""Developer-tool inboxes: GitLab, Azure DevOps, Linear, Trello, Notion, Discord, Sentry
and PagerDuty as trigger channels - same shape as pm.py. The item that matters is the one
POINTED AT YOU (assigned issue/MR/work item/card, a new unresolved error, an open incident,
a message in a watched channel); it lands on the Timeline and goes through the same triage
as mail. Each polls its own API with the owner's token; only Discord can carry a reply back
(a bot may post) - everything else is read-only by nature.
"""
import json
from datetime import datetime
import requests
from loguru import logger

from .pm import CAP, _cfg, _seed_source, _stamp


def _die(r, who, hint):
    if r.status_code in (401, 403): raise RuntimeError(f'{who} said {r.status_code} - {hint}')
    r.raise_for_status()


def _new(since): return since.strftime('%Y-%m-%d %H:%M:%S')     # local wall-clock floor


# ── GitLab ───────────────────────────────────────────────────────────────────────────────
def _gitlab(c, path, **params):
    base = (_cfg(c).get('base_url') or 'https://gitlab.com').strip().rstrip('/')
    r = requests.get(f'{base}/api/v4{path}', params=params, timeout=30,
                     headers={'PRIVATE-TOKEN': c.get('Secret') or ''})
    _die(r, 'GitLab', 'check the Personal Access Token (scope: read_api)')
    return r.json()


def test_gitlab(store, c) -> str:
    if not c.get('Secret'): raise RuntimeError('no token saved - GitLab: avatar → Preferences → Access tokens (scope read_api)')
    me = _gitlab(c, '/user')
    host = (_cfg(c).get('base_url') or 'https://gitlab.com').split('//', 1)[-1].rstrip('/')
    _seed_source(store, c, host)
    return f"authenticated as {me.get('name') or me.get('username')} on {host} - issues and MRs assigned to you flow in on the next sync"


def poll_gitlab(store, c, since, llm=None, file_only=False) -> int:
    from .ingest import ingest_message
    after, n = since.astimezone().isoformat(), 0
    items = ([('issue', i) for i in _gitlab(c, '/issues', scope='assigned_to_me', updated_after=after, per_page=CAP)]
             + [('merge request', m) for m in _gitlab(c, '/merge_requests', scope='assigned_to_me', updated_after=after, per_page=CAP)])
    for kind, i in items:
        who = (i.get('author') or {})
        proj = '/'.join(str(i.get('web_url') or '').split('/')[3:5]) or 'GitLab'
        out = ingest_message(store, file_only=file_only, msg={
            'external_id': f"gitlab:{kind[0]}{i['id']}", 'channel': 'gitlab',
            'subject': f"{'!' if kind[0] == 'm' else '#'}{i.get('iid')} {i.get('title') or ''}".strip(),
            'body': f"[GitLab {kind} in {proj} - state {i.get('state')} - assigned to you]\n"
                    f"{str(i.get('description') or '(no description)')[:20000]}",
            'from_name': who.get('name') or 'GitLab', 'conversation_id': f"gitlab:{kind[0]}{i['id']}",
            'sent_at': _stamp(i.get('updated_at')), 'source_link': i.get('web_url'), 'source_name': proj}, llm=llm)
        n += out['status'] != 'duplicate'
    return n


# ── Azure DevOps ─────────────────────────────────────────────────────────────────────────
def _azdo_base(c) -> str:
    org = (_cfg(c).get('org_url') or '').strip().rstrip('/')
    if not org: raise RuntimeError('no organization URL set - enter https://dev.azure.com/yourorg under Credentials')
    return org if org.startswith('http') else f'https://dev.azure.com/{org}'


def _azdo(c, method, path, **kw):
    r = requests.request(method, f'{_azdo_base(c)}{path}', timeout=30, auth=('', c.get('Secret') or ''), **kw)
    _die(r, 'Azure DevOps', 'check the PAT (scope: Work Items read)')
    return r.json()


def test_azdo(store, c) -> str:
    if not c.get('Secret'): raise RuntimeError('no PAT saved - Azure DevOps: User settings → Personal access tokens (Work Items: Read)')
    j = _azdo(c, 'get', '/_apis/projects?api-version=7.0')
    _seed_source(store, c, _azdo_base(c).split('//', 1)[-1])
    return f"authenticated - {j.get('count', 0)} project(s) visible - work items assigned to you flow in on the next sync"


def poll_azdo(store, c, since, llm=None, file_only=False) -> int:
    from .ingest import ingest_message
    # WIQL dates are day-precision, so the query over-fetches and the watermark filters below
    wiql = ("Select [System.Id] From WorkItems Where [System.AssignedTo] = @Me "
            f"And [System.ChangedDate] >= '{since.strftime('%Y-%m-%d')}' Order By [System.ChangedDate] Asc")
    ids = [str(w['id']) for w in _azdo(c, 'post', '/_apis/wit/wiql?api-version=7.0', json={'query': wiql}).get('workItems') or []][:CAP]
    if not ids: return 0
    j = _azdo(c, 'get', f"/_apis/wit/workitems?ids={','.join(ids)}&api-version=7.0")
    base, n = _azdo_base(c), 0
    for w in j.get('value') or []:
        f = w.get('fields') or {}
        if _stamp(f.get('System.ChangedDate')) < _new(since): continue
        proj = f.get('System.TeamProject') or ''
        out = ingest_message(store, file_only=file_only, msg={
            'external_id': f"azdo:{w['id']}", 'channel': 'azdo',
            'subject': f"#{w['id']} {f.get('System.Title') or ''}".strip(),
            'body': f"[Azure DevOps {f.get('System.WorkItemType') or 'work item'} in {proj} - "
                    f"state {f.get('System.State')} - assigned to you]\n"
                    f"{str(f.get('System.Description') or '(no description)')[:20000]}",
            'from_name': ((f.get('System.CreatedBy') or {}).get('displayName')
                          if isinstance(f.get('System.CreatedBy'), dict) else f.get('System.CreatedBy')) or 'Azure DevOps',
            'conversation_id': f"azdo:{w['id']}", 'sent_at': _stamp(f.get('System.ChangedDate')),
            'source_link': f'{base}/{proj}/_workitems/edit/{w["id"]}', 'source_name': proj or 'Azure DevOps'}, llm=llm)
        n += out['status'] != 'duplicate'
    return n


# ── Linear ───────────────────────────────────────────────────────────────────────────────
def _linear(c, query: str):
    r = requests.post('https://api.linear.app/graphql', json={'query': query}, timeout=30,
                      headers={'Authorization': c.get('Secret') or ''})
    _die(r, 'Linear', 'check the API key (Settings → Security & access → Personal API keys)')
    j = r.json()
    if j.get('errors'): raise RuntimeError(f"linear: {j['errors'][0].get('message') or j['errors']}")
    return j['data']


def test_linear(store, c) -> str:
    if not c.get('Secret'): raise RuntimeError('no API key saved - Linear: Settings → Security & access → Personal API keys')
    me = _linear(c, '{ viewer { name email } }')['viewer']
    _seed_source(store, c, me.get('name') or 'Linear')
    return f"authenticated as {me.get('name')} - issues assigned to you flow in on the next sync"


def poll_linear(store, c, since, llm=None, file_only=False) -> int:
    from .ingest import ingest_message
    iso = since.astimezone().isoformat()
    data = _linear(c, '{ issues(filter: {assignee: {isMe: {eq: true}}, updatedAt: {gt: "%s"}}, first: %d) '
                      '{ nodes { identifier title description url updatedAt state { name } '
                      'creator { name } project { name } } } }' % (iso, CAP))
    n = 0
    for i in (data.get('issues') or {}).get('nodes') or []:
        proj = (i.get('project') or {}).get('name')
        out = ingest_message(store, file_only=file_only, msg={
            'external_id': f"linear:{i['identifier']}", 'channel': 'linear',
            'subject': f"{i['identifier']} {i.get('title') or ''}".strip(),
            'body': f"[Linear issue{f' in {proj}' if proj else ''} - state {((i.get('state') or {}).get('name'))} - assigned to you]\n"
                    f"{str(i.get('description') or '(no description)')[:20000]}",
            'from_name': ((i.get('creator') or {}).get('name')) or 'Linear',
            'conversation_id': f"linear:{i['identifier']}", 'sent_at': _stamp(i.get('updatedAt')),
            'source_link': i.get('url'), 'source_name': proj or 'Linear'}, llm=llm)
        n += out['status'] != 'duplicate'
    return n


# ── Trello ───────────────────────────────────────────────────────────────────────────────
def _trello(c, path, **params):
    r = requests.get(f'https://api.trello.com/1{path}', timeout=30,
                     params={**params, 'key': _cfg(c).get('api_key') or '', 'token': c.get('Secret') or ''})
    _die(r, 'Trello', 'check the API key + token (trello.com/power-ups/admin → API key → Token)')
    return r.json()


def test_trello(store, c) -> str:
    if not (_cfg(c).get('api_key') and c.get('Secret')):
        raise RuntimeError('need the API key (under Credentials) AND the token (write-only) - trello.com/power-ups/admin')
    me = _trello(c, '/members/me', fields='fullName,username')
    _seed_source(store, c, me.get('fullName') or me.get('username') or 'Trello')
    return f"authenticated as {me.get('fullName') or me.get('username')} - cards assigned to you flow in on the next sync"


def poll_trello(store, c, since, llm=None, file_only=False) -> int:
    from .ingest import ingest_message
    cards = _trello(c, '/members/me/cards', filter='open',
                    fields='name,desc,dateLastActivity,url,idBoard', boards='open', board_fields='name')
    n = 0
    for t in cards[:200]:
        if _stamp(t.get('dateLastActivity')) < _new(since): continue
        board = ((t.get('board') or {}).get('name')) or 'Trello'
        out = ingest_message(store, file_only=file_only, msg={
            'external_id': f"trello:{t['id']}", 'channel': 'trello',
            'subject': (t.get('name') or '').strip() or 'Trello card',
            'body': f"[Trello card on \"{board}\" - assigned to you]\n{str(t.get('desc') or '(no description)')[:20000]}",
            'from_name': 'Trello', 'conversation_id': f"trello:{t['id']}",
            'sent_at': _stamp(t.get('dateLastActivity')), 'source_link': t.get('url'), 'source_name': board}, llm=llm)
        n += out['status'] != 'duplicate'
    return n


# ── Notion ───────────────────────────────────────────────────────────────────────────────
def _notion(c, method, path, **kw):
    r = requests.request(method, f'https://api.notion.com/v1{path}', timeout=30,
                         headers={'Authorization': f"Bearer {c.get('Secret') or ''}", 'Notion-Version': '2022-06-28'}, **kw)
    _die(r, 'Notion', 'check the integration secret (notion.so/my-integrations) - and share the pages with the integration')
    return r.json()


def _notion_title(page) -> str:
    for p in (page.get('properties') or {}).values():
        if p.get('type') == 'title':
            return ''.join(t.get('plain_text') or '' for t in p.get('title') or []) or 'Untitled'
    return 'Untitled'


def test_notion(store, c) -> str:
    if not c.get('Secret'): raise RuntimeError('no integration secret saved - create one at notion.so/my-integrations, then share pages with it')
    me = _notion(c, 'get', '/users/me')
    _seed_source(store, c, me.get('name') or 'Notion')
    return (f"authenticated as {me.get('name') or 'the integration'} - pages shared with it show on the "
            'Timeline as they change (a feed: Notion edits are information, not assignments)')


def poll_notion(store, c, since, llm=None, file_only=False) -> int:
    from .ingest import ingest_message
    j = _notion(c, 'post', '/search', json={'filter': {'property': 'object', 'value': 'page'},
                                            'sort': {'direction': 'descending', 'timestamp': 'last_edited_time'},
                                            'page_size': CAP})
    n = 0
    for p in j.get('results') or []:
        at = _stamp(p.get('last_edited_time'))
        if at < _new(since): continue
        out = ingest_message(store, file_only=file_only, msg={
            'external_id': f"notion:{p['id']}:{str(p.get('last_edited_time') or '')[:16]}", 'channel': 'notion',
            'subject': _notion_title(p), 'body': f'[Notion page edited]\n{p.get("url") or ""}',
            'from_name': 'Notion', 'conversation_id': f"notion:{p['id']}",
            'sent_at': at, 'source_link': p.get('url'), 'source_name': 'Notion'}, llm=llm)
        n += out['status'] != 'duplicate'
    return n


# ── Discord ──────────────────────────────────────────────────────────────────────────────
DISCORD = 'https://discord.com/api/v10'

def _discord(c, method, path, **kw):
    r = requests.request(method, f'{DISCORD}{path}', timeout=30,
                         headers={'Authorization': f"Bot {c.get('Secret') or ''}"}, **kw)
    _die(r, 'Discord', 'check the bot token - and the bot needs the Message Content intent plus access to the channel')
    return r.json()


def test_discord(store, c) -> str:
    if not c.get('Secret'): raise RuntimeError('no bot token saved - discord.com/developers → your app → Bot → Reset Token')
    me = _discord(c, 'get', '/users/@me')
    return (f"authenticated as {me.get('username')} - add channel IDs under Sources "
            '(right-click a channel → Copy Channel ID, with Developer Mode on)')


def poll_discord(store, c, src, since, llm=None, file_only=False) -> int:
    """Per-source, like Slack: each watched channel id is one source."""
    from .ingest import ingest_message
    msgs = _discord(c, 'get', f"/channels/{src['Address']}/messages", params={'limit': CAP})
    n = 0
    for m in reversed(msgs if isinstance(msgs, list) else []):
        if (m.get('author') or {}).get('bot'): continue
        at = _stamp(m.get('timestamp'))
        if at < _new(since) or not (m.get('content') or '').strip(): continue
        who = m.get('author') or {}
        out = ingest_message(store, file_only=file_only, msg={
            'external_id': f"discord:{m['id']}", 'channel': 'discord',
            'subject': None, 'body': m.get('content'),
            'from_name': who.get('global_name') or who.get('username') or 'Discord',
            'conversation_id': f"discord:{src['Address']}", 'sent_at': at,
            'source_name': src['Address']}, llm=llm)
        n += out['status'] != 'duplicate'
    return n


def discord_send(store, channel_id: str, body: str) -> dict:
    c = store.get_connector_by_type('discord', with_secret=True)
    if not (c and c.get('Secret')): raise RuntimeError('no Discord bot token saved')
    _discord(c, 'post', f'/channels/{channel_id}/messages', json={'content': body[:2000]})
    return {'channel': 'discord', 'chat': channel_id}


# ── Sentry ───────────────────────────────────────────────────────────────────────────────
def _sentry(c, path, **params):
    base = (_cfg(c).get('base_url') or 'https://sentry.io').strip().rstrip('/')
    r = requests.get(f'{base}{path}', params=params, timeout=30,
                     headers={'Authorization': f"Bearer {c.get('Secret') or ''}"})
    _die(r, 'Sentry', 'check the auth token (Settings → Auth Tokens; scopes org:read + event:read)')
    return r.json()


def _sentry_org(c) -> str:
    org = (_cfg(c).get('org') or '').strip()
    if not org: raise RuntimeError('no organization slug set - it is the first path segment of your Sentry URLs')
    return org


def test_sentry(store, c) -> str:
    if not c.get('Secret'): raise RuntimeError('no auth token saved - Sentry: Settings → Auth Tokens')
    j = _sentry(c, f'/api/0/organizations/{_sentry_org(c)}/')
    _seed_source(store, c, j.get('slug') or _sentry_org(c))
    return f"authenticated to {j.get('name') or j.get('slug')} - new unresolved errors flow in on the next sync"


def poll_sentry(store, c, since, llm=None, file_only=False) -> int:
    from .ingest import ingest_message
    rows = _sentry(c, f'/api/0/organizations/{_sentry_org(c)}/issues/',
                   query='is:unresolved', sort='date', limit=CAP, statsPeriod='14d')
    n = 0
    for i in rows if isinstance(rows, list) else []:
        at = _stamp(i.get('lastSeen'))
        if at < _new(since): continue
        proj = ((i.get('project') or {}).get('slug')) or 'sentry'
        out = ingest_message(store, file_only=file_only, msg={
            'external_id': f"sentry:{i['id']}:{at[:16]}", 'channel': 'sentry',
            'subject': f"{i.get('shortId')} {i.get('title') or ''}".strip(),
            'body': f"[Sentry {i.get('level') or 'error'} in {proj} - seen {i.get('count')}x, "
                    f"{i.get('userCount') or 0} user(s)]\n{i.get('culprit') or ''}",
            'from_name': 'Sentry', 'conversation_id': f"sentry:{i['id']}",
            'sent_at': at, 'source_link': i.get('permalink'), 'source_name': proj}, llm=llm)
        n += out['status'] != 'duplicate'
    return n


# ── PagerDuty ────────────────────────────────────────────────────────────────────────────
def _pagerduty(c, path, **params):
    r = requests.get(f'https://api.pagerduty.com{path}', params=params, timeout=30,
                     headers={'Authorization': f"Token token={c.get('Secret') or ''}",
                              'Content-Type': 'application/json'})
    _die(r, 'PagerDuty', 'check the API token (Integrations → API Access Keys, or My Profile → User Settings)')
    return r.json()


def test_pagerduty(store, c) -> str:
    if not c.get('Secret'): raise RuntimeError('no API token saved - PagerDuty: Integrations → API Access Keys')
    _pagerduty(c, '/incidents', limit=1)
    _seed_source(store, c, 'PagerDuty')
    return 'authenticated - open (triggered/acknowledged) incidents flow in on the next sync'


def poll_pagerduty(store, c, since, llm=None, file_only=False) -> int:
    from .ingest import ingest_message
    j = _pagerduty(c, '/incidents', since=since.astimezone().isoformat(), limit=CAP,
                   **{'sort_by': 'created_at:asc', 'statuses[]': ['triggered', 'acknowledged']})
    n = 0
    for i in j.get('incidents') or []:
        svc = ((i.get('service') or {}).get('summary')) or 'PagerDuty'
        out = ingest_message(store, file_only=file_only, msg={
            'external_id': f"pagerduty:{i['id']}", 'channel': 'pagerduty',
            'subject': f"#{i.get('incident_number')} {i.get('title') or ''}".strip(),
            'body': f"[PagerDuty incident on {svc} - {i.get('status')} - urgency {i.get('urgency')}]\n"
                    f"{str(((i.get('body') or {}).get('details')) or i.get('summary') or '')[:20000]}",
            'from_name': svc, 'conversation_id': f"pagerduty:{i['id']}",
            'sent_at': _stamp(i.get('created_at')), 'source_link': i.get('html_url'), 'source_name': svc}, llm=llm)
        n += out['status'] != 'duplicate'
    return n


TESTS = {'gitlab': test_gitlab, 'azdo': test_azdo, 'linear': test_linear, 'trello': test_trello,
         'notion': test_notion, 'discord': test_discord, 'sentry': test_sentry, 'pagerduty': test_pagerduty}
POLLS = {'gitlab': poll_gitlab, 'azdo': poll_azdo, 'linear': poll_linear, 'trello': poll_trello,
         'notion': poll_notion, 'sentry': poll_sentry, 'pagerduty': poll_pagerduty}
TYPES = tuple(TESTS)

def test(store, c) -> str: return TESTS[c['Type']](store, c)

def poll(store, c, since, llm=None, file_only=False) -> int:
    try:
        return POLLS[c['Type']](store, c, since, llm, file_only)
    except requests.RequestException as e:
        raise RuntimeError(f"{c['Type']} poll failed: {e}") from e
