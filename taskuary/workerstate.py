"""One worker status model, fed by explicit events, read by every surface (PW-222, PW-226, PW-227, PW-137, PW-139, PW-141).

A session's status was read off its screen: a bare prompt meant "stopped and waiting on you", a quiet
terminal meant a question, and every consumer disagreed with the next. A worker's state is derived
here from explicit, persisted events - Working, Input needed (with the unanswered question), Approval
needed (with the specific pending action), Finished (an explicit result), Failed, Disconnected,
Stopped - keyed by task, run (session id) and request id, deduplicated, with events from a run that is
no longer the task's current one rejected. A response ending (`turn_end`) is not a finish: without an
explicit result or an open request the state is `unknown`, never a guessed hand raise. An answer is
bound to the exact outstanding request and run: delivered once, refused when resolved or when the run
changed, and written into the task's discussion with its delivery outcome.
"""
import hashlib, json, re, threading, time
from pathlib import Path
from loguru import logger
from .kinds import SHOWN, shown as shown_agent   # who the owner sees at work: Taskuary, never the profile (kinds.json `shown_`)

KINDS = ('working', 'turn_end', 'background', 'input_needed', 'approval_needed', 'stalled', 'answered', 'finished', 'failed', 'disconnected', 'stopped',
         'floor_denied')
# A NOTE on the run, not a state of it: the floor refused one call of a stranger's session (floor.py) and the agent carries on,
# so the run's state is still read off the event before it
NOTES = ('floor_denied',)
# A `stalled` request is a turn that DIED on a wall - a rate limit, a token ceiling, an API error - with the
# CLI alive at its prompt. On the screen that looks exactly like a question. It is not terminal (Claude can
# auto-resume; the owner can retry), so it is a request: open until the run speaks again (hooks.py).
REQUESTS = ('input_needed', 'approval_needed', 'stalled')
# `background` is a turn that ended with work still RUNNING - a shell, a monitor, a subagent (background.py) - its
# jobs in ChoicesJson, each with a deadline. Working while any is inside it; past them all it is a plain turn_end.
# A job ending wakes the run for a turn of its own: `working` with this text, which is not the owner speaking.
WAKE = 'woken by background work'
TERMINAL = ('failed', 'disconnected', 'stopped')
# ONE SENTENCE PER SUB-STATE of a blocked agent, from lanes.json (the desktop reads the same entry in
# funnelPile.js). Seven surfaces each spelled "parked at its prompt" their own way, and none of them
# could say "stuck on a rate limit" at all, because each composed its sentence from two booleans
# (the 2026-09-18 audit's top open item). The request's KIND picks the sentence; the booleans are
# the fallback for a run whose word is silent.
SAYS = next(l for l in json.loads((Path(__file__).parent / 'lanes.json').read_text(encoding='utf-8'))['lanes'] if l['key'] == 'blocked')['says']
_SUB = {'approval_needed': 'approval', 'stalled': 'stalled', 'input_needed': 'asking'}


def sub_state(waiting: bool = True, asking: bool = False, req: dict = None) -> str | None:
    """'asking' | 'approval' | 'stalled' | 'parked', or None when the agent is not waiting at all."""
    if req: return _SUB.get(str(req.get('kind') or ''), 'asking')
    return ('asking' if asking else 'parked') if waiting else None


def says(sub: str, agent: str = None, text: str = '') -> str:
    """The sentence for a sub-state: with the request's words when it has any."""
    s = SAYS.get(sub) or SAYS['parked']
    text = ' '.join(str(text or '').split())[:300]
    return (s['line'] if text and s.get('line') else s['bare']).format(agent=agent or SHOWN, text=text)


def request_id_for(text: str) -> str:
    """A stable id for a request whose producer gave none: the same question asked twice is one request."""
    return hashlib.sha1(' '.join(str(text or '').split()).lower().encode()).hexdigest()[:12]


def _live(tid: int):
    from . import terminal as term
    return next((x for x in list(term.SESSIONS.values()) if getattr(x, 'task_id', None) == tid and getattr(x, 'alive', False)), None)


LIVE_SESSION, OTHER_SESSION = 'the agent session on it is still open', 'another agent session on it is still open'

