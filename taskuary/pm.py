"""Project-management inboxes: Jira, Asana and Monday.com as trigger channels. The item that
matters from these systems is the one ASSIGNED TO YOU - it lands on the Timeline and goes
through the same triage as mail, so "assigned in Jira" and "asked by email" end up in the
one funnel. Each connector polls its own API with the owner's token; nothing is written back.
"""
import json
from datetime import datetime
import requests
from loguru import logger

CAP = 25                     # items per poll, like the other channels


def _cfg(c):
    try: return json.loads(c.get('ConfigJson') or '{}')
    except ValueError: return {}


def _seed_source(store, c, address: str):
    """The poller walks sources; give this connector one to walk (its site/workspace)."""
    if not any(s['Channel'] == c['Type'] for s in store.list_sources(active_only=False)):
        store.save_source({'Channel': c['Type'], 'Address': address, 'ConnectorId': c['ConnectorId'],
                           'Active': 1}, 'connector-test')


def _stamp(iso: str) -> str:
    """A vendor timestamp (2026-08-23T14:02:11.000+0000 / ...Z) as a local wall-clock stamp."""
    try:
        s = (iso or '').replace('Z', '+00:00')
        if len(s) > 5 and (s[-5] in '+-') and ':' not in s[-5:]: s = f'{s[:-2]}:{s[-2:]}'
        return datetime.fromisoformat(s).astimezone().strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ── Jira ─────────────────────────────────────────────────────────────────────────────────
def _jira_base(c) -> str:
    base = (_cfg(c).get('base_url') or '').strip().rstrip('/')
    if not base: raise RuntimeError('no site URL set - enter https://yourteam.atlassian.net under Credentials')
    return base if base.startswith('http') else f'https://{base}'


def _jira_get(c, path, **params):
    r = requests.get(f'{_jira_base(c)}{path}', params=params, timeout=30,
                     auth=(_cfg(c).get('email') or '', c.get('Secret') or ''),
                     headers={'Accept': 'application/json'})
    if r.status_code == 401: raise RuntimeError('Jira said 401 - check the account email and API token')
    r.raise_for_status()
    return r.json()


def test_jira(store, c) -> str:
    if not c.get('Secret'): raise RuntimeError('no API token saved - create one at id.atlassian.com → Security → API tokens')
    me = _jira_get(c, '/rest/api/2/myself')
    _seed_source(store, c, _jira_base(c).split('//', 1)[-1])
    return f"authenticated as {me.get('displayName') or me.get('emailAddress')} - issues assigned to you flow in on the next sync"


