"""ONE LOG PER TASK (the owner's approved redesign A, 2026-11-19): what a task's chat draws is appended here once, as it happens, at the
place it gets then - his line when the agent heard it, a message that came in, his press, a turn, each step of a turn, the one action box,
a failure. The row's `Id` is its place for good: nothing renumbers it, re-sorts it, re-dates it or moves it. What can still change - a turn
at work that ends, a card he presses - is updated in place (`State`, `Body`, `Rev`), never moved. The reader is one indexed SELECT.

Every producer writes through `put`/`update`/`step`; the reader is `read`. The rule for when a running turn is split by his line lives in
`step`, at write time, decided once."""
import hashlib, json, logging, os, re, sqlite3, threading, time
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


# EVERY USE OF THE WRITER'S CONNECTION IS UNDER THE STORE'S LOCK (walk 3, 2026-11-19, a py-spy dump of the freeze): `migrated` read
# store.cx bare on a request thread while another held the lock mid-statement - sqlite's connection mutex on one side, the GIL on the
# other, and every request stopped. The helpers take the (re-entrant) lock themselves, so no caller can forget it.
def _bump(store, tid: int) -> None:
    with store.lock: store.cx.execute('INSERT INTO chatlog_task (TaskId, Rev) VALUES (?, 1) ON CONFLICT(TaskId) DO UPDATE SET Rev = Rev + 1', (int(tid),))


def _poke(store, tid: int) -> None:
    try: store._poke('task-changed', task_id=int(tid))
    except Exception: pass


def _row(store, tid: int, key: str):
    with store.lock: r = store.cx.execute('SELECT * FROM chatlog WHERE TaskId=? AND Key=?', (int(tid), key)).fetchone()
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
            try:
                cur = store.cx.execute('INSERT INTO chatlog (TaskId, Key, Kind, Parent, At, Src, Body, State) VALUES (?,?,?,?,?,?,?,?)',
                                       (int(tid), key, kind, _parent(store, tid, parent), _when(body.get('at') if at is None else at), src, json.dumps(body, default=str), state))
            except sqlite3.IntegrityError:
                # ...WRITTEN THIS SAME BEAT ON ANOTHER CONNECTION (CI, 2026-11-22, three times on macOS: a card press and a chat read on two threads
                # both found the card's row missing; the second insert failed, the rest of its advance was dropped and the card stood nowhere): the
                # key names it for good - it is updated in place, as an existing key is
                if not (old := _row(store, tid, key)): raise
                _update(store, tid, old, state, body); store.cx.commit(); n = old['Id']
            else:
                n = cur.lastrowid
                if kind != 'turn' and parent is None: _goes_on(store, tid, n)
                _bump(store, tid); store.cx.commit()
    _poke(store, tid)
    return n


def forget(store, tid: int, key: str) -> None:
    "Take row `key` off task `tid`'s log: what it recorded never happened (a press withdrawn as it was made)."
    with store.lock:
        if store.cx.execute('DELETE FROM chatlog WHERE TaskId=? AND Key=?', (int(tid), key)).rowcount: _bump(store, tid)
        store.cx.commit()
    _poke(store, tid)


def _goes_on(store, tid: int, below: int) -> None:
    with store.lock: _goes_on_(store, tid, below)
def _goes_on_(store, tid: int, below: int) -> None:
    """WHAT IS APPENDED WHILE A TURN WORKS STANDS ABOVE THE REST OF IT (the turn at work is always the last thing): the part of the turn before
    it is over, and the turn goes on in a new row under it ({cont}) - its steps from then on go there. Under the store's lock."""
    t = store.cx.execute("SELECT * FROM chatlog WHERE TaskId=? AND Kind='turn' AND Parent IS NULL AND State IN ('starting','working') "
                         "ORDER BY Id DESC LIMIT 1", (int(tid),)).fetchone()
    if not t: return
    b = json.loads(t['Body'] or '{}')
    store.cx.execute("UPDATE chatlog SET State='done', Rev=Rev+1 WHERE Id=?", (t['Id'],))
    store.cx.execute('INSERT INTO chatlog (TaskId, Key, Kind, At, Src, Body, State) VALUES (?,?,?,?,?,?,?)',
                     (int(tid), f"{t['Key'].split('+')[0]}+{below}", 'turn', time.time(), t['Src'],
                      json.dumps({'cont': t['Key'], 'started': time.time(), 'ended': None, 'text': '', **({'sid': b['sid']} if b.get('sid') else {})}), t['State']))


def _update(store, tid: int, old: dict, state, patch: dict) -> bool:
    with store.lock: return _update_(store, tid, old, state, patch)
def _update_(store, tid: int, old: dict, state, patch: dict) -> bool:
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


def step(store, tid: int, sid: str, ref: str, step: dict, state=None, turns: bool = False) -> int:
    """One tool, thought or said item of the turn at work, merged in place by its `ref` (a tool call updated as it runs). If his line, a
    message or a press was appended after that turn began, the rest of the turn is a NEW turn row under it ({cont: the turn it goes on from})
    - so what the agent did after it heard him is below his line by construction. The files a step made ride on its own row.
    `turns`: the row is the turn's that last updated it (a plan) - updated after his line, it is drawn anew below it, the old one left as it stood."""
    key = f's:{sid}:{ref}'
    with store.lock:
        old = _row(store, tid, key)
        if turns and old and (r := store.cx.execute('SELECT * FROM chatlog WHERE TaskId=? AND substr(Key, 1, ?)=? ORDER BY Id DESC LIMIT 1',
                                                    (int(tid), len(key) + 1, f'{key}@')).fetchone()): old = dict(r)
        if turns and old and store.cx.execute(f"SELECT 1 FROM chatlog WHERE TaskId=? AND Id>? AND Parent IS NULL AND Kind IN ({','.join('?' * len(INPUTS))}) LIMIT 1",
                                              (int(tid), old['Id'], *INPUTS)).fetchone():
            key, old, step = f"{key}@{old['Id']}", None, {k: v for k, v in step.items() if v is not None}
        if old:
            _update(store, tid, old, state, step); store.cx.commit(); n = old['Id']
        else:
            last = store.cx.execute("SELECT * FROM chatlog WHERE TaskId=? AND Kind='turn' AND Parent IS NULL ORDER BY Id DESC LIMIT 1", (int(tid),)).fetchone()
            t = open_turn(store, tid)
            # ...WHAT THE CLI WRITES AFTER HIS STOP IS NOT DRAWN (decided 2026-11-20): the turn reads stopped, the agent's record keeps the rest -
            # no race between his Stop and its last words decides what he sees. Only his line or a message after the stop begins new work
            if t is None and last and last['State'] == 'stopped' and not store.cx.execute(
                    "SELECT 1 FROM chatlog WHERE TaskId=? AND Id>? AND Parent IS NULL AND Kind IN ('line','arrival') LIMIT 1", (int(tid), last['Id'])).fetchone():
                return last['Id']
            if t is None:
                prev = json.loads(last['Body']) if last else {}
                k = f"{last['Key']}+{store.cx.execute('SELECT COUNT(*) FROM chatlog WHERE TaskId=? AND Kind=?', (int(tid), 'turn')).fetchone()[0]}" if last else f't:{sid}:0'
                body = {'cont': last['Key'], 'started': time.time(), 'sid': sid} if last else {'started': time.time(), 'sid': sid}
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
    """A card waiting behind the front is drawn nowhere; an offer outside the line only while no card of the line waits (one box, D). And a
    letter that never had words is no card he saw (walk 4, 2026-11-19: a greyed "Subject / Attach a file / Send" stood where a newer draft
    replaced an empty one): once it is not his to press it draws nowhere."""
    if r['Kind'] != 'card': return True
    if r['State'] == 'held' or r['State'] == 'offer' and lit: return False
    b = json.loads(r['Body'] or '{}')
    return not (b.get('what') in ('draft', 'draft_reply', 'slot') and not b.get('was') and (b.get('status') or r['State']) not in ('pending', 'approved', 'edited', 'sent'))


def _item(r: dict) -> dict:
    b = json.loads(r['Body'] or '{}')
    # ...a card carries what it said (`was`) only while that is what it shows (conversation._card): one he pressed is its pressed card
    if r['Kind'] == 'card' and b.get('was') and b.get('status') not in ('passed', 'withdrawn', 'pending', 'rejected'): b.pop('was')
    return {**b, 'id': r['Key'], 'kind': r['Kind'], **({'state': r['State']} if r['State'] is not None else {}), 'at': b.get('at', r['At'])}


def rev(store, tid: int) -> int:
    with store.lock: r = store.cx.execute('SELECT Rev FROM chatlog_task WHERE TaskId=?', (int(tid),)).fetchone()
    return r['Rev'] if r else 0


def reconcile(store, tid: int) -> None:
    """The turn at work reads what is so (general.working - one fact): starting until its agent works, at work while it does. And a coding
    agent in a terminal - Claude Code, Codex, any CLI whose own log Taskuary reads (codingchat.sessions) - has the steps its log added since
    written in the one shape, as every other road writes them as they come (logged)."""
    from . import general
    # ...STARTING UNTIL ITS SESSION HAS IT (the walks, 2026-11-17): from his press the task is at work, but the turn reads "starting" until the
    # hand-over took and its session is busy with it - working from then on, `opening` (_now) until its prompt is out
    # ...and its hand-over written (a turn heard from the row's own time on): a session is busy from the moment it takes the floor, before it takes
    # what waits (send_prompt), and a hand-over held up there reads starting still
    if (t := _live(store, tid)) and t['State'] == 'starting' and getattr(general._live_of(int(tid)), 'busy', False) and \
            store._one("SELECT 1 AS x FROM heard WHERE TaskId=? AND Kind='turn' AND At>=? LIMIT 1", (int(tid), t['At'])): update(store, tid, t['Key'], state='working')
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
    """A CLI log's steps (sessionrecord: Claude's, Codex's, Copilot's, Gemini's) by their place in its log - which only grows, so a place is a
    step's for good: new ones appended, changed ones in place."""
    f = _feeds(store).setdefault((int(tid), f'log:{sid}'), {'wrote': {}})
    for i, s in enumerate(steps):
        if s.get('k') in ('you', 'brief'): continue
        x, ref = one_step(s), f'log:{i}'
        if f['wrote'].get(ref) == (j := json.dumps(x, sort_keys=True, default=str)): continue
        f['wrote'][ref] = j
        step(store, tid, sid, ref, x, state=x.get('status'))


