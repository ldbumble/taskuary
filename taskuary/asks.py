"""What the owner asked for, remembered as tasks and said back at the door they asked from
(docs/superpowers/specs/2026-10-05-assistant-remembers-asks-design.md).

The assistant is deliberately light - it hands work to tasks and keeps nothing of its own - so it forgot: "where's the tab
check?" had no answer, and finished work was silent. An ask IS a task, marked with where it was asked (`AskedVia`); its
state is its rail lane in the rail's own words; a move into a lane that needs the owner, or its end, is said once. No
memory store, no model call.
"""


def door() -> str:
    """Where the owner is asking from right now: the phone chat speaking this turn, else the desktop."""
    from . import remote_assistant
    at = remote_assistant.asking()
    return f"{at['channel']}:{at['chat']}" if at and at.get('channel') and at.get('chat') else 'desktop'


def of(task) -> str | None:
    """The door a task was asked from, or None for work the owner did not ask for (triage, reports, ...)."""
    return (task or {}).get('AskedVia') or None


# ── where an ask stands: its task's rail lane, in the rail's own words ───────────────────
# ONE VOCABULARY: an ask has no statuses of its own. These are the lanes whose arrival is said at the ask's door - the
# owner is needed (blocked, approve), it is stuck (stopped, broken), or it ended. `working`, `queued`... are never said.
SAID = ('blocked', 'approve', 'stopped', 'broken', 'finished')
AGENT_REFS = ('assistant:agent', 'assistant:handoff')      # a chat hand-off IS an agent's job from its first second


def _rail(store) -> list:
    """The rail as it stands - the cached build when there is one (funnel.pile caches; a task write invalidates it)."""
    from . import funnel
    funnel.pile(store, quiet=True)
    return funnel.full_items(store) or (funnel.cached_pile(store) or {}).get('items') or []


def agent_touched(store, tid: int) -> bool:
    """Has an agent worked this? A to-do the owner does themselves has nothing to report."""
    t = store.get_task(tid) or {}
    if str(t.get('Assignee') or '').startswith('agent:') or t.get('SourceRef') in AGENT_REFS: return True
    return bool(store._one('SELECT 1 x FROM run WHERE TaskId=? UNION SELECT 1 FROM transcript WHERE TaskId=? '
                           'UNION SELECT 1 FROM worker_event WHERE TaskId=? LIMIT 1', (tid, tid, tid)))


def state(store, tid: int) -> tuple:
    """(lane, sentence) - the rail's lane for this task and its own words; 'finished' when closed, 'quiet' when it is on
    no rail row. Where it has emails to send, how many are drafted rides along (slots.py)."""
    from . import funnel, slots
    t = store.get_task(tid) or {}
    if t.get('Status') in ('done', 'dropped'):
        found = funnel.agent_found(store, tid)
        return 'finished', ('done' + (f': {found}' if found else '') if t.get('Status') == 'done' else 'dropped')
    row = next((i for i in _rail(store) if i.get('tid') == tid), None)
    if not row: return 'quiet', ''
    lane, says = row.get('lane') or 'quiet', str(row.get('why') or '').strip()
    owed = slots.all_(store, tid)
    if owed and lane == 'approve':
        drafted = sum(1 for i in owed if i.get('rid'))
        says = f"{drafted} of {len(owed)} emails drafted, waiting on your yes"
    return lane, says
