"""WRITE-BACK TO THE TRACKERS: Jira (REST v3), Monday.com and Linear (GraphQL) - comment on an item, move its status, assign it,
close it (G5, 2026-10-25). Until now pm.py read them and nothing went back: "monday.com = note + close item (NOT built yet)".

Every act here reaches people - a comment is read by everyone on the item, and a move or an assignment is what each tracker tells
the people following it - so every one is in scopes.REACHES: an agent's call waits as a run_tool proposal on its own task, and only
the owner's press runs it (the owner, 2026-10-25: a Jira or GitHub comment counts as a send). The close-out (`close_item`) is
Taskuary's own, raised when a tracker task's agent finishes, like ghcloseout's merge: comment and move to done, one press.

What "done" is comes from the tracker, never from a status's name: Jira's statusCategory 'done', Monday's status column
`done_colors`, Linear's workflow state type 'completed'. A tracker that names none - or a workflow with no move to it from where
the item stands - is said plainly, and the close-out offers the comment alone.

The calls are plain requests with GraphQL VARIABLES, never words pasted into a document: an item's key and a comment come from an
agent that read other people's mail.
"""
import json, re
import requests
from loguru import logger

NAMES = {'jira': 'Jira', 'monday': 'Monday', 'linear': 'Linear'}
VERBS = ('comment', 'move', 'assign', 'close')
TYPES = {f'{t}_{v}': (t, v) for t in NAMES for v in VERBS}
NEED = {'comment': 'body', 'move': 'status', 'assign': 'assignee', 'close': ''}
# an item key goes into a Jira URL path and a GraphQL variable: its own shape, nothing that could walk elsewhere
KEY = {'jira': re.compile(r'^[A-Z][A-Z0-9_]*-\d+$'), 'monday': re.compile(r'^\d+$'),
       'linear': re.compile(r'^([A-Za-z][A-Za-z0-9]*-\d+|[0-9a-f-]{36})$')}
MONDAY_URL, LINEAR_URL = 'https://api.monday.com/v2', 'https://api.linear.app/graphql'


def item_of(store, tid) -> dict | None:
    """{tracker, item} the task came from - the conversation its tracker messages carry (pm: jira:NW-12, monday:123, linear:NW-12)."""
    if not tid: return None
    r = store._one("SELECT Channel, ConversationId FROM message WHERE TaskId=? AND Channel IN ('jira','monday','linear') "
                   "AND ConversationId LIKE Channel || ':%' ORDER BY MessageId LIMIT 1", (int(tid),))
    return {'tracker': r['Channel'], 'item': r['ConversationId'].split(':', 1)[1]} if r else None


def check(p: dict) -> str:
    "'' when a tracker proposal is whole, else what is missing - asked at the proposal and again at the press."
    t, v = TYPES.get(p.get('type'), (p.get('tracker'), 'close'))
    if t not in NAMES: return f'{t!r} is not a tracker Taskuary writes to'
    from .reports import CONNECTION_KEYS
    if set(p) & (CONNECTION_KEYS - {'connector_id'}): return 'a proposal does not name its own connection - the saved card is the one that runs'
    item = str(p.get('item') or '').strip()
    if not item: return f'{p.get("type") or "close_item"} needs the item - this task came from no {NAMES[t]} item'
    if not KEY[t].match(item): return f'{item!r} is not a {NAMES[t]} item key'
    if NEED[v] and not str(p.get(NEED[v]) or '').strip(): return f'{p["type"]} needs {NEED[v]}'
    return ''


def words(p: dict) -> str:
    "What a tracker proposal does, for the owner's card."
    t, v = TYPES.get(p.get('type'), (p.get('tracker'), 'close'))
    at = f"{p.get('item')} in {NAMES.get(t, t)}"
    if p.get('action') == 'close_item':
        return f"comment on {at} - it cannot be moved to done ({p['no_done']})" if p.get('no_done') else             f"comment on {at} and move it to {p.get('status') or 'its done state'}"
    return {'comment': f'comment on {at}', 'move': f"move {at} to {p.get('status')}", 'assign': f"assign {at} to {p.get('assignee')}",
            'close': f"move {at} to {p.get('status') or 'its done state'}"}[v]


