"""RECENTLY DELETED: a Remove acts at once, and is taken back from here (the owner, 2026-10-21: no "are you sure" on an action).

Remove asked "Delete report?" with Cancel first, Not ours asked which kind, and Sign out asked again - and once it was done, nothing
brought it back. Now each acts on the press and the page shows "Removed <it> - Undo". What it took is kept whole in the store's own
`deleted` table, so Restore puts it back exactly: the row under its old id while nothing has taken it, a profile's settings and its
rules document, a rule's hidden history hidden again.

Two lengths of keeping. A report, a workflow, a routing rule and a profile are listed under Recently deleted for KEEP_DAYS, the way a
playbook is (playbooks.py). A connection removed or signed out is kept only for the Undo line's minutes (UNDO_SECONDS): its sign-in
stays sealed where the vault put it, and what makes the removal final - forgetting a keychain entry, ending a ChatGPT session at
OpenAI - waits for purge(), which runs at startup, in the housekeeping, and whenever this list is read or written.
"""
import json, time
from loguru import logger

KEEP_DAYS, UNDO_SECONDS = 30, 600
LISTED = ('report', 'workflow', 'dashboard', 'rule', 'profile')        # what Recently deleted lists; the rest is an Undo line's alone
SHORT = ('connection', 'signout', 'cli')                   # kept for the Undo line's minutes, then finished off


BRIEF = SHORT + ('task',)                                  # ...and a task Removed as not a task: its Undo line's alone, nothing to finish


def _keep(kind: str) -> float: return UNDO_SECONDS if kind in BRIEF else KEEP_DAYS * 86400


def keep(store, kind: str, title: str, data: dict, now: float = None) -> int:
    """File what a Remove took; its id is what Undo and Restore name."""
    now = time.time() if now is None else now
    purge(store, now)
    return store.keep_deleted(kind, str(title or kind)[:200], data, now, now + _keep(kind))