def live_work(store, tid: int, but=None, skip: tuple = ()) -> list:
    """Everything still working or live on this task, each in its words - [] when nothing is. THE ONE CHECK every AUTOMATIC close asks
    (the owner, 2026-11-01: "If anything still working never close the task automatically" - a Send closed a task whose agent sat at
    its prompt waiting on him). An agent waiting on the owner is live: its session is open. `but` is the session asking (an agent's own
    --done), never counted against itself; `skip` names work the caller IS ('routine', 'quick'). The owner's own Mark done never asks this."""
    from . import quickwork, terminal as term, workflows, writeup
    tid, out = int(tid), []
    if but is None: live = _live(tid)
    else: live = next((x for x in list(term.SESSIONS.values()) if getattr(x, 'task_id', None) == tid and getattr(x, 'alive', False) and str(x.sid) != str(but)), None)
    if live: out.append(OTHER_SESSION if but is not None else LIVE_SESSION)
    # ...a run row is a session's too: with `but` its own row is the asker's, so only a live pty speaks for another
    elif but is None and any(r.get('TaskId') == tid for r in store.running_runs()): out.append('an agent run on it is still going')
    with quickwork._RUN_LOCK: quick = tid in quickwork.RUNNING
    if quick and 'quick' not in skip: out.append('a quick answer is still being worked out on it')
    if writeup.running(tid) and not writeup.in_job(): out.append('its write-up is still being written')
    with workflows._LOCK: flowing = tid in workflows._STARTING
    if flowing and 'routine' not in skip: out.append('its routine is still running')
    if store.get_dispatch(tid): out.append('an agent is queued to start on it')
    return out


def current_sid(store, tid: int):
    """The run that owns the task now: its live session, else the newest run that ever reported."""
    s = _live(tid)
    if s: return str(s.sid)
    evs = store.worker_events(tid)
    return str(evs[-1]['Sid']) if evs else None


def record(store, tid: int, sid: str, kind: str, request_id: str = None, text: str = '', choices: list = None,
           source: str = 'api', event_id: str = None) -> bool:
    """One event. False when it is a replay (same event id), a duplicate open request, or from a run that
    is no longer the task's current one (PW-227)."""
    if kind not in KINDS: raise ValueError(f'unknown worker event: {kind}')
    if event_id and store.worker_event_exists(event_id): return False
    # a LIVE run owns the task: another run's word is stale and ignored. With no live run the newest run to
    # report is the task's current one (a restart, a headless worker) - its events are kept
    live = _live(tid)
    if live and str(sid) != str(live.sid) and kind not in TERMINAL:
        logger.debug(f'worker event from run {sid} ignored: task {tid} is with run {live.sid}')
        return False
    if kind in REQUESTS:
        request_id = request_id or request_id_for(text)
        if any(r['request_id'] == request_id for r in status(store, tid)['requests']): return False
    store.add_worker_event({'TaskId': tid, 'Sid': str(sid), 'Kind': kind, 'RequestId': request_id, 'Text': str(text or '')[:4000],
                            'ChoicesJson': json.dumps(list(choices)) if choices else None, 'Source': source, 'EventId': event_id})
    try: store._poke('task-changed', task_id=tid)
    except Exception: pass
    if kind == 'turn_end' or kind in TERMINAL:   # a batch close that waited for the turn (batch.close_if_settled)
        try:
            from . import batch
            batch.turn_ended(store, tid)
        except Exception as e: logger.debug(f'task {tid}: the turn end was not passed on - {e}')
    if kind == 'turn_end' or kind in REQUESTS:    # ...and its answer, or what it waits on, to the chats bound to it (agentchannels.py)
        try:
            from . import agentchannels
            agentchannels.on_event(store, tid, kind, text, source)
        except Exception as e: logger.debug(f'task {tid}: not said on its channel - {e}')
    return True


def background_jobs(e: dict) -> list:
    "the jobs of a `background` event still running now; [] for any other event"
    if not e or e.get('Kind') != 'background': return []
    from . import background
    try: return background.live(json.loads(e.get('ChoicesJson') or '[]'))
    except ValueError: return []


def events(store, tid: int, sid: str = None) -> list:
    return [e for e in store.worker_events(tid) if sid is None or str(e['Sid']) == str(sid)]


def open_requests(evs: list) -> list:
    """The requests still outstanding, oldest first.

    A question the owner has SPOKEN SINCE is not still being asked. `working` is the owner
    speaking - hooks.py records it on UserPromptSubmit - so a request from before their latest
    prompt has been overtaken by it, whether or not anyone wrote an `answered` event.

    Only the answer route writes one, and answering in the pane is the ordinary way to answer. So
    a single permission notification made a session read "stopped - waiting on you" for the rest
    of its life: TQ-0500 sat at the top of Work under that sentence while the agent was mid-search,
    twenty minutes and four prompts later (the owner, 2026-09-11: "when i input another prompt it
    does not pick up its coding again"). A request raised DURING the current turn still stands -
    it comes after that turn's own prompt.
    """
    answered = {e['RequestId'] for e in evs if e['Kind'] == 'answered'}
    spoke = max((i for i, e in enumerate(evs) if e['Kind'] == 'working' and e.get('Text') != WAKE), default=-1)
    return [e for i, e in enumerate(evs)
            if i > spoke and e['Kind'] in REQUESTS and e['RequestId'] not in answered]


def _public_request(e: dict) -> dict:
    try: choices = json.loads(e['ChoicesJson']) if e.get('ChoicesJson') else []
    except ValueError: choices = []
    # `source` travels with it because it changes what an ANSWER is: a request read off a chooser is
    # answered by picking, not by typing the option's words back at it (see `answer`)
    return {'request_id': e['RequestId'], 'kind': e['Kind'], 'text': e['Text'], 'choices': choices,
            'sid': e['Sid'], 'at': e['CreatedAt'], 'source': e.get('Source') or 'api'}