def read(store, tid: int, level: str = None, ending: bool = False, also=None) -> dict:
    """`level`: how much of each turn's work is shown (detailed) - the task's own, else its kind's setting.
    The task's chat in its one order: top-level rows by their place, each turn with its steps, and its cards and failures once it is
    no longer at work (a card is a turn's last thing - the reader's one rule). `ending`: the turn's answer is filed and its session has not let
    go (serve) - what came in under it waits by the box till it has: written at the foot then, the next read had it at work over that mail."""
    reconcile(store, tid)
    if not ending: came_in(store, tid)
    advance(store, tid)
    # ...read on one reader snapshot, and built after it, never under the writer's lock (store.pinned_read): `also`, what else must be read
    # in the same view (serve: what waits by the box)
    with store.pinned_read():
        rows = store._rows('SELECT * FROM chatlog WHERE TaskId=? ORDER BY Id', (int(tid),))
        n = (store._one('SELECT Rev FROM chatlog_task WHERE TaskId=?', (int(tid),)) or {}).get('Rev', 0)
        side = also() if also else None
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
            # ...AND WHAT THE ANSWER SAYS IS SAID ONCE (walk 5: "I can't look those up from here" twice, word for word) - BY THE ANSWER (the owner,
            # 2026-11-23: words stay where they were said): the words that streamed are its rows, as they stood while it worked; of the filed
            # answer only what they did not say is drawn under them (`tail`) - the answer itself kept whole, as he copies it - each message's
            # opener said once (conversation._said)
            from .conversation import _said, unsaid
            x['steps'] = _said(x['steps'])
            if x.get('text'): x['tail'] = unsaid(str(x['text']), x['steps'])
            # ...and one taken back (took_back) says so as its step: its words and their summary are no answer
            if any(s.get('took') for s in x['steps']): x['text'] = ''; x.pop('summary', None)
            x['cards'] = [] if r['State'] in LIVE else [_item(k) for k in ks if k['Kind'] in ('card', 'fail') and _drawn(k, lit)]
            if r['State'] not in LIVE: x['ran'] = run_of(x, ks)
            # ...a turn that ended having said, done and left nothing is no item (a part a line cut off before it did anything)
            if r['State'] not in LIVE and not (x.get('text') or x['steps'] or x['cards'] or x.get('summary') or x.get('fail')): continue
        out.append(x)
    moved_past(store, out, tid)
    from .origin import QUIET_LINE, quiet
    if any(x['kind'] == 'arrival' for x in out) and (q := quiet(store, tid)):
        for x in out:
            if x['kind'] == 'arrival' and x.get('mid') in q: x['kept'] = QUIET_LINE
    lvl = level_of(store, store.get_task(int(tid)) or {}, level)
    return {'rev': n, 'items': [detailed(x, lvl) for x in out], 'level': lvl, **({'also': side} if also else {})}


def run_of(turn: dict, kids: list) -> float:
    """HOW LONG A FINISHED TURN RAN, TO THE LAST THING IT DID - the one number its head says (the owner, 2026-11-23: "ran 1m 15s" over steps that
    went on for five minutes). Its answer ends it (`ended`), but its session can go on writing steps under it after (a second turn of the same
    session, the work it went on with): those are its run too. Seconds; 0 where it never said when it began."""
    if not turn.get('started'): return 0.
    till = max([_when(turn['ended']) if turn.get('ended') else 0., *(float(k['At']) for k in kids if k['Kind'] == 'step' and k.get('At'))])
    return round(max(0., till - _when(turn['started'])), 1) if till else 0.


DRAFTS = ('draft_reply', 'draft')
def moved_past(store, out: list, tid: int = None) -> None:
    """A CARD HE WROTE PAST IS GREY WHERE IT STANDS, from the read his line is drawn in (the owner, 2026-11-12; the recorded walk on the log,
    2026-11-19: the old draft stood pressable over his newer line until the turn that heard it set it aside) - by the ONE rule of what the chat
    moved past (proposals.written_past: never an email he wrote himself), its buttons greyed and no reason line (the owner, 2026-11-18)."""
    from . import proposals
    if tid is None: return
    past = proposals.written_past(store, int(tid))
    for x in out:
        for c in [x] if x['kind'] == 'card' else x.get('cards') or [] if x['kind'] == 'turn' else []:
            if c.get('status') == 'pending': c.update({'status': 'passed'} if c.get('review') in past else {'stands': True})   # ...one the rule keeps (his own email) still stands


# ── the producers' doors (dual-write: the legacy reader still serves the page; the log is written beside it) ─────────────────────────
def _safe(f):
    "A producer's write to the log never breaks the road it rides on: the old record is still what the agent and the page read."
    def go(*a, **k):
        try: return f(*a, **k)
        except Frozen: raise
        except Exception as e: logger.warning(f'chatlog: {f.__name__} was not written - {e}')
    go.__name__ = f.__name__
    return go


def _kids(store, t: dict) -> bool:
    with store.lock: return bool(store.cx.execute('SELECT 1 FROM chatlog WHERE Parent=? LIMIT 1', (t['Id'],)).fetchone())


@_safe
def heard(store, tid: int, new: list, at: float) -> None:
    """What one hand-over took (conversation.hear), in the order it took it: his lines, the messages, the presses - and the turn it began.
    Each is appended now, under everything already in the log - the place it is heard is its place for good. ALL OF IT IN ONE STEP under the
    store's lock (the owner, ~10x: the working line is under his line at once): no read ever sees his line without the turn it began."""
    with store.lock: _heard(store, tid, new, at)
def _heard(store, tid: int, new: list, at: float) -> None:
    from . import general
    from .conversation import _mail, stamp
    tid = int(tid)
    mails = {str(x['MessageId']): x for x in _mail(store, tid)} if any(k == 'mail' for k, _ in new) else {}
    presses = {m['id'].split('-')[1]: m for m in general.press_lines(store, tid)} if any(k == 'press' for k, _ in new) else {}
    # ...WHY A TURN BEGAN is kept on its row (data, drawn nowhere): the lines, messages and presses this hand-over took - none, a wake of its own
    why = {k: [r for kk, r in new if kk == k] for k in ('line', 'mail', 'press') if any(kk == k for kk, _ in new)}
    # ...the turn his lines were heard for at a press is the one that now begins (ahead, below): it takes them already heard
    # ...and so is one a task's first read froze while its start was on its way (migrate: the old list drew it "starting" from the press)
    ahead = (o := open_turn(store, tid)) and o['State'] in LIVE and not _kids(store, o) and (json.loads(o['Body'] or '{}').get('ahead') or o.get('Src') == 'legacy')
    # ...one turn at work, ever: a turn the agent never answered is over when the next begins - before what this hand-over took is appended
    if any(k == 'turn' for k, _ in new) and not ahead and (old := _live(store, tid)): update(store, tid, old['Key'], state='done')
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
        # ...a turn heard once more (a press and his line taken in the same beat - CI, 2026-11-22) is the turn already in the log: it began when
        # it was first heard, and that stays its start
        elif k == 'turn' and not ahead and not _row(store, tid, f't:{r}'):
            put(store, tid, 'turn', f't:{r}', {'started': at, 'ended': None, 'text': '', 'why': why}, state='starting', src='heard', at=at)
    # ...HIS LINES HEARD AT A PRESS, THEIR TURN ON ITS WAY (general.stop_turn - the recorded stop, 2026-11-12: what waited is heard under the
    # stop, the turn that answers it at work from that moment): that turn stands under them from this read, never a beat of nothing under his line
    # ...AND EVERY LINE OF HIS HEARD HAS ITS TURN UNDER IT AT ONCE (the owner's rule: after his line, the turn at work is under it; audit parity b:
    # a card the agent raised in the gap before the turn's row landed loose): the turn at work above it goes on under it, from its own time
    # ...and never for a line whose own turn is in the log already (CI on a slow runner, 2026-11-22: his line was read after its turn had ended, and
    # an empty turn "starting" stood under the finished one - its key names the line it answers, t:<line>:<n>)
    lines = [r for k, r in new if k == 'line']
    answered = lines and all(store._one("SELECT 1 AS x FROM chatlog WHERE TaskId=? AND Kind='turn' AND Key LIKE ? LIMIT 1", (tid, f't:{r}:%')) for r in lines)
    if not any(k == 'turn' for k, _ in new) and lines and not answered and not (open_turn(store, tid) or {}).get('State') in LIVE:
        if (old := _live(store, tid)): update(store, tid, old['Key'], state='done')
        put(store, tid, 'turn', f't:{time.time_ns()}', {'started': at, 'ended': None, 'text': '', 'ahead': True, 'why': why}, state='starting', src='heard', at=at)


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
    from . import say
    words = say.paths(clean(str(body or '')))       # ...his words never carry Taskuary's own folders (say.paths)
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
        if t['State'] == 'stopped': done = {**done, 'text': ''}       # ...an answer filed after his stop is the record's, never the stopped turn's words
        update(store, tid, t['Key'], state='failed' if fail or t['State'] == 'failed' else t['State'] if t['State'] == 'stopped' else 'done', **done)
    else:
        with store.lock:                    # ...the last input before this answer: what its turn raised stands after it (below)
            ins = store.cx.execute(f"SELECT MAX(Id) AS i FROM chatlog WHERE TaskId=? AND Parent IS NULL AND Kind IN ({','.join('?' * len(INPUTS))})",
                                   (tid, *INPUTS)).fetchone()['i'] or 0
        opener(store, tid)                  # ...a task's first answer with no hand-over before it still opens on what started it
        n = put(store, tid, 'turn', f'a:c{cid}', {'started': _when(created), **done}, state='failed' if fail else 'done', src=f'comment:{cid}')
        # ...AND THE CARDS IT RAISED BEFORE ITS ANSWER WAS FILED ARE ITS OWN (audit parity, 2026-11-19: on the API road a reply raised mid-turn,
        # with no turn row yet, stood loose at the chat's foot while the CLI road's stood in its turn): what was put at the foot since the last
        # input is this turn's - still its last thing, under the words it just filed
        with store.lock:
            store.cx.execute("UPDATE chatlog SET Parent=?, Rev=Rev+1 WHERE TaskId=? AND Parent IS NULL AND Kind='card' AND State IN ('pending','offer','also') AND Id>? AND Id<?",
                             (n, tid, ins, n)); store.cx.commit()
    # ...and a press he made while it worked, which no turn will hear (a second Trust, a tap on what was already done), goes in under it: kept
    # for a turn that never comes, it stood by the box while this one ran and was gone the moment it answered. One a next turn hears is in place
    began = json.loads(t['Body'] or '{}').get('started') if t and t['State'] in LIVE else None
    for m in general.press_lines(store, tid) if began else ():
        if m.get('press') and _when(m['createdAt']) >= began - 1 and not get(store, tid, f"p:{(aid := m['id'].split('-')[1])}"):
            put(store, tid, 'press', f'p:{aid}', {'at': m['createdAt'], 'text': m['content'][0]['text'], **({'perm': m['perm']} if m.get('perm') else {})},
                src=f'audit:{aid}')
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
def ran(store, tid: int) -> None:
    """A ROUTINE'S RUN OF STEPS IS ITS TASK'S TURN (flow.turn), written as it goes: each step under it in order, at work while the run has the
    task (workflows.at_work), its last word once it is over. One key for the run (`run:<task>`), the one the frozen list gives it, so a task
    read mid-run goes on in place. A task not frozen yet is frozen whole at its first read."""
    from . import flow, workflows
    tid = int(tid)
    if not migrated(store, tid) or not (ft := flow.turn(store, tid, workflows.at_work(tid))): return
    key = ft['id']
    put(store, tid, 'turn', key, {k: ft[k] for k in ('at', 'started', 'ended', 'text')} if ft['state'] == 'done' else {'at': ft['at'], 'started': ft['started']},
        state=ft['state'], src=f'run:{tid}')
    for i, s in enumerate(ft['steps']): put(store, tid, 'step', f'{key}:s{i}', s, parent=key)


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
        # ...A TURN THAT RAISED CARDS HAS THEM SAY WHAT IS ON HIM (DESIGN-FINAL 4b, facts from the app): each card, its "1 of 2" and its "Sent"
        # are the app's, true as they stand - the agent's "Press Send on the notes" outlived both presses (the real-Claude walk, 2026-11-19)
        mine = [str(s) for s in sm.get('on_you') or [] if str(s).strip()] if not sm.get('nothing_left') and not x.get('cards') else []
        was = x.get('on_you_kept')
        if was in (None, WAITS):
            waits = (ask and ask.get('turn') == x['id']) or letters == x['id'] or any(c.get('status') == 'pending' for c in x.get('cards') or [])
            under = any(y['kind'] in ('line', 'arrival') for y in out[i + 1:])
            if waits and not under:
                if was is None: update(store, tid, x['id'], on_you_kept=WAITS)
                continue
            if not sm and len(out) == i + 1: continue
            # ...SETTLED FROM WHAT IS STILL OWED (the real walk, 2026-11-19: "Press Send on the notes to Erin and Marcus" drawn under one sent and
            # one not-sent card): a turn that waited on his press or answer left THAT on him - its cards and question say it, and once they are
            # settled nothing of it is owed; its to-do is never drawn late over what is done
            was = '1' if mine and mine != said and not waits and was != WAITS else ''
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
    st = taskstate.task_state(store, tid=int(tid))
    if st.finished or (idle := funnel.idle_state(store, int(tid), st))['kind'] != 'left' or not idle['line']: return
    # ...and a run the log holds no turn of (its session's own record only - a CLI it never read) says it too, at the foot: never silent
    put(store, tid, 'note', f"n:left:{t['Key'] if t else 'run'}", {'text': idle['line']}, src='idle')


