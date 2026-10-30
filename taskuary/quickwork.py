"""Quick general work (spec 2026-10-29): a general task triage judged quick is answered in one call, not an agent session.

An agent session costs a launch and a long wait for what is often one sentence ("does it make sense to go on Friday?"). This module only
READS the depth - triage's difficulty, plus the things that always need the agent (a browser, a stranger, several emails owed, a task that
already ran deep). It never guesses from the words of the task.

THE DEPTH RULING (2026-10-29, after the replay found 93 of 140 recent tasks with no recorded difficulty and 30 'standard'): quick when triage
read the work as quick or standard or recorded nothing; the agent only for hard work, a browser, a stranger, several emails owed, a task that
already ran deep, and a routine. A quick call that finds it needs more escalates, so a wrong 'quick' costs one cheap call."""
import re, threading
from typing import NamedTuple
from loguru import logger
from . import brainroute, browserview, general, ingest, llm, origin, selfclose, slots

DEEP_WHY = ('kind', 'routine', 'hard', 'browser', 'stranger', 'emails', 'ran deep')
SETUP_REFS = (general.SETUP_REF, 'connector:setup')
NOT_RUNS = ('answered',)          # an answer is the owner's reply landing, not a run; owner and judge events carry their own Source


def _runs(store, tid) -> list: return [e for e in store.worker_events(tid) if e.get('Kind') not in NOT_RUNS and e.get('Source') not in ('owner', 'judge')]

def only_quick(store, tid) -> bool:
    "True when the task has run events and every one came from the quick path."
    rs = _runs(store, tid)
    return bool(rs) and all(e.get('Source') == 'quick' for e in rs)

def ran_deep(store, tid) -> bool:
    "A run that was not quick, or a conversation from before runs were recorded (general history, no run event)."
    rs = _runs(store, tid)
    return any(e.get('Source') != 'quick' for e in rs) if rs else bool(general.history(store, tid))

def why_deep(store, tid) -> str:
    "'' when this general task is answered in one call (quick), else why it takes the agent - one of DEEP_WHY."
    t = store.get_task(tid) or {}
    if not general.handles(t) or general.is_dock(t) or str(t.get('SourceRef') or '') in SETUP_REFS: return 'kind'
    if t.get('Source') == 'workflow': return 'routine'            # a routine runs on its own brain and definition (workflows.brain)
    if brainroute.judged(store, t)['difficulty'] == 'hard': return 'hard'
    if browserview.wanted(t) or ingest.triage_wants_browser(store, tid): return 'browser'
    if origin.of_task(store, tid)[0] == 'stranger': return 'stranger'
    if slots.all_(store, tid): return 'emails'
    if ran_deep(store, tid): return 'ran deep'
    return ''

def takes(store, tid) -> bool: return not why_deep(store, tid)


QUICK_TOKENS = 3_000
_STR = lambda null=False: {'type': ['string', 'null']} if null else {'type': 'string'}
QUICK_WANT = {'name': 'quick_work', 'schema': {'type': 'object', 'additionalProperties': False,
    'required': ['report', 'draft', 'question', 'done', 'escalate', 'why'],
    'properties': {'report': _STR(), 'draft': _STR(True), 'question': _STR(True), 'done': {'type': 'boolean'}, 'escalate': {'type': 'boolean'}, 'why': _STR()}}}
QUICK_LINE = ('QUICK WORK: answer in one go, as one JSON object with the fields report, draft, question, done, escalate, why - not as an agent session, and '
    'without the [[TASKUARY-...]] markers above; their jobs are fields here. report is what the owner reads (a few sentences). draft is the reply to send, '
    'or null. question is one question only the owner can answer, or null. done is true when nothing more is owed on this task, and why says in a line what finished it. '
    'Set escalate to true, with one line in why, when the job needs more than a lookup: acting anywhere, files to work through, booking, or multi-step research. '
    'A decision that is the owner\'s to make - spending, who goes, which option - is not a reason to escalate: give your recommendation in report, '
    'the draft built on it, and the decision in question with the options. '
    'Never claim an action you did not take. You have no mail search, no connectors and no files: when the answer depends on any of them, '
    'or on anything you cannot verify, set escalate rather than answer from memory. Never set done while a question is pending.')