def reconcile_screen_request(store, t, asking: bool) -> dict | None:
    """Keep a request READ OFF THE SCREEN in step with the screen. Returns the open request, if any.

    A CLI that reports its questions leaves nothing for this to do. Claude, asking inside a turn,
    reports nothing at all - so its chooser had a question, four answers and no way to click any of
    them: the card could only say "waiting on you" and point at the pane (the owner, 2026-09-17).
    Recording it as an ordinary `input_needed` gives it what every other question has - the text, the
    options, and an id an answer binds to - and every surface then works unchanged.

    Both directions matter, and nothing else can keep this side of the books. Choosing an option in
    the pane submits no prompt and fires no hook, so no other event would ever close this request and
    the card would say "asked you" for the rest of the run. A chooser that has left the screen was
    answered in the pane - and a chooser REPLACED BY THE NEXT ONE was too, which is the ordinary
    shape of a walk through a plan: answer, next question, answer. The screen is what this request
    is, so the screen is what it follows.
    """
    from . import terminal as term
    tid, sid = getattr(t, 'task_id', None), str(getattr(t, 'sid', '') or '')
    if not tid or not sid: return None
    open_ = asking_of(store, t)
    mine = open_ if (open_ or {}).get('source') == 'screen' else None
    q = term.screen_question(t) if asking else None
    if mine and (not asking or (q and q['text'] and q['text'] != mine['text'])):
        record(store, int(tid), sid, 'answered', request_id=mine['request_id'], text='answered in the pane', source='screen')
        open_ = None
    if asking and not open_ and q and len(q['choices']) > 1:
        record(store, int(tid), sid, 'input_needed', text=q['text'] or 'Choose how to go on.',
               choices=q['choices'], source='screen')
        return asking_of(store, t)
    return open_


def status(store, tid: int) -> dict:
    """{state, requests, result, sid, live}. Derived, never guessed: no event and no request is `unknown`."""
    sid = current_sid(store, tid)
    live = _live(tid) is not None
    evs = events(store, tid, sid) if sid else []
    requests = [_public_request(e) for e in open_requests(evs)]
    # what the run SAID last - the Stop hook's last_assistant_message (hooks.py) - so a card with the screen
    # folded still shows what the agent is waiting on (the owner, 2026-09-23: "when it's closed you can't
    # see any of the questions")
    said = next((e['Text'] for e in reversed(evs) if e['Kind'] == 'turn_end' and e.get('Text')), '')
    out = {'sid': sid, 'live': live, 'requests': requests, 'result': None, 'state': 'unknown', 'said': said}
    evs = [e for e in evs if e['Kind'] not in NOTES]
    if not evs: return out
    last = evs[-1]
    if last['Kind'] in TERMINAL: out['state'] = last['Kind']; return out
    # a wall outranks any question: nothing can be answered through a rate limit
    if any(r['kind'] == 'stalled' for r in requests): out['state'] = 'stalled'; return out
    if any(r['kind'] == 'approval_needed' for r in requests): out['state'] = 'approval_needed'; return out
    if requests: out['state'] = 'input_needed'; return out
    # a finish counts until a new turn starts work again
    for e in reversed(evs):
        if e['Kind'] == 'finished': out['state'], out['result'] = 'finished', e['Text']; return out
        if e['Kind'] == 'working': break
    if not live: out['state'] = 'disconnected'; return out
    # the newest word decides: a prompt submitted is work in flight; an answer delivered is work resumed; a
    # response that merely ended is nothing anyone should act on (PW-226)
    jobs = background_jobs(last)
    if jobs: out['background'] = jobs
    out['state'] = 'working' if last['Kind'] in ('working', 'answered') or jobs else 'unknown'
    return out


ENDINGS = ('finished', *TERMINAL)


# A QUESTION THE AGENT ITSELF ASKED, as its run recorded it: its question tool's (q:<group>:<n>), a chooser read off its screen, an API
# agent's ask, or the model's read of the prose that ended its turn (hooks.judge_turn) - never the CLI's bare idle notice, which follows
# every quiet turn whether or not anything was asked. RESUMED is one of those carried onto the session a restart reopened (server.resume_asking):
# still the agent's question, and the mark that it was brought back once already
RESUMED = 'resumed'
def own_question(r: dict) -> bool:
    return r.get('kind') == 'input_needed' and bool(r.get('text')) and (r.get('source') in ('judge', 'screen', 'api', RESUMED) or bool(group_of(r.get('request_id'))))


