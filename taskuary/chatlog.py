"""ONE LOG PER TASK (the owner's approved redesign A, 2026-11-19): what a task's chat draws is appended here once, as it happens, at the
place it gets then - his line when the agent heard it, a message that came in, his press, a turn, each step of a turn, the one action box,
a failure. The row's `Id` is its place for good: nothing renumbers it, re-sorts it, re-dates it or moves it. What can still change - a turn
at work that ends, a card he presses - is updated in place (`State`, `Body`, `Rev`), never moved. The reader is one indexed SELECT.

Every producer writes through `put`/`update`/`step`; the reader is `read`. The rule for when a running turn is split by his line lives in
`step`, at write time, decided once."""
import hashlib, json, logging, os, re, time
from .timewords import plural

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
            n = cur.lastrowid
            if kind != 'turn' and parent is None: _goes_on(store, tid, n)
            _bump(store, tid); store.cx.commit()
    _poke(store, tid)
    return n


def _goes_on(store, tid: int, below: int) -> None:
    """WHAT IS APPENDED WHILE A TURN WORKS STANDS ABOVE THE REST OF IT (the turn at work is always the last thing): the part of the turn before
    it is over, and the turn goes on in a new row under it ({cont}) - its steps from then on go there. Under the store's lock."""
    t = store.cx.execute("SELECT * FROM chatlog WHERE TaskId=? AND Kind='turn' AND Parent IS NULL AND State IN ('starting','working') AND Id<? "
                         "ORDER BY Id DESC LIMIT 1", (int(tid), below)).fetchone()
    if not t: return
    b = json.loads(t['Body'] or '{}')
    store.cx.execute("UPDATE chatlog SET State='done', Rev=Rev+1 WHERE Id=?", (t['Id'],))
    store.cx.execute('INSERT INTO chatlog (TaskId, Key, Kind, At, Src, Body, State) VALUES (?,?,?,?,?,?,?)',
                     (int(tid), f"{t['Key'].split('+')[0]}+{below}", 'turn', time.time(), t['Src'],
                      json.dumps({'cont': t['Key'], 'started': b.get('started'), 'ended': None, 'text': '', **({'sid': b['sid']} if b.get('sid') else {})}), t['State']))


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
                # ...and the part above his line is over: the work goes on below it (the same turn's state, carried down, never two at work)
                if last and last['State'] in LIVE: store.cx.execute("UPDATE chatlog SET State='done', Rev=Rev+1 WHERE Id=?", (last['Id'],))
            if t.get('State') == 'starting': store.cx.execute("UPDATE chatlog SET State='working', Rev=Rev+1 WHERE Id=?", (t['Id'],))
            cur = store.cx.execute('INSERT INTO chatlog (TaskId, Key, Kind, Parent, At, Src, Body, State) VALUES (?,?,?,?,?,?,?,?)',
                                   (int(tid), key, 'step', t['Id'], time.time(), f'{sid}:{ref}', json.dumps(step, default=str), state))
            _bump(store, tid); store.cx.commit(); n = cur.lastrowid
    return n            # ...a step is its road's news (run-tail), never a task-changed of its own


def _drawn(r: dict, lit: bool) -> bool:
    "A card waiting behind the front is drawn nowhere; an offer outside the line only while no card of the line waits (one box, D)."
    return r['Kind'] not in ('card',) or r['State'] != 'held' and not (r['State'] == 'offer' and lit)


def _item(r: dict) -> dict:
    b = json.loads(r['Body'] or '{}')
    return {**b, 'id': r['Key'], 'kind': r['Kind'], **({'state': r['State']} if r['State'] is not None else {}), 'at': b.get('at', r['At'])}


def rev(store, tid: int) -> int:
    r = store.cx.execute('SELECT Rev FROM chatlog_task WHERE TaskId=?', (int(tid),)).fetchone()
    return r['Rev'] if r else 0


def reconcile(store, tid: int) -> None:
    """The turn at work reads what is so (general.working - one fact): starting until its agent works, at work while it does. And a coding
    agent in a terminal - Claude Code, Codex, any CLI whose own log Taskuary reads (codingchat.sessions) - has the steps its log added since
    written in the one shape, as every other road writes them as they come (logged)."""
    from . import general
    if (t := _live(store, tid)) and t['State'] == 'starting' and general.working(store, int(tid)): update(store, tid, t['Key'], state='working')
    logged(store, tid)


def logged(store, tid: int) -> None:
    try: _logged(store, tid)
    except Exception as e: logger.warning(f'chatlog: the CLI log of task {tid} was not read into the chat - {e}')


def _logged(store, tid: int) -> None:
    from . import codingchat
    if not codingchat._live(int(tid)): return
    for s in codingchat.owned(store, int(tid), codingchat.sessions(store, int(tid), local=False)):
        if s.get('source') == 'acp' or not s.get('live'): continue        # ...ACP writes its own, update by update (feed)
        steps_of(store, tid, str(s['sid']), s.get('steps') or [])


def steps_of(store, tid: int, sid: str, steps: list) -> None:
    "A CLI log's steps (sessionrecord: Claude's, Codex's, Copilot's, Gemini's) by their place in its log: new ones appended, changed ones in place."
    f = _FEEDS.setdefault((int(tid), f'log:{sid}'), {'wrote': {}})
    for i, s in enumerate(steps):
        if s.get('k') in ('you', 'brief'): continue
        x = one_step(s)
        if f['wrote'].get(i) == (j := json.dumps(x, sort_keys=True, default=str)): continue
        f['wrote'][i] = j
        step(store, tid, sid, f'log:{i}', x, state=x.get('status'))


def read(store, tid: int, level: str = None) -> dict:
    """`level`: how much of each turn's work is shown (detailed) - the task's own, else its kind's setting.
    The task's chat in its one order: top-level rows by their place, each turn with its steps, and its cards and failures once it is
    no longer at work (a card is a turn's last thing - the reader's one rule)."""
    reconcile(store, tid)
    came_in(store, tid)
    advance(store, tid)
    with store.lock:
        rows = [dict(r) for r in store.cx.execute('SELECT * FROM chatlog WHERE TaskId=? ORDER BY Id', (int(tid),))]
        n = rev(store, tid)
    kids, out = {}, []
    lit = any(r['Kind'] == 'card' and r['State'] == 'pending' for r in rows)
    for r in rows:
        if r['Parent'] is not None: kids.setdefault(r['Parent'], []).append(r)
    for r in rows:
        if r['Parent'] is not None or not _drawn(r, lit): continue
        x = _item(r)
        if r['Kind'] == 'turn':
            ks = kids.get(r['Id'], [])
            x['steps'] = [_item(k) for k in ks if k['Kind'] == 'step']
            # ...a turn with its failed line says the failure once: there, never again as an error step under it
            if x.get('fail'): x['steps'] = [s for s in x['steps'] if s.get('k') != 'error']
            # ...and one taken back (took_back) says so as its step: its words and their summary are no answer
            if any(s.get('took') for s in x['steps']): x['text'] = ''; x.pop('summary', None)
            x['cards'] = [] if r['State'] in LIVE else [_item(k) for k in ks if k['Kind'] in ('card', 'fail') and _drawn(k, lit)]
            # ...a turn that ended having said, done and left nothing is no item (a part a line cut off before it did anything)
            if r['State'] not in LIVE and not (x.get('text') or x['steps'] or x['cards'] or x.get('summary') or x.get('fail')): continue
        out.append(x)
    moved_past(store, out)
    lvl = level_of(store, store.get_task(int(tid)) or {}, level)
    return {'rev': n, 'items': [detailed(x, lvl) for x in out], 'level': lvl}


