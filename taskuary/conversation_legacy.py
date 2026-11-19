"""THE OLD BUILD OF A TASK'S CHAT, FROZEN (the one-log redesign, stage 8): it pieced the list together from a dozen records on every read,
each item placed by a sort key made up per read. The chat is read from its log now (chatlog.py); this is kept only for chatlog.migrate,
which freezes a task's chat into the log once, as this build last drew it. Nothing else reads it."""
import hashlib, json, math, re, threading, time

from .conversation import (INF, DRAFTS, LIVE, WENT, FAILED_TRY, LATER, START_BY_WRITING, TOOK_BACK, _after, _card, _flat, _mail, _said,
                           _session_steps, came, clean, ep, said_once, stamp, started_by, unwritten)


def served_back(store, tid: int, out: list, was: dict, waiting: set) -> list:
    """AN ITEM ONCE DRAWN IS IN EVERY READ AFTER (the basic flow's check on the release run, 2026-11-12: a turn at work whose session was
    dropped under it left the chat with what it had done): an arrival and a turn at work are kept as drawn (the `shown` ledger's Host), and
    one the facts no longer give is drawn from there - a turn that was at work as stopped where it stood."""
    have = {x.get('id') for x in out}
    for k, host in was.items():
        if k in have or k in waiting or not host or not host.startswith('{'): continue
        try: x = json.loads(host)
        except ValueError: continue
        if x.get('kind') == 'turn': out.append({**x, 'state': 'stopped' if x.get('state') in LIVE else x.get('state'), 'cards': [], 'ended': x.get('ended') or x.get('started')})
        elif x.get('kind') == 'arrival': out.append(x)
    return out


def keep_shown(store, tid: int, out: list, was: dict) -> None:
    "What served_back draws an item from: an arrival as first drawn, a turn at work as it stands - written after `served` gave each its place."
    for x in out:
        if x['kind'] == 'arrival' and not was.get(x['id']) or x['kind'] == 'turn' and x.get('state') in LIVE and (x.get('text') or x.get('steps')):
            if (snap := json.dumps(x, default=str)) != was.get(x['id']): store._exec('UPDATE shown SET Host=? WHERE TaskId=? AND Key=?', (snap, int(tid), x['id']))


def served(store, tid: int, out: list) -> list:
    """THE CHAT ONLY EVER GROWS AT ITS FOOT (the owner, 2026-11-12: "have you ever seen a chat that you type something new and the past agent
    turn changes. of course not"): each item keeps the place it was first served in (the `shown` ledger) - a reload, a reopen, a restart draw
    the same order - and an item never served before goes under all of them, in the order this read made. Only an item's state changes."""
    known = {r['Key']: r['Seq'] for r in store._rows('SELECT Key, Seq FROM shown WHERE TaskId=?', (int(tid),))}
    new = [x for x in out if x['id'] not in known]
    if new:
        n = max(known.values(), default=0)
        with store.lock:
            store.cx.executemany('INSERT OR IGNORE INTO shown (TaskId, Key, Seq) VALUES (?,?,?)', [(int(tid), x['id'], n + i + 1) for i, x in enumerate(new)])
            store.cx.commit()
    return sorted((x for x in out if x['id'] in known), key=lambda x: known[x['id']]) + new


def dated(store, tid: int, out: list) -> None:
    """A TURN'S TIME IS SET ONCE (design round 5, I3: a turn read 4:57 while it worked and 5:12 once done; the turn under his 4:58 line read
    4:57). `at` is when the turn began IN THE CHAT - never before the input it stands under - written in the `shown` ledger the first read
    that draws it, and the same on every read after, at work and done. How long it ran is its clock's (`started`), never its head's time."""
    tid, prev = int(tid), 0.
    kept = {r['Key'][2:]: r['Host'] for r in store._rows("SELECT Key, Host FROM shown WHERE TaskId=? AND Key LIKE 'T:%'", (tid,))}
    new = []
    for x in out:
        if x['kind'] != 'turn':
            if x['kind'] in ('line', 'arrival', 'press') and x.get('at'): prev = max(prev, ep(x['at']))
            continue
        if (was := kept.get(x['id'])): x['at'] = was
        elif (at := max(ep(x.get('at')) if x.get('at') else 0., prev)): x['at'] = stamp(at); new.append((tid, f"T:{x['id']}", 0, x['at']))
        # ...AND ITS CLOCK COUNTS FROM THERE (design round 6, D6: under his 7:25 line a turn read "working 1m 28s" ten seconds after his Enter - the
        # clock of the CLI's turn, begun at 7:23 above it): at work and done alike, the turn's own time is what it ran
        if x.get('started') and x.get('at'): x['started'] = max(x['started'], ep(x['at']))
    if new:
        with store.lock: store.cx.executemany('INSERT OR IGNORE INTO shown (TaskId, Key, Seq, Host) VALUES (?,?,?,?)', new); store.cx.commit()


def left_on_him(store, tid: int, out: list, ask: dict = None, letters: str = None) -> None:
    """"FOR YOU TO DO" IS THE TURN'S OWN, SAID ONCE AND KEPT (design round 5, I3: it vanished from a turn when he typed, and the same words
    came back on the next turn). Whether a finished turn says what it left on him (`on_you`, its summary's) is settled the first read that
    can - its summary filed, its own question and cards pressed, or his line under it - in the `shown` ledger, and never changes after: never
    grown above his reply (2026-11-17: an ask answered, and the old turn grew its step over his answer), never moved to a later turn. Not
    where the turn before said the same."""
    tid = int(tid)
    kept = {r['Key'][2:]: r['Host'] for r in store._rows("SELECT Key, Host FROM shown WHERE TaskId=? AND Key LIKE 'Y:%'", (tid,))}
    new, said = [], None
    for i, x in enumerate(out):
        if x['kind'] != 'turn' or x['state'] in LIVE: continue
        sm = x.get('summary') or {}
        mine = [str(s) for s in sm.get('on_you') or [] if str(s).strip()] if not sm.get('nothing_left') else []
        if (was := kept.get(x['id'])) in (None, WAITS):
            # ...not yet while its own question, letters or cards are the step (WAITS, kept) - settled once they are pressed, or as nothing
            # where his own line or a message came under it first (nothing new above his line) - nor before its summary is filed (a beat after)
            waits = (ask and ask.get('turn') == x['id']) or letters == x['id'] or any(c['status'] == 'pending' for c in x['cards'])
            under = any(y['kind'] in ('line', 'arrival') for y in out[i + 1:])
            if waits and not under:
                if was is None: new.append((tid, f"Y:{x['id']}", 0, WAITS))
                continue
            if not sm and len(out) == i + 1: continue
            was = '1' if mine and mine != said and not waits and not (was == WAITS and under) else ''
            new.append((tid, f"Y:{x['id']}", 0, was))
        if was: x['on_you'], said = True, mine
    if new:
        with store.lock:
            store.cx.executemany('INSERT INTO shown (TaskId, Key, Seq, Host) VALUES (?,?,?,?) ON CONFLICT(TaskId, Key) DO UPDATE SET Host=excluded.Host '
                                 f"WHERE shown.Host='{WAITS}'", new); store.cx.commit()
WAITS = 'w'


# ONE BUILD OF A TASK'S CONVERSATION AT A TIME (the owner's live app, 2026-11-16: a working coding agent's chat took 25-40 s a call, and the
# page's polls, the task's read and the rail's ran their builds side by side, each slowing the others): a call while one is building waits for
# it and takes its result - the same list, built once
_BUILDS, _BUILDS_LOCK = {}, threading.Lock()


# ONE CLOCK FOR A TURN (the owner, 2026-11-16: a reply turn read "working 1m 39s" while it ran and "ran 1m 27s" once it was done): it starts
# at the FIRST hand-over after the answer before it - his line or press, a mail it woke for - live and finished alike. The latest one, read
# for the finished turn, was an input heard mid-way, and the turn he had watched for 1m 39s "ran" 12 seconds less
# ...AND A STOP ENDS A TURN AS AN ANSWER DOES (the real-CLI walk, 2026-11-17: a turn he stopped files no answer, so the 12 s turn after it
# counted from the stopped one's start and "ran 37s"): `stops`, when each of his stops was heard - the turn begins after the last one

def turn_start(marks, after: float, before: float = float('inf'), stops=()) -> float:
    "When the turn after answer `after` and before `before` began: its first hand-over from `after` on, and from his last stop (0. with none)."
    ms = [m['At'] for m in marks if after <= m['Seq'] < before]
    cut = max((s for s in stops if ms and s <= max(ms)), default=0.)
    return min((a for a in ms if a >= cut), default=0.)