def left_asking(store, tid) -> list:
    """The questions a run that is OVER was still asking the owner when it ended - cut off by a restart, its CLI gone, stopped - with no
    prompt of theirs since: [] while a session is live (its own pane asks) or when the run ended on no question of its own.

    A run that ends there is still waiting on the owner (the owner, 2026-11-03: "it's asking me question but the ai closed the agent why?"):
    an agent's "Ready to push to main - go ahead?" was cut off by an update's restart, and the page drew a finished run with nothing asking."""
    if not tid or _live(int(tid)): return []
    st = status(store, int(tid))
    return [r for r in st['requests'] if own_question(r)] if st['state'] in ('disconnected', 'stopped') else []


def newest(store, tid, evs=None, kinds=None, skip=()):
    """The task's newest event - of `kinds` only, none of `skip` - or None: off `evs` (its events, oldest first) when the caller holds
    them (taskstate.TaskState), else the one indexed row (store.last_worker_event). The same reading either way."""
    if evs is None: return store.last_worker_event(tid, kinds=kinds, skip=skip)
    return next((e for e in reversed(evs) if (not kinds or e['Kind'] in kinds) and e['Kind'] not in skip), None)


def ended(store, tid, live_too: bool = False, evs=None) -> str | None:
    """How the task's last run ENDED, by its own word, with nothing live on it: 'finished' (an explicit result no prompt has
    followed, as status reads it), 'failed', 'stopped' or 'disconnected' - else None: live, never reported, or silent on how it
    ended. Silence is never an ending here: a general conversation that answered and closed is a saved conversation, not a failure.

    THE ONE READING every surface takes of a run that is over (G7, 2026-10-20): the task list and the Board said "on you" or
    "waiting to start" over a run that failed, finished or was stopped, while the worker said so - taskstate and the rail read it here."""
    # `live_too`: the run's own last word even while its session is still open - a run that FAILED reads failed whatever the
    # session does (R2): a failed agent whose session stayed up read "waiting on you" on the phone (the 2026-10-22 re-walk)
    if not tid or (_live(tid) and not live_too): return None
    last = newest(store, tid, evs, skip=NOTES)
    if not last: return None
    if last['Kind'] in TERMINAL: return last['Kind']
    fin = newest(store, tid, evs, ('finished',))
    work = fin and newest(store, tid, evs, ('working',))
    return 'finished' if fin and (not work or work['Id'] < fin['Id']) else None


# QUESTIONS ASKED TOGETHER (the owner, 2026-09-28: a coding agent's three questions showed as one, and the answer was
# typed into the wrong question). One ask's questions share a stem - q:<group>:<n> - so every surface reads the group
# and answers it whole. The group is keyed on the questions themselves (hooks._group), so the three hooks that see the
# same AskUserQuestion (PreToolUse, PermissionRequest, PostToolUse) name the same requests and record() keeps one of each.
_QID = re.compile(r'^q:([0-9a-f]{10}):(\d+)$')


def group_key(key: str) -> str: return hashlib.sha1(str(key or '').encode('utf-8')).hexdigest()[:10]
def question_id(group: str, i: int) -> str: return f'q:{group}:{i}'


def group_of(request_id) -> str | None:
    m = _QID.match(str(request_id or ''))
    return m.group(1) if m else None


def group_requests(evs: list, group: str) -> list:
    """Every request of one group, open or answered, in the order they were asked."""
    got = {}
    for e in evs:
        if e['Kind'] in REQUESTS and group_of(e['RequestId']) == group: got.setdefault(e['RequestId'], e)
    return sorted(got.values(), key=lambda e: int(_QID.match(e['RequestId']).group(2)))


def question_group(store, t) -> list:
    """The questions of the newest open ask, in order, as public requests - one when it was asked alone."""
    tid, sid = getattr(t, 'task_id', None), str(getattr(t, 'sid', '') or '')
    if not tid or not sid: return []
    evs = events(store, tid, sid)
    open_ = open_requests(evs)
    if not open_: return []
    newest = open_[-1]
    g = group_of(newest['RequestId'])
    if not g: return [_public_request(newest)]
    ids = {e['RequestId'] for e in open_}
    return [_public_request(e) for e in group_requests(evs, g) if e['RequestId'] in ids]


# HELD: an ask a PreToolUse hook is holding open while the owner answers outside the terminal (hooks.ask). The hook
# waits on the event; answers land in `answers` as they come, and the event is set when every question has one - or
# when the owner lets the terminal have it (release), when the hook returns nothing and Claude draws its own form.
HELD = {}
_HELD_LOCK = threading.Lock()


def hold(tid: int, sid: str, group: str, rids: list) -> dict:
    with _HELD_LOCK:
        h = HELD[group] = {'tid': tid, 'sid': str(sid), 'rids': list(rids), 'answers': {}, 'released': False, 'event': threading.Event()}
    return h


# SET WHEN TASKUARY STOPS (desktop.Server). uvicorn waits for open requests BEFORE the lifespan shutdown that releases the
# holds (release_all), so a permit held for the owner held the process open with it (R26, the task 10 live check). Every wait
# watches this as well as its own event, and lets go the moment the server is told to exit.
STOP = threading.Event()
# ...and the server itself, so Quit in the browser (POST /api/quit) can tell it to exit. Here and not on desktop.Server: the exe runs
# desktop.py as __main__, a second copy of that module, and this one is shared by both (2026-10-25)
SERVER = [None]