DRAFTS = ('draft_reply', 'draft')
def moved_past(store, out: list) -> None:
    """A CARD HE WROTE PAST IS GREY WHERE IT STANDS, from the read his line is drawn in (the owner, 2026-11-12; the recorded walk on the log,
    2026-11-19: the old draft stood pressable over his newer line until the turn that heard it set it aside): a draft above a newer input, and
    any card of the agent's above his newer line, reads `passed` - its words kept, nothing to press - and says why (proposals.passed_why)."""
    from . import proposals
    last_in = max((i for i, x in enumerate(out) if x['kind'] in ('line', 'arrival')), default=-1)
    last_his = max((i for i, x in enumerate(out) if x['kind'] == 'line'), default=-1)
    for i, x in enumerate(out):
        for c in [x] if x['kind'] == 'card' else x.get('cards') or [] if x['kind'] == 'turn' else []:
            if c.get('status') == 'pending' and (c.get('was') or c.get('what') == 'batch') and (c.get('what') in DRAFTS and i < last_in or i < last_his):
                c['status'] = 'passed'
                if (rv := store.get_review(c['review'])): c['why'] = proposals.passed_why(store, rv)


# ── the producers' doors (dual-write: the legacy reader still serves the page; the log is written beside it) ─────────────────────────
def _safe(f):
    "A producer's write to the log never breaks the road it rides on: the old record is still what the agent and the page read."
    def go(*a, **k):
        try: return f(*a, **k)
        except Frozen: raise
        except Exception as e: logger.warning(f'chatlog: {f.__name__} was not written - {e}')
    go.__name__ = f.__name__
    return go


@_safe
def heard(store, tid: int, new: list, at: float) -> None:
    """What one hand-over took (conversation.hear), in the order it took it: his lines, the messages, the presses - and the turn it began.
    Each is appended now, under everything already in the log - the place it is heard is its place for good."""
    from . import general
    from .conversation import _mail, stamp
    tid = int(tid)
    mails = {str(x['MessageId']): x for x in _mail(store, tid)} if any(k == 'mail' for k, _ in new) else {}
    presses = {m['id'].split('-')[1]: m for m in general.press_lines(store, tid)} if any(k == 'press' for k, _ in new) else {}
    # ...one turn at work, ever: a turn the agent never answered is over when the next begins - before what this hand-over took is appended
    if any(k == 'turn' for k, _ in new) and (old := _live(store, tid)): update(store, tid, old['Key'], state='done')
    if any(k == 'turn' for k, _ in new): opener(store, tid, at)
    for k, r in new:
        if k == 'line':
            # ...heard at his press, a beat before its row is filed (general.take_line): its place is taken now, its words come with the row (filed)
            c = store._one('SELECT * FROM comment WHERE TaskId=? AND LineId=? ORDER BY CommentId DESC LIMIT 1', (tid, r))
            put(store, tid, 'line', r, {'at': c['CreatedAt'], **general.his_line(c)} if c else {'text': ''}, src=f"comment:{c['CommentId']}" if c else 'heard', at=at)
        elif k == 'mail' and (x := mails.get(r)) and (x.get('Channel') or '') != OWN:
            put(store, tid, 'arrival', f'm:{r}', {**general.mail_row(store, x), 'joined': stamp(x['T'])}, src=f'message:{r}', at=at)
        elif k == 'press' and (m := presses.get(r)):
            put(store, tid, 'press' if m.get('press') else 'note', f'p:{r}', {'at': m['createdAt'], 'text': m['content'][0]['text'],
                **({'perm': m['perm']} if m.get('perm') else {})}, src=f'audit:{r}', at=at)
        elif k == 'turn':
            put(store, tid, 'turn', f't:{r}', {'started': at, 'ended': None, 'text': ''}, state='starting', src='heard', at=at)


def _live(store, tid: int):
    with store.lock:
        r = store.cx.execute("SELECT * FROM chatlog WHERE TaskId=? AND Kind='turn' AND Parent IS NULL AND State IN ('starting','working') "
                             "ORDER BY Id DESC LIMIT 1", (int(tid),)).fetchone()
    return dict(r) if r else None


@_safe
def filed(store, tid: int, line_id: str, c: dict) -> None:
    "His line's row filed after it was heard: its words go into the place it took then."
    if (r := get(store, tid, line_id)) and r['kind'] == 'line' and not (r.get('text') or r.get('files')):
        from . import general
        update(store, tid, line_id, at=c['CreatedAt'], **general.his_line(c))


@_safe
def answered(store, tid: int, cid: int, actor: str, body: str, created: str) -> None:
    """An answer filed (an ASSISTANT_TYPE comment): the turn at work ends with its words - in place, never moved. Taskuary's own note in
    the agent's name (sessionrecord.NOTE_ACTOR) is a note; an answer nothing marked the start of is a turn of its own, where it is filed."""
    from . import general, sessionrecord
    from .conversation import clean
    tid = int(tid)
    words = clean(str(body or ''))
    if actor == sessionrecord.NOTE_ACTOR: return void(put(store, tid, 'note', f'n:c{cid}', {'at': created, 'text': words}, src=f'comment:{cid}'))
    flush(store, tid)
    text, fail = general.failed_line(words)
    with store.lock:
        t = store.cx.execute("SELECT * FROM chatlog WHERE TaskId=? AND Kind='turn' AND Parent IS NULL ORDER BY Id DESC LIMIT 1", (tid,)).fetchone()
    # ...A FAILURE IS ONE PLAIN LINE IN HIS WORDS (say.owner): the provider's raw error stood twice, once as the turn's words and once as its line
    if fail and (raw := fail.strip()):
        from . import say
        text = '' if text.strip() == raw or (raw[:1] in '{[' and raw in text) else text
        fail = say.owner({'kind': 'turn_failed', 'raw': raw})
    done = {'text': text, 'ended': _when(created), 'answer': f'comment-{cid}', **({'fail': fail.strip()} if fail else {})}
    # ...the turn at work, or one his stop or a failure ended that has not said its last words yet
    if t and (t['State'] in LIVE or t['State'] in ('failed', 'stopped') and not json.loads(t['Body'] or '{}').get('answer')):
        update(store, tid, t['Key'], state='failed' if fail or t['State'] == 'failed' else t['State'] if t['State'] == 'stopped' else 'done', **done)
    else: put(store, tid, 'turn', f'a:c{cid}', {'started': _when(created), **done}, state='failed' if fail else 'done', src=f'comment:{cid}')
    # ...an answer taken back before it was filed (conversation.take_back, `ahead`) is that turn's step from the moment it lands
    from .conversation import TOOK_BACK
    from .general import ASSISTANT_TYPE
    with store.lock:
        bs = store.cx.execute("SELECT * FROM heard WHERE TaskId=? AND Kind='back' AND (Ref=? OR Ref LIKE '>%')", (tid, str(cid))).fetchall()
    # ...a mark made before any answer was filed belongs to the FIRST answer after it, never to every later one
    first = lambda n: (store._one('SELECT MIN(CommentId) AS c FROM comment WHERE TaskId=? AND ActorType=? AND CommentId>?', (tid, ASSISTANT_TYPE, n)) or {}).get('c')
    bs = [dict(b) for b in bs if b['Ref'] == str(cid) or b['Ref'][1:].isdigit() and int(b['Ref'][1:]) < cid and first(int(b['Ref'][1:])) == cid]
    if bs:
        took_back(store, tid, cid, next((b['Sid'] for b in reversed(bs) if b['Sid']), '') or TOOK_BACK)