@_safe
def made_late(store, tid: int, text: str) -> None:
    """WHAT TASKUARY DID FOR A TURN'S CALL THAT NEVER REACHED IT IS SAID UNDER THAT TURN (walk 18, L4b): restarted mid-turn, the agent wrote its
    check-back was "not scheduled" while the chip beside it read "Checks back Thu 7 AM" - the call was made as the turn filed
    (agenttools.made_late). The app's fact stands under the agent's words, once a turn - written once its answer has ended it."""
    t = _newest_turn(store, tid)
    put(store, tid, 'note', f"n:late:{t['Key'].split('+')[0] if t else 'run'}", {'text': text}, src='late')


@_safe
def at_work(store, tid: int, sid: str = '') -> None:
    "The turn the agent has the prompt of: starting until then, working from its first word on (its road's own `prompt`)."
    if (t := open_turn(store, tid)) and t['State'] == 'starting': update(store, tid, t['Key'], state='working', **({'sid': sid} if sid else {}))


def asked_on_row(store, tid: int) -> set:
    "The calls whose rows carry his answer to the permission asked on them (asked_answered): that row is the answer's one record."
    with store.lock: return {r[0] for r in store.cx.execute("SELECT json_extract(Body, '$.call') FROM chatlog WHERE TaskId=? AND Kind='step' "
                                                           "AND json_extract(Body, '$.answer') IS NOT NULL", (int(tid),))}
@_safe
def asked_answered(store, tid: int, call: str, answer: str) -> None:
    """His answer to a permission asked on its call's row (permissions.ask) - written on that row, the one record of it: no press line besides.
    The row is the call's however it was written: its key names it (s:<sid>:<call>, feed), or its body does (`call`, or the `id` a frozen or
    older row kept). And HIS ANSWER CUTS THE TURN THERE, as his press line did (the owner's live app, 2026-11-18: the work after his Allow read
    "working 15m" from the turn's start): what the agent does after it goes on in a new part, started at his press (_goes_on_)."""
    if not call: return
    c = str(call)
    with store.lock:
        r = store.cx.execute("SELECT * FROM chatlog WHERE TaskId=? AND Kind='step' AND (Key LIKE 's:%' AND substr(Key, -?)=? OR ? IN "
                             "(json_extract(Body, '$.call'), json_extract(Body, '$.id'))) ORDER BY Id DESC LIMIT 1", (int(tid), len(c) + 1, f':{c}', c)).fetchone()
        if not r: return
        _update(store, tid, dict(r), None, {'call': c, 'answer': str(answer)}); _goes_on_(store, tid, r['Id']); store.cx.commit()
    _poke(store, tid)


ENDS = ('stopped_turn', 'close_from_assistant')      # ...his stop and his close end the turn they were pressed under, and never wait
AT_ONCE = {'browser_act_pressed'}         # presses drawn where he made them even under a turn at work
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
    # ...and so does Remind me with a day: it puts the agent to rest (remind.rest stops its turn), so no turn would ever hear it - kept for one,
    # the line stood by the box while the turn ran and was gone the moment it stopped
    stops = action == 'stopped_turn' or action == 'remind' and bool(_detail(store, aid).get('to'))
    # ...but HIS PRESS ON THE PAGE stands at once (the walk, 2026-11-19: "I'm done" in the browser left no line): the agent waits on that page
    # in a turn still open, the press is told to it as Taskuary's note - no heard line ever named it - so it was never drawn at all
    if live and not stops and action not in ENDS and action not in AT_ONCE and m.get('press'): return
    if live and (stops or action in ENDS): update(store, tid, live['Key'], state='stopped' if stops else 'done')
    put(store, tid, 'press' if m.get('press') else 'note', f'p:{aid}', {'at': m['createdAt'], 'text': m['content'][0]['text'],
        **({'perm': m['perm']} if m.get('perm') else {}), **({'stop': True} if action == 'stopped_turn' else {})}, src=f'audit:{aid}')
def _detail(store, aid: int) -> dict:
    try: return json.loads((store._one('SELECT Detail FROM audit WHERE Id=?', (int(aid),)) or {}).get('Detail') or '{}') or {}
    except (TypeError, ValueError): return {}


@_safe
def failed(store, tid: int) -> None:
    "A try that failed ends where it failed (conversation.failed_try): the turn at work is over, failed - its line is the answer filed after."
    with store.lock:
        live = store.cx.execute("SELECT Key FROM chatlog WHERE TaskId=? AND Kind='turn' AND Parent IS NULL AND State IN ('starting','working') "
                                "ORDER BY Id DESC LIMIT 1", (int(tid),)).fetchone()
    if live: update(store, tid, live['Key'], state='failed')


def his(body) -> dict:
    from . import general
    return general.his_line(body)


# ── STEPS: every road's record as the one step shape, written as it comes (stage 3) ──────────────────────────────────────────────────────
def one_step(s: dict) -> dict:
    """A step as every road writes it: what was done in plain words (`text` - its description where it gave one, else what it ran or read),
    the real command beside it (`detail`), the file it made or changed, its edit, status, output and error kept. One shape whatever the road."""
    from .sessionrecord import _args, _cut, _target
    k = s.get('k')
    # ...the agent's words as he reads them on every road (conversation.clean): an ACP coding turn's said step drew its [[TASKUARY-ASK]] marker
    if k == 'said' and s.get('text'):
        from .conversation import clean
        s = {**s, 'text': clean(s['text'])}
    if k != 'tool': return {x: s[x] for x in ('k', 'text', 'items', 'status', 'name', 'id', 'output') if s.get(x) not in (None, '')}
    a = s.get('args') if isinstance(s.get('args'), dict) else {}
    cmd = a.get('command') or a.get('cmd')
    cmd = ' '.join(map(str, cmd)) if isinstance(cmd, list) else str(cmd or '')
    desc = str(a.get('description') or '').strip()
    out = {'k': 'tool', 'name': str(s.get('name') or 'tool'), 'text': _cut(desc, 200) if desc else s.get('text') or _target(a) or cmd}
    if desc and cmd: out['detail'] = _cut(cmd, 4000)
    elif s.get('detail'): out['detail'] = s['detail']
    if (kept := _args(a)): out['args'] = kept
    for x in ('file', 'edit', 'status', 'output', 'out', 'id', 'parent', 'did', 'why', 'title', 'tool_kind', 'paths', 'ask'):
        if s.get(x) not in (None, '', {}): out[x] = s[x]
    if s.get('id'): out['call'] = str(s['id'])          # ...the agent's own id for it, kept beside the row's key: a permission asked names it
    return out


import weakref as _weakref
# ...WHAT EACH ROAD HAS WRITTEN, PER STORE (CI, 2026-11-19: a poll read differently from the one before on a busy runner): keyed by task and
# session alone, one store's record of what it wrote stood for another's - a test's store at the same task id - and steps went unwritten
_FEEDS = _weakref.WeakKeyDictionary()
def _feeds(store) -> dict:
    try: return _FEEDS.setdefault(store, {})
    except TypeError: return {}
def _ms() -> str: return f'{time.time_ns() // 1_000_000}'


# ONE ROW PER THING THE AGENT DID, KEYED BY ITS OWN ID (the owner, 2026-11-23: adopt the open-source model - Zed, Toad, agent-shell): a tool call
# is the row s:<sid>:<toolCallId>, a message s:<sid>:m:<messageId>, the turn's plan s:<sid>:plan:<run>. Each update patches its own row and
# nothing else - never a re-reading of the whole turn written back by its place in it, where a step that came between shifted every row after
@_safe
def feed(store, tid: int, sid: str, road: str, event, keep: bool = False) -> None:
    """ONE EVENT OF A ROAD'S RECORD, as it comes. An ACP update ('acp') is the record; a trace event ('trace': stream-json, Codex's JSONL, the
    API agent's loop) is first said as the ACP updates it stands for (conversation.acp_of_trace); a CLI's own log ('claude-log', 'codex-log')
    is read by its parser. `keep`: the updates are the task's own record too (codingchat.record_general - a coding session keeps its own)."""
    if not store or not tid or event is None: return
    # ...his stop is his press's line in the chat, never an error step of the turn (the trace marks it: general.send_prompt)
    if isinstance(event, dict) and event.get('type') == 'error' and isinstance(event.get('detail'), dict) and event['detail'].get('stop'): return
    f = _feeds(store).setdefault((int(tid), sid), {'run': _ms(), 'n': 0, 'k': 0, 'ents': {}, 'ids': {}, 'last': None, 'dirty': set()})
    if road in _LOGS: return _logged_road(store, tid, sid, road, event, f)
    if road == 'trace':
        if not isinstance(event, dict): return
        if event.get('type') == 'prompt': f['run'], f['acp'] = _ms(), False          # ...a run begins: what it numbers is its own
        # ...A RUN OVER ACP IS ITS UPDATES (agents.run_acp hands them in): its trace's tool calls and words are their echo, never a second row
        if f.get('acp') and event.get('type') != 'error': return
        from .conversation import acp_of_trace
        f['n'] += 1
        ups = [_own_ids(f, u) for u in acp_of_trace(event, f['n'])]
    else:
        if not isinstance(event, dict): return
        f['acp'], ups = True, [event]
    for u in ups:
        if keep:
            from . import codingchat
            codingchat.record_general(tid, sid, u)
        _upsert(store, tid, sid, f, u)