def card(store, t: str, connector_id=None) -> dict:
    "The tracker's card with its secret - on, or a refusal that says where to turn it on."
    c = store.get_connector(int(connector_id), with_secret=True) if connector_id else store.get_connector_by_type(t, with_secret=True)
    if not c or c.get('Type') != t: raise RuntimeError(f'no {NAMES[t]} connection')
    if not c.get('Active'): raise RuntimeError(f'the {NAMES[t]} connection is off - turn it on under Connections')
    if not c.get('Secret'): raise RuntimeError(f'the {NAMES[t]} connection has no token saved')
    return c


def _cfg(c) -> dict:
    try: return json.loads(c.get('ConfigJson') or '{}') or {}
    except ValueError: return {}


def _said(r) -> str:
    try: j = r.json()
    except ValueError: return (r.text or '')[:200]
    return '; '.join([*(j.get('errorMessages') or []), *[f'{k}: {v}' for k, v in (j.get('errors') or {}).items()]])[:300] if isinstance(j, dict) else str(j)[:200]


# ── the wire: one function per API, so a test fakes the upstream in one place ────────────────────────────────────────────────────────
def _jira(c, method: str, path: str, body=None):
    from .pm import _jira_base
    r = requests.request(method, f'{_jira_base(c)}{path}', json=body, timeout=30, auth=(_cfg(c).get('email') or '', c.get('Secret') or ''),
                         headers={'Accept': 'application/json'}, allow_redirects=False)
    if r.status_code in (401, 403): raise RuntimeError(f'Jira said {r.status_code} - check the account email and API token ({_said(r)})')
    if r.status_code >= 300: raise RuntimeError(f'Jira said {r.status_code}: {_said(r) or r.reason}')
    return r.json() if r.content else {}


def _gql(t: str, c, query: str, variables: dict) -> dict:
    hdr = {'Authorization': c.get('Secret') or '', **({'API-Version': '2024-10'} if t == 'monday' else {})}
    r = requests.post(MONDAY_URL if t == 'monday' else LINEAR_URL, json={'query': query, 'variables': variables}, headers=hdr, timeout=30,
                      allow_redirects=False)
    if r.status_code in (401, 403): raise RuntimeError(f'{NAMES[t]} said {r.status_code} - check the API token')
    if r.status_code >= 300: raise RuntimeError(f'{NAMES[t]} said {r.status_code}')
    j = r.json()
    if j.get('errors'): raise RuntimeError(f"{NAMES[t]}: {(j['errors'][0] or {}).get('message') or j['errors']}")
    return j.get('data') or {}


def _adf(text: str) -> dict:
    "Plain text as Jira v3's document format: a paragraph per blank-line block, a hard break per line."
    paras = [p for p in re.split(r'\n\s*\n', str(text or '').strip()) if p.strip()]
    def para(p):
        out = []
        for i, line in enumerate(p.split('\n')):
            if i: out.append({'type': 'hardBreak'})
            if line: out.append({'type': 'text', 'text': line})
        return {'type': 'paragraph', 'content': out}
    return {'type': 'doc', 'version': 1, 'content': [para(p) for p in paras]}


# ── reading where an item stands: {item, title, status, done, to: {id, name} | None, why, statuses, url} ─────────────────────────────
def _jira_state(c, key):
    i = _jira(c, 'GET', f'/rest/api/3/issue/{key}?fields=status,summary')
    st = (i.get('fields') or {}).get('status') or {}
    tr = _jira(c, 'GET', f'/rest/api/3/issue/{key}/transitions').get('transitions') or []
    done = ((st.get('statusCategory') or {}).get('key')) == 'done'
    to = next(({'id': x['id'], 'name': (x.get('to') or {}).get('name') or x.get('name')} for x in tr
               if (((x.get('to') or {}).get('statusCategory') or {}).get('key')) == 'done'), None)
    return {'item': key, 'title': (i.get('fields') or {}).get('summary') or '', 'status': st.get('name') or '?', 'done': done, 'to': to,
            'moves': [{'id': x['id'], 'name': x.get('name'), 'to': (x.get('to') or {}).get('name')} for x in tr],
            'why': '' if to or done else f"Jira's workflow offers no move to a done status from {st.get('name') or 'where it stands'}"}