@_safe
def took_back(store, tid: int, cid: int, why: str) -> None:
    """AN ANSWER TAKEN BACK IS A STEP OF ITS TURN (conversation.take_back): one note under the turn that filed it, its words no longer drawn
    as the answer (read) - and a later call says how it ended in that same line, never a second one. Its turn not in the log yet: answered
    reads the mark when the answer lands."""
    tid = int(tid)
    with store.lock:
        t = next((dict(r) for r in store.cx.execute("SELECT * FROM chatlog WHERE TaskId=? AND Kind='turn' AND Body LIKE ? ORDER BY Id DESC",
                                                     (tid, f'%"comment-{int(cid)}"%')) if json.loads(r['Body'] or '{}').get('answer') == f'comment-{int(cid)}'), None)
        if not t: return
        s = next((dict(r) for r in store.cx.execute("SELECT * FROM chatlog WHERE Parent=? AND Kind='step' ORDER BY Id", (t['Id'],))
                  if json.loads(r['Body'] or '{}').get('took')), None)
        if s: _update(store, tid, s, None, {'text': why})
        else:
            store.cx.execute('INSERT INTO chatlog (TaskId, Key, Kind, Parent, At, Src, Body, State) VALUES (?,?,?,?,?,?,?,?)',
                             (tid, f'back:c{int(cid)}', 'step', t['Id'], time.time(), f'comment:{int(cid)}', json.dumps({'k': 'note', 'text': why, 'took': True}), None))
            _bump(store, tid)
        store.cx.commit()
    _poke(store, tid)


def void(_): return None


@_safe
def summarized(store, tid: int, body: str) -> None:
    "A turn's summary (what it was about, what it did, what is left on him) filed after its answer: kept on that turn's own row."
    try: sm = json.loads(body or '')
    except ValueError: return
    with store.lock:
        t = store.cx.execute("SELECT Key FROM chatlog WHERE TaskId=? AND Kind='turn' AND Parent IS NULL AND Body LIKE '%\"answer\"%' ORDER BY Id DESC LIMIT 1",
                             (int(tid),)).fetchone()
    if t: update(store, tid, t['Key'], summary=sm)


WAITS = 'w'
def left_on_him(store, tid: int, out: list, ask: dict = None, letters: str = None) -> None:
    """"FOR YOU TO DO" IS THE TURN'S OWN, SAID ONCE AND KEPT (design round 5, I3, the owner's): whether a finished turn says what it left on him
    (its summary's `on_you`) is settled the first read that can - its summary filed, its own question, letters and cards pressed, or his line
    under it - and written on THAT turn's row (`on_you_kept`), never changed after: never grown above his reply, never moved to a later turn,
    not said again where the turn before said the same. It stands at that turn's foot, under its cards."""
    said = None
    for i, x in enumerate(out):
        if x['kind'] != 'turn' or x.get('state') in LIVE: continue
        sm = x.get('summary') or {}
        mine = [str(s) for s in sm.get('on_you') or [] if str(s).strip()] if not sm.get('nothing_left') else []
        was = x.get('on_you_kept')
        if was in (None, WAITS):
            waits = (ask and ask.get('turn') == x['id']) or letters == x['id'] or any(c.get('status') == 'pending' for c in x.get('cards') or [])
            under = any(y['kind'] in ('line', 'arrival') for y in out[i + 1:])
            if waits and not under:
                if was is None: update(store, tid, x['id'], on_you_kept=WAITS)
                continue
            if not sm and len(out) == i + 1: continue
            was = '1' if mine and mine != said and not waits and not (was == WAITS and under) else ''
            update(store, tid, x['id'], on_you_kept=was)
        if was and was != WAITS: x['on_you'], said = True, mine


@_safe
def left_note(store, tid: int, at_work: bool) -> None:
    """A CODING RUN THAT LEFT WITHOUT FINISHING SAYS SO IN ITS CHAT, WHERE IT HAPPENED (no dead ends - the owner's rule 4): the task's own idle
    sentence (funnel.idle_state, the one its rail row reads) appended once under the turn it left after, and kept there when the run is taken up
    again - a later leaving is a line of its own under its own turn."""
    from . import codingchat, funnel, general, taskstate
    task = store.get_task(int(tid)) or {}
    if at_work or codingchat._live(int(tid)) or general.handles(task) or task.get('Status') in ('done', 'dropped'): return
    t = _newest_turn(store, tid)
    if not t: return
    st = taskstate.task_state(store, tid=int(tid))
    if st.finished or (idle := funnel.idle_state(store, int(tid), st))['kind'] != 'left' or not idle['line']: return
    put(store, tid, 'note', f"n:left:{t['Key']}", {'text': idle['line']}, src='idle')


@_safe
def at_work(store, tid: int, sid: str = '') -> None:
    "The turn the agent has the prompt of: starting until then, working from its first word on (its road's own `prompt`)."
    if (t := open_turn(store, tid)) and t['State'] == 'starting': update(store, tid, t['Key'], state='working', **({'sid': sid} if sid else {}))


ENDS = ('stopped_turn', 'close_from_assistant')      # ...his stop and his close end the turn they were pressed under, and never wait
@_safe
def pressed(store, tid: int, aid: int, action: str) -> None:
    """His press (an audit row of his whose words general.PRESSES says): appended where he made it - unless a turn is at work, which hears
    it at its end (then `heard` appends it, where it was heard). His stop or close ends the turn at work, in place."""
    from . import general
    if action not in general.PRESSES: return
    m = next((m for m in general.press_lines(store, tid) if m['id'] == f'press-{aid}'), None)
    if not m: return
    with store.lock:
        live = store.cx.execute("SELECT * FROM chatlog WHERE TaskId=? AND Kind='turn' AND Parent IS NULL AND State IN ('starting','working') "
                                "ORDER BY Id DESC LIMIT 1", (int(tid),)).fetchone()
    if live and action not in ENDS and m.get('press'): return
    if live and action in ENDS: update(store, tid, live['Key'], state='stopped' if action == 'stopped_turn' else 'done')
    put(store, tid, 'press' if m.get('press') else 'note', f'p:{aid}', {'at': m['createdAt'], 'text': m['content'][0]['text'],
        **({'perm': m['perm']} if m.get('perm') else {}), **({'stop': True} if action == 'stopped_turn' else {})}, src=f'audit:{aid}')