def items(store, tid: int) -> dict:
    "The task's conversation: {rev, items, pending, working, started} - see the module's head. One build per task at a time (_BUILDS)."
    key = (id(store), int(tid))
    with _BUILDS_LOCK:
        b, mine = _BUILDS.get(key), False
        if b is None: b, mine = _BUILDS.setdefault(key, {'done': threading.Event(), 'got': None, 'err': None, 'by': threading.get_ident()}), True
    # ...a build that asks for its own task's list from inside it is that build: read straight, never waiting on itself
    if not mine and b['by'] == threading.get_ident(): return _items(store, tid)
    if not mine:
        b['done'].wait()
        if b['err'] is not None: raise b['err']
        return b['got']
    try: b['got'] = _items(store, tid)
    except BaseException as e: b['err'] = e; raise
    finally:
        with _BUILDS_LOCK: _BUILDS.pop(key, None)
        b['done'].set()
    return b['got']


def _items(store, tid: int) -> dict:
    from . import codingchat, funnel, general, ownwork, session_artifacts, sessionrecord, wrapup
    from .general import ASSISTANT_TYPE, FOLD_HEAD, USER_TYPE, WAITING_TYPE
    from .processing_unread import OWNER_ACTORS
    tid = int(tid)
    # ...read BEFORE the conversation: a turn that ends between the two reads is still at work in this one, its answer not yet read
    from . import origin
    hold_ = origin.hold(store, tid)
    at_work, t0 = (general.working(store, tid), general.turn_started(tid)) if not hold_ else (bool(getattr(general._live_of(tid), 'busy', False)), general.turn_started(tid))
    # ...the lines BEFORE the ledger: a line at rest is heard and then kept (general.take_line), so one read here has its hand-over in the
    # ledger read after it - never by the box for a frame, with the answer above it marked at work
    # ...and ONE MOMENT FOR THE WHOLE READ (the owner's live app, 2026-11-19): a read took 17 s on a busy store, the ledger read at its start
    # and the session's record at its end - the agent's steps after his line were drawn while the line still waited by the box, and once a
    # place is served it is kept: the turn and its "Thinking..." stood above his line for good. The record is read as of the ledger
    cut = time.time()
    rows, kept = store.list_comments(tid, internal=True), {c['CommentId']: c for c in general.chat_rows(store, tid)}
    led = {(r['Kind'], r['Ref']): r for r in store._rows('SELECT * FROM heard WHERE TaskId=? ORDER BY HId', (tid,))}
    era = min((r['At'] for r in led.values()), default=INF)
    marks = [r for (k, _), r in led.items() if k == 'turn']; prev_answer = 0       # the answer before the turn being read (turn_start)
    # ...AND A TURN HIS LINE BEGAN STARTS AT THAT LINE (the walks, 2026-11-17): heard at his press (general.take_line), it is the first thing
    # of the turn the ledger has - the turn not yet handed over read from his press, then went back to its hand-over seconds later
    starts = [r for (k, _), r in led.items() if k in ('turn', 'line')]
    # ...his stops, where heard (else from their own second - a stamp is no finer): each ends the turn it stopped (turn_start)
    # ...and HIS CLOSE, which stops its agent as a stop does (a stress round, 2026-11-18: closed while it worked and reopened by a new mail, the
    # turn the mail began counted from the stopped one's hand-over - drawn as that old turn at work above "You marked it done", its put-down
    # card taken into it)
    ends = (general.PRESSES['stopped_turn']({}), general.PRESSES['close_from_assistant']({}))
    stops = [(h := led.get(('press', str(i)))) and h['At'] or ep(at) for i, at, w, *_ in general.presses(store, tid) if w in ends]
    stops += [r['At'] for (k, _), r in led.items() if k == FAILED_TRY]          # ...and each try that failed (failed_try)
    backs = [int(r[1:]) for k, r in led if k == 'back' and r[:1] == '>']      # an answer taken back before its row was filed (take_back)
    back_why = lambda cid: next((w for n in sorted(backs, reverse=True) if n < cid and (w := led[('back', f'>{n}')].get('Sid'))), '')
    asked = None                                   # the task's own row: the ask that opened it, where no message did
    pend, ev = [], []                              # ev: (when, rank - an input before the work it began, order, entry)
    put = lambda t, rank, e, hid=0: ev.append((t, rank, hid, len(ev), e))        # ...and what one hand-over took, in the order it took it

    # the comments are one chain, in the order they were filed: his lines, Taskuary's briefs (never drawn - a turn begins there), the answers
    summ, steps_of, last, lines, texts = general.turn_summaries(store, tid), {}, 0., [], set()
    p = sessionrecord._gen_path(tid)
    if p.is_file():
        for l in p.read_text(encoding='utf-8', errors='replace').splitlines():
            try: j = json.loads(l); steps_of.setdefault(j.get('reply'), []).extend(j.get('steps') or [])
            except ValueError: continue
    snaps = store.draft_snapshots(tid)
    turn_of = {}                                   # an answer's CommentId -> its turn entry (a card names its turn by it)
    for c in rows:
        ty, cid = c.get('ActorType'), c['CommentId']
        # ONLY WORDS HE TYPED ARE A LINE, by who filed them here - never by the role a CLI or a runtime gave the text (the owner, 2026-11-11, of
        # Taskuary's own note to the agent drawn as his bubble: "it's not a prompt if you hit approve?"). What the app tells the agent - a
        # note, a wake, a press's result, whoever's name it is filed under - is no item at all: his press is its own quiet line (press_lines)
        if ty == WAITING_TYPE or (ty == USER_TYPE and c.get('Actor') in OWNER_ACTORS):
            body = general.his_line(c)
            it = {'id': c.get('LineId') or f'c:{cid}', 'kind': 'line', 'at': c['CreatedAt'], **body}
            h = led.get(('line', c.get('LineId') or ''))
            if not h and ty == WAITING_TYPE: pend.append({**it, '_after': _after(c['Body']), '_k': came(c)}); continue
            if h: it['_h'] = h['At']
            # ...one the ledger heard stands at its hand-over's own moment, beside what was taken with it (in the ledger's order, `put`): moved
            # a hair on for each line before it, every message of a flood stood above its second line
            last = h['At'] if h and h['At'] >= last else max(last + 1e-7, h['At'] if h else ep(c['CreatedAt']))
            put(last, 0, it, h['HId'] if h else 0); lines.append((last, _flat(body['text']), len(ev) - 1)); texts.add(_flat(body['text']))
        elif ty == USER_TYPE:
            last = max(last + 1e-7, ep(c['CreatedAt']))
            if str(c.get('Body') or '').startswith(FOLD_HEAD):
                put(last, 0, {'id': f'n:c{cid}', 'kind': 'note', 'at': c['CreatedAt'], 'text': 'Folded in ' + c['Body'][len(FOLD_HEAD):].split('\n', 1)[0]})
        elif ty == ASSISTANT_TYPE:
            body = clean(str((kept.get(cid) or c).get('Body') or ''))
            if c.get('Actor') == sessionrecord.NOTE_ACTOR:
                # ...after ALL of its own second, as a press is - its stamp is no finer: said in the second of the turn's last step (a turn cut
                # as Taskuary closed), it stood above the work it was said of
                last = max(last + 1e-7, ep(c['CreatedAt']) + 0.999); put(last, 0, {'id': f'n:c{cid}', 'kind': 'note', 'at': c['CreatedAt'], 'text': body}); continue
            began = max((m['At'] for m in marks if m['Seq'] < cid), default=0.)
            clock, prev_answer = turn_start(starts, prev_answer, cid, stops) or began, cid      # ...its clock (turn_start); `began` places it
            # ...AN ANSWER NOBODY MARKED THE START OF STANDS AT ITS OWN TIME (every task answered before hand-overs were written down - his
            # older tasks, the demo's): placed at the start of time, it stood above the mail it answered and the chat began with the agent
            last = max(last + 1e-7, began or ep(c['CreatedAt']))
            # ...ONE THAT FAILED says so where it failed, for good (general.file_turn): its closing line, after the app's own mark, is its `fail`
            body, fail = general.failed_line(body)
            st = _said(steps_of.get(cid, []), body, seen := set()); body = said_once(body, seen)
            # ...one it was made to take back (take_back): its words are a step of the work that goes on under it
            # ...and its summary goes with its words (the recorded walk, 2026-11-12: the saved sign-in's folded turn still drew its summary - "Erin
            # asked Alex ...; no reference number has been read yet" - under the note that it had signed in, the owner in the third person)
            took = (('back', str(cid)) in led or any(n < cid for n in backs)) and body
            if took:
                st, body, backs = [*st, {'k': 'note', 'text': (led.get(('back', str(cid))) or {}).get('Sid') or back_why(cid) or TOOK_BACK, 'took': True}], '', [n for n in backs if n >= cid]
            # ...and it BEGAN at its own time too (the demo walk, 2026-11-18): with no start it counted as begun at the start of time, so a card
            # made long before it was "made in" it - a played Send's card was taken into the line said after it, and jumped down under it
            t = {'kind': 'turn', 'at': stamp(clock) or c['CreatedAt'], 'state': 'failed' if fail else 'done', 'steps': st, 'text': body, 'cards': [],
                 'started': clock or ep(c['CreatedAt']), **({'fail': fail.strip()} if fail else {}),
                 'ended': ep(c['CreatedAt']), 'answer': f'comment-{cid}', **({'summary': summ[cid]} if cid in summ and not took else {})}
            # ...and each draft this turn left that a later turn rewrote: greyed where it stood, never moved
            newest = {s['review']: k for k, ss in snaps.items() for s in ss}
            t['cards'] = [{'id': f"r:{s['review']}:c{cid}", 'kind': 'card', 'review': s['review'], 'what': 'draft_reply', 'status': 'superseded', 'at': s['at'], 'was': s}
                          for s in snaps.get(cid, []) if newest.get(s['review']) != cid]
            turn_of[cid] = t; put(last, 1, t)

    # A ROUTINE'S RUN OF STEPS IS A TURN, on the one road every turn takes (flow.turn, 2026-11-17): at work while the run has the task and no
    # agent has taken it from there - "working" is one fact, so the run's at work is the chat's
    from . import flow, workflows
    flowing = workflows.at_work(tid) and not at_work
    if (ft := flow.turn(store, tid, flowing)): put(ft['started'] or last + 1e-7, 1, ft)      # ...where the run began: an agent it hands to answers under it
    at_work = at_work or flowing

    # a chat agent's turn at work: under what it was given, its steps as they come
    ses = general.session_for(tid)
    # ...never once its answer is filed: the session reads busy for a beat after (recorded 2026-11-12: a second, empty turn spun under the
    # answer for a frame and went) - the turn at work is the one the newest hand-over began, and that one has answered
    done_ = turn_of and turn_of[max(turn_of)]['ended'] >= max((m['At'] for m in marks), default=INF) - 0.01
    if ses is not None and getattr(ses, 'busy', False) and not done_:
        answered = max(turn_of, default=0)
        began = max((m['At'] for m in marks if m['Seq'] >= answered), default=0.) or max(last + 1e-7, getattr(ses, 'last', 0) or 0)
        clock = turn_start(starts, answered, stops=stops) or general.PRESSED.get(tid) or began      # its clock, as the finished turn reads it (his press before it is written)
        # ...and never from before a stop or a close of his that no hand-over has followed yet: the work it begins is under that press (a stamp
        # is a whole second) - read from the stopped turn's hand-over, it stood as that turn, at work again above the press
        # ...only for a turn that began since (the session's own turn clock, `last`): one still letting go of the stopped turn stays above the press
        if (cut := max(stops, default=0.)) >= began and (getattr(ses, 'last', 0) or 0) > cut: began = cut + 1; clock = max(clock or 0., began)
        # ...only what came after the newest line of his it heard mid-turn (sessionrecord.since_heard): before it stands above that line
        trace = sessionrecord.since_heard(getattr(ses, 'trace', None), max((r['At'] for r in led.values()), default=0.))
        # ...and the answer it is writing, while that is the newest thing it did (agents.ACPSteps._live): the turn's line of what it is doing
        doing = (lambda e: clean(e.get('detail')) if e and e.get('type') == 'live' and e.get('name') == 'writing' else '')(trace[-1] if trace else None)
        # ...STARTING UNTIL ITS AGENT HAS THE PROMPT (recorded on the real CLI, 2026-11-16: a cold adapter took most of a minute to open, and the
        # turn read "Thinking..." over it): no word from the agent's road yet but its own start - every CLI road traces `prompt` as it hands it over
        # ...OPENING while its agent really is starting: the turn says so from its start where its CLI is not up (general.cold, 2026-11-17), and
        # the prompt its road then hands over ends it - a kept conversation is never opening
        kinds = [e.get('type') for e in trace]
        opening = 'opening' in kinds and kinds[::-1].index('opening') < (kinds[::-1].index('prompt') if 'prompt' in kinds else len(kinds))
        put(max(last + 1e-7, began), 1, {'kind': 'turn', 'at': stamp(clock), 'state': 'working', 'steps': _said(sessionrecord.trace_steps(trace)), 'text': '', 'cards': [],
                                        'started': clock, 'ended': None, 'sid': getattr(ses, 'sid', ''), **({'doing': doing} if doing else {}), **({'opening': True} if opening else {})})

    # a coding session's record: its steps, cut into turns where it was given something. What it was given is never drawn from the record -
    # his lines are the ledger's, Taskuary's briefs nobody's - but a line typed into the pane itself, or one from before the ledger, is his
    live_sid = None
    for sid, live, steps in _session_steps(store, tid) if not general.handles(store.get_task(tid) or {}) or codingchat._live(tid) else []:
        if live: live_sid = sid
        steps = [s for s in steps if s['T'] <= cut]          # its times only grow (_session_steps): what it wrote after the ledger is the next read's
        took, n = [x for x in lines], 0
        for i, s in enumerate(steps):
            k = s.get('k')
            if k in ('you', 'brief'):
                n += 1
                if k == 'brief' or s.get('line') and ('line', s['line']) in led: continue
                f = _flat(s.get('text'))
                # ...one of his the ledger already placed (heard up to the step's own time): the same words, once
                hit = next((j for j, (at, w, _) in enumerate(took) if at <= s['T'] + 2 and w and (w == f or f.startswith(w[:150]) or w.startswith(f[:150]))), None) if s['T'] >= era - 2 else None
                if hit is not None:
                    # ...and where its own record says WHEN it took the line, that is when it heard it: a pane's CLI holds a typed line until
                    # its turn ends, and the answer before it was drawn under it (the recorded walk, 2026-11-11)
                    at, _, at_ev = took.pop(hit)
                    if s['T'] > at: ev[at_ev] = (s['T'], *ev[at_ev][1:])
                    continue
                # ...and one that names his kept line is that line - by the box until its hand-over is written, then where it was heard - never
                # a second line under the record's own name: sent into a turn, it stood in the chat AND by the box until the ledger caught up,
                # and went from one name to the other (the recorded hold, 2026-11-11)
                if s.get('line'): continue
                put(s['T'], 0, {'id': f'y:{sid}:{i}', 'kind': 'line', 'at': stamp(s['T']), 'text': s.get('text') or '', 'files': []})
            else: put(s['T'], 1, {'kind': 'step', 'sid': sid, 'seg': n, 'step': {k_: v for k_, v in s.items() if k_ != 'T'}, 'T': s['T']})

    # what came in, and what he pressed: at the moment the agent heard it, else at its own time
    # ...what the chat has drawn (the `shown` ledger) - its place, and for an arrival or a turn at work what it said (Host): drawn once, an item
    # is on the canvas in every read after (served_back)
    was_shown = {r['Key']: r['Host'] for r in store._rows('SELECT Key, Host FROM shown WHERE TaskId=?', (tid,))}
    waits = min((x.pop('_after') for x in pend), default=INF)
    began = (t0 or max((r['At'] for r in led.values()), default=0.) or INF) if at_work else INF
    any_mail = False
    for x in _mail(store, tid):
        any_mail = True
        # ...the task's OWN row (ownwork.ensure: his ask, filed as its first session opens) never "came in": it is what opened the chat (below)
        if (x.get('Channel') or '') == ownwork.CHANNEL: asked = x; continue
        h, it = led.get(('mail', str(x['MessageId']))), None
        row = general.mail_row(store, x)
        it = {'id': f"m:{x['MessageId']}", 'kind': 'arrival', **row, 'joined': stamp(x['T']), **({'_hm': h['At']} if h else {})}
        # ...a stamp is a whole second: one that joined in the turn's first second came in under it (it stood ABOVE the turn at work)
        # ...and one that came in while a line of his waits by the box waits there with it: drawn at once, the line entered above it when
        # both were heard, in the order they came (the recorded flood on a pane, 2026-11-11)
        # ...and what an untrusted sender wrote on a thread an agent works: it waits, behind the Trust action (origin.hold)
        # ...and one the chat has drawn never goes back by the box (the release run on macOS, 2026-11-12: a coding turn began in the second the
        # first mail joined, and the mail left the canvas for the waiting room)
        if not h and it['id'] not in was_shown and (at_work and x['T'] + 1 > began or x['MessageId'] > waits or (hold_ and x['MessageId'] in hold_['mids'] and (turn_of or live_sid))): pend.append({**it, '_k': came(x)})
        else: put(h['At'] if h else x['T'], 0 if h else -1, it, h['HId'] if h else 0)
    # ...AND ONE THAT WAS DRAWN HERE STAYS, though it moved to a task of its own (a break-out; the basic flow's check, 2026-11-12: the second
    # matter left the chat with the turn that answered it): where it stood, saying where it went
    here = {f"m:{x['MessageId']}" for x in _mail(store, tid)}
    for r in store._rows("SELECT Key FROM shown WHERE TaskId=? AND Key LIKE 'm:%'", (tid,)):
        if r['Key'] in here or not (m := store.get_message(int(r['Key'][2:]))) or int(m.get('TaskId') or 0) == tid: continue
        h = led.get(('mail', r['Key'][2:]))
        put(h['At'] if h else ep(m.get('CreatedAt')), 0, {'id': r['Key'], 'kind': 'arrival', **general.mail_row(store, {**m, 'T': ep(m.get('CreatedAt'))}),
                                                       'moved': int(m.get('TaskId') or 0)}, h['HId'] if h else 0)
    stop =f"You {general.PRESSES['stopped_turn']({})}."
    # ...HIS CLOSE IS ONE LINE (the recorded closed task, 2026-11-12: "You marked it done" and under it the page's "Mark done 4m ago"): the
    # press that closed an open-again-never task is marked `closes`, with the note he closed it with, and the page draws no line of its own
    # ...and every close of his, which ends the turn it was pressed under as his stop does (`_shut`, below)
    closes_ = [str(r['Id']) for r in store._rows("SELECT Id FROM audit WHERE EntityType='task' AND EntityId=? AND Action='close_from_assistant' ORDER BY Id", (tid,))]
    shut = {'Id': closes_[-1]} if closes_ and (store.get_task(tid) or {}).get('Status') == 'done' else None
    for m in general.press_lines(store, tid):
        aid, text = m['id'].split('-')[1], m['content'][0]['text']
        h, closes = led.get(('press', aid)), bool(shut) and aid == str(shut['Id'])
        if closes and (note := next((c['note'] for c in reversed(store.closeouts(tid)) if c['what'] == 'closed'), '')): text = f"{text.rstrip('.')} - {note.rstrip('.')}."
        it = {'id': f'p:{aid}', 'kind': 'press' if m.get('press') else 'note', 'at': m['createdAt'], 'text': text, **({'closes': True} if closes else {}),
              **({'_shut': not h} if aid in closes_ else {}),
              **({'perm': m['perm']} if m.get('perm') else {}),
              **({'stop': True, '_hs': bool(h)} if text == stop else {})}
        # ...and one the chat has drawn never goes back by the box, as a drawn mail does not (a stress round, 2026-11-18: his Mark done, drawn,
        # left the canvas while the turn a reopening mail began was starting, and came back above that mail once it was at work) - and his
        # close never waits there at all: like his stop it ends the turn it was pressed under, it is no input for the next
        if not h and it['id'] not in was_shown and at_work and ep(m['createdAt']) + 1 > began and m.get('press') and text != stop and aid not in closes_: pend.append({**it, '_k': (int(ep(m['createdAt'])), INF, 2, int(aid))})
        # ...A PRESS NOBODY HEARD YET STANDS AFTER ALL OF ITS OWN SECOND - its stamp is no finer: a stop pressed in the second its turn's line was
        # heard sorted above that line, and the stop's mark fell on the answer before it (a same-second tie, seen as a flash and a red test)
        else: put(h['At'] if h else ep(m['createdAt']) + 0.999, 0 if h else -1, it, h['HId'] if h else 0)
    # ...AND WHAT WAITS IN THE ORDER IT CAME, on the hand-over's own key (came; a press after all of its second): gathered kind by kind, his
    # lines stood by the box above the mail between them - and a read in the beat before the hand-over served them so, a place kept for good
    # (Windows CI, 2026-11-18: a flood read every line of his, then every mail)
    pend.sort(key=lambda p: p.pop('_k'))

    # in order - and an input nobody heard never cuts a turn's work in two: it stands after the turn it came in under
    # ...A CHAT TURN'S TOO, wherever its answer was placed (the stress round, 2026-11-18): a note filed while the turn worked (his reply from
    # the mailbox put the draft down) stands at the end of its second and pushes the answer after it - past his reply, read at its own time,
    # and the finished turn was drawn under the reply as the next turn's, then gone
    spans = [(e['started'], t) for t, _, _, _, e in ev if e['kind'] == 'turn' and e.get('started')]
    # (one step past it, exactly: at an epoch's size a 1e-7 nudge is under the float's grain and leaves the tie it was to break)
    ev = [(max([t] + [math.nextafter(at, INF) for b, at in spans if b <= t <= at]) if rank == -1 else t, rank, *r) for t, rank, *r in ev]
    from .failures import cli_quota
    out, held, run = [], [], None
    def close():
        nonlocal run
        run = None; out.extend(held); held.clear()
    for t, rank, _, _, e in sorted(ev, key=lambda x: x[:4]):
        if e['kind'] == 'step':
            if run is None or run['sid'] != e['sid'] or run['seg'] != e['seg']:
                close(); run = {'kind': 'turn', 'sid': e['sid'], 'seg': e['seg'], 'at': stamp(e['T']), 'state': 'done', 'steps': [], 'text': '', 'cards': [], 'started': e['T'], 'ended': e['T']}
                out.append(run)
            step = e['step']
            if step['k'] == 'error' and (notice := cli_quota(step.get('text'))):
                run.update(state='failed', fail=notice, quota=True)
                run['steps'] = [s for s in run['steps'] if s['k'] != 'said' or str(s.get('text') or '').strip().rstrip('.') != notice]
            else: run['steps'] += _said([step], seen=run.setdefault('_seen', set()))
            run['ended'] = e['T']
        elif rank == -1 and run is not None: held.append(e)
        else: close(); out.append(e)
    close()
    # THE ASK THAT OPENED THE TASK IS THE FIRST THING IN ITS CHAT, AS HIS WORDS (the owner, 2026-11-11, of a task he made with New: "i create
    # new agent it did not show the prompt i asked it to do???" - the chat held only the agent's turn at work): a task he started himself has
    # no message and, opened by its page, no typed line - its ask is the task's own (ownwork). It is the input the first turn heard, so it
    # stands above that turn, a line of his; where a line or a message already opens the chat, that is the ask
    first = next((x for x in out if x['kind'] in ('turn', 'line', 'arrival')), None)
    # ...from the moment its agent is started: its own row is filed only as the first session opens, a beat after the turn is at work. A
    # task he made and has not started says nothing yet - shown there, the title stood as his line and went when the line he typed began it
    # ...and once drawn it stays, whatever starts or stops after (the basic flow's check, 2026-11-12: it went when the turn it began ended)
    once = bool(store._one("SELECT 1 AS x FROM shown WHERE TaskId=? AND Key=?", (tid, f'a:{tid}')))
    once_s = bool(store._one("SELECT 1 AS x FROM shown WHERE TaskId=? AND Key=?", (tid, f's:{tid}')))
    # ...and never while a line of his begins the turn (PRESSED: his press; or heard and not yet filed): that line is the ask (CI parity, 2026-11-12: the task's title stood
    # as his line over the line he typed on one backend, from a read in that beat)
    drawn0 = {x.get('id') for x in out} | {p['id'] for p in pend}
    typed = any(k == 'line' and ref not in drawn0 for (k, ref) in led)
    if (asked or once or not any_mail and at_work and not pend and not typed and tid not in general.PRESSED) and (once or first is None or first['kind'] == 'turn') and (said := ownwork.ask(store, store.get_task(tid) or {}, asked)):
        at = asked['T'] if asked else ep((store.get_task(tid) or {}).get('CreatedAt'))
        # ...his words and his files, read as every line of his is (split_files): a file attached in New stood in his bubble as its path
        out.insert(0, {'id': f'a:{tid}', 'kind': 'line', 'at': stamp(at), **general.split_files(said), '_h': at})
    # ...AND A START NOBODY TYPED OPENS IT AS WHAT STARTED IT (started_by): where no line or message stands above its first work
    work = next((i for i, x in enumerate(out) if x['kind'] in ('turn', 'step', 'line', 'arrival')), None)
    # ...from its first read on: a chat drawn without it (from before this) never gets it under what was already there
    begun = once_s or not was_shown and (at_work or work is not None and out[work]['kind'] in ('turn', 'step'))
    if begun and (work is None or out[work]['kind'] in ('turn', 'step')) and (by := started_by(store, store.get_task(tid) or {})):
        at = ep((store.get_task(tid) or {}).get('CreatedAt'))
        out.insert(0, {'id': f's:{tid}', 'kind': 'arrival', 'who': by['head'], 'head': by['head'], 'channel': by['channel'], 'own': False,
                       'at': stamp(at), 'files': 0, 'words': by['words'], '_hm': at})
    # ONE TURN AT WORK, AND IT IS THE LAST (the owner's live task, 2026-11-11: a second head spun under a later, finished answer while the task
    # read done): a turn stands where it began, so one that reads at work with a turn after it has ended - whatever its session still says
    turns_ = [x for x in out if x['kind'] == 'turn']
    for x in turns_[:-1]:
        if x['state'] in ('working', 'starting'): x.update(state='done', ended=x.get('ended') or x.get('started'))
    # the turn at work is the last thing in the list: one the agent has not yet said a word in is there too, the moment its input was heard
    # ACP keeps streaming after a permission press. Show that work below its answered card.
    tail = next((x for x in reversed(out) if x['kind'] in ('turn', 'line', 'arrival') or (live_sid and x.get('perm'))), None)
    # ...A TURN HE STOPPED IS STOPPED FROM THE PRESS (the recorded stop, 2026-11-11: its CLI took seconds to let go, and all that time the turn
    # spun above "You stopped the agent"): what is at work from there is the turn his waiting lines begin, under the press - with none
    # waiting, nothing is
    # ...UNTIL A TURN BEGINS UNDER THE STOP: one that heard his stop (its hand-over wrote the press down, `hear`) answers what the stopped
    # turn took in and never spoke to (acpcoding._unanswered) - its lines stand above the stop, so no input of its own is under it
    # ...AND HIS CLOSE, the same (a stress round, 2026-11-18): it stopped the agent, so the turn above it is over, and what works after it - a
    # mail that reopened the task - is the turn under it, never that one at work again above "You marked it done"
    # ...AND ONE STOPPED BEFORE ITS FIRST STEP IS NO ITEM YET (recorded over ACP, 2026-11-17): his line is the newest thing, and the stop under
    # it was not read as ending its turn - a new turn stood under the stop, "Waiting for the agent to start", then vanished
    shut_ = bool(tail and tail['kind'] == 'turn' and any(x.get('_shut') for x in out[out.index(tail):]))
    halted = shut_ or bool(tail and any(x.get('stop') and not x['_hs'] for x in out[out.index(tail):]))
    if halted:
        # ...and from the press too where the stopped turn owes him an answer: that turn is on its way, and nothing else says so meanwhile
        at_work = bool(pend) or not shut_ and bool(getattr(general._live_of(tid), 'owes_stop', lambda: False)())     # ...a close owes nothing
        if tail.get('state') in ('working', 'starting'): tail.update(state='done', ended=tail.get('ended') or time.time())
    # ...A TURN IS MADE ONCE, AT ITS HAND-OVER: the live session's last turn is the one at work only where its work came after the newest
    # hand-over - one that ended before it is finished, and the turn now beginning stands under it (a wake after a press marked the answer
    # above "working" again, and the card under it lost its place)
    mark = max((m['At'] for m in marks), default=0.)
    # ...AND A TURN WHOSE ANSWER IS FILED AFTER THE NEWEST HAND-OVER IS THE WORK THAT WAS AT WORK (recorded 2026-11-12: its session still read
    # busy for a beat after the answer was filed, and a second, empty turn stood "starting" under it for a frame and went): nothing new runs
    # ...BUT A HAND-OVER ON ITS WAY IS NEW WORK (the browser audit, 2026-11-15): the agent's turn ended asking for the sign-in, its answer filed,
    # and the ~3 s Taskuary typed the saved one read as nothing at work - "agent waiting on you" with nothing on him (general.starting): that
    # turn is the one at work again, its last step the sign-in going in
    if at_work and not pend and tail and tail['kind'] == 'turn' and tail['state'] == 'done' and tail.get('answer') and (tail.get('ended') or 0) >= mark - 0.01 \
            and not (t0 and t0 > (tail.get('ended') or 0)):
        if general.starting(tid): tail.update(state='working', ended=None)
        else: at_work = False
    mine =not halted and tail and tail['kind'] == 'turn' and (tail['state'] == 'working' or tail.get('sid') == live_sid and live_sid and (tail.get('ended') or INF) >= mark - 0.01)
    # ...AND NONE BEFORE THE LINE THAT BEGINS IT IS IN THE LIST (recorded 2026-11-12: a read between take_line's "at work" and its keeping the
    # line drew the new turn's dots under the old answer, his line then under them): a line heard and not yet filed is the input it waits for
    drawn = {x.get('id') for x in out}
    unfiled = any(k == 'line' and r['At'] >= mark - 0.01 and ref not in drawn and ref not in {p['id'] for p in pend} for (k, ref), r in led.items())
    # ...A TURN NOT YET HANDED OVER IS THE SAME TURN (the walks, 2026-11-17): its clock and stamp the ones it keeps once at work - the first
    # thing heard from the press that began it (`starts`) - and opening where the turn at work will be (general.cold)
    begun, opens = min((r['At'] for r in starts if t0 and r['At'] >= t0), default=0.), ({'opening': True} if general.cold(tid) else {})
    # ...AND WHAT WORKS UNDER HIS ANSWER TO A STEP COUNTS FROM IT (the owner's live app, 2026-11-18: allowed a push at 9:00 in a turn begun at
    # 8:45, the work after it read "AGENT · 8:45 PM · working 15m" under his card): never a clock from before the press it stands under
    floor = lambda upto: max((x.get('_h') or ep(x.get('at')) for x in out[:upto] if x.get('perm')), default=0.)
    if at_work and not mine and unfiled: pass
    elif at_work and not mine:
        if tail and tail.get('perm') and turns_ and turns_[-1]['state'] in LIVE:
            turns_[-1].update(state='done', ended=tail.get('_h') or ep(tail.get('at')))
        # ...AND WHAT IT WILL TAKE STANDS ABOVE IT FROM THE FIRST READ (the walks, 2026-11-17: his outside reply, handed to the agent at rest,
        # sat ~3 s as a chip by the box under the turn's bare dots, then jumped up into the chat): where no input heard since begins this turn,
        # what waits - a mail, a line of his - is its input, drawn where it will stand once heard, under its own name. Behind a Trust it waits
        if not hold_ and not (tail and tail['kind'] in ('line', 'arrival', 'press') and (tail.get('_h') or tail.get('_hm') or ('press', tail['id'][2:]) in led)):
            took = [p for p in pend if p['kind'] in ('line', 'arrival')]
            if took: out += took; pend = [p for p in pend if p not in took]; tail = took[-1]
        began_ =begun or t0 or max(mark if tail and tail['kind'] == 'turn' and mark >= (tail.get('ended') or 0) else 0., (tail or {}).get('_h') or (tail or {}).get('_hm') or 0.) or time.time()      # from its hand-over, where one is written
        if (cut := max(stops, default=0.)) >= began_: began_ = cut + 1        # ...never from before a stop or a close of his (as the turn at work, above)
        began_ = max(began_, floor(len(out)))
        out.append(tail := {'kind': 'turn', 'at': stamp(began_), 'state': 'starting', 'steps': [], 'text': '', 'cards': [], 'started': began_, 'ended': None, **opens})
    elif at_work and tail['state'] != 'working':
        b_ = max(t0 or tail['started'], floor(out.index(tail))); tail.update(state='working', ended=None, started=b_, at=stamp(b_) if b_ != tail['started'] else tail['at'])
    # ...AND NEVER ABOVE HIS NEWEST LINE (the owner's live task, 2026-11-12: the dots stood over "try now"; recorded on ACP the same day for a
    # frame - the session's record had not yet cut its turn at his line): what works now is the turn his line began, under it
    if at_work and (his := max((i for i, x in enumerate(out) if x['kind'] == 'line'), default=-1)) >= 0:
        for x in out[:his]:
            if x['kind'] == 'turn' and x['state'] in ('working', 'starting'): x.update(state='done', ended=x.get('ended') or x.get('started'))
        if not any(x['kind'] == 'turn' and x['state'] in ('working', 'starting') for x in out[his + 1:]):
            b_ = begun or t0 or out[his].get('_h') or time.time()
            out.append({'kind': 'turn', 'at': stamp(b_), 'state': 'starting', 'steps': [], 'text': '', 'cards': [], 'started': b_, 'ended': None, **opens})
    # ..."WORKING" IS ONE FACT, the one the task's header reads: where it is false no turn spins
    if not at_work:
        for x in out:
            if x['kind'] == 'turn' and x['state'] in ('working', 'starting'): x.update(state='done', ended=x.get('ended') or x.get('started'))
    # ...a turn he stopped ended there, and one that failed says so where it failed, with the way past it
    for i, x in enumerate(out):
        # ...the turn right above his stop - one stopped before it said or did anything left nothing, and the mark fell on the finished answer
        # above the line it never got to answer (the recorded stop, 2026-11-11)
        if x.get('stop') and (t := next((y for y in reversed(out[:i]) if y['kind'] in ('turn', 'line', 'arrival')), None)) and t['kind'] == 'turn' and t['state'] == 'done': t['state'] = 'stopped'
    # ...and one stopped before it said or did anything is no item: his stop's own line says it. It was drawn empty between his line and
    # the press while its session still held it, and was gone once the next turn ended (the recorded stop, 2026-11-11)
    out = [x for x in out if not (x['kind'] == 'turn' and x['state'] == 'stopped' and not (x['text'] or x['steps'] or x['cards']))]
    # ...AND STAYS THERE ONCE HE HAS MOVED ON (the Continue round, 2026-11-18): drawn only while it was the run's last word, the failure went from
    # above his line the moment he pressed Continue with a note - his first ask then stood with nothing under it. It stands under the input it
    # failed on, by its own time; the way past it (`fix`) only while it is still the run's ending
    if not at_work and (f := funnel.run_failed(store, tid, live_too=True)):
        evf = store.last_worker_event(tid, kinds=('failed',)) or {}
        t = next((y for y in reversed(out) if y['kind'] in ('turn', 'line', 'arrival')), None)
        if not (t and t['kind'] == 'turn'):
            if ep(evf.get('CreatedAt')) >= ep((t or {}).get('at')) - 1: out.append(t := {'kind': 'turn', 'at': evf.get('CreatedAt') or '', 'state': 'failed', 'steps': [], 'text': '', 'cards': [], 'started': None, 'ended': ep(evf.get('CreatedAt'))})
            else: t = None
        if t and (t.get('ended') or 0) <= ep(evf.get('CreatedAt')) + 1: t.update(state='failed', fail=f['sentence'], fix=f.get('fix'))
    # ...AND STAYS THERE ONCE HE HAS MOVED ON (the Continue round, 2026-11-18): drawn only while it was the run's last word, the failure went from
    # above his line the moment he pressed Continue with a note, and his first ask stood with nothing under it. Past, it stands under the input it
    # failed on, by its own time, without the way past it - the turn after it is that
    elif (evf := store.last_worker_event(tid, kinds=('failed',))):
        tf = ep(evf.get('CreatedAt'))
        i = next((k for k in range(len(out) - 1, -1, -1) if out[k]['kind'] in ('line', 'arrival') and ep(out[k].get('at')) <= tf), None)
        if i is not None and i + 1 < len(out):
            f, t = funnel.failure_of(evf, tid), out[i + 1]
            if not (t['kind'] == 'turn' and t['state'] != 'working' and (t.get('ended') or 0) <= tf + 1):
                out.insert(i + 1, t := {'kind': 'turn', 'at': evf.get('CreatedAt') or '', 'state': 'failed', 'steps': [], 'text': '', 'cards': [], 'started': None, 'ended': tf})
            t.update(state='failed', fail=f['sentence'], fix=None)

    # names: an input's is its own; a turn's is the input it stands under and its place after it
    seen, anchor, n = set(), f'0:{tid}', 0
    for x in out:
        if x['kind'] == 'turn':
            # ...a coding session's turn by its own record (its session, its place in it): an input that joined above it never renames it (the
            # basic flow's check, 2026-11-12: a mail placed over a closed session's turn renamed it, and the turn went and came back)
            x['_seg'] = x.pop('seg', None)
            # ...and a routine's run by its own (flow.turn's `run:<task>`), the key its steps go on writing under (chatlog.ran)
            x['id'] = (x['id'] if str(x.get('id') or '').startswith('run:') else f"t:{x['sid']}:{x['_seg']}" if x.get('sid') and x['_seg'] is not None
                       else f't:{anchor}:{n}'); n += 1
        else:
            if x['kind'] in ('line', 'arrival', 'press'): anchor, n = x['id'], 0
        if x['id'] in seen: x['id'] += f":{len(seen)}"
        seen.add(x['id'])

    # A TURN'S CARDS STAND LAST IN IT: each action under the turn that set it up (the one that last left a draft as it stands), else where it was made
    # ...the turn that was at work when a thing was made: the first one that had begun (where its start is known) and had not yet ended
    # ...and a turn still at work before one that ended a moment ago (2026-11-12: a stamp is a whole second, so the turn that ended just
    # before can still read as open by it - a step held in the turn at work went up to the one before, above his line)
    def made_in(at):
        open_ = [x for x in out if x['kind'] == 'turn' and (x.get('ended') is None or x['ended'] + 1 >= at - 0.999) and (x.get('started') or 0) <= at]
        return next((x for x in open_ if x.get('ended') is None), open_[0] if open_ else None)
    # ...and each page it showed or published, by that same rule, named by its turn (`after`: the page's key for a turn); None: at the foot
    from . import outputs
    published = [{**p, 'after': (t.get('answer') or t['id']) if (t := made_in(ep(p.get('created_at')) + 0.999)) else None} for p in outputs.pages(store, tid)]
    # ...A CARD STANDS IN THE TURN IT WAS FIRST DRAWN IN, or a later one that left it again - never back up (the `shown` ledger's Host)
    hosts = {r['Key'][2:]: r['Host'] for r in store._rows("SELECT Key, Host FROM shown WHERE TaskId=? AND Key LIKE 'c:%'", (tid,))}
    # ...by name, not place: a card no turn holds is put into `out` itself, and every place after it moves down one
    turn_by = {x['id']: x for x in out if x['kind'] == 'turn'}
    turns_at = {k: i for i, k in enumerate(turn_by)}
    newest = next((x for x in reversed(out) if x['kind'] == 'turn'), None)
    from .proposals import passed as proposals_passed
    # ONE CARD AT A TIME (cardqueue): a card that waits behind another is drawn nowhere until its turn comes - and then where the chat has
    # got to, never back in the turn that raised it, above what came since: in the newest turn when nothing came in after it, else under
    # everything. One that waited and was over before it ever stood (taken back, written past) never stands at all
    from . import cardqueue
    queue = cardqueue.state(store, tid); cardqueue.mark(store, tid, queue)
    held = {x for x in queue['held'] if x != cardqueue.LAND}
    # ...and what the chat moved past is greyed where it stood from the moment the input came (proposals.written_past): an email too
    past = queue['past']
    waited = {r['Key'][2:] for r in store._rows("SELECT Key FROM shown WHERE TaskId=? AND Key LIKE 'q:%'", (tid,))}
    last_in = max((i for i, x in enumerate(out) if x['kind'] in ('line', 'arrival', 'press')), default=-1)
    ahead = newest if newest and out.index(newest) > last_in else None
    def place(card, at, cid=None):
        # ...a draft no turn has left yet is new now, whenever its row was made (the recorded walk, 2026-11-12: a reply owed since the mail came
        # was filled in the turn under his line and drawn in the turn of the mail's arrival - live, above his line): it goes in the newest turn,
        # which holds it back while it works
        fresh = card['what'] in DRAFTS and card['status'] == 'pending' and not cid
        h = hosts.get(card['id'])
        if card['id'] in waited and not h:
            # ...(where it first stood under everything it stays: '' is that place in the ledger)
            if ahead is None or h == '':
                if h is None: store._exec('INSERT OR IGNORE INTO shown (TaskId, Key, Seq, Host) VALUES (?,?,0,?)', (tid, f"c:{card['id']}", ''))
                out.append(card); return
            cid, fresh = None, True
        t = (turn_of.get(cid) if cid else None) or (newest if fresh and newest else made_in(at))
        # ...down only to a turn that LEFT it again (its record names that turn): a turn begun after it is not one (recorded on ACP, 2026-11-12:
        # the session went on into a second turn and the card, drawn in the first, went from the chat until the second ended)
        # ...(one with no words yet has nothing that stood anywhere: it is the newest turn's, each time, with what that turn needs for it)
        if h in turns_at and not (fresh and not card.get('was')) and (t is None or not cid or turns_at.get(t['id'], -1) < turns_at[h]): t = turn_by[h]
        elif t is not None and h != t['id'] and not (t['state'] in LIVE):
            store._exec('INSERT INTO shown (TaskId, Key, Seq, Host) VALUES (?,?,0,?) ON CONFLICT(TaskId, Key) DO UPDATE SET Host=excluded.Host', (tid, f"c:{card['id']}", t['id']))
        if t is None:
            i = max((j for j, x in enumerate(out) if ep(x.get('started') or x.get('at')) <= at), default=-1)
            if i >= 0 and out[i]['kind'] == 'turn': t = out[i]
            else: out.insert(i + 1, card); return
        t['cards'].append(card)
    # ...a task's emails are the page's own block while they wait (`letters`, below); one he wrote past stays where it stood, greyed with
    # its words, as a reply does
    # ...AND ONE THAT WENT IS A CARD OF THE TURN IT STOOD UNDER, as a reply that went is (the audit, 2026-11-13, recorded on the real CLI: two
    # emails sent, and the list placed neither - the page drew them under everything, so they went from the chat while each later turn
    # worked and came back at its foot, under words written long after them)
    # ...A BULK CARD IS ONE CARD (bulkcard.py): its rows stand as the one card of its first, which the page draws in its bulk form
    batches = {}
    for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Batch IS NOT NULL ORDER BY ReviewId", (tid,)): batches.setdefault(r['Batch'], []).append(r)
    for r in store._rows("SELECT * FROM review WHERE TaskId=? ORDER BY ReviewId", (tid,)):
        if (b := r.get('Batch')):
            rs = batches.get(b) or [r]
            if r['ReviewId'] != rs[0]['ReviewId'] or r['ReviewId'] in held: continue
            # ...greyed where it stood once the chat moved past it, as any card (written_past) - and one that waited behind another and was
            # over before it ever stood never stands, as a single card's rule below
            open_ = [x for x in rs if x['Status'] == 'pending']
            gone = all(x['ReviewId'] in past for x in open_) if open_ else any(proposals_passed(x) for x in rs)
            if (f"r:{r['ReviewId']}" in waited and hosts.get(f"r:{r['ReviewId']}") is None and (gone or not open_)
                    and not any(x.get('DecidedBy') in OWNER_ACTORS for x in rs)): continue
            place({'id': f"r:{r['ReviewId']}", 'kind': 'card', 'review': r['ReviewId'], 'what': 'batch', 'batch': b, 'n': len(rs),
                   'status': 'passed' if gone else 'pending' if open_ else 'done', 'at': r['CreatedAt'], 'decided': None}, ep(r['CreatedAt']) + 0.999)
            continue
        # ...and one he said Don't send to stays too, greyed where it stood (the real-CLI walk, 2026-11-16: it went from the chat - _card)
        if r['Kind'] == 'slot' and not (str(r.get('DraftText') or '').strip() and (proposals_passed(r) or r['Status'] in (*WENT, 'rejected') or r['ReviewId'] in past)): continue
        if unwritten(r) or r['ReviewId'] in held: continue
        if cardqueue.obsolete_read(store, tid, r): continue
        # ...(one the chat moved past while it waited is over already, before its agent has heard the line that did it)
        if f"r:{r['ReviewId']}" in waited and hosts.get(f"r:{r['ReviewId']}") is None and (r['Status'] != 'pending' or r['ReviewId'] in past) and r.get('DecidedBy') not in OWNER_ACTORS: continue
        left = None if r['Kind'] == 'action' else wrapup.left_by(store, r['ReviewId'])
        place(_card(r), ep(r['CreatedAt']) + 0.999, (left or {}).get('CommentId'))

    # A CARD STANDS WHERE ITS TURN LEFT IT, FOR GOOD (the owner, 2026-11-12: "It's a chat with prompts and agent turns, nothing ever goes
    # backwards"): no card is moved under a later answer, copied there, or left behind as a ghost - he moves on past one by writing again (a
    # draft above his newer line is set aside then, `hear`), and the agent raises what is still owed as a new card in its own turn.
    # ...AND A TURN'S CARD IS DRAWN ONCE THE TURN HAS ENDED, as its last thing (the owner, 2026-11-12: "it should finish thinking and last thing
    # should be show action box" - its words landed above a card drawn while it worked): a step it is stopped at waits on him mid-turn as its
    # permission (`permissions`, drawn under the turn), never as a card in it
    # ...AND A TURN THAT GOES ON FROM THE ONE BEFORE IT, WITH NO INPUT BETWEEN, IS THE SAME WORK (the owner's live task, 2026-11-13: a turn
    # left its reply card, Taskuary woke its agent a beat later, and the woken turn's words were drawn UNDER that card - "text after the
    # action box"): what still waits for his press stands at the END of the run, under its last words - once the turn that goes on has
    # ended. WHILE IT WORKS the card stays where it stood, lit (the owner, 2026-11-13: "never close actions boxes" - a Send on one of two
    # emails woke the agent, and the other email vanished for the 15-30 s that turn ran). A card he pressed, or one set aside, stays put
    for a, b in zip(out, out[1:]):
        if a['kind'] == 'turn' and b['kind'] == 'turn' and b['state'] not in LIVE and (lit := [c for c in a['cards'] if c['status'] == 'pending']):
            a['cards'], b['cards'] = [c for c in a['cards'] if c['status'] != 'pending'], [*lit, *b['cards']]
            for c in lit:
                if hosts.get(c['id']) != b['id']:
                    store._exec('INSERT INTO shown (TaskId, Key, Seq, Host) VALUES (?,?,0,?) ON CONFLICT(TaskId, Key) DO UPDATE SET Host=excluded.Host', (tid, f"c:{c['id']}", b['id']))
    from . import permissions
    perms = permissions.pending(tid, store)
    for x in out:
        # ...a turn at work holds back only what it has not drawn yet: a card already shown in it stays (the owner, 2026-11-13: "never close
        # actions boxes" - a Send woke the agent, the same turn went on, and the other email waiting in it vanished until the turn ended)
        if x['kind'] == 'turn' and x['state'] in ('working', 'starting'): x['cards'] = [c for c in x['cards'] if hosts.get(c['id']) == x['id']]
    # ...A REPLY DRAFT ABOVE A NEWER INPUT IS NOT THE ONE TO PRESS, from the frame that input is drawn (`hear` settles it as the turn takes the
    # input): greyed where it stood - its turn drafts again under the input where a reply is still owed
    # ...and a turn that ended having said, done and left nothing (a CLI turn that only took a line in) is no item: the page drew nothing for it
    out = [x for x in out if not (x['kind'] == 'turn' and x['state'] == 'done' and not (x['text'] or x['steps'] or x['cards'] or x.get('summary')))]
    # ...and EACH VIEW IT SHOWED IS DRAWN FROM THE TASK'S OWN COPY, on the turn's `show` step - whatever the CLI's trace kept of the call
    sessionrecord.views_onto(out, store._rows("SELECT * FROM task_artifact WHERE TaskId=? AND Kind=?", (int(tid), session_artifacts.VIEW)))

    # A CODING RUN THAT LEFT WITHOUT FINISHING SAYS SO IN ITS CHAT (decided 2026-11-12): the header chip read "agent stopped", the rail row the
    # sentence cut by its width, and the chat nothing. The task's own idle sentence (funnel.idle_state - the one the row reads) is its last line
    task_ = store.get_task(tid) or {}
    if out and not at_work and not live_sid and not general.handles(task_) and task_.get('Status') not in ('done', 'dropped'):
        from . import funnel, taskstate
        st_ = taskstate.task_state(store, tid=tid)
        if not st_.finished and (idle := funnel.idle_state(store, tid, st_))['kind'] == 'left' and idle['line']:
            out.append({'id': 'n:left', 'kind': 'note', 'at': out[-1].get('at'), 'text': idle['line']})
    # ...and once said it stays where it was said when the run is taken up again (the basic flow's check, 2026-11-12: it went from the chat)
    was_left = store._one("SELECT Host FROM shown WHERE TaskId=? AND Key='n:left'", (tid,))
    if was_left and was_left['Host'] and not any(x['id'] == 'n:left' for x in out if x.get('id')):
        out.append({'id': 'n:left', 'kind': 'note', 'at': '', 'text': was_left['Host']})
    for x in [*out, *pend]: x.pop('stop', None); x.pop('_h', None); x.pop('_hm', None); x.pop('_hs', None); x.pop('_seg', None); x.pop('_shut', None); x.pop('_seen', None)
    out = served(store, tid, served_back(store, tid, out, was_shown, {p['id'] for p in pend})); keep_shown(store, tid, out, was_shown)
    dated(store, tid, out)
    # (the reply draft above a newer input, greyed - read in the order drawn)
    # (and any card of the agent's above his newer line - every kind, 2026-11-12 - `hear` settles it as his line is heard)
    # ...and one the thread moved past that no agent has heard yet, by the rule the header's pill and the rail read (proposals.written_past)
    from . import proposals
    last_in = max((i for i, x in enumerate(out) if x['kind'] in ('line', 'arrival')), default=-1)
    last_his = max((i for i, x in enumerate(out) if x['kind'] == 'line'), default=-1)
    for i, x in enumerate(out):
        for c in [x] if x['kind'] == 'card' else x['cards'] if x['kind'] == 'turn' else []:
            # ...a card of several emails as well: it has no words of its own to keep, and lit over his newer line it offered two Sends he had
            # just written past (the real-CLI card walk, 2026-11-18)
            set_aside = c.get('was') or c['what'] == 'batch'
            if c['status'] == 'pending' and set_aside and (c['what'] in DRAFTS and i < last_in or i < last_his or c['review'] in past): c['status'] = 'passed'
            # ...each says why in what happened (proposals.passed_why), never "you moved on" over a draft he never saw
            if c['status'] == 'passed' and (rv := store.get_review(c['review'])): c['why'] = proposals.passed_why(store, rv)
            elif c['status'] == 'pending' and set_aside: c['aside'] = proposals.WROTE_PAST      # ...and the page says it from his Enter (withMine)
    # ...and a reply with NO words yet - its card said only what its agent needed - is not the one to press above his newer line either
    # (recorded 2026-11-13: he answered the agent's question, and the empty reply box stood lit over his answer while the turn that writes it
    # worked): it has nothing to grey, so it is not drawn there; the turn his line began raises it, written, as its own last thing
    for i, x in enumerate(out[:max(last_his, 0)]):
        if x['kind'] == 'turn': x['cards'] = [c for c in x['cards'] if not (c['status'] == 'pending' and c['what'] in DRAFTS and not c.get('was'))]
    if (said_ :=next((x['text'] for x in out if x['id'] == 'n:left'), None)) and not (was_left and was_left['Host'] == said_):
        store._exec("UPDATE shown SET Host=? WHERE TaskId=? AND Key='n:left'", (said_, tid))
    # ...and what the agent waits on him for, and the CLI that runs: read by the page off this one list (the chat's own payloads are gone)
    from . import taskstate
    live = general._live_of(tid)
    ask = taskstate.asking(store, store.get_task(tid) or {'TaskId': tid}, general.session_for(tid) or (live if codingchat._live(tid) else None))
    # A QUESTION IS SAID ONCE, IN ITS TURN'S OWN WORDS, ABOVE ITS CARD (the owner, 2026-11-11; the recorded walk drew it a second time under
    # the reply card): where the newest answer already holds the ask's words the list says `said`, and the page draws no line of its own
    # A STEP THAT WAITS ON HIS ALLOW IS ONE CARD (the owner, 2026-11-11: "the question has 2 approve buttons?" - recorded on a coding agent: the
    # permission's card with Allow once / Reject, and under it the same request again as the agent's question, with the same two buttons):
    # the request a permission made is `permissions`' to draw, never the agent's question beside it
    if ask and ask.get('source') == 'permission' and perms: ask = None
    flat = lambda v: ' '.join(re.sub(r'[*_`]', '', str(v or '')).split())
    last = next((x for x in reversed(out) if x['kind'] == 'turn'), None)
    if last and last['state'] == 'failed' and (notice := cli_quota(last.get('fail'))):
        last.update(fail=notice, quota=True)
        if not at_work: ask = None
    # ...a coding turn's words are its `said` steps, its text empty: the demo's #214 drew its closing question twice
    words = last and ' '.join([str(last.get('text') or ''), *(s.get('text') or '' for s in last.get('steps') or [] if s.get('k') == 'said')])
    if ask and last and flat(ask.get('text')) and flat(ask['text']) in flat(words): ask = {**ask, 'said': True}
    # ...AND IT STANDS IN THE TURN THAT ASKED IT, NEVER AT THE CHAT'S FOOT (the owner, 2026-11-13: "never ever pin items on the bottom of the
    # chat" - recorded the same day: a question still open was drawn again under each later turn, leaving the one it had stood under): the
    # list names that turn (`turn`: the one at work when the ask was raised, else the newest) and the page draws the ask inside it, once -
    # with no line of its own where that turn's words already hold it
    if ask and last:
        said_of = lambda t: ' '.join([str(t.get('text') or ''), *(s.get('text') or '' for s in t.get('steps') or [] if s.get('k') == 'said')])
        by = (made_in(ep(ask['at']) + 0.999) if ask.get('at') else None) or last
        ask = {**ask, 'turn': by['id'], **({'said': True} if flat(ask.get('text')) and flat(ask['text']) in flat(said_of(by)) else {})}
    # ...AND IT IS THE ONE THING ASKED (the owner: a missing fact is one question in the task; recorded on the real CLI, 2026-11-15: under the
    # agent's question stood the reply it could not write yet, captioned with the same question, an empty box over a greyed Send): a reply
    # with no words is not drawn while its agent waits on his answer - the turn his answer begins writes it
    if ask:
        for x in out:
            if x['kind'] == 'turn': x['cards'] = [c for c in x['cards'] if not (c['status'] == 'pending' and c['what'] in DRAFTS and not c.get('was'))]
    # WHERE THE LETTERS THAT WAIT FOR HIS SEND ARE DRAWN: the reply and the task's emails are one block of the page (the reply's card, the
    # emails over it), and the list names its turn - `letters`: the LAST turn that left a letter still waiting, the end of its run. The page
    # hung the block on the newest reply whatever its state, so an email written turns after a reply had gone was drawn up at that reply's
    # card, above everything said since; a turn at work holds the block back as it does its cards
    order = {x['id']: i for i, x in enumerate(out)}
    def run_end(t):
        i = order.get((t or {}).get('id'), -1)
        # ...never into a turn at work (recorded on the real CLI, 2026-11-15; the owner, 2026-11-13: "never close action boxes"): he sent one of
        # two emails, the agent was woken, and for the eleven seconds its turn worked the other email was off the screen - a turn at work
        # shows no block. It keeps its place until that turn has ended, then stands under its words
        while 0 <= i < len(out) - 1 and out[i + 1]['kind'] == 'turn' and (i < 0 or out[i + 1]['state'] not in LIVE or out[i]['state'] in LIVE): i += 1
        return out[i] if i >= 0 else None
    # ...an email is written INSIDE its turn: of two turns a whole-second stamp cannot tell apart, the later one wrote it (the one before had ended)
    wrote = lambda at: next((x for x in reversed(out) if x['kind'] == 'turn' and (x.get('started') or 0) <= at and (x.get('ended') is None or x['ended'] + 1 >= at - 0.999)), None)
    spots = [x for x in out if x['kind'] == 'turn' and any(c['status'] == 'pending' and c['what'] in DRAFTS for c in x['cards'])]
    # ...one that waited its turn (cardqueue) where it came to stand: the turn it was first drawn in, else the newest one past the last input
    def spot(r):
        k = f"r:{r['ReviewId']}"
        if k not in waited: return run_end(wrote(ep(r['CreatedAt']) + 0.999))
        return turn_by.get(hosts.get(k) or (ahead or {}).get('id'))
    spots += [t for r in store._rows("SELECT ReviewId, CreatedAt, DraftText FROM review WHERE TaskId=? AND Kind='slot' AND Status='pending' AND Batch IS NULL", (tid,))
              if str(r.get('DraftText') or '').strip() and r['ReviewId'] not in held | past and (t := spot(r))]
    letters = max(spots, key=lambda t: order.get(t['id'], -1))['id'] if spots else None
    # ...and where its block stands is where each waiting email STOOD, kept as a card's place is (`shown` Host): sent, it stays there
    if letters and turn_by.get(letters, {}).get('state') not in LIVE:
        for r in store._rows("SELECT ReviewId FROM review WHERE TaskId=? AND Kind='slot' AND Status='pending' AND Batch IS NULL", (tid,)):
            if r['ReviewId'] not in held | past and hosts.get(f"r:{r['ReviewId']}") != letters:
                store._exec('INSERT INTO shown (TaskId, Key, Seq, Host) VALUES (?,?,0,?) ON CONFLICT(TaskId, Key) DO UPDATE SET Host=excluded.Host', (tid, f"c:r:{r['ReviewId']}", letters))
    left_on_him(store, tid, out, ask, letters)
    # THE WAITING ROOM (the owner, 2026-11-12): what waits for the agent is drawn in ONE place until it is heard - his lines as rows over the
    # box, messages as counts on their sender's chip - and `now` says whether a waiting line can be handed into the turn at work at once (a
    # session that takes words mid-turn, not stopped at his Allow); `dropped`: the lines he took back, which leave no trace
    live_ = codingchat._live(tid)
    now = bool(at_work and pend and not perms and live_ is not None and getattr(live_, 'steerable', lambda: False)())
    later = LATER if at_work and any(p['kind'] == 'line' for p in pend) and not getattr(general._live_of(tid), 'hears_mid_turn', lambda: True)() else ''
    dropped = [json.loads(r['Detail'] or '{}').get('line') for r in store._rows("SELECT Detail FROM audit WHERE EntityType='task' AND EntityId=? AND Action='line_dropped'", (tid,))]
    # A START THAT DID NOT HAPPEN SAYS WHY, WHERE HE LOOKS (the owner's rule 4; recorded on the real CLI, 2026-11-15: the switch off, the task
    # read "waiting to start" over a chat that held only the mail). The reason was written on the task (ingest.not_started) and drawn nowhere:
    # it stands under the chat while nothing has worked the task and nothing is at work - never over a stranger's hold, which says its own.
    # Beside the list, not an item of it: a chat's items never leave it, and this line is true only until a turn begins
    idle = None
    if not at_work and not hold_ and not pend and task_.get('Status') not in ('done', 'dropped') and out and all(x['kind'] == 'arrival' for x in out):
        from .ingest import NOT_STARTED
        why = next((c for c in reversed(store.list_comments(tid, internal=True)) if str(c.get('Body') or '').startswith(NOT_STARTED)), None)
        if why: idle = f"{why['Body']} {START_BY_WRITING}"
    # ...HIS FIRST LINE ON A REPORT HE SENT ON CARRIES ITS NAME (the owner, 2026-11-17: "it says report name then your prompt"): the report is the
    # pill in his bubble, as it was on the box he typed it in - and the report itself on the task's Came from
    if (task_.get('Source') == 'report') and not any(x['id'] == f's:{tid}' for x in out) and (first := next((x for x in out if x['kind'] == 'line'), None)):
        m = next(iter(store.list_messages(tid)), None) or {}
        if (name := str(m.get('SourceName') or m.get('Subject') or '').strip()): first['came'] = name
    body = {'items': out, 'pending': pend, 'now': now, 'later': later, 'dropped': [d for d in dropped if d], 'working': at_work, 'started': t0 if at_work else None, 'asking': ask,
            'permissions': perms, 'live': codingchat.live_of(codingchat._live(tid)),
            'letters': letters, 'idle': idle,
            # ...and the line of cards (cardqueue): which one stands, which wait behind it unseen, and what the one standing says of them
            'queue': {'live': queue['live'], 'held': queue['held'], 'line': cardqueue.line(queue)}, 'hold': hold_ and {**{k: hold_[k] for k in ('line', 'person', 'org')},
                              **({'line': origin.JOINED_LINE.format(who=hold_['who'])} if any(x['kind'] == 'turn' for x in out) else {})}, 'published': published, 'ran': bool(turn_of) or any(x['kind'] == 'turn' for x in out)}
    # ...hashed in the order it is built - the same every time - not sorted: sorting every step's keys was seconds a poll on a long session
    return {'rev': hashlib.sha1(json.dumps(body, default=str).encode()).hexdigest()[:16], **body}