NO_LOOKUP_LINE = 'THIS AI CANNOT LOOK ANYTHING UP. When the answer depends on a fact that must be checked, set escalate (why: what needs checking) rather than answer from memory.'
NO_CLOSE_LINE = 'DO NOT CLOSE THIS TASK: set done to false; the owner decides when it is finished.'


class QuickAnswer(NamedTuple):
    report: str; draft: str; question: str; done: bool; escalate: bool; why: str


def _clean(s) -> str:
    "A string field with Taskuary's own markers taken out (a model told about them may still write one)."
    from .selfclose import draft_markers, for_screen, reply_marker
    return _unmark(for_screen(draft_markers(reply_marker(str(s or ''))[0])[0]))

# the [[TASKUARY-...]] tags, and the two envelopes _file also acts on: the Hub's <TASKUARY-HUB>...</TASKUARY-HUB> with what it carries, and a bare
# TASKUARY-PROPOSE (proposals.MARK)
_TAG = re.compile(r'<\s*TASKUARY-HUB[^>]*>.*?<\s*/\s*TASKUARY-HUB[^>]*>|\[\[\s*/?\s*TASKUARY[^\]]*\]\]|<\s*/?\s*TASKUARY[^>]*>|TASKUARY-PROPOSE', re.I | re.S)
def _unmark(text) -> str:
    "Every Taskuary tag out: the fields are words for the owner, and only as_reply writes the markers _file acts on."
    return _TAG.sub('', str(text or '')).strip()

def read(data) -> 'QuickAnswer | None':
    "The structured answer, or None when it is not an object or says neither something nor that the job is too big. A pending question is never done."
    if not isinstance(data, dict): return None
    r, d, q = (_clean(data.get(k)) for k in ('report', 'draft', 'question'))
    a = QuickAnswer(r, d, q, data.get('done') is True and not q, data.get('escalate') is True, _clean(data.get('why')))
    return a if a.report or a.escalate else None

def as_reply(out: QuickAnswer) -> str:
    "The answer as the markers a general turn writes, so GeneralSession._file reads it exactly as it reads one."
    return '\n\n'.join(x for x in (out.report, out.draft and f'[[TASKUARY-REPLY]]{out.draft}[[/TASKUARY-REPLY]]',
                                   out.question and f'[[TASKUARY-ASK]] {out.question}', out.done and f"{selfclose.MARKER} {' '.join(out.why.split())}") if x)   # the close reads one line

def prompt(store, tid, ask: str, lookups: bool) -> tuple:
    "(system, user): what the general agent reads, the mail history it would have had searched for it, and the ask."
    system, user = general._prompt(store, tid)
    said, prior = general.history_brief(store, tid, False)
    if said: system = f'{system}\n\n{said}'
    if prior: user = f'{prior}\n\n{user}'
    system = f'{system}\n\n{QUICK_LINE}' + ('' if lookups else f'\n\n{NO_LOOKUP_LINE}')
    if selfclose.mode(store) == 'off' or selfclose.stays_open(store, tid): system += f'\n\n{NO_CLOSE_LINE}'
    return system, f'{user}\n\n{ask}'

def ask(store, tid, ask: str, steps: list = None, cancel=None) -> 'QuickAnswer | None':
    "The one call. Raises what the brain raises; None for an answer that cannot be read."
    trace = (lambda kind, name, detail: steps.append((kind, name, detail))) if steps is not None else None
    brain = llm.build_llm(store, job='quick_work', task_id=tid, research='web', gear='main', trace=trace, cancel=cancel)
    if brain is None: raise RuntimeError(f'{general.NO_AI} - connect one to answer this task')
    # what the brain BUILT can do (a failover's every brain): a CLI run on the web-only flags, or an API brain with the provider's web search
    web = bool(getattr(brain, 'takes_web', False))
    lookups = bool(getattr(brain, 'looks_up', web))
    system, user = prompt(store, tid, ask, lookups)
    with llm.watching(trace): got = llm.ask_json(brain, system, user, want=None if web else QUICK_WANT, max_tokens=QUICK_TOKENS, **({'web': True} if web else {}))
    return read(got.data)