@_safe
def failed(store, tid: int) -> None:
    "A try that failed ends where it failed (conversation.failed_try): the turn at work is over, failed - its line is the answer filed after."
    with store.lock:
        live = store.cx.execute("SELECT Key FROM chatlog WHERE TaskId=? AND Kind='turn' AND Parent IS NULL AND State IN ('starting','working') "
                                "ORDER BY Id DESC LIMIT 1", (int(tid),)).fetchone()
    if live: update(store, tid, live['Key'], state='failed')


def _shape(xs: list) -> list:
    "What the screen draws, in order, by what each thing is: a turn by its words and its state, anything else by its own name."
    return [('turn', x.get('state') if x.get('state') in LIVE else 'over', (x.get('text') or '')[:60]) if x['kind'] == 'turn'
            else (x['kind'], x['id']) for x in xs if x['kind'] != 'step']


def shadow(legacy: dict, log: dict) -> str:
    "The first place the log's chat and the old build's list (conversation_legacy) draw differently - '' where they agree."
    a, b = _shape(legacy.get('items') or []), _shape(log.get('items') or [])
    if a == b: return ''
    i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return f'at {i}: list {a[i:i + 3]} | log {b[i:i + 3]} ({len(a)} vs {len(b)})'


def his(body) -> dict:
    from . import general
    return general.his_line(body)


# ── STEPS: every road's record as the one step shape, written as it comes (stage 3) ──────────────────────────────────────────────────────
def one_step(s: dict) -> dict:
    """A step as every road writes it: what was done in plain words (`text` - its description where it gave one, else what it ran or read),
    the real command beside it (`detail`), the file it made or changed, its edit, status, output and error kept. One shape whatever the road."""
    from .sessionrecord import _args, _cut, _target
    k = s.get('k')
    if k != 'tool': return {x: s[x] for x in ('k', 'text', 'items', 'status', 'name', 'id', 'output') if s.get(x) not in (None, '')}
    a = s.get('args') if isinstance(s.get('args'), dict) else {}
    cmd = a.get('command') or a.get('cmd')
    cmd = ' '.join(map(str, cmd)) if isinstance(cmd, list) else str(cmd or '')
    desc = str(a.get('description') or '').strip()
    out = {'k': 'tool', 'name': str(s.get('name') or 'tool'), 'text': _cut(desc, 200) if desc else s.get('text') or _target(a) or cmd}
    if desc and cmd: out['detail'] = _cut(cmd, 4000)
    elif s.get('detail'): out['detail'] = s['detail']
    if (kept := _args(a)): out['args'] = kept
    for x in ('file', 'edit', 'status', 'output', 'out', 'id', 'parent'):
        if s.get(x) not in (None, '', {}): out[x] = s[x]
    return out


def _convert(road: str, events: list) -> list:
    from . import conversation, sessionrecord
    if road == 'trace': return sessionrecord.trace_steps(events)
    if road == 'acp': return conversation.acp_steps(events)
    st = {'out': []}
    line_of = {'claude-log': sessionrecord._claude_line, 'codex-log': sessionrecord._codex_line}[road]
    for j in events: line_of(st, j)
    return st['out']


_FEEDS: dict = {}
@_safe
def feed(store, tid: int, sid: str, road: str, event) -> None:
    """ONE EVENT OF A ROAD'S RECORD (a chat agent's trace event, an ACP update, a line of a CLI's log), as it comes: the turn's steps are
    read in the one shape and each new or changed one is written in place - by its place in the turn, so an update never moves it."""
    if not store or not tid or event is None: return
    t = open_turn(store, tid)
    root = (t['Key'] if t else '').split('+')[0]
    f = _FEEDS.get((int(tid), sid))
    if not f or f['root'] != root: f = _FEEDS[(int(tid), sid)] = {'root': root, 'seq': f'{int(time.time() * 1000)}', 'events': [], 'wrote': {}}
    f['events'].append(event); f['road'] = road
    # ...words a token at a time are written a few times a second, not once a token: the rest at the next step or the answer (flush)
    if _chunk(event) and time.time() - f.get('at', 0) < CHUNK_S: f['dirty'] = True; return
    _write(store, tid, sid, f)


CHUNK_S = 0.4
def _chunk(e) -> bool:
    return isinstance(e, dict) and (e.get('sessionUpdate') in ('agent_message_chunk', 'agent_thought_chunk') or e.get('type') == 'live')


@_safe
def flush(store, tid: int) -> None:
    "What the roads of task `tid` still hold back (a sentence's last tokens): written now - its answer is filed, or its turn ended."
    if not store or not tid: return
    for (t, sid), f in list(_FEEDS.items()):
        if t == int(tid) and f.get('dirty'): _write(store, tid, sid, f)


def _write(store, tid: int, sid: str, f: dict) -> None:
    f['at'], f['dirty'] = time.time(), False
    for i, s in enumerate(_convert(f['road'], f['events'])):
        if s.get('k') in ('you', 'brief'): continue          # ...his lines and Taskuary's briefs are the hand-over's, never a step
        x = one_step(s)
        if f['wrote'].get(i) == (j := json.dumps(x, sort_keys=True, default=str)): continue
        f['wrote'][i] = j
        step(store, tid, sid, f"{f['seq']}:{i}", x, state=x.get('status'))


# ── HOW MUCH OF THE WORK IS SHOWN: the one place the detail setting is applied ──────────────────────────────────────────────────────────
LEVELS = ('summary', 'steps', 'everything')
SETTING = {'coding': 'chat_detail_coding', 'other': 'chat_detail_other'}
SHIPPED = {'coding': 'everything', 'other': 'summary'}
SHOWN = ('said', 'show', 'view')          # ...what the agent put in front of him: never folded away


def level_of(store, task: dict, own: str = None) -> str:
    "The task's own level, else its kind's default from Settings (chat_detail_coding / chat_detail_other), else what ships."
    side = 'coding' if (task or {}).get('Kind') == 'coding' else 'other'
    return own if own in LEVELS else (v if (v := store.get_setting(SETTING[side], '')) in LEVELS else SHIPPED[side])


# ...EVERY TOOL CALL IS ONE ROW IN PLAIN WORDS (the owner, 2026-11-19: "better showing what tools are run on the canvas but not a billion
# details"): what it did and on what, its outcome in a few words where known, its output only behind the row - capped - and the same call made
# again folded into "(3 times)". The words are read off the call's own structure (its name, its arguments), never off what it means.
_DID = (('Ran', ('bash', 'shell', 'execute', 'powershell', 'local_shell_call', 'run')), ('Read', ('read', 'view', 'cat')),
        ('Edited', ('edit', 'multiedit', 'apply_patch', 'str_replace')), ('Wrote', ('write', 'create', 'notebookedit')),
        ('Searched the web for', ('websearch', 'web_search', 'search_web')), ('Opened', ('webfetch', 'fetch', 'open', 'navigate', 'browser')),
        ('Searched for', ('grep', 'glob', 'search', 'find')))