_MONDAY_ITEM = ('query($ids:[ID!]){ items(ids:$ids){ id name url board{ id columns{ id title type settings_str } } '
                'column_values{ id type text } } }')


def _monday_item(c, item):
    its = _gql('monday', c, _MONDAY_ITEM, {'ids': [str(item)]}).get('items') or []
    if not its: raise RuntimeError(f'Monday has no item {item} this token can see')
    return its[0]


def _monday_col(c, it, kind: str):
    "The item's status (or people) column: the one the card names (status_column / people_column), else the board's first."
    cols = [x for x in ((it.get('board') or {}).get('columns') or []) if x.get('type') == kind]
    want = str(_cfg(c).get(f"{'status' if kind == 'status' else 'people'}_column") or '')
    return next((x for x in cols if x['id'] == want), cols[0] if cols else None)


def _labels(col) -> tuple:
    "(every label, the done labels) of a Monday status column - done is the column's own done_colors, not a label's name."
    try: s = json.loads(col.get('settings_str') or '{}')
    except ValueError: s = {}
    labels = {str(k): v for k, v in (s.get('labels') or {}).items() if v}
    return list(labels.values()), [labels[str(i)] for i in (s.get('done_colors') or []) if str(i) in labels]


def _monday_state(c, item):
    it = _monday_item(c, item)
    col = _monday_col(c, it, 'status')
    if not col: return {'item': str(item), 'title': it.get('name') or '', 'status': '?', 'done': False, 'to': None, 'moves': [], 'url': it.get('url'),
                        'why': 'its board has no status column to move'}
    cur = next((v.get('text') or '' for v in (it.get('column_values') or []) if v.get('id') == col['id']), '')
    every, done = _labels(col)
    return {'item': str(item), 'title': it.get('name') or '', 'status': cur or '(none)', 'done': cur in done, 'url': it.get('url'),
            'to': {'id': col['id'], 'name': done[0], 'board': it['board']['id']} if done else None,
            'moves': [{'id': col['id'], 'name': x, 'board': it['board']['id']} for x in every],
            'why': '' if done else f"its status column \"{col.get('title')}\" marks no label as done"}


_LINEAR_ISSUE = ('query($id:String!){ issue(id:$id){ id identifier title url state{ id name type } '
                 'team{ states{ nodes{ id name type position } } } } }')


def _linear_issue(c, item):
    i = _gql('linear', c, _LINEAR_ISSUE, {'id': str(item)}).get('issue')
    if not i: raise RuntimeError(f'Linear has no issue {item} this key can see')
    return i


def _linear_state(c, item):
    i = _linear_issue(c, item)
    st, nodes = i.get('state') or {}, sorted((((i.get('team') or {}).get('states') or {}).get('nodes') or []), key=lambda s: s.get('position') or 0)
    to = next(({'id': s['id'], 'name': s['name']} for s in nodes if s.get('type') == 'completed'), None)
    return {'item': i.get('identifier') or str(item), 'uuid': i['id'], 'title': i.get('title') or '', 'status': st.get('name') or '?', 'url': i.get('url'),
            'done': st.get('type') == 'completed', 'to': to, 'moves': [{'id': s['id'], 'name': s['name']} for s in nodes],
            'why': '' if to else "its team's workflow has no completed state"}


STATE = {'jira': _jira_state, 'monday': _monday_state, 'linear': _linear_state}


def state(store, t: str, item, connector_id=None) -> dict: return STATE[t](card(store, t, connector_id), item)