def wait_held(group: str, seconds: float, step: float = 1.0) -> dict | None:
    """Block until the owner answers every question of the group; None on release, timeout or Taskuary stopping."""
    h = HELD.get(group)
    if not h: return None
    end = None if seconds is None else time.monotonic() + seconds
    while not h['event'].wait(step if end is None else max(0.0, min(step, end - time.monotonic()))):
        if STOP.is_set() or end is not None and time.monotonic() >= end: break
    with _HELD_LOCK: HELD.pop(group, None)
    return None if h['released'] or len(h['answers']) < len(h['rids']) else dict(h['answers'])


def held_for(tid: int) -> list:
    return [g for g, h in list(HELD.items()) if h['tid'] == tid]


def release(tid: int) -> bool:
    """The owner answers in the terminal instead: every ask held for this task lets go, and Claude shows its form."""
    got = False
    with _HELD_LOCK:
        for h in HELD.values():
            if h['tid'] == tid: h['released'] = True; h['event'].set(); got = True
    return got


def release_all() -> bool:
    """The app is closing: every held ask and permit lets go - a permit released is a refusal - so the threads holding
    them return and the process can exit."""
    with _HELD_LOCK:
        for h in HELD.values(): h['released'] = True; h['event'].set()
        return bool(HELD)


# WHOSE WORDS AN ANSWER IS (the agent walk, 2026-11-09). The waiting room's own notes - a press that went, a branch that landed - reach an
# agent parked on a question as the thing that lets the question go. They are Taskuary's, never the owner's: the note stood in their bubble
# ("You: The owner pressed Send on what you set up..."), went into the record the Advisor learns the owner's words from, and the press
# itself waited twelve seconds on the turn it began. Its writer is the room's 'router'; anyone else answering is the owner
def ours(actor) -> bool: return actor == 'router'
def said_by(actor) -> str: return 'taskuary' if ours(actor) else 'owner'
def _as(actor) -> dict: return {'brief': True} if ours(actor) else {}
def _brief(sess, text):
    "Taskuary's note as a chat agent's next turn, on its own thread: nobody who pressed a button waits for the turn that follows."
    def go():
        try: sess.send_prompt(text, brief=True)
        except Exception as e: logger.warning(f"task {getattr(sess, 'task_id', '?')}: Taskuary's note did not reach its agent - {e}")
    threading.Thread(target=go, daemon=True, name='brief').start()


def _answer_held(store, tid, h, answers: dict, actor) -> dict:
    """Answers for a held ask: kept until every question has one, then the hook is let go with all of them."""
    with _HELD_LOCK:
        for rid, text in answers.items():
            if rid in h['rids']: h['answers'][rid] = text
        done = len(h['answers']) >= len(h['rids'])
    for rid, text in answers.items():
        if rid in h['rids']: record(store, tid, h['sid'], 'answered', request_id=rid, text=text, source=said_by(actor))
    if done:
        h['event'].set()
        store.add_comment(tid, actor, 'human', 'Answered the agent: ' + '; '.join(h['answers'][r] for r in h['rids']) + ' - delivered with its question.')
        store.audit('task', tid, 'worker_answer', actor, detail={'request_ids': h['rids'], 'sid': h['sid'], 'path': 'hook'})
    return {'delivered': True, 'state': 'delivered' if done else 'noted', 'sid': h['sid'], 'path': 'hook',
            'left': 0 if done else len(h['rids']) - len(h['answers'])}


def _stranger_held(store, tid, rids=()) -> dict:
    """An answer refused because the task turned a stranger's under a full session (terminal.stranger_now) - a hook's held ask included:
    letting it go is the agent's next step with full tools. {} when the answer may go.
    A PERMIT is no relay: Allow/Deny is the owner's own ruling on the one tool call its card shows and puts no words in the session,
    so answers to permits only always go - held, a stranger's pane sat on its permit with no way left to refuse it."""
    from . import terminal as term
    if rids:
        kinds = {e['RequestId']: e['Kind'] for e in events(store, tid) if e['Kind'] in REQUESTS}
        if all(kinds.get(r) == 'approval_needed' for r in rids): return {}
    why = term.stranger_now(store, tid)
    return {'delivered': False, 'state': 'held_stranger', 'why': why} if why else {}