_KIND = {'Ran': ('ran', 'ran {n} commands', 'ran a command'), 'Read': ('read', 'read {n} files', 'read a file'), 'Edited': ('edited', 'edited {n} files', 'edited a file'),
         'Wrote': ('wrote', 'wrote {n} files', 'wrote a file'), 'Opened': ('opened', 'opened {n} sites', 'opened a site'),
         'Searched the web for': ('searched', 'searched the web {n} times', 'searched the web'), 'Searched for': ('searched', 'searched {n} times', 'searched'),
         'Used': ('used', 'used {n} tools', 'used a tool')}
OUT_N = 1500


def _verb(name: str) -> str:
    n = str(name or '').lower().rsplit('__', 1)[-1]
    return next((v for v, ks in _DID if any(n == k or n.startswith(k) for k in ks)), 'Used')


def _on(s: dict, verb: str) -> str:
    import os, re
    a = s.get('args') or {}
    if verb in ('Read', 'Edited', 'Wrote') and (f := s.get('file') or a.get('file_path') or a.get('path')): return os.path.basename(str(f).replace('\\', '/').rstrip('/')) or str(f)
    if verb == 'Opened' and (u := a.get('url') or s.get('text')) and (m := re.match(r'https?://(?:www\.)?([^/\s]+)', str(u))): return m.group(1)
    if verb == 'Ran': return str(s.get('detail') or a.get('command') or s.get('text') or '')[:160]
    if verb == 'Used': return str(s.get('name') or 'a tool').rsplit('__', 1)[-1]
    return str(a.get('query') or a.get('pattern') or s.get('text') or '')[:160]


def outcome(s: dict) -> str:
    "Its outcome in a few words, where its record says one: failed, a test run's own count, the number of results."
    import re
    out = str(s.get('output') or s.get('out') or '')
    if (m := re.findall(r'(\d+) (passed|failed|errors?)\b', out[-2000:])): return ', '.join(f'{n} {w}' for n, w in m[-2:])
    if s.get('status') == 'failed': return 'failed'
    return ''


def _capped(out: str) -> dict:
    out = str(out or '')
    return {} if not out else {'output': out} if len(out) <= 2 * OUT_N else {'output': f"{out[:OUT_N]}\n…\n{out[-OUT_N:]}", 'size': len(out)}


def tool_rows(steps: list) -> list:
    "A turn's steps with each tool call as its one row (`line`, `outcome`, the output capped behind it) and the same call again as `times`."
    out = []
    for s in steps:
        if s.get('k') != 'tool': out.append(s); continue
        verb = _verb(s.get('name')); on = _on(s, verb)
        r = {**{k: v for k, v in s.items() if k not in ('output', 'out')}, 'line': f'{verb} {on}'.strip() if on else verb, 'verb': verb,
             **({'outcome': o} if (o := outcome(s)) else {}), **_capped(s.get('output') or s.get('out'))}
        if out and out[-1].get('k') == 'tool' and out[-1]['line'] == r['line']: out[-1]['times'] = out[-1].get('times', 1) + 1; out[-1].update({k: r[k] for k in ('outcome', 'status') if k in r}); continue
        out.append(r)
    return out


def fold_line(rows: list) -> str:
    "A turn's work as one line: '12 steps - ran tests, read 3 files, opened 2 sites'."
    tools = [r for r in rows if r.get('k') == 'tool']
    n = sum(r.get('times', 1) for r in rows if r.get('k') != 'said') if rows else 0
    if not n: return ''
    by = {}
    for r in tools: by[r['verb']] = by.get(r['verb'], 0) + r.get('times', 1)
    said = [(_KIND[v][1].format(n=c) if c > 1 else _KIND[v][2]) for v, c in by.items()]
    return plural(n, 'step') + (f" - {', '.join(said)}" if said else '')


def detailed(turn: dict, level: str) -> dict:
    """A turn as the level shows it - THE ONE PLACE the detail setting is applied, the same for every brain road. Each tool call is one row in
    plain words (tool_rows). `summary`: its words, what it showed and its cards, every other row behind one line that opens on them (`fold`,
    `folded`: "12 steps - ran tests, read 3 files"); `steps` and `everything`: every row. A turn at work shows at every level what it says
    and shows as it comes, its rows under the one climbing line - the level decides once it has ended."""
    if turn.get('kind') != 'turn': return turn
    steps = tool_rows(turn.get('steps') or [])
    if level in ('steps', 'everything') and turn.get('state') not in LIVE: return {**turn, 'steps': steps, 'level': level}
    # ...every row stays in its order (`steps`); what the fold holds is named (`fold`), and the one line over it (`fold_line`)
    rest = [s for s in steps if s.get('k') not in SHOWN]
    return {**turn, 'steps': steps, 'fold': rest, 'folded': len(rest), 'fold_line': fold_line(rest),
            'level': 'summary' if turn.get('state') not in LIVE else 'live'}


# ── ARRIVALS (stage 4): what opened the task, and what came in while nothing worked ──────────────────────────────────────────────────────
EARLIER = 3600.
OWN = 'own'                     # ownwork.CHANNEL: the task's own row - his ask - never "came in"
def _inputs(store, tid: int) -> bool:
    with store.lock:
        return bool(store.cx.execute(f"SELECT 1 FROM chatlog WHERE TaskId=? AND Parent IS NULL AND Kind IN ('line','arrival') LIMIT 1", (int(tid),)).fetchone())


@_safe
def opener(store, tid: int, at: float = None) -> None:
    """THE FIRST TURN'S INPUT, where nothing he typed and nothing that came in opens the chat: his own ask (New - `a:`, his line) or what
    started it (a routine, a report - `s:`). Appended before the turn it began, once."""
    from . import ownwork
    from .conversation import started_by, stamp, _mail
    from .general import split_files
    if _inputs(store, tid): return
    t = store.get_task(int(tid)) or {}
    row = next((x for x in _mail(store, int(tid)) if (x.get('Channel') or '') == OWN), None)
    if (said := ownwork.ask(store, t, row)):
        when = row['T'] if row else _when(t.get('CreatedAt'))
        put(store, tid, 'line', f'a:{tid}', {'at': stamp(when), **split_files(said)}, src='ask', at=at)
    elif (by := started_by(store, t)):
        put(store, tid, 'arrival', f's:{tid}', {'who': by['head'], 'head': by['head'], 'channel': by['channel'], 'own': False,
                                               'at': t.get('CreatedAt'), 'files': 0, 'words': by['words']}, src='started', at=at)


