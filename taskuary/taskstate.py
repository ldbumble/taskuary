"""ONE STATE PER TASK, for the Tasks list and the Board (T1-T9, the owner, 2026-09-25: "everything should be the task
list and the board just follows whatever is going on there").

The list said "on you" for a task waiting to start, a session you saved and an agent that stopped; the Board put all
three - and a task Taskuary closed on - in one "Queued" column, and its "Waiting on you" held an asking agent, a
drafted reply and a task waiting on somebody else. Each page decided from its own facts in the browser. This decides
once, on the server, with the rail's rules (funnel.left_by_facts, general_not_started, finish_evidence) and the rail's
words (lanes.json), and both pages draw what it says.

The keys are lanes.json's own: a lane where the rail has one (blocked, working, approve, queued, saved, stopped,
yours), `theirs` for a task waiting on somebody else, and for a closed task `agentdone` (the agent finished
it) or `closed` (you did).
"""
from . import funnel
from .processing_unread import OWNER_ACTORS, finish_evidence

# the Board's columns, left to right: what each holds (T2, T3)
BOARD = (('queued', ('queued',)), ('working', ('working',)), ('blocked', ('blocked',)),
         ('left', ('saved', 'stopped')), ('agentdone', ('agentdone', 'approve')))


def _general_waiting(store, t) -> bool:
    """A regular-agent task triage handed on and nothing started (A10): read only for an open general task, the one
    kind the rule can hold."""
    if str(t.get('Kind') or '') != 'general' or t.get('Status') not in ('open', 'in_progress'): return False
    from .general import ASSISTANT_TYPE, USER_TYPE
    talked = any(c.get('ActorType') in (USER_TYPE, ASSISTANT_TYPE) for c in store.list_comments(t['TaskId']) or [])
    return funnel.general_not_started(t, talked, store.list_routes(t['TaskId']) or [])


def state(store, t: dict, session=None, queued=None) -> str:
    """This task's state key. `session` is its live session row, `queued` its dispatch-queue row."""
    live = bool(session and session.get('alive', True))
    # a live session is the fact happening now - a done task continued is work in progress again (T8). A session that
    # PREDATES the close is a terminal nobody shut, not the task picked back up (the Board's old rule, kept).
    if live and t.get('Status') == 'done' and t.get('ClosedAt') and str(session.get('started') or '') < str(t['ClosedAt']): live = False
    if live: return 'blocked' if session.get('waiting') else 'working'
    st = t.get('Status')
    if st == 'dropped': return 'dropped'
    if st == 'done':
        if str(t.get('UpdatedBy') or '') in OWNER_ACTORS: return 'closed'        # yours: no need to read its notes
        return 'agentdone' if finish_evidence(store, t['TaskId']) else 'closed'
    if t.get('RunStatus') == 'running': return 'working'
    if t.get('ReviewStatus') == 'pending': return 'approve'
    # still waiting to start, a failed start included - the row carries the error and the page offers Start now / Cancel (T10)
    if queued: return 'queued'
    left = funnel.left_by_facts(t.get('Tags'), [{'Status': t.get('RunStatus')}] if t.get('RunStatus') else [])
    if not left and str(t.get('Assignee') or '').startswith('agent:') and store.last_transcript(t['TaskId']): left = 'stopped'
    if left: return left
    if str(t.get('Assignee') or '').startswith('agent:') or _general_waiting(store, t): return 'queued'
    if st == 'waiting': return 'theirs'
    return 'yours'


def column(key: str) -> str | None:
    """The Board column a state sits in, or None - a task that is yours, or waiting on them, is not agent work."""
    return next((c for c, keys in BOARD if key in keys), None)