# ── the four acts, per tracker ───────────────────────────────────────────────────────────────────────────────────────────────────
def _comment(t, c, s, body: str) -> str:
    if t == 'jira':
        j = _jira(c, 'POST', f"/rest/api/3/issue/{s['item']}/comment", {'body': _adf(body)})
        return str(j.get('id') or '')
    if t == 'monday':
        return str(((_gql('monday', c, 'mutation($i:ID!,$b:String!){ create_update(item_id:$i, body:$b){ id } }',
                          {'i': s['item'], 'b': body}).get('create_update')) or {}).get('id') or '')
    j = _gql('linear', c, 'mutation($i:String!,$b:String!){ commentCreate(input:{issueId:$i, body:$b}){ success comment{ id url } } }',
             {'i': s['uuid'], 'b': body}).get('commentCreate') or {}
    if not j.get('success'): raise RuntimeError('Linear did not take the comment')
    return str((j.get('comment') or {}).get('url') or '')


def _move(t, c, s, to: dict) -> None:
    if t == 'jira': _jira(c, 'POST', f"/rest/api/3/issue/{s['item']}/transitions", {'transition': {'id': to['id']}}); return
    if t == 'monday':
        _gql('monday', c, 'mutation($b:ID!,$i:ID!,$c:String!,$v:String){ change_simple_column_value(board_id:$b, item_id:$i, column_id:$c, '
                          'value:$v){ id } }', {'b': to['board'], 'i': s['item'], 'c': to['id'], 'v': to['name']}); return
    j = _gql('linear', c, 'mutation($i:String!,$s:String!){ issueUpdate(id:$i, input:{stateId:$s}){ success } }',
             {'i': s['uuid'], 's': to['id']}).get('issueUpdate') or {}
    if not j.get('success'): raise RuntimeError(f"Linear did not move {s['item']}")


def _target(t, s, status: str) -> dict:
    "The move to the status the proposal names - by the tracker's own name for it, exactly (case aside), or a refusal listing the rest."
    want = str(status or '').strip().lower()
    hit = next((m for m in s['moves'] if want in (str(m.get('name') or '').lower(), str(m.get('to') or '').lower())), None)
    if hit: return {**hit, 'name': hit.get('to') or hit['name']}
    have = ', '.join(dict.fromkeys(str(m.get('to') or m['name']) for m in s['moves'])) or 'none'
    raise RuntimeError(f"{NAMES[t]} offers no move to {status!r} for {s['item']} from {s['status']} - it offers: {have}. Nothing was changed.")


def _person(t, c, s, who: str) -> dict:
    "ONE person the tracker knows by this name or address - two or none is a refusal, never a guess at which."
    who = str(who or '').strip()
    if t == 'jira':
        hits = _jira(c, 'GET', f"/rest/api/3/user/assignable/search?issueKey={s['item']}&query={requests.utils.quote(who)}") or []
        exact = [u for u in hits if who.lower() in (str(u.get('displayName') or '').lower(), str(u.get('emailAddress') or '').lower())]
        got = exact or hits
        rows = [{'id': u.get('accountId'), 'name': u.get('displayName')} for u in got]
    elif t == 'monday':
        hits = _gql('monday', c, 'query($n:String){ users(name:$n){ id name email } }', {'n': who}).get('users') or []
        if '@' in who: hits = _gql('monday', c, 'query($e:[String]){ users(emails:$e){ id name email } }', {'e': [who]}).get('users') or hits
        rows = [{'id': u.get('id'), 'name': u.get('name')} for u in hits]
    else:
        f = {'or': [{'name': {'eqIgnoreCase': who}}, {'displayName': {'eqIgnoreCase': who}}, {'email': {'eqIgnoreCase': who}}]}
        rows = [{'id': u.get('id'), 'name': u.get('name')} for u in
                ((_gql('linear', c, 'query($f:UserFilter){ users(filter:$f){ nodes{ id name } } }', {'f': f}).get('users') or {}).get('nodes') or [])]
    if len(rows) != 1:
        raise RuntimeError(f"{NAMES[t]} knows {'nobody' if not rows else str(len(rows)) + ' people'} as {who!r} on {s['item']}"
                           + (f" ({', '.join(str(r['name']) for r in rows[:5])})" if rows else '') + ' - name one exactly. Nothing was changed.')
    return rows[0]