@_safe
def came_in(store, tid: int) -> None:
    """WHAT CAME IN WHILE NOTHING WORKED is appended at the foot as it is found (a turn at work hears it at its end - `heard` - and until then
    it waits by the box). A THREAD THAT JOINED WITH ITS HISTORY (the owner, 2026-11-19): what is older than the chat's foot is never drawn above
    it - one line at the foot, "<name>'s thread joined (N messages, M earlier)", opens the earlier ones; the newest stand as they came."""
    from . import general
    from .conversation import _mail, stamp
    tid = int(tid)
    if _live(store, tid): return
    with store.lock:
        rows = [dict(r) for r in store.cx.execute("SELECT Key, Body FROM chatlog WHERE TaskId=? AND Kind='arrival'", (tid,))]
        have = {r['Key'] for r in rows} | {f'm:{m}' for r in rows if r['Key'][:2] == 'j:' for m in (json.loads(r['Body']).get('thread') or {}).get('mids') or []}
        foot = store.cx.execute('SELECT MAX(At) AS a FROM chatlog WHERE TaskId=? AND Parent IS NULL', (tid,)).fetchone()['a'] or 0
    # ...never what an untrusted sender wrote on a thread an agent works: it waits behind the Trust press (origin.hold)
    from . import origin
    held = set((origin.hold(store, tid) or {}).get('mids') or [])
    new = [x for x in _mail(store, tid) if (x.get('Channel') or '') != OWN and f"m:{x['MessageId']}" not in have and x['MessageId'] not in held]
    if not new: return
    # ...older by its OWN time (sent, else filed) - joined now, a thread from last week reads as now by when it joined
    # ...by more than a mail held up on its way takes (EARLIER): one a sender's clock or a slow server put a minute back stands as it came
    older = [x for x in new if foot and _when(x.get('SentAt') or x.get('CreatedAt')) < foot - EARLIER]
    if older:
        rest = [x for x in new if x not in older]
        who = older[-1].get('FromName') or older[-1].get('FromEmail') or 'A'
        n = len(older) + len(rest)
        put(store, tid, 'arrival', f"j:{older[-1]['MessageId']}",
            {'thread': {'name': who, 'n': n, 'earlier': len(older), 'mids': [x['MessageId'] for x in older]},
             'head': f"{who}'s thread joined ({plural(n, 'message')}, {len(older)} earlier)", 'who': who, 'own': False,
             'at': stamp(older[-1]['T']), 'words': '', 'files': 0}, src='thread')
        new = rest
    for x in new:
        put(store, tid, 'arrival', f"m:{x['MessageId']}", {**general.mail_row(store, x), 'joined': stamp(x['T'])}, src=f"message:{x['MessageId']}")


# ── THE ONE ACTION BOX (stage 5, D): cardqueue.advance is the only writer of card rows ─────────────────────────────────────────────────────
@_safe
def advance(store, tid: int) -> None:
    """The line of cards on task `tid` (cardqueue.state) into the log: the front is put as the ONE pending card - under the newest turn, as
    its last thing, once that turn is no longer at work - with the line's "n of m · next" in it; a card that stood is updated in place as it
    is pressed, withdrawn or moved past, never moved; one held behind the front has no row, so nothing can draw it. A card outside the line
    (Taskuary's own offer beside a reply - a playbook) stands as an `offer`, drawn only while no card of the line waits."""
    from . import cardqueue
    from .conversation import _card
    tid = int(tid)
    q = cardqueue.state(store, tid)
    with store.lock:
        rows = {r['Key']: dict(r) for r in store.cx.execute("SELECT * FROM chatlog WHERE TaskId=? AND Kind='card'", (tid,))}
    by = {r['ReviewId']: r for r in store._rows('SELECT * FROM review WHERE TaskId=? ORDER BY ReviewId', (tid,))}
    front = [x for x in q['live'] if x != cardqueue.LAND]
    held = set(q['held'])
    # ...every card that stood reads as its review does now: pressed, withdrawn, moved past - in its place
    for k, r in rows.items():
        rv = by.get(json.loads(r['Body']).get('review'))
        if not rv: continue
        st = _card(rv)['status']
        # ...one the chat moved past stays where it stood, its buttons greyed (proposals.written_past) - never taken off as if it waited behind
        if st == 'pending' and rv['ReviewId'] not in front: st = 'passed' if rv['ReviewId'] in q['past'] else 'offer' if r['State'] == 'offer' else 'held'
        if st != r['State']: update(store, tid, k, state=st, status=st)
    if front and (rv := by.get(front[0])) and f"r:{front[0]}" not in rows:
        t = _newest_turn(store, tid)
        if t and t['State'] in LIVE: return                     # ...a turn's card is its last thing: it comes when the turn has ended
        put(store, tid, 'card', f"r:{front[0]}", {**_card(rv), 'rids': front, 'line': cardqueue.line(q)}, parent=t['Id'] if t else None,
            state='pending', src=f"review:{front[0]}")
    elif front and f"r:{front[0]}" in rows: update(store, tid, f"r:{front[0]}", line=cardqueue.line(q))
    for rid, rv in by.items():
        if f'r:{rid}' in rows or rv['Status'] != 'pending' or cardqueue.in_line(rv) or rid in held: continue
        from .conversation import unwritten
        if unwritten(rv) or cardqueue.obsolete_read(store, tid, rv): continue
        t = _newest_turn(store, tid)
        if t and t['State'] in LIVE: continue
        put(store, tid, 'card', f'r:{rid}', {**_card(rv), 'offer': True}, parent=t['Id'] if t else None, state='offer', src=f'review:{rid}')


def _newest_turn(store, tid: int):
    with store.lock:
        r = store.cx.execute("SELECT * FROM chatlog WHERE TaskId=? AND Kind='turn' AND Parent IS NULL ORDER BY Id DESC LIMIT 1", (int(tid),)).fetchone()
    return dict(r) if r else None


def live_card(store, tid: int):
    "The one action box of task `tid` - what every surface draws (the chat, the browser's view, the phone, the rail) - or None."
    with store.lock:
        r = store.cx.execute("SELECT * FROM chatlog WHERE TaskId=? AND Kind='card' AND State='pending'", (int(tid),)).fetchone()
    return _item(dict(r)) if r else None


# ── MIGRATION (stage 6): what he saw stays as he saw it ───────────────────────────────────────────────────────────────────────────────────
_BACKED = set()
def backed_up(store) -> bool:
    """A copy of the database before the first task is written into the log - nothing is migrated without one (backups.make, `before-chatlog`).
    A store in memory has nothing to lose. False where the copy could not be made: then nothing migrates."""
    from pathlib import Path
    from . import backups
    db = getattr(store, '_path', '') or ''
    if db in _BACKED or db == ':memory:' or not Path(db).is_file(): return True
    try:
        if not store.get_setting('chatlog_backup', ''):
            out = backups.make(db, Path(db).parent, why='before-chatlog', files=False)
            if not out: return False
            store.set_setting('chatlog_backup', str(out), 'router')
        _BACKED.add(db); return True
    except Exception as e:
        logger.warning(f'chatlog: no copy of the database before the log - nothing migrates ({e})'); return False


def migrated(store, tid: int) -> bool:
    r = store.cx.execute('SELECT Migrated FROM chatlog_task WHERE TaskId=?', (int(tid),)).fetchone()
    return bool(r and r['Migrated'])


