"""Quick general work (spec 2026-10-29; with tools since 2026-11-13): a general task triage judged quick or normal is worked by the warm
agent - a turn of the task's own session, with its tools, on the quick_work job and a fraction of a desk - not the full agent's start.

This module only READS the depth - triage's difficulty, plus the things that always need the full agent (a browser, a stranger, several
emails owed, a task that already ran deep). It never guesses from the words of the task.

THE DEPTH RULING (2026-10-29, after the replay found 93 of 140 recent tasks with no recorded difficulty and 30 'standard'; the owner again,
2026-11-13: "only complex things" go to the full agent): quick when triage read the work as quick or standard or recorded nothing; the full
agent for hard work, a browser, a stranger, several emails owed, a task that already ran deep, coding, and a routine. A warm turn that finds
it needs more hands on itself (HAND_ON), so a wrong 'quick' costs one turn, whose notes the full agent starts from."""
import json, re, threading
from loguru import logger
from . import agents, brainroute, browserview, general, ingest, origin, slots, workerstate

DEEP_WHY = ('kind', 'routine', 'hard', 'browser', 'stranger', 'emails', 'ran deep')
SETUP_REFS = (general.SETUP_REF, 'connector:setup')
NOT_RUNS = ('answered',)          # an answer is the owner's reply landing, not a run; the owner's events carry their own Source


def _runs(store, tid) -> list: return [e for e in store.worker_events(tid) if e.get('Kind') not in NOT_RUNS and e.get('Source') not in ('owner', workerstate.READ_OFF_PROSE)]

def only_quick(store, tid) -> bool:
    "True when the task has run events and every one came from the quick path."
    rs = _runs(store, tid)
    return bool(rs) and all(e.get('Source') == 'quick' for e in rs)

def ran_deep(store, tid) -> bool:
    "A run that was not quick, or a conversation from before runs were recorded (general history, no run event)."
    rs = _runs(store, tid)
    return any(e.get('Source') != 'quick' for e in rs) if rs else bool(general.history(store, tid))

def why_deep(store, tid) -> str:
    "'' when the warm agent works this general task (quick or normal work), else why it takes the full agent - one of DEEP_WHY."
    t = store.get_task(tid) or {}
    # ...and a CODING task on an AI card is a coding session's, never the warm agent's, though its session is this module's (general.ON_CARD)
    if not general.handles(t) or general.is_dock(t) or str(t.get('SourceRef') or '') in SETUP_REFS or str(t.get('Kind') or '').lower() in agents.CODING_KINDS: return 'kind'
    if t.get('Source') == 'workflow': return 'routine'            # a routine runs on its own brain and definition (workflows.brain)
    if brainroute.judged(store, t)['difficulty'] == 'hard': return 'hard'
    if browserview.wanted(t) or ingest.triage_wants_browser(store, tid): return 'browser'
    if origin.of_task(store, tid)[0] == 'stranger': return 'stranger'
    if slots.all_(store, tid): return 'emails'
    # ...his own lines waiting on it (typed while its sender was held) are no reason any more: the warm turn takes them, as any turn does
    # (GeneralSession.send_prompt, take_kept) - the tool-less call that could not was what sent them to the agent (2026-11-11)
    return 'ran deep' if ran_deep(store, tid) else ''

def takes(store, tid) -> bool: return not why_deep(store, tid)


# THE QUICK LANE IS THE AGENT, WITH ITS TOOLS (the owner, 2026-11-13: "that warm agent should be open for all the easy tasks and reply only
# tasks and they should have tools"): one tool-less call could not open the screenshot, the attachment, the code or the owner's systems -
# 16 of 20 handed on, each then paying a full agent's start. Quick and normal work is now a turn of the task's own session, with every
# tool, floor and stranger gate an agent's turn has (GeneralSession.send_prompt), routed as quick_work and holding a fraction of a desk.
# The warm agent itself says when the work needs the full agent - by the marker, which Taskuary acts on (handed_on, escalate)
HAND_ON = '[[TASKUARY-FULL-AGENT]]'
WARM_LINE = (f"YOU ARE THE QUICK AGENT on this task: do it here with your tools when it is a lookup, an answer or a reply - a decision that "
             f"is the owner's is a question for them, not a reason to hand on. Where it needs the full agent (a browser, a long build, many steps "
             f"across systems), write {HAND_ON} and one line saying why, after what you found so far, and stop.")