def _entry(r: dict, now: float) -> dict:
    return {'id': r['DeletedId'], 'kind': r['Kind'], 'title': r['Title'], 'deleted_at': r['DeletedAt'], 'purge_at': r['KeepUntil'],
            'days_left': max(0, int((r['KeepUntil'] - now) // 86400))}


def listing(store, kinds=LISTED, now: float = None) -> list:
    """Recently deleted, newest first: what Restore can still bring back, and when it goes for good."""
    now = time.time() if now is None else now
    purge(store, now)
    return [_entry(r, now) for r in store.deleted_rows() if r['Kind'] in kinds]


def _finish(store, kind: str, data: dict):
    """What makes a short-kept removal final, once its Undo has passed."""
    from . import vault
    secret = (data.get('row') or {}).get('Secret')
    if kind == 'signout' and data.get('revoke') == 'chatgpt' and secret:
        from . import chatgptauth
        try: chatgptauth.revoke(data.get('cfg') or {}, vault.unseal(secret))
        except Exception as e: logger.warning(f'the ChatGPT session was not ended at OpenAI: {e}')
    # a keychain entry is forgotten only if nothing took the connection back in the meantime
    cur = (store.get_connector(data.get('cid'), with_secret=False) or {}) if data.get('cid') else {}
    if secret and not cur.get('HasSecret', cur.get('Secret')): vault.forget(secret)


def purge(store, now: float = None) -> list:
    """Drop what has been kept its time, finishing off a connection's removal. The ids it purged."""
    now, gone = time.time() if now is None else now, []
    for r in store.deleted_rows():
        if r['KeepUntil'] > now: continue
        if r['Kind'] in SHORT:
            try: _finish(store, r['Kind'], json.loads(r['DataJson'] or '{}'))
            except Exception as e: logger.warning(f'a removed connection was not finished off: {e}')
        store.drop_deleted(r['DeletedId']); gone.append(r['DeletedId'])
    return gone


def take(store, did: int) -> dict | None:
    """The kept thing, out of the list - {kind, title, data} - or None when it is gone (purged, or restored already)."""
    r = store.get_deleted(int(did))
    if not r: return None
    store.drop_deleted(r['DeletedId'])
    return {'kind': r['Kind'], 'title': r['Title'], 'data': json.loads(r['DataJson'] or '{}')}


# ── each Remove, and its way back ───────────────────────────────────────────────────────────────────────────────────────────

def source_kind(row: dict) -> str:
    """A report and a workflow are listed under their own names; a mailbox address or a channel is an Undo line's alone."""
    if row.get('Channel') != 'report': return 'source'
    from . import workflows, dashboards
    return 'workflow' if workflows.is_workflow(row) else 'dashboard' if dashboards.is_dashboard(dashboards.cfg_of(row)) else 'report'


def source_title(row: dict) -> str:
    try: cfg = json.loads(row.get('ConfigJson') or '{}') or {}
    except ValueError: cfg = {}
    return str(cfg.get('title') or row.get('Address') or 'untitled')


def remove_source(store, sid: int) -> dict:
    row = store.get_source(sid)
    did = keep(store, source_kind(row), source_title(row), {'row': row})
    store.delete_source(sid)
    return {'deleted': did, 'title': source_title(row), 'kind': source_kind(row)}


def remove_policy(store, pid: int) -> dict:
    from . import policy as policy_engine
    p = next((x for x in store.list_policies(active_only=False) if x['PolicyId'] == pid), None)
    did = keep(store, 'rule', p.get('Name') or 'rule', {'row': p})
    shown = policy_engine.apply_retroactively(store, {**p, 'Active': 0})
    store.delete_policy(pid)
    return {'deleted': did, 'title': p.get('Name') or 'rule', 'restored': shown, 'kind': 'rule'}


def remove_profile(store, cfg: dict, name: str) -> dict:
    """A profile's settings, its row and - when nothing else shares it - the rules document an import wrote."""
    from . import agents as hub_agents, config
    doc = hub_agents.profile_document(store, name)
    orphan = doc == name and store.doc_owner(doc) == 'import'
    kept = {'name': name, 'conf': cfg['agents'][name], 'row': store.get_agent(name),
            'doc': store.get_doc_row(doc) if orphan else None}
    did = keep(store, 'profile', name, kept)
    cfg['agents'].pop(name)
    config.save(cfg)
    store.delete_agent(name)
    if orphan: store.delete_doc(doc)
    return {'deleted': did, 'title': name, 'kind': 'profile'}


def remove_connection(store, cid: int, title: str) -> dict:
    """Remove connection: wiped at once, its sealed sign-in kept for the Undo line's minutes (purge forgets it after)."""
    row = store._one('SELECT ConfigJson, Secret, Active, Scope, LastSyncAt FROM connector WHERE ConnectorId=?', (cid,)) or {}
    on = [s['SourceId'] for s in store.list_sources(active_only=False) if s.get('ConnectorId') == cid and s.get('Active')]
    did = keep(store, 'connection', title, {'cid': cid, 'row': row, 'sources': on})
    store._exec('UPDATE connector SET Secret=NULL, ConfigJson=NULL, Active=0, LastSyncAt=NULL, LastError=NULL, Scope=NULL WHERE ConnectorId=?', (cid,))
    store._exec('UPDATE source SET Active=0 WHERE ConnectorId=?', (cid,))
    return {'deleted': did, 'title': title, 'kind': 'connection'}


def sign_out(store, cid: int, title: str, cfg_after: dict, revoke: str = None, cfg_before: dict = None) -> dict:
    """Sign out: forgotten here at once; a ChatGPT session is ended at OpenAI once the Undo line has passed (purge)."""
    row = store._one('SELECT ConfigJson, Secret, Active FROM connector WHERE ConnectorId=?', (cid,)) or {}
    did = keep(store, 'signout', title, {'cid': cid, 'row': row, 'revoke': revoke, 'cfg': cfg_before or {}})
    store._exec('UPDATE connector SET ConfigJson=?, Secret=NULL, Active=0 WHERE ConnectorId=?', (json.dumps(cfg_after), cid))
    return {'deleted': did, 'title': title, 'kind': 'signout'}


def remove_cli(store, cfg: dict, name: str, users: list) -> dict:
    """A CLI connection, and which profiles ran on it - Undo puts each back on it."""
    kept = {'name': name, 'conn': cfg['cli_connections'][name], 'users': {n: dict(cfg['agents'][n]) for n in users}}
    return {'deleted': keep(store, 'cli', name, kept), 'title': name, 'kind': 'cli'}


TASK_ROWS = (('review', 'ReviewId'), ('comment', 'CommentId'), ('run', 'RunId'), ('task_artifact', 'ArtifactId'), ('session_resume', 'TaskId'))


def task_snapshot(store, tid: int) -> dict:
    """REMOVE - NOT A TASK IS TAKEN BACK BY ITS UNDO (the owner, 2026-10-21: no "are you sure"; the task card had no Undo, 2026-10-22).
    What store.delete_task takes or unhooks, read before it runs: the task row, the rows it deletes, which messages and routes it lets
    go (and as what), and the Advisor ideas it dismisses. The verdict's own marks - the ignore route and the memory note - are added
    to it by the caller (`ignore`, `memory`) so the Undo takes those back too."""
    rows = lambda q: store._rows(q, (tid,))
    return {'task': store.get_task(tid),
            **{t: rows(f'SELECT * FROM {t} WHERE TaskId=?') for t, _ in TASK_ROWS},
            'messages': rows('SELECT MessageId, Status FROM message WHERE TaskId=?'),
            'routes': [r['RouteId'] for r in rows('SELECT RouteId FROM route WHERE TaskId=?')],
            'ideas': store._rows("SELECT IdeaId, Status, DecidedBy, DecidedAt FROM idea WHERE Status IN ('open','snoozed') AND (json_extract(ActionJson,'$.tid')=? "
                                 "OR IdeaId IN (SELECT CAST(substr(SourceRef,16) AS INTEGER) FROM task WHERE TaskId=? AND SourceRef LIKE 'assistant:idea:%'))", (tid, tid))}


def keep_task(store, snap: dict) -> dict:
    t = snap.get('task') or {}
    return {'deleted': keep(store, 'task', t.get('Title') or 'the task', snap), 'title': t.get('Title') or 'the task', 'kind': 'task'}


def _restore_task(store, d: dict) -> int:
    """The task back as it stood - under its old id while nothing has taken it - with its rows, its messages and routes, its ideas;
    the verdict's ignore route deleted and its memory note switched off, so the next message on the thread can open work again."""
    tid = store.put_back('task', d['task'], 'TaskId')
    for t, key in TASK_ROWS:
        for r in d.get(t) or []: store.put_back(t, {**r, 'TaskId': tid}, key)
    for m in d.get('messages') or []:
        store._exec('UPDATE message SET TaskId=?, Status=? WHERE MessageId=? AND TaskId IS NULL', (tid, m['Status'], m['MessageId']))
    for rid in d.get('routes') or []: store._exec('UPDATE route SET TaskId=? WHERE RouteId=? AND TaskId IS NULL', (tid, rid))
    if d.get('ignore'): store._exec("DELETE FROM route WHERE RouteId=? AND Decision='ignore'", (d['ignore'],))
    if d.get('memory'):
        store.set_memory_active(d['memory'], False)        # ...which takes its LEARNED.md line out too (memorylines, 2026-10-27)
        from . import learn                 # ...and what that note fed in LEARNED.md goes with it (learn.withdraw)
        learn.withdraw(store, d['memory']); learn.note_verdicts(store)
    for i in d.get('ideas') or []:
        store._exec('UPDATE idea SET Status=?, DecidedBy=?, DecidedAt=? WHERE IdeaId=?', (i['Status'], i.get('DecidedBy'), i.get('DecidedAt'), i['IdeaId']))
    store._bump_snapshots()
    store._poke('feed-changed', 'task-changed', task_id=tid)
    return tid


class Gone(LookupError): pass
class Taken(ValueError): pass


def restore(store, cfg: dict, did: int) -> dict:
    """Put one back as it was. Gone when Recently deleted no longer holds it; Taken when its place was filled since."""
    r = store.get_deleted(int(did))
    if not r: raise Gone('it is no longer in Recently deleted')
    kind, d = r['Kind'], json.loads(r['DataJson'] or '{}')
    if kind == 'profile' and d['name'] in cfg.get('agents', {}): raise Taken(f"a profile named {d['name']} exists again - rename it first")
    if kind == 'cli' and d['name'] in cfg.get('cli_connections', {}): raise Taken(f"{d['name']} is connected again already")
    store.drop_deleted(r['DeletedId'])
    if kind in ('report', 'workflow', 'dashboard', 'source'): store.put_back('source', d['row'], 'SourceId')
    elif kind == 'rule':
        from . import policy as policy_engine
        store.put_back('policy', d['row'], 'PolicyId')
        policy_engine.apply_retroactively(store, d['row'])         # a skip rule hides its sender's history again
    elif kind == 'profile':
        from . import config
        cfg.setdefault('agents', {})[d['name']] = d['conf']
        config.save(cfg)
        if d.get('row') and not store.get_agent(d['name']): store.put_back('agent', d['row'], 'AgentId')
        doc = d.get('doc')
        if doc and store.get_doc(doc['Name']) is None: store.save_doc(doc['Name'], doc['Content'], doc.get('UpdatedBy') or 'import')
    elif kind == 'cli':
        from . import config, cli_connections
        cfg.setdefault('cli_connections', {})[d['name']] = d['conn']
        for n, prof in (d.get('users') or {}).items():
            if n in cfg.get('agents', {}): cfg['agents'][n] = prof
        config.save(cfg)
        cli_connections.sync(cfg, store)
    elif kind == 'task': return {'kind': kind, 'title': r['Title'], 'task_id': _restore_task(store, d)}
    elif kind in SHORT:
        row = d.get('row') or {}
        store._exec('UPDATE connector SET ConfigJson=?, Secret=?, Active=?' + (', Scope=?, LastSyncAt=?' if kind == 'connection' else '')
                    + ' WHERE ConnectorId=?',
                    [row.get('ConfigJson'), row.get('Secret'), row.get('Active') or 0]
                    + ([row.get('Scope'), row.get('LastSyncAt')] if kind == 'connection' else []) + [d['cid']])
        for sid in d.get('sources') or []: store._exec('UPDATE source SET Active=1 WHERE SourceId=?', (sid,))
    return {'kind': kind, 'title': r['Title']}