def answer_group(store, tid: int, answers: dict, actor: str = 'owner') -> dict:
    """ALL the answers to one ask, together (request_id -> words). Held by a hook: handed to it. A general agent: one
    message naming each question. A pane standing on Claude's form: its keys, as measured (terminal.answer_form).
    Anything else: each answer on its own road."""
    answers = {str(k): ' '.join(str(v or '').split()) for k, v in (answers or {}).items() if str(v or '').strip()}
    if not answers: raise ValueError('say something')
    if (held := _stranger_held(store, tid, list(answers))): return held
    groups = {group_of(r) for r in answers}
    for g in groups:
        h = HELD.get(g) if g else None
        if h and h['tid'] == tid: return _answer_held(store, tid, h, answers, actor)
    sess = _live(tid)
    evs = events(store, tid)
    open_ids = {e['RequestId'] for e in open_requests(evs)}
    reqs = [_public_request(e) for e in evs if e['Kind'] in REQUESTS and e['RequestId'] in answers and e['RequestId'] in open_ids]
    reqs = list({r['request_id']: r for r in reqs}.values())
    if not reqs: return {'delivered': False, 'state': 'resolved', 'why': 'those questions are no longer outstanding'}
    if not sess: return {'delivered': False, 'state': 'disconnected', 'why': 'no live worker on this task'}
    if any(str(sess.sid) != str(r['sid']) for r in reqs):
        return {'delivered': False, 'state': 'stale', 'why': 'the run that asked is no longer the one on the task'}
    if len(reqs) == 1: return answer(store, tid, reqs[0]['request_id'], answers[reqs[0]['request_id']], actor)
    reqs.sort(key=lambda r: int(_QID.match(r['request_id']).group(2)) if _QID.match(r['request_id']) else 0)
    from . import terminal as term
    try:
        said = '\n'.join(f"{i}. {r['text']} - {answers[r['request_id']]}" for i, r in enumerate(reqs, 1))
        if hasattr(sess, 'send_prompt'): _brief(sess, said) if ours(actor) else sess.send_prompt(said)
        elif getattr(sess, 'cli', '') == 'codex':
            # codex asked in words: its answers are its next turn, through its own queue (typed only if that refuses)
            if not term.queue_codex(sess, said): term.type_into(sess, said, **_as(actor))
        elif all(r.get('choices') for r in reqs) and all(r.get('source') == 'hook' for r in reqs):
            term.answer_form(sess, [(r.get('choices') or [], answers[r['request_id']]) for r in reqs])
        else:
            return {'delivered': all(answer(store, tid, r['request_id'], answers[r['request_id']], actor).get('delivered') for r in reqs),
                    'state': 'delivered', 'sid': sess.sid}
    except Exception as e:
        store.add_comment(tid, actor, 'human', f'Answers could not be delivered to the agent: {str(e)[:200]}')
        return {'delivered': False, 'state': 'failed', 'why': str(e)[:200]}
    for r in reqs: record(store, tid, sess.sid, 'answered', request_id=r['request_id'], text=answers[r['request_id']], source=said_by(actor))
    store.add_comment(tid, actor, 'human', 'Answered the agent: ' + '; '.join(f"{r['text'][:80]} - {answers[r['request_id']][:200]}" for r in reqs)
                      + f' - delivered (run {sess.sid}).')
    store.audit('task', tid, 'worker_answer', actor, detail={'request_ids': [r['request_id'] for r in reqs], 'sid': sess.sid})
    return {'delivered': True, 'state': 'delivered', 'sid': sess.sid}


_NUMBERED = re.compile(r'(?:^|[\n,;])\s*(\d{1,2})\s*[:.)\-]?\s+([^\n,;]+)')


def split_answers(text: str, qs: list) -> dict:
    """The owner's one line for several questions (a chat's answer): "1 main, 2 raise the cap" goes to each by its
    number - the numbers are the ones WE put on the questions. Anything unnumbered is the whole line, for each."""
    words = ' '.join(str(text or '').split())
    got = {}
    for n, said in _NUMBERED.findall(str(text or '')):
        i = int(n) - 1
        if 0 <= i < len(qs): got[qs[i]['request_id']] = said.strip()
    return {q['request_id']: got.get(q['request_id'], words) for q in qs}