def poll_jira(store, c, since, llm=None, file_only=False) -> int:
    from .ingest import ingest_message
    mins = max(2, int((datetime.now() - since).total_seconds() // 60) + 1)
    j = _jira_get(c, '/rest/api/2/search', maxResults=CAP,
                  jql=f'assignee = currentUser() AND updated >= "-{mins}m" ORDER BY updated ASC',
                  fields='summary,description,status,priority,reporter,updated')
    base, n = _jira_base(c), 0
    for i in j.get('issues', []):
        f = i.get('fields') or {}
        rep = (f.get('reporter') or {})
        head = (f"[Jira {i['key']} - status {((f.get('status') or {}).get('name') or '?')}"
                f" · priority {((f.get('priority') or {}).get('name') or '?')} · assigned to you]")
        out = ingest_message(store, file_only=file_only, msg={
            'external_id': f"jira:{i['key']}", 'channel': 'jira',
            'subject': f"{i['key']} {f.get('summary') or ''}".strip(),
            'body': f"{head}\n{str(f.get('description') or '(no description)')[:20000]}",
            'from_name': rep.get('displayName') or 'Jira', 'from_email': rep.get('emailAddress'),
            'conversation_id': f"jira:{i['key']}", 'sent_at': _stamp(f.get('updated')),
            'source_link': f"{base}/browse/{i['key']}", 'source_name': base.split('//', 1)[-1]}, llm=llm)
        n += out['status'] != 'duplicate'
    return n


# ── Asana ────────────────────────────────────────────────────────────────────────────────
def _asana_get(c, path, **params):
    r = requests.get(f'https://app.asana.com/api/1.0{path}', params=params, timeout=30,
                     headers={'Authorization': f"Bearer {c.get('Secret') or ''}"})
    if r.status_code == 401: raise RuntimeError('Asana said 401 - check the Personal Access Token')
    r.raise_for_status()
    return r.json().get('data')


def test_asana(store, c) -> str:
    if not c.get('Secret'): raise RuntimeError('no token saved - create a Personal Access Token at app.asana.com/0/my-apps')
    me = _asana_get(c, '/users/me', opt_fields='name,workspaces.name')
    ws = (me.get('workspaces') or [])
    if not ws: raise RuntimeError('the token reaches no workspace')
    cfg = _cfg(c)
    if not cfg.get('workspace_gid'):     # remembered so the poller never guesses
        store.set_connector_config(c['ConnectorId'], {**cfg, 'workspace_gid': ws[0]['gid']})
    _seed_source(store, c, ws[0].get('name') or 'Asana')
    return f"authenticated as {me.get('name')} in {ws[0].get('name')} - tasks assigned to you flow in on the next sync"


def poll_asana(store, c, since, llm=None, file_only=False) -> int:
    from .ingest import ingest_message
    gid = _cfg(c).get('workspace_gid')
    if not gid: raise RuntimeError('no workspace known yet - run Test on the Asana card once')
    rows = _asana_get(c, '/tasks', assignee='me', workspace=gid, completed_since='now', limit=CAP,
                      opt_fields='name,notes,modified_at,created_by.name,permalink_url,memberships.project.name') or []
    n = 0
    for t in rows:
        if _stamp(t.get('modified_at')) < since.strftime('%Y-%m-%d %H:%M:%S'): continue
        proj = next((m['project']['name'] for m in (t.get('memberships') or []) if m.get('project')), None)
        out = ingest_message(store, file_only=file_only, msg={
            'external_id': f"asana:{t['gid']}", 'channel': 'asana',
            'subject': (t.get('name') or '').strip() or 'Asana task',
            'body': f"[Asana task{f' in {proj}' if proj else ''} - assigned to you]\n"
                    f"{str(t.get('notes') or '(no description)')[:20000]}",
            'from_name': ((t.get('created_by') or {}).get('name')) or 'Asana',
            'conversation_id': f"asana:{t['gid']}", 'sent_at': _stamp(t.get('modified_at')),
            'source_link': t.get('permalink_url'), 'source_name': proj or 'Asana'}, llm=llm)
        n += out['status'] != 'duplicate'
    return n


# ── Monday.com ───────────────────────────────────────────────────────────────────────────
def _monday(c, query: str):
    r = requests.post('https://api.monday.com/v2', json={'query': query}, timeout=30,
                      headers={'Authorization': c.get('Secret') or '', 'API-Version': '2024-10'})
    if r.status_code == 401: raise RuntimeError('Monday said 401 - check the API token (admin → Developers → My access tokens)')
    r.raise_for_status()
    j = r.json()
    if j.get('errors'): raise RuntimeError(f"monday: {j['errors'][0].get('message') or j['errors']}")
    return j['data']


def test_monday(store, c) -> str:
    if not c.get('Secret'): raise RuntimeError('no API token saved - Monday: your avatar → Developers → My access tokens')
    me = _monday(c, '{ me { id name } }')['me']
    cfg = _cfg(c)
    if str(cfg.get('me_id') or '') != str(me['id']):     # who "assigned to you" means, kept local
        store.set_connector_config(c['ConnectorId'], {**cfg, 'me_id': str(me['id'])})
    _seed_source(store, c, me.get('name') or 'Monday')
    return f"authenticated as {me.get('name')} - items assigned to you flow in on the next sync"


def poll_monday(store, c, since, llm=None, file_only=False) -> int:
    """Monday has no 'my items' query, so the poll walks boards (the configured ids, or the
    most recently used) and keeps items whose People column names the owner."""
    from .ingest import ingest_message
    cfg = _cfg(c)
    me = str(cfg.get('me_id') or '')
    if not me: raise RuntimeError('who you are on Monday is not known yet - run Test on the card once')
    ids = [b.strip() for b in str(cfg.get('board_ids') or '').split(',') if b.strip()]
    scope = f'ids: [{", ".join(ids)}]' if ids else 'limit: 25, order_by: used_at'
    data = _monday(c, '{ boards (%s) { name items_page (limit: 50) { items { id name updated_at url '
                      'creator { name } column_values { text type ... on PeopleValue '
                      '{ persons_and_teams { id kind } } } } } } }' % scope)
    n = 0
    for b in data.get('boards') or []:
        for it in ((b.get('items_page') or {}).get('items') or []):
            people = [str(p.get('id')) for cv in (it.get('column_values') or [])
                      for p in (cv.get('persons_and_teams') or []) if p.get('kind') != 'team']
            if me not in people: continue
            if _stamp(it.get('updated_at')) < since.strftime('%Y-%m-%d %H:%M:%S'): continue
            cols = ' · '.join(f"{cv.get('type')}: {cv['text']}" for cv in (it.get('column_values') or [])
                              if (cv.get('text') or '').strip())[:2000]
            out = ingest_message(store, file_only=file_only, msg={
                'external_id': f"monday:{it['id']}", 'channel': 'monday',
                'subject': (it.get('name') or '').strip() or 'Monday item',
                'body': f"[Monday item on board \"{b.get('name')}\" - assigned to you]\n{cols or '(no details)'}",
                'from_name': ((it.get('creator') or {}).get('name')) or 'Monday',
                'conversation_id': f"monday:{it['id']}", 'sent_at': _stamp(it.get('updated_at')),
                'source_link': it.get('url'), 'source_name': b.get('name') or 'Monday'}, llm=llm)
            n += out['status'] != 'duplicate'
    return n


TESTS = {'jira': test_jira, 'asana': test_asana, 'monday': test_monday}
POLLS = {'jira': poll_jira, 'asana': poll_asana, 'monday': poll_monday}

def test(store, c) -> str: return TESTS[c['Type']](store, c)

def poll(store, c, since, llm=None, file_only=False) -> int:
    try:
        return POLLS[c['Type']](store, c, since, llm, file_only)
    except requests.RequestException as e:
        raise RuntimeError(f"{c['Type']} poll failed: {e}") from e