def _assign(t, c, s, item, who: str) -> str:
    u = _person(t, c, s, who)
    if t == 'jira': _jira(c, 'PUT', f"/rest/api/3/issue/{s['item']}/assignee", {'accountId': u['id']})
    elif t == 'monday':
        it = _monday_item(c, item)
        col = _monday_col(c, it, 'people')
        if not col: raise RuntimeError(f'the board of Monday item {item} has no People column. Nothing was changed.')
        _gql('monday', c, 'mutation($b:ID!,$i:ID!,$c:String!,$v:JSON!){ change_column_value(board_id:$b, item_id:$i, column_id:$c, value:$v){ id } }',
             {'b': it['board']['id'], 'i': str(item), 'c': col['id'], 'v': json.dumps({'personsAndTeams': [{'id': int(u['id']), 'kind': 'person'}]})})
    else:
        j = _gql('linear', c, 'mutation($i:String!,$u:String!){ issueUpdate(id:$i, input:{assigneeId:$u}){ success } }',
                 {'i': s['uuid'], 'u': u['id']}).get('issueUpdate') or {}
        if not j.get('success'): raise RuntimeError(f"Linear did not assign {s['item']}")
    return str(u['name'])


def run(type_: str):
    "The REGISTRY executor for one act - run only from the owner's press (proposals.execute) or the owner's own tools/run call."
    t, v = TYPES[type_]
    def executor(cfg):
        if why := check({**{k: x for k, x in cfg.items() if k not in ('_card', 'token')}, 'type': type_}): raise RuntimeError(why)
        c = cfg.get('_card') or {}
        if c.get('Type') != t: raise RuntimeError(f'no {NAMES[t]} connection')
        item = str(cfg['item']).strip()
        s = STATE[t](c, item)
        if v == 'comment':
            ref = _comment(t, c, s, str(cfg['body']))
            return f"commented on {s['item']} in {NAMES[t]}", json.dumps({'item': s['item'], 'comment': ref, 'url': s.get('url')})
        if v == 'assign':
            who = _assign(t, c, s, item, cfg['assignee'])
            return f"assigned {s['item']} in {NAMES[t]} to {who}", json.dumps({'item': s['item'], 'assignee': who})
        if v == 'move': to = _target(t, s, cfg['status'])
        else:
            if s['done']: return f"{s['item']} is already {s['status']} in {NAMES[t]}", json.dumps({'item': s['item'], 'status': s['status']})
            if not s['to']: raise RuntimeError(f"{s['why']} for {s['item']} - nothing was changed")
            to = s['to']
        if v == 'close' and str(cfg.get('body') or '').strip():
            _comment(t, c, s, str(cfg['body']))
            # the comment went: a failed move is said beside it, never raised - a second press would post it twice
            try: _move(t, c, s, to)
            except Exception as e:
                return f"commented on {s['item']} in {NAMES[t]}; it was not moved", json.dumps({'item': s['item'], 'not_moved': str(e)[:300]})
            return f"commented on {s['item']} and moved it to {to['name']} in {NAMES[t]}", json.dumps({'item': s['item'], 'from': s['status'], 'to': to['name']})
        _move(t, c, s, to)
        return f"moved {s['item']} in {NAMES[t]} to {to['name']}", json.dumps({'item': s['item'], 'from': s['status'], 'to': to['name']})
    executor.__doc__ = f"{NAMES[t]}: {v} an item - {{item, {NEED[v] or 'body (optional)'}}}. Reaches people: an agent's call waits for the owner's press."
    return executor


def connection(t: str):
    "reports.CONNECTION_OF's entry: the card, secret and all, as `_card` - which no request body may set (reports.CONNECTION_KEYS)."
    def conn(store, connector_id=None) -> dict:
        # the secret rides at the top as well, where every card's does (test_every_card_is_reachable): the executor spends `_card`
        try: c = card(store, t, connector_id); return {'_card': c, 'token': c['Secret']}
        except RuntimeError: return {}
    return conn