def migrate(store, tid: int, legacy=None) -> bool:
    """A TASK'S CHAT, FROZEN ONCE AS IT WAS LAST DRAWN (the spec's §4): the list the old build serves (`legacy` - conversation_legacy.items) is
    written item by item in its order - each turn's steps and cards under it - and from then on the producers append. What waits by the box
    stays pending; a turn at work stays at work, so its road goes on appending under it; of two cards that waited at once the front stays
    and the other is held (one box). Done once per task, under the store's lock; True when it was done now."""
    from . import cardqueue
    if migrated(store, tid) or not backed_up(store): return False
    got = legacy if legacy is not None else _legacy(store, tid)
    live = set((cardqueue.state(store, int(tid)) or {}).get('live') or [])
    with store.lock:
        if migrated(store, tid): return False
        store.cx.execute('DELETE FROM chatlog WHERE TaskId=?', (int(tid),))          # ...what dual-write wrote before is the warm-up: the list is the record
        prev, seen_live = 0., False
        def row(kind, key, body, parent=None, state=None):
            nonlocal prev
            at = max(prev, _when(body.get('started') if kind == 'turn' else body.get('at')) if (body.get('started') or body.get('at')) else prev)
            prev = at
            cur = store.cx.execute('INSERT OR IGNORE INTO chatlog (TaskId, Key, Kind, Parent, At, Src, Body, State) VALUES (?,?,?,?,?,?,?,?)',
                                   (int(tid), key, kind, parent, at or time.time(), 'legacy', json.dumps(body, default=str), state))
            return cur.lastrowid
        for x in got.get('items') or []:
            body = {k: v for k, v in x.items() if k not in ('id', 'kind', 'state', 'steps', 'cards') and not k.startswith('_')}
            if x['kind'] != 'turn':
                st = x.get('status') if x['kind'] == 'card' else None
                if x['kind'] == 'card' and st == 'pending': st = 'pending' if not seen_live and (x.get('review') in live or not live) else 'held'
                seen_live = seen_live or st == 'pending'
                row(x['kind'], x['id'], body, state=st); continue
            n = row('turn', x['id'], body, state=x.get('state'))
            if x.get('state') in LIVE and x.get('sid'):
                store.cx.execute('UPDATE chatlog SET Src=? WHERE Id=?', (f"sid:{x['sid']}", n))
            for i, s in enumerate(x.get('steps') or []):
                store.cx.execute('INSERT OR IGNORE INTO chatlog (TaskId, Key, Kind, Parent, At, Src, Body, State) VALUES (?,?,?,?,?,?,?,?)',
                                 (int(tid), f"{x['id']}:s{i}", 'step', n, prev or time.time(), 'legacy', json.dumps(s, default=str), s.get('status')))
            for c in x.get('cards') or []:
                st = c.get('status')
                if st == 'pending': st = 'pending' if not seen_live and (c.get('review') in live or not live) else 'held'
                seen_live = seen_live or st == 'pending'
                store.cx.execute('INSERT OR IGNORE INTO chatlog (TaskId, Key, Kind, Parent, At, Src, Body, State) VALUES (?,?,?,?,?,?,?,?)',
                                 (int(tid), c['id'], 'card', n, prev or time.time(), 'legacy', json.dumps({k: v for k, v in c.items() if k not in ('id', 'kind')}, default=str), st))
        store.cx.execute("INSERT INTO chatlog_task (TaskId, Rev, Migrated) VALUES (?, 1, datetime('now')) ON CONFLICT(TaskId) DO UPDATE SET Rev=Rev+1, Migrated=excluded.Migrated",
                         (int(tid),))
        store.cx.commit()
    return True


def _legacy(store, tid: int) -> dict:
    from . import conversation_legacy
    return conversation_legacy.items(store, int(tid))


def migrate_open(store, stop=None) -> int:
    "The background pass after start-up: every open task's chat frozen into the log, one at a time - a done task migrates when it is opened."
    n = 0
    for t in store._rows("SELECT TaskId FROM task WHERE Status NOT IN ('done','dropped') ORDER BY TaskId DESC"):
        if stop is not None and stop.is_set(): break
        try: n += migrate(store, t['TaskId'])
        except Exception as e: logger.warning(f"chatlog: task {t['TaskId']} not migrated - {e}")
    return n


# ── THE READER (stage 8): the page's chat is the log's - and what stands beside it, read here ──────────────────────────────────────────────
def serve(store, tid: int, level: str = None) -> dict:
    """What the page draws for task `tid`: the log's items, in its one order, each turn at its level, and beside them what waits by the box,
    what the agent asks, the permissions it waits on, the line of cards and the hold. A task is frozen into the log at its first read
    (migrate); what waits is never also drawn (an input is in one place)."""
    from . import general, origin
    tid = int(tid)
    if not migrated(store, tid): migrate(store, tid)
    hold_ = origin.hold(store, tid)
    at_work = general.working(store, tid) if not hold_ else bool(getattr(general._live_of(tid), 'busy', False))
    if at_work and (h := _halted(store, tid)): at_work = bool(general.waiting_lines(store, tid)) or h == 'stopped_turn' and bool(getattr(general._live_of(tid), 'owes_stop', lambda: False)())
    # ..."working" is one fact (general.working): a turn the log holds at work while nothing works has either not begun yet - nothing of it is
    # drawn until it has - or was left by a process that is gone (a restart): it is over, in place
    if not at_work and (t := _live(store, tid)):
        with store.lock: n = store.cx.execute('SELECT COUNT(*) FROM chatlog WHERE Parent=?', (t['Id'],)).fetchone()[0]
        if n or json.loads(t['Body'] or '{}').get('text'): update(store, tid, t['Key'], state='done')
    left_note(store, tid, at_work)
    got = read(store, tid, level)
    out = got['items'] if at_work else [x for x in got['items'] if not (x['kind'] == 'turn' and x.get('state') in LIVE)]
    if at_work and (lv := next((x for x in reversed(out) if x['kind'] == 'turn' and x.get('state') in LIVE), None)): lv.update(_now(tid, lv))
    body = {'items': out, 'level': got['level'], **beside(store, tid, out, at_work, hold_)}
    return {'rev': hashlib.sha1(json.dumps(body, default=str).encode()).hexdigest()[:16], **body}


def _halted(store, tid: int) -> str:
    """His stop or close (its audit action, ENDS) while it is the newest thing in the chat, '' else. A TURN HE STOPPED IS STOPPED FROM THE PRESS
    (the recorded stops, 2026-11-11 and 2026-11-17): its CLI takes a beat to let go, and all that time nothing works under "You stopped the
    agent" - only the turn his waiting lines begin, or the one the stopped turn owes him (owes_stop); a close owes nothing."""
    with store.lock:
        for r in store.cx.execute('SELECT Kind, Key FROM chatlog WHERE TaskId=? AND Parent IS NULL ORDER BY Id DESC', (int(tid),)):
            if r['Kind'] in ('turn', 'line', 'arrival'): return ''
            if r['Kind'] in ('press', 'note') and r['Key'][2:].isdigit():
                a = store.cx.execute('SELECT Action FROM audit WHERE Id=?', (int(r['Key'][2:]),)).fetchone()
                if a and a['Action'] in ENDS: return a['Action']
    return ''