_HAND = re.compile(r'\[\[\s*TASKUARY-FULL-AGENT\s*\]\][ \t]*([^\n]*)', re.I)

def handed_on(reply) -> tuple:
    "(the reply without the marker, why the warm agent hands the work on - '' when it does not). A turn that said nothing else says that."
    m = _HAND.search(str(reply or ''))
    if not m: return reply, ''
    why, rest = ' '.join(m.group(1).split()).rstrip('.') or 'it needs more than a quick turn', _HAND.sub('', reply).strip()
    return rest or f'{ESCALATED}{why}.', why


def _clean(s) -> str:
    "A string field with Taskuary's own markers taken out (a model told about them may still write one)."
    from .selfclose import draft_markers, for_screen, reply_marker
    return _unmark(for_screen(draft_markers(reply_marker(str(s or ''))[0])[0]))

# the [[TASKUARY-...]] tags, and the two envelopes _file also acts on: the Hub's <TASKUARY-HUB>...</TASKUARY-HUB> with what it carries, and a bare
# TASKUARY-PROPOSE (proposals.MARK)
_TAG = re.compile(r'<\s*TASKUARY-HUB[^>]*>.*?<\s*/\s*TASKUARY-HUB[^>]*>|\[\[\s*/?\s*TASKUARY[^\]]*\]\]|<\s*/?\s*TASKUARY[^>]*>|TASKUARY-PROPOSE', re.I | re.S)
def _unmark(text) -> str:
    "Every Taskuary tag out: a stored field is words for the owner."
    return _TAG.sub('', str(text or '')).strip()

# A TURN STORED AS THE ONE CALL'S RAW OBJECT (until 2026-11-13 a quick answer was one JSON object, and a few were filed whole, fenced or cut
# short - the owner, 2026-11-03): it reads back as the report it holds, wherever the chat is read (general._split, sessionrecord)
RAW = re.compile(r'^\s*(?:```(?:json)?\s*)?\{\s*"(?:report|draft|question|done|escalate|why)"\s*:', re.I)
def is_raw(text) -> bool: return bool(RAW.match(str(text or '')))

_REPORT = re.compile(r'"report"\s*:\s*"((?:[^"\\]|\\.)*)', re.S)
def report_of(text) -> str:
    "The report a raw quick answer holds - or the text as it is, when it is not one."
    t = str(text or '')
    if not is_raw(t): return t
    body = re.sub(r'^\s*```(?:json)?\s*|\s*```\s*$', '', t)
    try: d = json.loads(body)
    except ValueError: d = None
    if isinstance(d, dict) and d.get('report'): return _clean(d['report'])
    m = _REPORT.search(body)                       # cut short: the report as far as it got, its last escape whole or dropped
    if not m: return ''
    try: return _clean(json.loads('"' + re.sub(r'\\u?[0-9a-fA-F]{0,3}$|\\$', '', m.group(1)) + '"'))
    except ValueError: return _clean(m.group(1).replace('\\n', '\n'))


# A QUICK TURN IS A FRACTION OF A DESK (the owner, 2026-10-30: "5 of them are one or something like that"): it takes a slot only while
# ingest.has_room has 1/light_per_agent to spare, so quick work and agent sessions share the one "Agents at once" width. It never holds a
# desk of its own (blackboard.live_count skips quick sessions); a turn in flight is counted here, from taking its slot to giving it back.
GATE, WAIT_POLL = threading.Condition(), 2.0     # sessions ending and subagents finishing do not notify the gate, so a waiter looks again
_IN_FLIGHT = 0

def in_flight() -> int: return _IN_FLIGHT

def _fits(store) -> bool:
    per = ingest.light_per_agent(store)
    return _IN_FLIGHT < ingest.auto_sessions(store) * per and ingest.has_room(store, 1 / per)   # the first is the hard ceiling, whatever the load reads

def _take(store, tid) -> None:
    "Wait for room, then hold a quick slot."
    global _IN_FLIGHT
    with GATE:
        if not _fits(store):
            store.add_comment(tid, 'router', 'agent', f'Waiting its turn: {ingest.busy_words(store)}, and the quick answer comes when there is room.')
            while not _fits(store): GATE.wait(WAIT_POLL)
        _IN_FLIGHT += 1

