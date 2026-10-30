"""Quick general work (spec 2026-10-29): a general task triage judged quick is answered in one call, not an agent session.

An agent session costs a launch and a long wait for what is often one sentence ("does it make sense to go on Friday?"). This module only
READS the depth - triage's difficulty, plus the things that always need the agent (a browser, a stranger, several emails owed, a task that
already ran deep). It never guesses from the words of the task."""
from . import brainroute, browserview, general, ingest, origin, slots

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
