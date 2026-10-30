"""Quick general work (spec 2026-10-29): a general task triage judged quick is answered in one call, not an agent session.

An agent session costs a launch and a long wait for what is often one sentence ("does it make sense to go on Friday?"). This module only
READS the depth - triage's difficulty, plus the things that always need the agent (a browser, a stranger, several emails owed, a task that
already ran deep). It never guesses from the words of the task."""
import re, threading
from typing import NamedTuple
from loguru import logger
from . import brainroute, browserview, general, ingest, llm, origin, selfclose, slots

DEEP_WHY = ('kind', 'difficulty', 'browser', 'stranger', 'emails', 'ran deep')
SETUP_REFS = (general.SETUP_REF, 'connector:setup')
NOT_RUNS = ('answered',)          # an answer is the owner's reply landing, not a run; owner and judge events carry their own Source


def _runs(store, tid) -> list: return [e for e in store.worker_events(tid) if e.get('Kind') not in NOT_RUNS and e.get('Source') not in ('owner', 'judge')]

def only_quick(store, tid) -> bool:
    "True when the task has worker events and every run event came from the quick path."
    evs = store.worker_events(tid)
    return bool(evs) and all(e.get('Source') == 'quick' for e in _runs(store, tid))

def why_deep(store, tid) -> str:
    "'' when this general task is answered in one call (quick), else why it takes the agent - one of DEEP_WHY."
    t = store.get_task(tid) or {}
    if not general.handles(t) or general.is_dock(t) or str(t.get('SourceRef') or '') in SETUP_REFS: return 'kind'
    if brainroute.judged(store, t)['difficulty'] != 'quick': return 'difficulty'
    if browserview.wanted(t) or ingest.triage_wants_browser(store, tid): return 'browser'
    if origin.of_task(store, tid)[0] == 'stranger': return 'stranger'
    if slots.all_(store, tid): return 'emails'
    if store.worker_events(tid) and not only_quick(store, tid): return 'ran deep'
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
    'Never claim an action you did not take.')
NO_LOOKUP_LINE = 'THIS AI CANNOT LOOK ANYTHING UP. When a fact must be checked, set escalate (why: what needs checking) rather than answer from memory.'
NO_CLOSE_LINE = 'DO NOT CLOSE THIS TASK: set done to false; the owner decides when it is finished.'


class QuickAnswer(NamedTuple):
    report: str; draft: str; question: str; done: bool; escalate: bool; why: str


def _clean(s) -> str:
    "A string field with Taskuary's own markers taken out (a model told about them may still write one)."
    from .selfclose import draft_markers, for_screen, reply_marker
    return _unmark(for_screen(draft_markers(reply_marker(str(s or ''))[0])[0]))

# the [[TASKUARY-...]] tags, and the two envelopes _file also acts on: the Hub's <TASKUARY-HUB> and a bare TASKUARY-PROPOSE (proposals.MARK)
_TAG = re.compile(r'\[\[\s*/?\s*TASKUARY[^\]]*\]\]|<\s*/?\s*TASKUARY[^>]*>|TASKUARY-PROPOSE', re.I)
def _unmark(text) -> str:
    "Every Taskuary tag out: the fields are words for the owner, and only as_reply writes the markers _file acts on."
    return _TAG.sub('', str(text or '')).strip()

def read(data) -> 'QuickAnswer | None':
    "The structured answer, or None when it is not an object or says neither something nor that the job is too big."
    if not isinstance(data, dict): return None
    a = QuickAnswer(*(_clean(data.get(k)) for k in ('report', 'draft', 'question')), data.get('done') is True, data.get('escalate') is True, _clean(data.get('why')))
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
    web = bool(getattr(brain, 'takes_web', False))
    lookups = web or brainroute.choose(store, 'quick_work', tid).pick.startswith('cli:')
    system, user = prompt(store, tid, ask, lookups)
    with llm.watching(trace): got = llm.ask_json(brain, system, user, want=None if web else QUICK_WANT, max_tokens=QUICK_TOKENS, **({'web': True} if web else {}))
    return read(got.data)


QUICK_TIMEOUT = 180
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

def start(store, tid, brief: str = None, as_owner: bool = True) -> str:
    """One call for a quick task, filed as a general turn - 'filed'; or the deep path, when the call says it needs more or fails - 'escalated';
    or 'failed', when the answer could not be filed: written on the task and counted on the retry budget, as _start_general does. Never raises."""
    q, steps, cancel = ingest.first_ask(store, tid, brief), [], threading.Event()
    timer = threading.Timer(QUICK_TIMEOUT, cancel.set); timer.daemon = True; timer.start()
    try: out, failed = ask(store, tid, q, steps, cancel), ''
    except Exception as e: out, failed = None, f'the quick answer could not be made ({e})'
    finally: timer.cancel()
    if out is None or out.escalate:
        why = failed or ('the quick answer could not be read' if out is None else out.why or 'it needs more than one call')
        escalate(store, tid, q, why, out.report if out else '')
        return 'escalated'
    try:
        ses = general.start_session(store, tid, actor='router'); ses.quick = True
        ses.file_quick(q, out, steps, as_owner)
        return 'filed'
    except Exception as e:
        logger.warning(f'quick answer could not be filed for task {tid}: {e}')
        from . import blackboard as bb
        bb.record_failure(store, tid, e, 'assistant', label='The assistant')
        return 'failed'
