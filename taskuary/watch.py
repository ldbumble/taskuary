"""Watch it: a task that is not the owner's, kept open while somebody else handles it.

The owner, 2026-11-01: a move beside Remind me for work that is someone else's to do, which they want to see through. Nothing is sent.
The task stays OPEN and leaves the walk - it sits under Watching at the foot of Tasks (lanes.level_of 'watching'), and railwalk.line
skips it as it skips For later. It comes back on the walk when its thread moves (a new inbound message joins it: ingest calls `moved`),
and triage's `handled_elsewhere` says whether that message shows somebody else dealt with it - then Mark done is lit (rulebook
'watch_handled'). After QUIET_DAYS with nothing on the thread it comes back once, Chase them / Let it go lit (rulebook 'watch_quiet').
Any move the owner presses on it ends the watch (`stop`); Mark done closes it as ever. Nothing here closes a task: a watch only comes back.
"""
from datetime import datetime, timedelta
from loguru import logger

QUIET_DAYS = 7
BACK = ('moved', 'handled', 'quiet')        # why a watch came back on the walk, until the owner's next move
QUIET_NOTE = 'A week watched and nothing on the thread - chase them, or let it go.'
CLOSED = ('done', 'dropped')


def _stamp(at: datetime = None) -> str: return f"{at or datetime.now():%Y-%m-%d %H:%M:%S}"
def watching(task) -> bool: return bool((task or {}).get('WatchedAt')) and (task or {}).get('Status') not in CLOSED
def back(task) -> str: return str((task or {}).get('WatchBack') or '') if (task or {}).get('Status') not in CLOSED else ''


def watch(store, tid: int, actor: str = 'owner') -> dict:
    """Keep it open, off the walk, until its thread moves or a quiet week passes. A Remind me day is dropped: one road back at a time."""
    t = store.get_task(tid)
    if not t: raise ValueError('task not found')
    if t.get('Status') in CLOSED:
        from .failures import Closed
        raise Closed(tid, 'that task is done - reopen it first')
    store.update_task(tid, {'WatchedAt': _stamp(), 'WatchBack': '', 'RemindAt': ''}, actor)
    store.audit('task', tid, 'watch', actor, detail={'quiet_days': QUIET_DAYS})
    return {'taskId': tid, 'watching': True, 'quietDays': QUIET_DAYS}


def stop(store, tid, actor: str = 'owner') -> bool:
    """The owner pressed a move on it: the watch, and why it came back, are over. True when there was one to end."""
    t = store.get_task(int(tid)) if tid else None
    if not t or not (t.get('WatchedAt') or t.get('WatchBack')): return False
    store.update_task(int(tid), {'WatchedAt': '', 'WatchBack': ''}, actor)
    store.audit('task', int(tid), 'unwatch', actor)
    return True


def moved(store, tid: int, msg: dict, follow: dict | None, mine, actor: str) -> bool:
    """A message from somebody else joined a watched task: it is back on the walk, and 'handled' when triage read it as dealt with."""
    t = store.get_task(tid) or {}
    if not watching(t) or str(msg.get('from_email') or '').lower() in (mine or ()): return False
    why = 'handled' if (follow or {}).get('handled_elsewhere') is True else 'moved'
    store.update_task(tid, {'WatchedAt': '', 'WatchBack': why}, actor)
    from . import words
    who = msg.get('from_name') or msg.get('from_email') or 'They'
    store.add_comment(tid, actor, 'agent', f"{who} wrote on it - brought back from {words.name('watching')}"
                      + (' - it looks handled.' if why == 'handled' else '.'))
    logger.info(f'watch: task {tid} back on the walk ({why})')
    return True


def due(store, now: datetime = None) -> int:
    """Each watch QUIET_DAYS old with nothing on its thread comes back, once: the note is new activity, and the rule lights Chase them /
    Let it go. Run with the reminders (remind.tick)."""
    since, n = _stamp((now or datetime.now()) - timedelta(days=QUIET_DAYS)), 0
    for t in store._rows("SELECT TaskId FROM task WHERE IFNULL(WatchedAt,'')<>'' AND WatchedAt<=? AND Status NOT IN ('done','dropped')", (since,)):
        store.update_task(t['TaskId'], {'WatchedAt': '', 'WatchBack': 'quiet'}, 'assistant')
        store.add_comment(t['TaskId'], 'assistant', 'agent', QUIET_NOTE); n += 1
    return n