def answer(store, tid: int, request_id: str, text: str, actor: str = 'owner', owner: str = None, press: bool = False) -> dict:
    """Deliver the owner's answer to ONE outstanding request of the run that asked it (PW-139/141): once,
    to that run, and say what happened - delivered, resolved already, stale (the run changed),
    disconnected (no live worker: open the workspace), or failed. `press`: the Done on the browser view for a step handed to the owner
    on the page - their press, with no words of theirs (browsergate.done)."""
    from . import browsergate, browserview, terminal as term
    text, press = ' '.join(str(text or '').split()), press and str(request_id).startswith(browserview.TURN_PREFIX)
    if not text and not press: raise ValueError('say something')
    if (held := _stranger_held(store, tid, [request_id])): return held
    # the request is looked up across every run of the task: one that belongs to a run that is no longer the
    # task's is STALE, not silently forwarded to whatever worker has the task now (PW-139)
    evs = events(store, tid)
    answered = {e['RequestId'] for e in evs if e['Kind'] == 'answered'}
    asked = next((_public_request(e) for e in reversed(evs) if e['Kind'] in REQUESTS and e['RequestId'] == request_id), None)
    if not asked or request_id in answered: return {'delivered': False, 'state': 'resolved', 'why': 'that request is no longer outstanding'}
    req = asked
    h = HELD.get(group_of(request_id) or '')
    if h and h['tid'] == tid: return _answer_held(store, tid, h, {request_id: text}, actor)
    sess = _live(tid)
    # THE VIEW'S DONE closes the hand-over and Taskuary tells the agent - the one that asked, or none running (it is started on it). A
    # different run on the task is never handed it: stale, below
    if press and (not sess or str(sess.sid) == str(req['sid'])):
        return ({'delivered': True, 'state': 'delivered'} if browsergate.done(store, tid, request_id)
                else {'delivered': False, 'state': 'resolved', 'why': 'that request is no longer outstanding'})
    text = text or browserview.TURN_DONE
    if not sess:
        store.add_comment(tid, actor, 'human', f'Answer to "{req["text"][:160]}": {text[:500]} - could not be delivered: no live worker on this task. Open the workspace to continue.')
        return {'delivered': False, 'state': 'disconnected', 'why': 'no live worker on this task'}
    if str(sess.sid) != str(req['sid']):
        store.add_comment(tid, actor, 'human', f'Answer to "{req["text"][:160]}": {text[:500]} - not delivered: the run that asked ({req["sid"]}) is gone and a different worker has the task.')
        return {'delivered': False, 'state': 'stale', 'why': 'the run that asked is no longer the one on the task'}
    who = getattr(sess, 'agent', None) or getattr(sess, 'label', None) or 'the agent'
    # a sign-in's "Signed in" is told as a fill's is - the site and "continue" - on a chat or a terminal alike (signin.signed_in)
    from . import signin
    if signin.said_done(request_id, text): return signin.signed_in(store, tid, request_id)
    # A CHOOSER IS ANSWERED BY ITS NUMBER. A request read off the screen belongs to a list the pane
    # is standing on, where the option's own words are not an answer at all - they would land in
    # whatever "type something" field the list offers last. The owner's words stay the owner's words
    # everywhere they are READ (the comment below, the audit); only the keystroke changes.
    send = text
    # ...and a press handed over on the page, answered in words: the agent hears that it was not pressed (browsergate.owner_said). A chat
    # hears it from its own send_prompt, which every owner word to it passes through
    if str(request_id).startswith(browsergate.PRESS) and not hasattr(sess, 'send_prompt'):
        if (note := browsergate.owner_said(store, tid, req['sid'], text)): send = f'{text} ({note})'     # one line: a newline typed into a CLI's prompt is its Enter
    # a codex question asked in WORDS is answered through its own queue - a chooser or an approval is still a keystroke
    words = req['kind'] == 'input_needed' and req.get('source') != 'screen' and (not req.get('choices') or _cli(sess) == 'codex')
    # ...and so is a HOOK's chooser once its hold ran out and Claude drew the form (B12, the owner, 2026-10-11): its label
    # typed + Enter submitted whichever option was highlighted, and the log said "delivered". An approval reports no
    # options, so they are read off the pane; where none can be read the words go as they always did.
    opts = None if hasattr(sess, 'send_prompt') or words else (req.get('choices') or (_on_screen(sess) if req['kind'] == 'approval_needed' else None))
    if opts:
        pick = pick_of(opts, text)
        if not pick:
            return {'delivered': False, 'state': 'not_a_choice', 'choices': opts,
                    'why': f'{who} is waiting on a pick - say one of: ' + '; '.join(f'{i}. {c}' for i, c in enumerate(opts, 1))
                           + ' - or answer it in the terminal'}
        send = str(pick)
    try:
        # ...a chat is handed the owner's own words, with what the Assistant added to them folded as Taskuary's (general.say_relayed)
        if hasattr(sess, 'send_prompt'):
            from . import general
            if ours(actor): _brief(sess, send)
            else: general.say_relayed(sess, owner or send, send) if owner else sess.send_prompt(send)
        elif words and term.queue_codex(sess, send):
            if ours(actor):
                from . import sessionrecord
                sessionrecord.keep_seed(tid, send)          # its `you` step in the record reads as Taskuary's brief (mark_briefs)
        else: term.type_into(sess, send, **_as(actor))
    except Exception as e:
        store.add_comment(tid, actor, 'human', f'Answer to "{req["text"][:160]}": {text[:500]} - could not be delivered to {who}: {str(e)[:200]}')
        return {'delivered': False, 'state': 'failed', 'why': str(e)[:200]}
    words = ' '.join(str(owner or text).split())          # the record reads what the owner said, not the Assistant's version
    record(store, tid, sess.sid, 'answered', request_id=request_id, text=words, source=said_by(actor))
    store.add_comment(tid, actor, 'human', f'Told {who} (run {sess.sid}), which was asking "{req["text"][:160]}": {words[:500]}' if ours(actor) else
                      f'Answered "{req["text"][:160]}": {words[:500]} - delivered to {who} (run {sess.sid}).')
    store.audit('task', tid, 'worker_answer', actor, detail={'request_id': request_id, 'sid': sess.sid})
    return {'delivered': True, 'state': 'delivered', 'sid': sess.sid}