def _give(store) -> None:
    global _IN_FLIGHT
    with GATE: _IN_FLIGHT -= 1; GATE.notify_all()
    try:
        from . import blackboard as bb
        if store.queued_dispatches(): bb.drain_later(store, 0)      # a queued agent may fit now; never on this thread, which the drain could hold
    except Exception as e: logger.debug(f'no drain after a quick turn: {e}')
ESCALATED = 'This needs the full agent: '
ESCALATE_BRIEF = 'THE QUICK AGENT CAME FIRST and found this needs the full agent - {why}. What it did and found is in the conversation above. Take it from here.'

def escalate(store, tid, ask: str, why: str, said: bool = False) -> None:
    "The deep path, on the same session, the warm turn's notes in its conversation. The cap, the queue and the retry budget apply as to any deep start."
    if not said: store.add_comment(tid, 'router', 'agent', f'{ESCALATED}{why}')       # `said`: the warm turn's own words already say it
    store.audit('task', tid, 'quick_escalated', 'router', 'agent', {'why': why})
    ask = ask.removeprefix(ingest.reply_job(store, tid)).strip()       # first_ask puts the reply job back in front of the brief
    ingest._auto_general(store, tid, f"{ask}\n\n{ESCALATE_BRIEF.format(why=why.rstrip('.'))}", deep=True)

RUNNING, _RUN_LOCK = set(), threading.Lock()      # tasks with a quick start in flight: a second start on one (two arrivals in a poll) makes no second turn

def again(store, tid, session, turn: str, **kw) -> str:
    """The warm agent's turn on a quick session: filed as its turn - 'filed' - or handed to the full agent when it says the work needs it -
    'escalated', whose start reuses this session (general.start_session returns session_for). Holds a quick slot while it runs.
    `kw`: send_prompt's (brief - Taskuary's words unless the owner typed them - and mails). Raises what the turn raises."""
    # ...AT WORK FROM THE MOMENT IT IS ASKED, as any start is (recorded on the real CLI, 2026-11-13: the sender wrote again, and while the
    # answer was made the chat stood on her message with nothing at work and the header at rest)
    general.OPENING.add(tid)
    try:
        _take(store, tid)
        try: said = session.send_prompt(turn, **{'brief': True, **kw}, quick=True, delivery_instructions=WARM_LINE)
        finally: _give(store)
    finally: general.OPENING.discard(tid)
    why = getattr(session, 'handed_on', '')
    if not (isinstance(why, str) and why): return 'filed'
    session.handed_on = ''
    escalate(store, tid, turn, why, said=str(said or '').startswith(ESCALATED))
    return 'escalated'

def start(store, tid, brief: str = None, **pick) -> str:
    """The warm agent on a quick task, its turn filed as a general turn - 'filed'; or the full agent, when the turn hands it on - 'escalated';
    or 'failed', when the turn failed: written on the task and counted on the retry budget, as _start_general does;
    or 'running', when a quick start is already in flight on this task. `pick`: the owner's choice of AI (model=, pick=). Never raises."""
    with _RUN_LOCK:
        if tid in RUNNING: return 'running'
        RUNNING.add(tid)
    # OPENING, as a carried-on turn holds it (ingest._continue_general): a line landing mid-turn is passed in behind this one (_pass_general), never a second start
    general.OPENING.add(tid)
    try:
        ses = general.start_session(store, tid, actor='router', quick=True, **pick)        # quick from birth: never a desk, even for an instant
        return again(store, tid, ses, ingest.first_ask(store, tid, brief))        # the ask is Taskuary's, not the owner's (general.BRIEF_ACTOR)
    except Exception as e:
        if isinstance(e, general.Stopped): return 'filed'          # the owner stopped it: nothing failed, and nothing starts it again
        logger.warning(f'the quick agent could not take task {tid}: {e}')
        try:
            from . import blackboard as bb
            bb.record_failure(store, tid, e, 'assistant', label='The assistant')
        except Exception as e2: logger.warning(f'the quick failure on task {tid} was not recorded: {e2}')
        return 'failed'
    finally:
        general.OPENING.discard(tid)
        with _RUN_LOCK: RUNNING.discard(tid)