QUICK_TIMEOUT = 180
QUICK_POOL = 8
POOL = threading.BoundedSemaphore(QUICK_POOL)       # apart from ingest.auto_sessions: a quick call is not a desk
ESCALATED = 'A quick look found this needs the agent: '
ESCALATE_BRIEF = 'A QUICK LOOK CAME FIRST: one call, which could not act, found this needs the agent - {why}. Take it from here.'
FOUND = 'What it found so far: '

def escalate(store, tid, ask: str, why: str, report: str = '') -> None:
    "The deep path, with the quick call's notes as its brief. The cap, the queue and the retry budget apply as to any deep start."
    store.add_comment(tid, 'router', 'agent', f'{ESCALATED}{why}')
    store.audit('task', tid, 'quick_escalated', 'router', 'agent', {'why': why})
    ask = ask.removeprefix(ingest.reply_job(store, tid)).strip()       # first_ask puts the reply job back in front of the brief
    note = ESCALATE_BRIEF.format(why=why.rstrip('.')) + (f'\n{FOUND}{report}' if report else '')
    ingest._auto_general(store, tid, f'{ask}\n\n{note}', deep=True)

RUNNING, _RUN_LOCK = set(), threading.Lock()      # tasks with a quick start in flight: a second start on one (two arrivals in a poll) makes no second call

def _call(store, tid, ask_: str, steps: list) -> tuple:
    "(the answer or None, why it failed or ''): the one call, holding a POOL slot only while it runs; the timeout counts the call, not the wait."
    cancel = threading.Event()
    try:
        with POOL:
            timer = threading.Timer(QUICK_TIMEOUT, cancel.set); timer.daemon = True; timer.start()
            try: return ask(store, tid, ask_, steps, cancel), ''
            finally: timer.cancel()
    except Exception as e: return None, f'the quick answer could not be made ({e})'

def _escalated(store, tid, q: str, out, failed: str) -> bool:
    "True, having handed the task to the deep path, when the call failed, could not be read or said it needs more."
    if out is not None and not out.escalate: return False
    escalate(store, tid, q, failed or ('the quick answer could not be read' if out is None else out.why or 'it needs more than one call'), out.report if out else '')
    return True

def start(store, tid, brief: str = None, as_owner: bool = True) -> str:
    """One call for a quick task, filed as a general turn - 'filed'; or the deep path, when the call says it needs more or fails - 'escalated';
    or 'failed', when the answer could not be filed: written on the task and counted on the retry budget, as _start_general does;
    or 'running', when a quick start is already in flight on this task. Never raises."""
    with _RUN_LOCK:
        if tid in RUNNING: return 'running'
        RUNNING.add(tid)
    # OPENING, as a carried-on turn holds it (ingest._continue_general): a line landing mid-call is passed in behind this one (_pass_general), never a second start
    general.OPENING.add(tid)
    try:
        q, steps = ingest.first_ask(store, tid, brief), []
        out, failed = _call(store, tid, q, steps)
        if _escalated(store, tid, q, out, failed): return 'escalated'
        ses = general.start_session(store, tid, actor='router'); ses.quick = True
        ses.file_quick(q, out, steps, as_owner, brief=True)      # the ask is Taskuary's, not the owner's (general.BRIEF_ACTOR)
        return 'filed'
    except Exception as e:
        logger.warning(f'quick answer could not be filed for task {tid}: {e}')
        try:
            from . import blackboard as bb
            bb.record_failure(store, tid, e, 'assistant', label='The assistant')
        except Exception as e2: logger.warning(f'the quick failure on task {tid} was not recorded: {e2}')
        return 'failed'
    finally:
        general.OPENING.discard(tid)
        with _RUN_LOCK: RUNNING.discard(tid)

def again(store, tid, session, turn: str) -> str:
    """More work on a task whose live session is quick: another one call, filed on that session as the next turn - 'filed' - or the deep
    path - 'escalated', whose start reuses this session (general.start_session returns session_for). Raises what filing raises."""
    steps = []
    out, failed = _call(store, tid, turn, steps)
    if _escalated(store, tid, turn, out, failed): return 'escalated'
    session.file_quick(turn, out, steps, as_owner=False)
    return 'filed'
