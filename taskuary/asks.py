"""What the owner asked for, remembered as tasks and said back at the door they asked from
(docs/superpowers/specs/2026-10-05-assistant-remembers-asks-design.md).

The assistant is deliberately light - it hands work to tasks and keeps nothing of its own - so it forgot: "where's the tab
check?" had no answer, and finished work was silent. An ask IS a task, marked with where it was asked (`AskedVia`); its
state is its rail lane in the rail's own words; a move into a lane that needs the owner, or its end, is said once. No
memory store, no model call.
"""
import threading, time
from datetime import datetime, timedelta

from loguru import logger


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


# ── saying it moved: once, at the door it was asked from ─────────────────────────────────
def _told(store, tid: int, lane: str):
    """The last lane said (or passed over) for this ask - written quietly: a poke here would queue the same task again."""
    store._exec('UPDATE task SET AskedTold=?, AskedToldAt=? WHERE TaskId=?', (lane, datetime.now().isoformat(' ', 'seconds'), tid))


def _say(store, task: dict, line: str) -> bool:
    """One line at the ask's door. The phone when it was asked there, or while the walk is handed to it - only in a gap
    of the conversation (remote_assistant.quiet: never between a card and its answer); False = not now, try again.
    Everywhere else, the desktop Assistant chat."""
    from . import concierge, general, remote_assistant
    via, handed = of(task) or 'desktop', remote_assistant.handoff(store)
    channel, chat = via.split(':', 1) if ':' in via else ((handed or {}).get('channel'), (handed or {}).get('chat'))
    cid = None
    if channel and chat:
        c = remote_assistant.connector_for_chat(store, channel, chat)
        cid = (c or {}).get('ConnectorId') or ((handed or {}).get('connector_id') if handed and handed.get('chat') == chat else None)
    dock = general.dock_task(store, 'owner')[0]['TaskId']
    if cid:
        if not remote_assistant.quiet(store, channel, chat): return False
        remote_assistant.send(store, channel, chat, line, cid)
        concierge.record(store, dock, 'assistant', line, phone=True)     # the next turn's history carries it
        return True
    concierge.record(store, dock, 'assistant', line)
    return True


def check(store, tid: int) -> str | None:
    """Say this ask's move if it moved into a said lane since it was last told. The line said, or None."""
    from .store import task_ref
    t = store.get_task(tid) or {}
    if not of(t) or not agent_touched(store, tid): return None
    lane, says = state(store, tid)
    if lane == 'quiet' or lane == t.get('AskedTold'): return None
    if lane not in SAID:
        _told(store, tid, lane); return None
    line = f"{task_ref(tid)} {str(t.get('Title') or '').strip()} - {says or lane}."
    if not _say(store, t, line): return None
    _told(store, tid, lane)
    return line


# Event-driven: a task write (store._poke 'task-changed') queues its id; one worker drains the queue a moment later, so a
# 150-row catch-up is one pass over the few asks it touched. A slow sweep catches what no write announces (an agent going
# quiet). Off until watch() starts it - tests and scripts never get a background thread.
WAIT, SWEEP, DAYS = 2.0, 300.0, 30
_Q = {'on': False, 'pending': {}, 'lock': threading.Lock(), 'wake': threading.Event()}


def notice(store, tid):
    if not _Q['on'] or not tid: return
    with _Q['lock']: _Q['pending'][int(tid)] = store
    _Q['wake'].set()


def drain():
    with _Q['lock']: due, _Q['pending'] = _Q['pending'], {}
    for tid, store in due.items():
        try: check(store, tid)
        except Exception as e: logger.warning(f'asks: could not check {tid} - {e}')


def sweep(store):
    since = (datetime.now() - timedelta(days=DAYS)).isoformat(' ', 'seconds')
    for r in store._rows("SELECT TaskId FROM task WHERE AskedVia IS NOT NULL AND CreatedAt>=? AND "
                         "(Status NOT IN ('done','dropped') OR IFNULL(AskedTold,'')<>'finished') ORDER BY TaskId", (since,)):
        try: check(store, r['TaskId'])
        except Exception as e: logger.warning(f"asks: could not check {r['TaskId']} - {e}")


def watch(store):
    """Start the one worker (the server's lifespan does; conftest replaces this)."""
    if _Q['on']: return
    _Q['on'] = True
    def loop():
        last = 0.0
        while True:
            woke = _Q['wake'].wait(timeout=SWEEP); _Q['wake'].clear()
            try:
                if woke: time.sleep(WAIT); drain()
                if time.monotonic() - last >= SWEEP: sweep(store); last = time.monotonic()
            except Exception as e: logger.warning(f'asks watcher: {e}')
    threading.Thread(target=loop, daemon=True, name='asks').start()
