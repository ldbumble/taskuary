"""ONE LOG PER TASK (the owner's approved redesign A, 2026-11-19): what a task's chat draws is appended here once, as it happens, at the
place it gets then - his line when the agent heard it, a message that came in, his press, a turn, each step of a turn, the one action box,
a failure. The row's `Id` is its place for good: nothing renumbers it, re-sorts it, re-dates it or moves it. What can still change - a turn
at work that ends, a card he presses - is updated in place (`State`, `Body`, `Rev`), never moved. The reader is one indexed SELECT.

Every producer writes through `put`/`update`/`step`; the reader is `read`. The rule for when a running turn is split by his line lives in
`step`, at write time, decided once."""
import json, logging, os, time

logger = logging.getLogger(__name__)

KINDS = ('line', 'arrival', 'press', 'note', 'turn', 'step', 'card', 'fail', 'handover')
TOP = ('line', 'arrival', 'press', 'note', 'turn', 'card', 'fail', 'handover')     # ...a card or a failure with no turn above it stands alone
INPUTS = ('line', 'arrival', 'press')          # ...what a turn heard: one appended after a turn begun ends that turn's run of steps
LIVE = ('starting', 'working')


class Frozen(ValueError):
    "A field that was written once and is the record of what he saw: when a thing came, when a turn began, a finished turn's words."


def _frozen(kind: str, state, old: dict, new: dict) -> list:
    keys = ['at'] if kind in INPUTS else []
    if kind == 'turn': keys += ['started'] + (['text'] if state == 'done' else [])
    return [k for k in keys if k in old and old[k] not in (None, '') and k in new and new[k] != old[k]]


def _strict() -> bool: return 'PYTEST_CURRENT_TEST' in os.environ


def _bump(store, tid: int) -> None:
    store.cx.execute('INSERT INTO chatlog_task (TaskId, Rev) VALUES (?, 1) ON CONFLICT(TaskId) DO UPDATE SET Rev = Rev + 1', (int(tid),))


def _poke(store, tid: int) -> None:
    try: store._poke('task-changed', task_id=int(tid))
    except Exception: pass


def _row(store, tid: int, key: str):
    r = store.cx.execute('SELECT * FROM chatlog WHERE TaskId=? AND Key=?', (int(tid), key)).fetchone()
    return dict(r) if r else None


def _parent(store, tid: int, parent):
    if parent is None or isinstance(parent, int): return parent
    r = _row(store, tid, str(parent))
    return r['Id'] if r else None


def _when(at) -> float:
    "A row's time as a number: given as one, or a stamp the store wrote; else now."
    if isinstance(at, (int, float)) and at: return float(at)
    if at:
        from .conversation import ep
        if (t := ep(at)): return t
    return time.time()


def put(store, tid: int, kind: str, key: str, body: dict, parent=None, state=None, src=None, at: float = None) -> int:
    """Append once (the task's `key` names it for good); an existing key is update()d in place. Returns the row's Id - its place.
    `parent`: the turn row (its Id or key) a step, card or failure belongs to; `at`: when it happened, the time the screen shows."""
    if kind not in KINDS: raise ValueError(f'no chat item of kind {kind!r}')
    with store.lock:
        if (old := _row(store, tid, key)):
            _update(store, tid, old, state, body)
            store.cx.commit()
            n = old['Id']
        else:
            body = dict(body or {})
            cur = store.cx.execute('INSERT INTO chatlog (TaskId, Key, Kind, Parent, At, Src, Body, State) VALUES (?,?,?,?,?,?,?,?)',
                                   (int(tid), key, kind, _parent(store, tid, parent), _when(body.get('at') if at is None else at), src, json.dumps(body, default=str), state))
            _bump(store, tid); store.cx.commit()
            n = cur.lastrowid
    _poke(store, tid)
    return n


def _update(store, tid: int, old: dict, state, patch: dict) -> bool:
    body = json.loads(old['Body'] or '{}')
    if (bad := _frozen(old['Kind'], old['State'], body, patch or {})):
        msg = f"chatlog: {old['Key']} on task {tid} keeps its {', '.join(bad)} - the record of what he saw"
        if _strict(): raise Frozen(msg)
        logger.warning(msg); patch = {k: v for k, v in patch.items() if k not in bad}
    new = {**body, **(patch or {})}
    st = old['State'] if state is None else state
    if new == body and st == old['State']: return False
    store.cx.execute('UPDATE chatlog SET Body=?, State=?, Rev=Rev+1 WHERE Id=?', (json.dumps(new, default=str), st, old['Id']))
    _bump(store, tid)
    return True