def _now(tid: int, turn: dict) -> dict:
    """What the turn at work is doing this moment, off its session's own trace - never written to the log, it changes by the token:
    `opening` while its agent really is starting (recorded on the real CLI, 2026-11-16: a cold adapter took most of a minute under "Thinking...")
    - from its start where no CLI is up (general.cold), until its road hands it the prompt; `doing`, the answer being written while that is
    the newest thing it did."""
    from . import general
    from .conversation import clean
    ses = general.session_for(tid)
    if ses is None: return {'opening': True} if turn.get('state') == 'starting' and general.cold(tid) else {}
    trace = getattr(ses, 'trace', None) or []
    kinds = [e.get('type') for e in trace]
    opening = 'opening' in kinds and kinds[::-1].index('opening') < (kinds[::-1].index('prompt') if 'prompt' in kinds else len(kinds))
    e = trace[-1] if trace else {}
    doing = clean(e.get('detail')) if e.get('type') == 'live' and e.get('name') == 'writing' else ''
    return {**({'opening': True} if opening else {}), **({'doing': doing} if doing else {})}


def beside(store, tid: int, out: list, at_work: bool, hold_) -> dict:
    """What the page draws beside the chat's items, each from the fact that says it: what waits for the agent (`pending` - his lines not yet
    heard; a message, a press while a turn works; what an untrusted sender wrote), `now`/`later` (whether a waiting line goes in mid-turn),
    `asking` (in the turn that asked), `permissions`, `queue` (the line of cards), `hold`, `letters` (the turn whose letter waits), `idle`
    (why nothing started), the pages it published, and the CLI that runs."""
    from . import cardqueue, codingchat, general, origin, outputs, permissions, taskstate
    from .conversation import LATER, START_BY_WRITING, came, ep, stamp, _mail
    from .general import WAITING_TYPE
    task = store.get_task(tid) or {'TaskId': tid}
    drawn = {x['id'] for x in out}
    led = {(r['Kind'], r['Ref']) for r in store._rows('SELECT Kind, Ref FROM heard WHERE TaskId=?', (tid,))}
    held = set((hold_ or {}).get('mids') or [])
    pend = []
    for c in store.list_comments(tid, internal=True):
        k = c.get('LineId') or f"c:{c['CommentId']}"
        if c.get('ActorType') != WAITING_TYPE or k in drawn or ('line', c.get('LineId') or '') in led: continue
        pend.append({'id': k, 'kind': 'line', 'at': c['CreatedAt'], **general.his_line(c), '_k': came(c)})
    for x in _mail(store, tid):
        k = f"m:{x['MessageId']}"
        if (x.get('Channel') or '') == OWN or k in drawn or ('mail', str(x['MessageId'])) in led or not (at_work or x['MessageId'] in held): continue
        pend.append({'id': k, 'kind': 'arrival', **general.mail_row(store, x), 'joined': stamp(x['T']), '_k': came(x)})
    if at_work:
        for m in general.press_lines(store, tid):
            aid = m['id'].split('-')[1]
            if f'p:{aid}' in drawn or not m.get('press') or ('press', aid) in led: continue
            pend.append({'id': f'p:{aid}', 'kind': 'press', 'at': m['createdAt'], 'text': m['content'][0]['text'],
                         '_k': (int(ep(m['createdAt'])), float('inf'), 2, int(aid))})
    pend.sort(key=lambda p: p.pop('_k'))
    perms = permissions.pending(tid, store)
    live = general._live_of(tid)
    ask = taskstate.asking(store, task, general.session_for(tid) or (live if codingchat._live(tid) else None))
    if ask and ask.get('source') == 'permission' and perms: ask = None
    flat = lambda v: ' '.join(re.sub(r'[*_`]', '', str(v or '')).split())
    turns = [x for x in out if x['kind'] == 'turn']
    last = turns[-1] if turns else None
    if last and last.get('state') == 'failed':
        from .failures import cli_quota
        if (notice := cli_quota(last.get('fail'))):
            last.update(fail=notice, quota=True)
            if not at_work: ask = None
    if ask and last:
        said = ' '.join([str(last.get('text') or ''), *(s.get('text') or '' for s in last.get('steps') or [] if s.get('k') == 'said')])
        ask = {**ask, 'turn': last['id'], **({'said': True} if flat(ask.get('text')) and flat(ask['text']) in flat(said) else {})}
        # ...a missing fact is one question: the reply it cannot write yet is not drawn under it as an empty box
        for x in turns: x['cards'] = [c for c in x.get('cards') or [] if not (c.get('status') == 'pending' and c.get('what') in DRAFTS and not c.get('was'))]
    # ...the turn whose letter waits for his Send (the page hangs the letters' block there), never one at work
    letters = next((x['id'] for x in reversed(turns) if x.get('state') not in LIVE
                    and any(c.get('status') == 'pending' and c.get('what') in (*DRAFTS, 'slot') for c in x.get('cards') or [])), None)
    left_on_him(store, tid, out, ask, letters)
    lv = codingchat._live(tid)
    now = bool(at_work and pend and not perms and lv is not None and getattr(lv, 'steerable', lambda: False)())
    later = LATER if at_work and any(p['kind'] == 'line' for p in pend) and not getattr(live, 'hears_mid_turn', lambda: True)() else ''
    dropped = [json.loads(r['Detail'] or '{}').get('line') for r in store._rows(
        "SELECT Detail FROM audit WHERE EntityType='task' AND EntityId=? AND Action='line_dropped'", (tid,))]
    idle = None
    if not at_work and not hold_ and not pend and task.get('Status') not in ('done', 'dropped') and out and all(x['kind'] == 'arrival' for x in out):
        from .ingest import NOT_STARTED
        why = next((c for c in reversed(store.list_comments(tid, internal=True)) if str(c.get('Body') or '').startswith(NOT_STARTED)), None)
        if why: idle = f"{why['Body']} {START_BY_WRITING}"
    # ...HIS FIRST LINE ON A REPORT HE SENT ON CARRIES ITS NAME: the report is the pill in his bubble
    if task.get('Source') == 'report' and not any(x['id'] == f's:{tid}' for x in out) and (first := next((x for x in out if x['kind'] == 'line'), None)):
        m = next(iter(store.list_messages(tid)), None) or {}
        if (name := str(m.get('SourceName') or m.get('Subject') or '').strip()): first['came'] = name
    # ...each page it published stands in the turn that made it: the newest that had begun by then
    def after(at):
        t = next((x for x in reversed(turns) if (x.get('started') or 0) <= at), None)
        return (t.get('answer') or t['id']) if t else None
    published = [{**p, 'after': after(ep(p.get('created_at')) + 0.999)} for p in outputs.pages(store, tid)]
    q = cardqueue.state(store, tid)
    return {'pending': pend, 'now': now, 'later': later, 'dropped': [d for d in dropped if d], 'working': at_work,
            'started': general.turn_started(tid) if at_work else None, 'asking': ask, 'permissions': perms, 'live': codingchat.live_of(lv),
            'letters': letters, 'idle': idle, 'queue': {'live': q['live'], 'held': q['held'], 'line': cardqueue.line(q)},
            'hold': hold_ and {**{k: hold_[k] for k in ('line', 'person', 'org')},
                               **({'line': origin.JOINED_LINE.format(who=hold_['who'])} if turns else {})},
            'published': published, 'ran': bool(turns)}