def _own_ids(f: dict, u: dict) -> dict:
    "A trace road's ids made its run's own: `tool-0` and Codex's `item_0` begin again every run, and a message has none."
    if u.get('sessionUpdate') == 'tool_call':
        raw = str(u['toolCallId']); u['toolCallId'] = f['ids'][raw] = f"{f['run']}.{raw}"
    elif u.get('sessionUpdate') == 'tool_call_update': u['toolCallId'] = f['ids'].get(str(u['toolCallId']), f"{f['run']}.{u['toolCallId']}")
    elif u.get('messageId'): u['messageId'] = f"{f['run']}.{u['messageId']}"
    return u


CHUNK_S, OUT_KEEP, ENTS = 0.25, 20000, 600
_MSG = ('agent_message_chunk', 'agent_thought_chunk', 'user_message_chunk')
def _delta_only(u: dict) -> bool:
    return u.get('sessionUpdate') == 'tool_call_update' and set(u) <= {'sessionUpdate', 'toolCallId', '_meta', '_at', '_t'} and \
        set((u.get('_meta') or {})) <= {'terminal_output_delta'}


def _upsert(store, tid: int, sid: str, f: dict, u: dict) -> None:
    "One update into the one thing it is of - its row patched in place, or appended where it first came. Session state is no row."
    from .acp import _text_of
    kind, now, chunky = u.get('sessionUpdate'), time.time(), False
    if kind in ('tool_call', 'tool_call_update'):
        if not (ref := str(u.get('toolCallId') or '')): return
        e = f['ents'].setdefault(ref, {'ups': []})
        last = e['ups'][-1] if e['ups'] else None
        # ...a command's output as it streams is one growing tail on its call, never an update kept per delta (kept to its head)
        if (chunky := _delta_only(u)) and last is not None and _delta_only(last):
            d = last['_meta']['terminal_output_delta']
            d['data'] = (str(d.get('data') or '') + str(u['_meta']['terminal_output_delta'].get('data') or ''))[:OUT_KEEP]
        else: e['ups'].append({**u, '_meta': {**(u.get('_meta') or {})}} if chunky else u)
    elif kind in _MSG:
        unnamed = not u.get('messageId')
        if kind == 'agent_thought_chunk': f['last'] = (kind, unnamed); return            # ...a model's private reasoning is never a row (the owner)
        if unnamed and f['last'] != (kind, True): f['k'] += 1
        ref = f"m:{u.get('messageId') or f'''{f['run']}.{f['k']}'''}"
        e = f['ents'].get(ref)
        if e is None: e = f['ents'][ref] = {'ups': [{**u, 'content': {'type': 'text', 'text': _text_of(u.get('content'))}}]}
        else: e['ups'][0]['content']['text'] += _text_of(u.get('content'))
        chunky, f['last'] = True, (kind, unnamed)
    # ...ONE PLAN, REPLACED WHOLE (the ACP spec: each plan update carries every entry): one row, its first place kept - by its planId where the
    # agent names one (the newer plan_update), else the run's; a plan the agent removed stays as it last stood, as Zed keeps a finished one
    elif kind in ('plan', 'plan_update'):
        ref = f"plan:{u.get('planId') or f['run']}"; e = f['ents'][ref] = {**f['ents'].get(ref, {}), 'ups': [{**u, 'sessionUpdate': 'plan'}]}
    elif kind == 'error': f['n'] += 1; ref = f"e:{f['run']}.{f['n']}"; e = f['ents'][ref] = {'ups': [u]}
    elif kind == 'compaction_update':
        ref = f"c:{u.get('compactionId')}"; e = f['ents'].setdefault(ref, {'ups': []}); e['ups'].append(u)
    else: return            # ...commands, mode, usage: the session's state (acp.ACPClient), never a line of the chat
    if kind not in _MSG: f['last'] = (kind, False)
    # ...words a token at a time are written a few times a second, and what is held is written once it settles (_settle)
    if chunky and e.get('j') is not None and now - e.get('at', 0) < CHUNK_S: f['dirty'].add(ref); return _settle(store, tid, sid, f)
    for r in [r for r in f['dirty'] if r != ref]: _put(store, tid, sid, f, r)
    _put(store, tid, sid, f, ref)
    while len(f['ents']) > ENTS: f['ents'].pop(next(iter(f['ents'])))


# ...ON A CLOCK, NEVER ON THE NEXT THING IT DOES (his live chat, 2026-11-25: "I", then 10-20 s of Thinking, then the rest): a message's first
# token was written, the rest of the sentence came a beat later and was held, and the model then reasoned or wrote a tool call's input -
# nothing else came to write it. What is held is written CHUNK_S after it was held, whatever comes next
def _settle(store, tid: int, sid: str, f: dict) -> None:
    if f.get('settle'): return
    def go():
        f['settle'] = None
        if not (getattr(store, '_closed', False) or getattr(store, '_closing', False)):
            for r in list(f['dirty']): _put(store, tid, sid, f, r)
    f['settle'] = t = threading.Timer(CHUNK_S, _safe(go)); t.daemon = True; t.start()


def _put(store, tid: int, sid: str, f: dict, ref: str) -> None:
    from .conversation import acp_steps
    with f.setdefault('lock', threading.RLock()):          # ...the clock's write and the stream's are one at a time (_settle)
        f['dirty'].discard(ref)
        if not (e := f['ents'].get(ref)) or not (got := acp_steps(e['ups'])): return
        if (s := got[0]).get('k') in ('you', 'brief', 'thought'): return       # ...his lines and Taskuary's briefs are the hand-over's, never a step
        x = one_step(s)
        e['at'] = time.time()
        if e.get('j') == (j := json.dumps(x, sort_keys=True, default=str)): return
        # ...the row IS the step as it now reads: what it no longer says (an ask answered) is cleared, never left from the read before
        was, e['j'], e['keys'] = e.get('keys') or (), j, set(x)
        # ...a plan is the turn's that last updated it (the newest plan in the newest turn): one updated after his line never redraws above it
        n = step(store, tid, sid, ref, {**{k: None for k in was if k not in x}, **x}, state=x.get('status'), turns=x.get('k') == 'plan')
        from . import live
        if live._clients and (p := pushed(store, tid, n)): live.emit(live.RUN, task_id=int(tid), steps=[p])     # ...the open chat patches this row


_LOGS = ('claude-log', 'codex-log')
def _logged_road(store, tid: int, sid: str, road: str, event, f: dict) -> None:
    "A line of a CLI's own log, read by its parser into the steps it keeps, each written by its own id (steps_of)."
    from . import sessionrecord
    st = f.setdefault('log', {'out': []})
    {'claude-log': sessionrecord._claude_line, 'codex-log': sessionrecord._codex_line}[road](st, event)
    steps_of(store, tid, sid, st['out'])


@_safe
def flush(store, tid: int) -> None:
    "What the roads of task `tid` still hold back (a sentence's last tokens): written now - its answer is filed, or its turn ended."
    if not store or not tid: return
    for (t, sid), f in list(_feeds(store).items()):
        if t == int(tid):
            for r in list(f.get('dirty') or ()): _put(store, tid, sid, f, r)


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
OUT_N = 1500


def _verb(name: str) -> str:
    n = str(name or '').lower().rsplit('__', 1)[-1]
    return next((v for v, ks in _DID if any(n == k or n.startswith(k) for k in ks)), 'Used')


def _on(s: dict, verb: str) -> str:
    import os, re
    a = s.get('args') or {}
    # ...and what it wrote BY ITS NAME, whichever argument holds it (the judge's walk, 2026-11-19: "wrote Directory" - a tool's own noun, not the folder)
    f = s.get('file') or a.get('file_path') or a.get('path') or next((v for v in a.values() if isinstance(v, str) and ('/' in v or '\\' in v)), '')
    if verb in ('Read', 'Edited', 'Wrote') and f: return os.path.basename(str(f).replace('\\', '/').rstrip('/')) or str(f)
    if verb == 'Opened' and (u := a.get('url') or s.get('text')) and (m := re.match(r'https?://(?:www\.)?([^/\s]+)', str(u))): return m.group(1)
    if verb == 'Ran': return str(s.get('detail') or a.get('command') or s.get('text') or '')[:160]
    if verb == 'Used': return str(s.get('name') or 'a tool').rsplit('__', 1)[-1]
    # ...a search in a few plain words: its query cut at a word, never the raw string run on (the whole of it is behind the row)
    q = ' '.join(str(a.get('query') or a.get('pattern') or s.get('text') or '').split())
    return q if len(q) <= 60 else q[:60].rsplit(' ', 1)[0].rstrip(',;:') + '…'


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
    """A turn's steps with each tool call as its one row (`line`, `outcome`, the output capped behind it) - one row per call, always: the same
    call again is the page's to fold (agentSteps' "(3 times)", keyed by its first call), never a row taken out of the list under its key."""
    return [s if s.get('k') != 'tool' else tool_row(s) for s in steps]


def tool_row(s: dict) -> dict:
    verb = _verb(s.get('name')); on = _on(s, verb)
    return {**{k: v for k, v in s.items() if k not in ('output', 'out')}, 'line': s.get('did') or (f'{verb} {on}'.strip() if on else verb), 'verb': verb,
            **({'outcome': o} if (o := outcome(s)) else {}), **_capped(s.get('output') or s.get('out'))}