# ── the close-out: comment and move to done, the card's main move when a tracker task's agent finishes ──────────────────────────────
def closeout_due(store, tid) -> dict | None:
    """The close-out proposal a finished tracker task owes, read from the tracker now - None for a task from no tracker item, a card
    that is off, or an item already done there. Unreadable is not "no done state": the card reads it again when it is drawn."""
    it = item_of(store, tid)
    if not it: return None
    t = it['tracker']
    try: c = card(store, t)
    except RuntimeError: return None
    p = {'action': 'close_item', 'tracker': t, 'item': it['item'], 'connector_id': c['ConnectorId'], 'closeout': True}
    try: s = STATE[t](c, it['item'])
    except Exception as e:
        logger.warning(f'task {tid}: {NAMES[t]} {it["item"]} could not be read before its close-out ({e})')
        return {**p, 'status': None, 'why': f'the {NAMES[t]} item this task came from is still open'}
    if s['done']: return None
    return {**p, 'status': (s['to'] or {}).get('name'), 'from': s['status'], 'title': s['title'], 'link': s.get('url'),
            **({} if s['to'] else {'no_done': s['why']}), 'why': f"{it['item']} is still {s['status']} in {NAMES[t]}"}


def assess(store, p: dict) -> dict:
    """What the close-out card offers RIGHT NOW (server closeout_state), the same reading the press runs on: ok, why not, and the note
    that rides with it - "no move to done from here, so Approve posts the comment alone". FAIL CLOSED: an unreadable tracker is no
    live Approve."""
    t = p.get('tracker')
    out = {'state': 'open', 'ok': True, 'reason': '', 'note': '', 'offers': []}
    try: s = state(store, t, p.get('item'), p.get('connector_id'))
    except Exception as e:
        return {**out, 'state': 'unknown', 'ok': False, 'reason': f'{NAMES.get(t, t)} could not be read just now ({str(e)[:160]}) - open the card again in a moment'}
    if s['done']: return {**out, 'state': 'done', 'note': f"{s['item']} is already {s['status']} in {NAMES[t]} - {_approve()} posts the comment alone"}
    if not s['to']: return {**out, 'note': f"{s['why']} for {s['item']} - {_approve()} posts the comment alone"}
    return {**out, 'to': s['to']['name'], 'from': s['status']}


def _approve() -> str:
    from . import buttons
    return buttons.label('approve', 'action')


def close_out(store, p: dict) -> dict:
    """The owner pressed the close-out: the comment (when there is one), then the move to done when the tracker allows it now. A move
    it does not allow is said beside the comment that went - never a second press that would post the comment twice."""
    t, item, text = p['tracker'], str(p['item']), str(p.get('text') or '').strip()
    c = card(store, t, p.get('connector_id'))
    s = STATE[t](c, item)
    if not text and (s['done'] or not s['to']):
        raise RuntimeError(f"{s['why'] or s['item'] + ' is already ' + s['status']} and there is no comment to post - write one, or Mark done. Nothing was changed.")
    out = {'item': s['item'], 'tracker': NAMES[t]}
    if text: _comment(t, c, s, text); out['commented'] = True
    if s['done']: out['already'] = s['status']
    elif not s['to']: out['not_moved'] = s['why']
    else:
        try: _move(t, c, s, s['to']); out['moved'] = s['to']['name']
        except Exception as e:
            if not text: raise
            out['not_moved'] = f'the move failed: {str(e)[:200]}'
    return out


def said(out: dict) -> str:
    "The close-out's line on the task, in words."
    at = f"{out['item']} in {out['tracker']}"
    did = ('Commented on ' + at + (f" and moved it to {out['moved']}." if out.get('moved') else '.')) if out.get('commented') else \
          f"Moved {at} to {out['moved']}." if out.get('moved') else f'Nothing was written to {at}.'
    return did + (f" It was not moved: {out['not_moved']}." if out.get('not_moved') else f" It was already {out['already']}." if out.get('already') else '')