def update(store, tid: int, key: str, state=None, **patch) -> bool:
    "Merge `patch` into the row's body and set its state, in place: its Id, At and Parent never change. False when there is no such row."
    with store.lock:
        if not (old := _row(store, tid, key)): return False
        changed = _update(store, tid, old, state, patch)
        store.cx.commit()
    if changed: _poke(store, tid)
    return True


def get(store, tid: int, key: str):
    "One row as the reader draws it, or None."
    with store.lock: r = _row(store, tid, key)
    return _item(r) if r else None


def open_turn(store, tid: int):
    "The newest turn with nothing he or the world did appended after it - the one a step goes into - or None."
    with store.lock:
        t = store.cx.execute("SELECT * FROM chatlog WHERE TaskId=? AND Kind='turn' AND Parent IS NULL ORDER BY Id DESC LIMIT 1", (int(tid),)).fetchone()
        if not t: return None
        after = store.cx.execute(f"SELECT 1 FROM chatlog WHERE TaskId=? AND Id>? AND Parent IS NULL AND Kind IN ({','.join('?' * len(INPUTS))}) LIMIT 1",
                                 (int(tid), t['Id'], *INPUTS)).fetchone()
    return None if after else dict(t)


def step(store, tid: int, sid: str, ref: str, step: dict, state=None) -> int:
    """One tool, thought or said item of the turn at work, merged in place by its `ref` (a tool call updated as it runs). If his line, a
    message or a press was appended after that turn began, the rest of the turn is a NEW turn row under it ({cont: the turn it goes on from})
    - so what the agent did after it heard him is below his line by construction. The files a step made ride on its own row."""
    key = f's:{sid}:{ref}'
    with store.lock:
        if (old := _row(store, tid, key)):
            _update(store, tid, old, state, step); store.cx.commit(); n = old['Id']
        else:
            last = store.cx.execute("SELECT * FROM chatlog WHERE TaskId=? AND Kind='turn' AND Parent IS NULL ORDER BY Id DESC LIMIT 1", (int(tid),)).fetchone()
            t = open_turn(store, tid)
            if t is None:
                prev = json.loads(last['Body']) if last else {}
                k = f"{last['Key']}+{store.cx.execute('SELECT COUNT(*) FROM chatlog WHERE TaskId=? AND Kind=?', (int(tid), 'turn')).fetchone()[0]}" if last else f't:{sid}:0'
                body = {'cont': last['Key'], 'started': prev.get('started'), 'sid': sid} if last else {'started': time.time(), 'sid': sid}
                cur = store.cx.execute('INSERT INTO chatlog (TaskId, Key, Kind, At, Src, Body, State) VALUES (?,?,?,?,?,?,?)',
                                       (int(tid), k, 'turn', time.time(), f'sid:{sid}', json.dumps(body, default=str), last['State'] if last and last['State'] in LIVE else 'working'))
                t = {'Id': cur.lastrowid}
            cur = store.cx.execute('INSERT INTO chatlog (TaskId, Key, Kind, Parent, At, Src, Body, State) VALUES (?,?,?,?,?,?,?,?)',
                                   (int(tid), key, 'step', t['Id'], time.time(), f'{sid}:{ref}', json.dumps(step, default=str), state))
            _bump(store, tid); store.cx.commit(); n = cur.lastrowid
    _poke(store, tid)
    return n


def _item(r: dict) -> dict:
    b = json.loads(r['Body'] or '{}')
    return {**b, 'id': r['Key'], 'kind': r['Kind'], **({'state': r['State']} if r['State'] is not None else {}), 'at': b.get('at', r['At'])}


def rev(store, tid: int) -> int:
    r = store.cx.execute('SELECT Rev FROM chatlog_task WHERE TaskId=?', (int(tid),)).fetchone()
    return r['Rev'] if r else 0


def read(store, tid: int) -> dict:
    """The task's chat in its one order: top-level rows by their place, each turn with its steps, and its cards and failures once it is
    no longer at work (a card is a turn's last thing - the reader's one rule)."""
    with store.lock:
        rows = [dict(r) for r in store.cx.execute('SELECT * FROM chatlog WHERE TaskId=? ORDER BY Id', (int(tid),))]
        n = rev(store, tid)
    kids, out = {}, []
    for r in rows:
        if r['Parent'] is not None: kids.setdefault(r['Parent'], []).append(r)
    for r in rows:
        if r['Parent'] is not None: continue
        x = _item(r)
        if r['Kind'] == 'turn':
            ks = kids.get(r['Id'], [])
            x['steps'] = [_item(k) for k in ks if k['Kind'] == 'step']
            x['cards'] = [] if r['State'] in LIVE else [_item(k) for k in ks if k['Kind'] in ('card', 'fail')]
        out.append(x)
    return {'rev': n, 'items': out}