def pushed(store, tid: int, n: int) -> dict:
    """ONE ROW AS THE PAGE DRAWS IT, PUSHED AS IT IS WRITTEN (the owner, 2026-11-23: words stream into their row) - {turn, step}, the turn its
    row stands in and the step as a read serves it - so the open chat patches that one row in place, never waiting on its next read."""
    from .conversation import _said
    with store.lock:
        r = store.cx.execute('SELECT s.*, t.Key AS TurnKey FROM chatlog s JOIN chatlog t ON t.Id = s.Parent WHERE s.Id=?', (int(n),)).fetchone()
    if not r: return {}
    x = _item(dict(r))
    if x.get('k') == 'tool': x = tool_row(x)
    else:
        # ...read with what its turn said before it, as a read of the turn reads it (walk 21: an opener said again drew twice in the open chat)
        with store.lock: before = [_item(dict(k)) for k in store.cx.execute("SELECT * FROM chatlog WHERE Parent=? AND Kind='step' AND Id<? ORDER BY Id",
                                                                           (r['Parent'], int(n))).fetchall()]
        _said(before, seen=(seen := set()))
        if not (x := next(iter(_said([x], seen=seen)), None)): return {}
    return {'tid': int(tid), 'turn': r['TurnKey'], 'step': x}


def detailed(turn: dict, level: str) -> dict:
    """A turn as the level shows it - THE ONE PLACE the detail setting is applied, the same for every brain road. Each tool call is one row in
    plain words (tool_rows). `summary`: its words, what it showed and its cards, every other row behind one line that opens on them (`fold`,
    `folded`: "12 steps - ran tests, read 3 files"); `steps` and `everything`: every row. A turn at work shows at every level what it says
    and shows as it comes, its rows under the one climbing line - the level decides once it has ended."""
    if turn.get('kind') != 'turn': return turn
    steps = tool_rows(turn.get('steps') or [])
    if level in ('steps', 'everything') and turn.get('state') not in LIVE: return {**turn, 'steps': steps, 'level': level}
    # ...every row stays in its order (`steps`); what the fold holds is named (`fold`) - its one line is the page's, said from the rows it opens on
    rest = [s for s in steps if s.get('k') not in SHOWN]
    return {**turn, 'steps': steps, 'fold': rest, 'folded': len(rest),
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
    if _inputs(store, tid): return
    t = store.get_task(int(tid)) or {}
    row = next((x for x in _mail(store, int(tid)) if (x.get('Channel') or '') == OWN), None)
    if (said := ownwork.ask(store, t, row)):
        when = row['T'] if row else _when(t.get('CreatedAt'))
        put(store, tid, 'line', f'a:{tid}', {'at': stamp(when), **said}, src='ask', at=at)
    elif (by := started_by(store, t)):
        put(store, tid, 'arrival', f's:{tid}', {'who': by['head'], 'head': by['head'], 'channel': by['channel'], 'own': False,
                                               'at': t.get('CreatedAt'), 'files': 0, 'words': by['words']}, src='started', at=at)


def _waits_from(store, tid: int):
    "When his oldest line still waiting for the agent was typed (epoch), or None - what comes in after it waits with it (came_in)."
    from . import general
    led = {r['Ref'] for r in store._rows("SELECT Ref FROM heard WHERE TaskId=? AND Kind='line'", (int(tid),))}
    ws = [w for w in general.waiting_lines(store, int(tid)) if (w.get('line') or '') not in led]      # ...one already heard is in the chat
    return min(_when(w['at']) for w in ws) if ws else None


@_safe
def came_in(store, tid: int) -> None:
    """WHAT CAME IN WHILE NOTHING WORKED is appended at the foot as it is found (a turn at work hears it at its end - `heard` - and until then
    it waits by the box). A THREAD THAT JOINED WITH ITS HISTORY (the owner, 2026-11-19): what is older than the chat's foot is never drawn above
    it - one line at the foot, "<name>'s thread joined (N messages, M earlier)", opens the earlier ones; the newest stand as they came."""
    from . import general
    from .conversation import _mail, stamp
    tid = int(tid)
    if _live(store, tid): return
    # ...read on one reader snapshot, never the writer's lock, and only a joined thread's body (the load run, 2026-11-24: a 2,000-line chat's
    # every arrival read and parsed under the lock on each poll - 66 s of it in 15 min)
    with store.pinned_read():
        rows = store._rows("SELECT Key, CASE WHEN Key LIKE 'j:%' THEN Body END AS Body FROM chatlog WHERE TaskId=? AND Kind='arrival'", (tid,))
        foot = (store._one('SELECT MAX(At) AS a FROM chatlog WHERE TaskId=? AND Parent IS NULL', (tid,)) or {}).get('a') or 0
    have = {r['Key'] for r in rows} | {f'm:{m}' for r in rows if r['Key'][:2] == 'j:' for m in (json.loads(r['Body'] or '{}').get('thread') or {}).get('mids') or []}
    # ...AND WHAT A STRANGER WROTE TOO, the moment it is held (the Codex walk's judge, 2026-11-19: a failing CI build hidden 13 minutes behind
    # Trust, then drawn out of order): in its place, in time order - the hold's line and its Trust stand beside it; no agent hears it until then
    new = [x for x in _mail(store, tid) if (x.get('Channel') or '') != OWN and f"m:{x['MessageId']}" not in have]
    # ...AND NEVER WHAT CAME AFTER A LINE OF HIS THAT STILL WAITS (the recorded flood, 2026-11-11 - "34, 31, 46"): from his oldest waiting line on,
    # what comes in waits by the box with it, and the hand-over that takes them writes each in the order it came
    if (first := _waits_from(store, tid)) is not None: new = [x for x in new if _when(x.get('CreatedAt') or x.get('SentAt')) < first]      # ...by when it CAME, never its Date
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
ALSO = 'also'                   # a card row's state: the front of a later run - it waits for his press under his newer line, beside the one pending row
@_safe
def advance(store, tid: int) -> None:
    """The line of cards on task `tid` (cardqueue.state) into the log: the front is put as the ONE pending card - under the turn that raised
    it, as its last thing (drawn once that turn is no longer at work), else at the foot where an input came after every turn - with the
    line's "n of m · next" in it; a card that stood is updated in place as it
    is pressed, withdrawn or moved past, never moved; one held behind the front has no row, so nothing can draw it. A card outside the line
    (Taskuary's own offer beside a reply - a skill) stands as an `offer`, drawn only while no card of the line waits."""
    from . import cardqueue
    from .conversation import _card
    from .processing_unread import OWNER_ACTORS
    from .wrapup import OWNER_SID
    tid = int(tid)
    # ...and each step handed to him on a page has its card in that line, settled as the step ends (pagestep.sync)
    from . import pagestep
    pagestep.sync(store, tid)
    q = cardqueue.state(store, tid)
    with store.lock:
        rows = {r['Key']: dict(r) for r in store.cx.execute("SELECT * FROM chatlog WHERE TaskId=? AND Kind='card'", (tid,))}
    by = {r['ReviewId']: r for r in store._rows('SELECT * FROM review WHERE TaskId=? ORDER BY ReviewId', (tid,))}
    front = [x for x in q['live'] if x != cardqueue.LAND]
    held, also = set(q['held']), {f[0]: f for f in q['fronts'] if f != [cardqueue.LAND]}
    # ...AND THE HELD STEP OF A CARD'S BROWSER ROAD IS THAT CARD'S NEXT PRESS, DRAWN ON IT (walk 22, 2026-11-25: Post via the browser on the X card,
    # the agent's final Post held, and nothing to press anywhere - the card he had pressed stood "approved" over a step the line kept behind
    # it): the card waits again, carrying the step (`step`), until the step is pressed, taken back or moved past
    sp = cardqueue.step(q['units'][0]) if front else None
    step = {'review': sp['ReviewId'], 'what': cardqueue.step_says(sp),
            **({'press': 'done'} if cardqueue._p(sp).get('action') == pagestep.ACT else {}), **({'fill': True} if cardqueue._p(sp).get('fill') else {})} if sp else None
    # ...every card that stood reads as its review does now: pressed, withdrawn, moved past - in its place
    for k, r in list(rows.items()):
        rv = by.get(json.loads(r['Body']).get('review'))
        if not rv or k.count(':') > 1: continue          # ...an earlier version (r:<rid>:v<n>) is what it said then, for good
        st = _card(rv)['status']
        # ...A REPLY RAISED EMPTY AND WRITTEN AFTER HIS LINE IS THE CARD OF THE TURN THAT WROTE IT (the real walk 2, 2026-11-19: the agent asked,
        # he answered, and the letter its next turn wrote stood ABOVE his line, in the turn that had only asked): its words-less row was never
        # a card he could press, so it is put again where the words were written
        # ...and so is one A LATER TURN REWROTE IN PLACE (the owner's live app, 2026-11-25: "why is there text after the card?"): it stood in the
        # first turn with the second's words, and the turn that wrote them drew after it - the words are the newest writer's, and so is the card.
        # His own edit (wrapup.OWNER_SID) is not a turn's: it stays where he edited it
        # ...AND WHAT IT SAID BEFORE STAYS WHERE IT STOOD, greyed (the owner's plan, 2026-11-25): an earlier version is a row of its own, its words
        # as he saw them (`was`) - the key moves to the version now standing, never the place (conversation_legacy's r:<rid>:c<n>, the same shape)
        b = json.loads(r['Body'] or '{}')
        # ...(a bulk card's row has no words of its own - its rows' are each theirs: never "rewritten", and never greyed for it)
        if (st == 'pending' and b.get('what') != 'batch' and _card(rv).get('was') and _words(b) != _words(_card(rv)) and rv.get('DraftSid') != OWNER_SID
                and (o := open_turn(store, tid)) and o['Id'] != r.get('Parent')):
            with store.lock:
                store.cx.execute("UPDATE chatlog SET Key=?, State='passed', Body=?, Rev=Rev+1 WHERE Id=?",
                                 (f"{k}:v{r['Id']}", json.dumps({**b, 'status': 'passed'}, default=str), r['Id']))
                _bump(store, tid); store.cx.commit()
            rows.pop(k); continue
        # ...ONE TAKEN BACK BEFORE ITS TURN ENDED NEVER STOOD (drawn only then): its row goes, as nothing of it was ever on his screen
        if st not in ('pending', 'offer') and rv.get('DecidedBy') not in OWNER_ACTORS and (p := _above(store, r)) and p['State'] in LIVE:
            with store.lock: store.cx.execute('DELETE FROM chatlog WHERE Id=?', (r['Id'],)); store.cx.commit()
            continue
        # ...one the chat moved past stays where it stood, its buttons greyed (proposals.written_past) - never taken off as if it waited behind
        # ...ONE card waits per task (one_live_card): the front's own row, never another row of its unit
        # ...ONE WORD FOR A CARD ITS AGENT TOOK THE PLACE OF (decided 2026-11-20, the moved-past ruling): greyed - 'passed' - whether his line set it
        # aside first or the agent's rewrite did; which came first is a race, and no race decides what he sees
        if st == 'superseded' and rv.get('DecidedBy') not in OWNER_ACTORS: st = 'passed'
        # ...(one outside the line - his own email - is offered beside it by what it IS, not by the state its row last had: drawn `pending` while
        # no card stood in front, it read `held` and left the chat when a greyed card stood again - proposals.restore_set_aside)
        if st == 'pending' and rv['ReviewId'] != (front[0] if front else None):
            st = 'passed' if rv['ReviewId'] in q['past'] else ALSO if rv['ReviewId'] in also else 'held' if cardqueue.in_line(rv) else 'offer'
        if step and front and rv['ReviewId'] == front[0]: st = 'pending'
        if st != r['State']: update(store, tid, k, state=st, status='pending' if st == ALSO else st)
    if front and (rv := by.get(front[0])) and f"r:{front[0]}" not in rows:
        # ...the turn that raised it (advance_soon kept it), else the one open now; a turn's card is drawn when that turn has ended
        # ...else the turn at work when it was raised, by its own time: a card is a turn's last thing, never loose where a turn was
        t = _raised(store, front[0]) or (open_turn(store, tid) or _turn_at(store, tid, rv.get('CreatedAt')) or {}).get('Id')
        put(store, tid, 'card', f"r:{front[0]}", {**_card(rv), 'rids': front, 'line': cardqueue.line(q), 'step': step, **({'status': 'pending'} if step else {})},
            parent=t, state='pending', src=f"review:{front[0]}")
    elif front and f"r:{front[0]}" in rows: update(store, tid, f"r:{front[0]}", line=cardqueue.line(q))
    # ...AND THE FRONT OF EACH LATER RUN STANDS WHERE IT WAS RAISED, UNDER THE LINE OF HIS THAT BEGAN ITS RUN (walk 24, 2026-11-25: raised after
    # his answer it was a tab of the card above the answer, and came down the chat when that card's front was pressed): its own row from the
    # start (ALSO), which becomes the one pending row in place once the cards before it are settled
    for rid, f in also.items():
        if f"r:{rid}" not in rows and (rv := by.get(rid)):
            t = _raised(store, rid) or (open_turn(store, tid) or _turn_at(store, tid, rv.get('CreatedAt')) or {}).get('Id')
            put(store, tid, 'card', f"r:{rid}", {**_card(rv), 'rids': f}, parent=t, state=ALSO, src=f"review:{rid}")
    # ...its step on the card in front only: pressed, that card is done; taken back or moved past, the card is as it was
    for k, r in rows.items():
        if (want := step if front and k == f"r:{front[0]}" else None) != json.loads(r['Body'] or '{}').get('step'): update(store, tid, k, step=want)
    for rid, rv in by.items():
        if f'r:{rid}' in rows or rv['Status'] != 'pending' or cardqueue.in_line(rv) or rid in held: continue
        from .conversation import unwritten
        if unwritten(rv) or cardqueue.obsolete_read(store, tid, rv): continue
        t = open_turn(store, tid) or _turn_at(store, tid, rv.get('CreatedAt'))
        put(store, tid, 'card', f'r:{rid}', {**_card(rv), 'offer': True}, parent=t['Id'] if t else None, state='offer', src=f'review:{rid}')
    # ...AND ONE HE PRESSED BEFORE ITS ROW WAS WRITTEN STILL STANDS (nothing he did vanishes): raised and pressed - or pressed and failed -
    # within a beat, before the worker or any read put it, its row is written from the review as it is now, in the turn that raised it
    from .conversation import ep
    with store.lock: froze = store.cx.execute("SELECT MAX(At) AS a FROM chatlog WHERE TaskId=? AND Src='legacy'", (tid,)).fetchone()['a'] or 0
    for rid, rv in by.items():
        if froze and ep(rv.get('CreatedAt')) < froze - 1: continue       # ...what the old build drew was frozen as it was (migrate; a stamp is a whole second)
        if f'r:{rid}' in rows or rv['Status'] == 'pending' or (rv.get('Batch') and rid != min(x for x, y in by.items() if y.get('Batch') == rv['Batch'])): continue
        if cardqueue.obsolete_read(store, tid, rv): continue      # ...a held read the gate lets through now was never his to answer, answered or not
        if cardqueue._p(rv).get('card') in by: continue           # ...a card's own step stood on that card, never as one of its own
        c = _card(rv)
        # ...pressed, failed, set aside because he wrote past it - or REPLACED BY ITS AGENT WHILE IT WAS THE CARD IN FRONT (it stood, whether or not
        # a read drew it before the rewrite): greyed where it stood. One that waited behind another never stood
        if rv.get('DecidedBy') not in OWNER_ACTORS and c['status'] != 'failed':
            if c['status'] not in ('passed', 'superseded') or not _was_front(by, rv): continue
            c = {**c, 'status': 'passed'}
        # ...AND ONE PRESSED ON ITS TAB WHILE IT WAITED BEHIND THE FRONT (CardLine, 2026-11-25) beside the run's cards, where the run is one
        # card - never in the turn open at the press, which moved the run's one card down the chat to it
        t = _run_home(q, rid, rows) or _raised(store, rid) or (_turn_at(store, tid, rv.get('CreatedAt')) or {}).get('Id')
        put(store, tid, 'card', f'r:{rid}', c, parent=t, state=c['status'], src=f'review:{rid}')


def _run_home(q: dict, rid: int, rows: dict):
    """The turn the run that review `rid` is a tab of stands in (cardqueue.state's `runs`): its front's row's, else its newest row's - where the
    page draws it (cardLine.lineRuns). None for a card of no run, or of one with no row yet."""
    for r in q.get('runs') or []:
        if len(r) < 2 or not any(rid in u['rids'] for u in r): continue
        had = [u for u in r if f"r:{u['rids'][0]}" in rows and rid not in u['rids']]
        u = next((u for u in had if u['done'] is None), None) or (had[-1] if had else None)
        return rows[f"r:{u['rids'][0]}"]['Parent'] if u else None
    return None


def _words(card: dict) -> str:
    "The words a card's row stood with (`was`, conversation._card) - '' for one raised empty."
    return str((card.get('was') or {}).get('text') or '')


def _was_front(by: dict, rv: dict) -> bool:
    "Was review `rv` the card in front - no older card of the task still waiting when it was raised? Read from the stored reviews alone."
    from .conversation import ep
    at = ep(rv.get('CreatedAt'))
    return not any(r['ReviewId'] < rv['ReviewId'] and (r['Status'] == 'pending' or ep(r.get('DecidedAt')) > at) for r in by.values())


def _turn_at(store, tid: int, created):
    "The turn at work when a thing was raised at `created` (a stamp): the newest turn begun by then, else None."
    from .conversation import ep
    with store.lock:
        r = store.cx.execute("SELECT * FROM chatlog WHERE TaskId=? AND Kind='turn' AND Parent IS NULL AND At<=? ORDER BY Id DESC LIMIT 1",
                             (int(tid), ep(created) + 1)).fetchone()
    return dict(r) if r else None


# ...OFF THE WRITER'S THREAD (walk 2, 2026-11-19: the server froze ~20 s after an Approve - every request stuck, CPU flat): a review's write
# put its card from inside the store's own poke, under whatever its caller held - the store's lock, a press's claim, the waiting room's -
# and advance reads the whole line of cards through other roads that take their own. Two of those in opposite orders on two threads is a
# deadlock. The write only says the line moved; one worker puts it, holding nothing else, and every read still advances first.
_SOON, _SOON_LOCK, _SOON_GO, _SOON_T = {}, threading.Lock(), threading.Event(), [None]
import weakref
# store -> {review id: the Id of the turn open at the review's last write before its card stood - the turn that raised it}; held by the store
# itself, never by its address (a store gone and a new one at the same address - a test's - would read another task's turns)
_RAISED = weakref.WeakKeyDictionary()
def _raised(store, rid) -> int:
    try: return (_RAISED.get(store) or {}).get(int(rid))
    except TypeError: return None
def advance_soon(store, tid: int, rid: int = None) -> None:
    """The line of cards on task `tid` moved: put into the log by the one worker, never on the thread that wrote it. `rid`: the review that
    moved - until its card stands, the turn open at each of its writes is kept as the one that raised it (the one that wrote its words, for
    a reply raised empty) - plain reads, no other lock taken."""
    # ...AND A LETTER RAISED EMPTY (its row has no words) IS THE CARD OF THE TURN WRITING IT NOW (walk 8, 2026-11-20: Marcus's reply, raised empty in
    # the turn that asked him for times, was written by the turn after his answer - and put back in the first, above his line, where none looked)
    # ...and so is one whose words are not its row's: rewritten in place by a later turn (advance moves its row there)
    if rid and (not (row := get(store, tid, f'r:{int(rid)}')) or row.get('what') in DRAFTS + ('slot',)
                and (not row.get('was') or _words(row) != str((store.get_review(int(rid)) or {}).get('DraftText') or ''))):
        # ...the turn at work raised it even where his line landed under it a beat before its next step (the turn is cut there only at that step)
        try: _RAISED.setdefault(store, {})[int(rid)] = (open_turn(store, tid) or _live(store, tid) or {}).get('Id')
        except TypeError: pass                     # ...a store that cannot be held weakly keeps no note: the time of its raise places it
    if getattr(store, '_closed', False) or getattr(store, '_closing', False): return
    try: ref = weakref.ref(store)
    except TypeError: return advance(store, tid)                   # ...a store that cannot be held weakly is advanced where it was written
    with _SOON_LOCK:
        _SOON[(id(store), int(tid))] = (ref, int(tid))
        if not (_SOON_T[0] and _SOON_T[0].is_alive()):
            _SOON_T[0] = threading.Thread(target=_soon_loop, daemon=True, name='chatlog-cards'); _SOON_T[0].start()
    _SOON_GO.set()
# ...AND NEVER ON A STORE BEING CLOSED (the release run, 2026-11-19: the worker read a store a test's cleanup had torn down - an access violation):
# it holds a store only weakly and only for one job, never starts one on a closed store, and store.close() waits for the one at work (let_go)
_SOON_RUN = threading.Condition()
_SOON_ON = [None]                                 # id() of the store the worker is advancing right now
def _soon_loop() -> None:
    while True:
        _SOON_GO.wait(); _SOON_GO.clear()
        with _SOON_LOCK: jobs = list(_SOON.values()); _SOON.clear()
        for ref, tid in jobs:
            st = ref()
            if st is None: continue
            with _SOON_RUN:
                if getattr(st, '_closed', False) or getattr(st, '_closing', False): continue
                _SOON_ON[0] = id(st)
            try: advance(st, tid)
            finally:
                with _SOON_RUN: _SOON_ON[0] = None; _SOON_RUN.notify_all()
            del st
def settled(timeout: float = 5.) -> bool:
    "Has the worker put everything it was told of? A reader that counts the store's writes waits for it first. Waits up to `timeout`."
    end = time.time() + timeout
    while (_SOON or _SOON_ON[0] is not None) and time.time() < end: time.sleep(0.01)
    return not (_SOON or _SOON_ON[0] is not None)
def let_go(store, timeout: float = 10.) -> None:
    """Before `store` closes: what the worker was told of it is dropped, and a job at work on it is waited for - nothing reads it after."""
    with _SOON_LOCK:
        for k in [k for k in _SOON if k[0] == id(store)]: _SOON.pop(k, None)
    with _SOON_RUN:
        end = time.time() + timeout
        while _SOON_ON[0] == id(store) and time.time() < end: _SOON_RUN.wait(0.1)


def _above(store, r: dict):
    "The row a row stands under (its turn), or None."
    if r.get('Parent') is None: return None
    with store.lock: p = store.cx.execute('SELECT * FROM chatlog WHERE Id=?', (r['Parent'],)).fetchone()
    return dict(p) if p else None


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
_BACKUP = {}          # db path -> {'thread': the copy at work, 'failed': when it last failed}
BACKUP_AGAIN = 600.   # seconds before a copy that failed is tried again
def backed_up(store) -> bool:
    """A copy of the database before the first task is written into the log - nothing is migrated without one (backups.make, `before-chatlog`).
    NEVER MADE INSIDE A READ (the owner's live app, 2026-11-19: the copy failed on every chat read and each read waited 6-19 s for it): made
    once per process on its own thread, a failure remembered and tried again after BACKUP_AGAIN, never on every read. True once it exists;
    a store in memory has nothing to lose."""
    from pathlib import Path
    db = getattr(store, '_path', '') or ''
    if db in _BACKED or db == ':memory:' or not Path(db).is_file(): return True
    try:
        if store.get_setting('chatlog_backup', ''): _BACKED.add(db); return True
    except Exception: return False
    st = _BACKUP.setdefault(db, {})
    if (t := st.get('thread')) and t.is_alive(): return False
    if time.time() - st.get('failed', 0) < BACKUP_AGAIN: return False
    def make():
        from . import backups
        try:
            out = backups.make(db, Path(db).parent, why='before-chatlog', files=False)
            if not out: raise RuntimeError('no database to copy')
            store.set_setting('chatlog_backup', str(out), 'router'); _BACKED.add(db)
        except Exception as e:
            st['failed'] = time.time()
            logger.warning(f'chatlog: no copy of the database before the log yet - nothing migrates; tried again in {int(BACKUP_AGAIN)} s ({e})')
    st['thread'] = threading.Thread(target=make, daemon=True, name='chatlog-backup'); st['thread'].start()
    return False


def migrated(store, tid: int) -> bool:
    with store.lock: r = store.cx.execute('SELECT Migrated FROM chatlog_task WHERE TaskId=?', (int(tid),)).fetchone()
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
    # ...A LIST THAT HELD NOTHING HE SAW HAS NOTHING TO FREEZE (a new coding task read as its first start began: the old list drew no line yet,
    # the freeze wiped the line the press had heard, and his line stood by the box for good under the task's title, answered): the log is the record
    bare = lambda x: x['kind'] == 'turn' and x.get('state') in LIVE and not (x.get('steps') or x.get('text') or x.get('cards'))
    items, keep = got.get('items') or [], all(bare(x) for x in got.get('items') or [])   # ...still drawn: the turn at work is written beside it
    with store.lock:
        if migrated(store, tid): return False
        # ...what dual-write wrote before is the warm-up: the list is the record
        if not keep:
            store.cx.execute('DELETE FROM chatlog WHERE TaskId=?', (int(tid),))
            # ...and the turns noted as raising its cards (_RAISED) were rows of what was just cleared - their Ids free for any row now (the card
            # gallery, 2026-11-25: a sign-in's card raised during its task's first read was put under its own Id, and drawn nowhere)
            for x in store.cx.execute('SELECT ReviewId FROM review WHERE TaskId=?', (int(tid),)).fetchall(): (_RAISED.get(store) or {}).pop(x['ReviewId'], None)
        prev, seen_live = 0., False
        def row(kind, key, body, parent=None, state=None):
            nonlocal prev
            at = max(prev, _when(body.get('started') if kind == 'turn' else body.get('at')) if (body.get('started') or body.get('at')) else prev)
            prev = at
            cur = store.cx.execute('INSERT OR IGNORE INTO chatlog (TaskId, Key, Kind, Parent, At, Src, Body, State) VALUES (?,?,?,?,?,?,?,?)',
                                   (int(tid), key, kind, parent, at or time.time(), 'legacy', json.dumps(body, default=str), state))
            return cur.lastrowid
        for x in items:
            body = {k: v for k, v in x.items() if k not in ('id', 'kind', 'state', 'steps', 'cards', 'opening', 'doing') and not k.startswith('_')}   # (what a turn does this moment is read live: _now)
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
    "The chat of task `tid` (_serve), its mail read once (conversation.mail_once)."
    from .conversation import mail_once
    with mail_once(): return _serve(store, tid, level)


def _serve(store, tid: int, level: str = None) -> dict:
    """What the page draws for task `tid`: the log's items, in its one order, each turn at its level, and beside them what waits by the box,
    what the agent asks, the permissions it waits on, the line of cards and the hold. A task is frozen into the log at its first read
    (migrate); what waits is never also drawn (an input is in one place)."""
    from . import general, origin, workflows
    tid = int(tid)
    # ...A TASK NOT YET FROZEN WHILE THE COPY BEFORE THE LOG IS STILL BEING MADE (backed_up, on its own thread) reads as the old build drew it -
    # exactly what the freeze will write - and never waits for the copy
    if not migrated(store, tid) and not migrate(store, tid) and not migrated(store, tid): return _legacy(store, tid)
    hold_ = origin.hold(store, tid)
    at_work = general.working(store, tid) if not hold_ else bool(getattr(general._live_of(tid), 'busy', False))
    # ...A TURN WHOSE ANSWER IS FILED IS OVER (recorded 2026-11-12: its session read busy a beat after the answer was filed, and the dots stood
    # under that answer): with nothing heard since and no line of his waiting, nothing works - a hand-over on its way writes its turn as it goes
    # ...IN ONE VIEW OF THE HAND-OVER (Windows CI, 2026-11-21): the turn and what waits are read under the lock take_kept holds while it hears his
    # lines and takes them off the box - read on either side of it, the finished turn above and no line waiting said nothing worked, a beat
    # before the turn that took them stood under them
    # ...AND THE TURN ENDING IS NOT YET A CHAT AT REST (`ending`): what came in while it worked stays by the box until its session lets go -
    # written at the foot by this read (came_in), the next one (its session still busy, the turn no longer the newest) read it at work again
    with store.lock: t, w = open_turn(store, tid), _waits_from(store, tid)
    if at_work and t and t['State'] not in LIVE and w is None: at_work, ending = False, not general.HANDED.get(tid)     # (a line of his not yet heard keeps it)
    else: ending = False                    # ...an input handed over (general.hand) begins the next turn: it stands in the chat from the first read
    if at_work and (h := _halted(store, tid)): at_work = any(not get(store, tid, w.get('line') or f"c:{w['id']}") for w in general.waiting_lines(store, tid)) or h == 'stopped_turn' and bool(getattr(general._live_of(tid), 'owes_stop', lambda: False)())
    at_work = at_work or workflows.at_work(tid)            # ...a routine running its steps is at work with no agent at all (flow.turn)
    # ..."working" is one fact (general.working): a turn the log holds at work while nothing works has either not begun yet - nothing of it is
    # drawn until it has - or was left by a process that is gone (a restart): it is over, in place
    # ...and nothing at work holds back its last words: a coding turn files no answer (answered flushes), so the words its road said within a
    # beat of the one before - the could-not question after a second silence - were never written, and the chat drew nothing of them
    if not at_work: flush(store, tid)
    if not at_work and (t := _live(store, tid)):
        with store.lock: n = store.cx.execute('SELECT COUNT(*) FROM chatlog WHERE Parent=?', (t['Id'],)).fetchone()[0]
        if n or json.loads(t['Body'] or '{}').get('text'): update(store, tid, t['Key'], state='done')
    left_note(store, tid, at_work)
    got = read(store, tid, level, ending, also=lambda: _waits_from(store, tid)); w = got.pop('also')      # ...one view of the hand-over, as above
    # ...the same rule on what this read holds (its answer may be filed between the check above and the read): the newest thing a finished
    # turn with nothing heard under it and no line of his waiting - nothing works, no dots under a finished answer
    tail = next((x for x in reversed(got['items']) if x['kind'] in ('turn', 'line', 'arrival', 'press')), None)
    if at_work and tail and tail['kind'] == 'turn' and tail.get('state') not in LIVE and w is None and not workflows.at_work(tid):
        at_work, ending = False, not general.HANDED.get(tid)
    out = got['items'] if at_work else [x for x in got['items'] if not (x['kind'] == 'turn' and x.get('state') in LIVE)]
    # ...A TASK A STRANGER'S WORDS HOLD DRAWS NO CARD TO PRESS until he trusts them (the judge's browser round, 2026-11-19: the reply drafted on a
    # stranger's mail stood as the email card, Send lit, where the hold's line and its Trust belong): the hold is the one move, beside the list
    from . import origin
    if hold_ and origin.keeps_him(store, tid):           # ...a task a stranger STARTED; one who only joined never takes Send off the rest
        waits = lambda c: c.get('kind') == 'card' and (c.get('status') or c.get('state')) in ('pending', 'offer')
        out = [x if x['kind'] != 'turn' else {**x, 'cards': [c for c in x.get('cards') or [] if not waits(c)]} for x in out if not waits(x)]
    closed(store, tid, out)
    if at_work and (lv := next((x for x in reversed(out) if x['kind'] == 'turn' and x.get('state') in LIVE), None)): lv.update(_now(tid, lv))
    body = {'items': out, 'level': got['level'], **beside(store, tid, out, at_work, hold_, ending)}
    return {'rev': hashlib.sha1(json.dumps(body, default=str).encode()).hexdigest()[:16], **body}


def closed(store, tid: int, out: list) -> None:
    """HIS CLOSE IS ONE LINE WITH ITS NOTE (the recorded closed task, 2026-11-12: "You marked it done" and under it the page's own "Mark done
    4m ago"): the press that closed the task, while it is closed, is marked `closes` - the page then draws no line of its own - and says the
    note he closed it with."""
    if (store.get_task(tid) or {}).get('Status') != 'done': return
    a = store._one("SELECT Id FROM audit WHERE EntityType='task' AND EntityId=? AND Action='close_from_assistant' ORDER BY Id DESC LIMIT 1", (tid,))
    if not a or not (x := next((x for x in out if x['id'] == f"p:{a['Id']}"), None)): return
    x['closes'] = True
    if (note := next((c['note'] for c in reversed(store.closeouts(tid)) if c['what'] == 'closed'), '')): x['text'] = f"{x['text'].rstrip('.')} - {note.rstrip('.')}."


def missing(store, tid: int, got: dict, upto: int = None) -> list:
    """THE PERMANENT COMPARE (the owner's GO, 2026-11-19: "fix it once and for all"): what the store made for task `tid` against what the
    chat `got` shows - every answer filed has its turn, every line of his heard has its item, the card that waits on his press stands - each
    gap one sentence naming the road that made the thing. Read at rest only (a turn at work shows its card and answer at its end). [] when whole.
    `upto`: the newest comment filed before `got` was read - one filed after it is no gap of that read."""
    from . import cardqueue, general, sessionrecord
    if got.get('working'): return []
    ids = {x['id'] for x in got.get('items') or []} | {p['id'] for p in got.get('pending') or []}
    answers = {x.get('answer') for x in got.get('items') or [] if x['kind'] == 'turn'} | {x['id'] for x in got.get('items') or [] if x['kind'] == 'note'}
    cards = {c['review'] for x in got.get('items') or [] for c in ([x] if x['kind'] == 'card' else x.get('cards') or [])}
    out = []
    for c in store.list_comments(int(tid), internal=True):
        if upto is not None and c['CommentId'] > upto: continue
        if c.get('ActorType') == general.ASSISTANT_TYPE and f"comment-{c['CommentId']}" not in answers and f"n:c{c['CommentId']}" not in answers:
            out.append(f"i: answer comment-{c['CommentId']} filed by {c.get('Actor')!r} is in no turn")
        if c.get('ActorType') == general.USER_TYPE and c.get('Actor') != general.BRIEF_ACTOR and (k := c.get('LineId')) and k not in ids:
            out.append(f"i: his line {k} is drawn nowhere")
    for rid in [x for x in cardqueue.state(store, int(tid))['live'] if x != cardqueue.LAND][:1]:      # ...a unit's card is its first row's
        rv = store.get_review(rid) or {}
        # ...a reply no words were written for yet is no card while the agent asks for what it needs (beside: one question)
        if rv.get('Status') == 'pending' and rid not in cards and not (rv.get('Kind') in DRAFTS and not str(rv.get('DraftText') or '').strip()):
            out.append(f"i: the card that waits on him, review {rid} ({rv.get('Kind')} from {rv.get('Origin') or rv.get('DraftBy') or 'its road'}), is drawn nowhere")
    return out


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
    - from its start where no CLI is up (general.cold), until its road hands it the prompt. The answer it is writing is its own row, streamed
    into it (feed) - never a second copy on this line."""
    from . import general
    from .conversation import clean
    ses = general.session_for(tid)
    if ses is None or turn.get('state') == 'starting': return {'opening': True} if turn.get('state') == 'starting' and general.cold(tid) else {}
    trace = getattr(ses, 'trace', None) or []
    kinds = [e.get('type') for e in trace]
    # ...and NEVER PAST ITS CLI BEING UP (the owner, 2026-11-22: "Waiting for the agent to start" for 39 s; the benchmark on Claude: handed over
    # at 0.1 s, its first step at 22 s, "Waiting" the whole time - the road's prompt is written in the run's own trace, never this one, so
    # nothing here ended it): once its conversation is open the agent is at work - "Thinking..." until its first step
    opening = 'opening' in kinds and kinds[::-1].index('opening') < (kinds[::-1].index('prompt') if 'prompt' in kinds else len(kinds)) and general.cold(tid)
    e = trace[-1] if trace else {}
    # ...and `thinking`, the thought it is at while that is the newest thing (the owner, 2026-11-16: "Thinking..." for minutes): a thought is never
    # a step of the chat (conversation._said), so the line beside the dots is the only place it reads, and only while it is current
    from .chatformat import plain_text
    thinking = plain_text(clean(e.get('detail'))) if e.get('type') in ('live', 'progress') and e.get('name') in ('thinking', 'reasoning') else ''
    return {**({'opening': True} if opening else {}), **({'thinking': thinking} if thinking else {})}


# WHAT A TURN SAID IN ITS OWN WORDS - THE ONE RULE FOR WHAT IS SAID AGAIN UNDER IT (decided 2026-11-20, walk 8: never duplicate): an ask marker's
# text, and an owed reply's "what the agent needs" line, are drawn only under a turn that said nothing of its own
def turn_words(t: dict) -> str:
    "A turn's words - its answer and the lines it said while it worked - as one flat line ('' when it said nothing)."
    return ' '.join(re.sub(r'[*_`]', '', ' '.join([str(t.get('text') or ''), *(s.get('text') or '' for s in t.get('steps') or [] if s.get('k') == 'said')])).split())


def card_said(store, tid: int, rid: int) -> bool:
    "Did the turn review `rid`'s card stands in say something of its own (turn_words)? Then the card's own words of what it needs are not said again."
    r = _row(store, tid, f'r:{int(rid)}')
    if not r or r.get('Parent') is None: return False
    with store.lock: rows = [dict(x) for x in store.cx.execute('SELECT * FROM chatlog WHERE TaskId=? AND (Id=? OR Parent=?)', (int(tid), r['Parent'], r['Parent']))]
    t = next((_item(x) for x in rows if x['Id'] == r['Parent'] and x['Kind'] == 'turn'), None)
    return bool(t and turn_words({**t, 'steps': [_item(x) for x in rows if x['Kind'] == 'step']}))


def beside(store, tid: int, out: list, at_work: bool, hold_, ending: bool = False) -> dict:
    """What the page draws beside the chat's items, each from the fact that says it: what waits for the agent (`pending` - his lines not yet
    heard; a message, a press while a turn works; what an untrusted sender wrote), `now`/`later` (whether a waiting line goes in mid-turn),
    `asking` (in the turn that asked), `permissions`, `queue` (the line of cards), `hold`, `letters` (the turn whose letter waits), `idle`
    (why nothing started), the pages it published, and the CLI that runs. `ending`: a turn whose answer is filed while its session lets go -
    what came in under it still waits by the box (came_in writes it at the foot once nothing works)."""
    from . import cardqueue, codingchat, general, origin, outputs, permissions, taskstate
    from .conversation import LATER, START_BY_WRITING, came, ep, stamp, _mail
    from .general import WAITING_TYPE
    task = store.get_task(tid) or {'TaskId': tid}
    drawn = {x['id'] for x in out}
    led = {(r['Kind'], r['Ref']) for r in store._rows('SELECT Kind, Ref FROM heard WHERE TaskId=?', (tid,))}
    held = set((hold_ or {}).get('mids') or [])
    pend, waits = [], _waits_from(store, tid) is not None
    for c in store.list_comments(tid, internal=True):
        k = c.get('LineId') or f"c:{c['CommentId']}"
        # ...AND ONE A TURN HAS TAKEN BUT ITS HAND-OVER HAS NOT YET WRITTEN INTO THE CHAT (store.take_lines, then hear): still by the box -
        # every read sees his line in exactly one place, from the moment he sends it (nothing lost; the log, never the ledger, says drawn)
        taken = c.get('ActorType') == general.USER_TYPE and c.get('LineId') and c.get('Actor') != general.BRIEF_ACTOR
        if k in drawn or not (c.get('ActorType') == WAITING_TYPE and ('line', c.get('LineId') or '') not in led or taken): continue
        pend.append({'id': k, 'kind': 'line', 'at': c['CreatedAt'], **general.his_line(c), '_k': came(c)})
    # ...AND A MESSAGE THE HAND-OVER HAS HEARD BUT NOT YET WRITTEN INTO THE CHAT, as his line taken (above): still by the box - heard between this
    # read's chat and this, it was in neither (Windows CI: "m:N left the waiting room and is nowhere", the flood and the delayed mail)
    drawn |= {f'm:{m}' for x in out if x.get('kind') == 'arrival' for m in (x.get('thread') or {}).get('mids') or []}
    for x in _mail(store, tid):
        k = f"m:{x['MessageId']}"
        if (x.get('Channel') or '') == OWN or k in drawn: continue
        if ('mail', str(x['MessageId'])) not in led and not (at_work or ending or x['MessageId'] in held or waits): continue
        pend.append({'id': k, 'kind': 'arrival', **general.mail_row(store, x), 'joined': stamp(x['T']), '_k': came(x)})
    if at_work or ending:
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
        said = turn_words
        # ...IN THE TURN THAT ASKED IT (the real walk, 2026-11-19: the sender wrote again mid-question, and the new turn at work drew the old
        # question word for word as its own): the turn whose words hold it, else the newest one
        q = flat(ask.get('text'))
        at = next((t for t in reversed(turns) if q and q in said(t)), None)
        # ...one no turn's words hold (a CLI's own question tool, a step handed over): the turn at work when it was asked
        raised = (_turn_at(store, tid, ask['at']) or {}).get('Key') if ask.get('at') else None
        on = at or next((t for t in turns if t['id'] == raised), None) or last
        # ...AND THE AGENT'S OWN WORDS ARE THE QUESTION (decided 2026-11-20, walk 8: asked in its prose and again in the marker, the turn asked
        # Marcus's times twice): the marker sets the wait; its text is drawn only under a turn with no words of its own
        # ...a plain question only: a chooser's picks and a sign-in's or a hand-over's own line are drawn whatever the turn said
        mine = not ask.get('choices') and ask.get('ask', 'question') == 'question' and said(on)
        ask = {**ask, 'turn': on['id'], **({'said': True} if at or mine else {})}
        # ...and ITS QUESTION IS THE TURN'S MOVE: no Try again its summary asked for stands under it (the walk, 2026-11-21: a two-way question
        # with only "Try again" under it, which answered neither)
        if isinstance(on.get('summary'), dict) and on['summary'].get('retry'): on['summary'] = {k: v for k, v in on['summary'].items() if k != 'retry'}
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
    # ...AND WHETHER HE HAS A PART ON THE PAGE, by the one answer the assistant read gives (taskstate.needs_owner) - in the payload that carries
    # the ask, so a coding task's hand-over is shown him as a chat's is: read only from the chat's own state, which a coding task reads once
    # at its opening, its page never drew (the design loop, 2026-11-20)
    sid = getattr(lv, 'sid', '') or getattr(live, 'sid', '') or ''
    return {'pending': pend, 'needsOwner': taskstate.needs_owner(ask, taskstate.browser_acts(store, tid), sid), 'now': now, 'later': later, 'dropped': [d for d in dropped if d], 'working': at_work,
            'started': general.turn_started(tid) if at_work else None, 'asking': ask, 'permissions': perms, 'live': codingchat.live_of(lv),
            # ...and its runs, each one card with a tab per card (cardqueue.tabs) - none on a task a stranger's words hold: no card waits there
            'letters': letters, 'idle': idle, 'queue': {'live': q['live'], 'held': q['held'], 'line': cardqueue.line(q),
                                                         'runs': [] if hold_ and origin.keeps_him(store, tid) else cardqueue.tabs(store, q)},
            'hold': hold_ and {**{k: hold_[k] for k in ('line', 'person', 'org')},
                               **({'line': origin.JOINED_LINE.format(who=hold_['who'])} if turns else {})},
            'published': published, 'ran': bool(turns)}