def _cli(sess) -> str:
    from . import terminal as term
    return getattr(sess, 'cli', '') or term.cli_of(getattr(sess, 'argv', None))


def _on_screen(sess) -> list:
    """The options of the chooser the pane is standing on - [] when it is not offering one (or cannot be read)."""
    from . import terminal as term
    try: return (term.screen_question(sess) or {}).get('choices') or []
    except Exception: return []


def pick_of(choices: list, text: str) -> int | None:
    """The option the owner's words NAME, 1-based: its number, its whole label, or the label's lead before its first comma
    or bracket ("No" for "No, and tell Claude what to do differently (esc)") - the lowest such option. The words are matched
    against the agent's OWN options, never read for intent: "no, don't delete that" names none of them and gets None."""
    said = ' '.join(str(text or '').split()).strip().rstrip('.!').lower()
    cs = [' '.join(str(c).split()).lower() for c in choices or []]
    if said.isdigit() and 1 <= int(said) <= len(cs): return int(said)
    lead = lambda c: re.split(r'[,(]', c, 1)[0].strip()
    return next((i for i, c in enumerate(cs, 1) if c == said), None) or next((i for i, c in enumerate(cs, 1) if said and lead(c) == said), None)


def delivery_path(sess) -> str | None:
    """The integration's own reply road (PW-140): an API session takes a prompt, a pty is typed into;
    None means there is nothing to deliver to - open the workspace."""
    if not sess or not getattr(sess, 'alive', False): return None
    return 'api' if hasattr(sess, 'send_prompt') else 'pty'


def answer_open(store, tid: int, text: str, actor: str = 'owner', owner: str = None) -> dict:
    """The chat's answer, bound to the newest open request of the run that has the task - an approval first
    (PW-138). No open request from a live run is `no_request`: the caller's waiting room takes the words."""
    sess = _live(tid)
    req = asking_of(store, sess) if sess else None
    if not req: return {'delivered': False, 'state': 'no_request', 'why': 'no open request from a live run'}
    qs = question_group(store, sess)
    # ...and Taskuary's note is never split over a group of questions as if it answered each: it is told once, to the one that is showing
    if len(qs) > 1 and req.get('kind') != 'approval_needed' and not ours(actor):
        return {**answer_group(store, tid, split_answers(text, qs), actor), 'path': delivery_path(sess), 'request_id': qs[0]['request_id']}
    return {**answer(store, tid, req['request_id'], text, actor, owner=owner), 'path': delivery_path(sess), 'request_id': req['request_id']}


def waiting_of(store, t):
    """Is this session waiting on the owner, by ITS OWN WORD? True when a request of its is open, False
    while it says it is working; None when its word is SILENT on the question, so the caller falls back
    to the screen (PW-228).

    Silence is not a no. A response that merely ended (`turn_end`) says the run stopped talking and
    nothing about who the ball is with - and reading that as "definitely not waiting" locked every
    surface into `working` for as long as a finished pane stayed open (the wall, 2026-09-10). Only a
    run with work in flight - a prompt submitted, an answer delivered - denies the hand raise.
    """
    tid, sid = getattr(t, 'task_id', None), str(getattr(t, 'sid', '') or '')
    if not tid or not sid: return None
    evs = events(store, tid, sid)
    if not evs: return None
    if open_requests(evs): return True
    return False if evs[-1]['Kind'] in ('working', 'answered') or background_jobs(evs[-1]) else None


def asking_of(store, t):
    """The newest open request of this session - what to show and what an answer is bound to - or None."""
    tid, sid = getattr(t, 'task_id', None), str(getattr(t, 'sid', '') or '')
    if not tid or not sid: return None
    evs = events(store, tid, sid)
    open_ = open_requests(evs)
    if not open_: return None
    approvals = [e for e in open_ if e['Kind'] == 'approval_needed']
    return _public_request(approvals[-1]) if approvals else shown_ask([_public_request(e) for e in open_])


def shown_ask(reqs: list) -> dict | None:
    """The ask to SHOW of these open requests (public, oldest first): the newest one - or, when that turn asked several, its FIRST question
    with "(+N more)" and every one in `questions`. The rail and the chip held only the last of four, and "where from?" was hidden behind
    "any airline?" (agent-flow audit, 2026-11-07). What an answer binds to is the whole set either way (answer_open, question_group)."""
    if not reqs: return None
    g = group_of(reqs[-1]['request_id'])
    grp = [r for r in reqs if g and group_of(r['request_id']) == g] or reqs[-1:]
    one = grp[0]
    return one if len(grp) < 2 else {**one, 'text': f"{one['text']} (+{len(grp) - 1} more)", 'questions': [r['text'] for r in grp]}


def request_line(agent: str, req: dict) -> str:
    """One sentence for a raised hand, from the request itself."""
    return says(sub_state(req=req), agent, req.get('text'))
