"""Check-backs: the general agent schedules its own follow-up on the same task (the owner, 2026-11-05, from the open-source assistants' cron:
a payment that should clear, a reply expected by a date, a form that takes a day).

The agent names WHEN and WHAT to verify - `taskuary --check-back`, the check_back tool, or "check_back" in its turn summary (any brain has
that one). It rides on the task (CheckBackAt / CheckBackWhat), one at a time, and comes due on the reminders' own clock (remind.tick: on
start, every sync, the five-minute sweep) - no daemon of its own. When it is due the SAME task's agent is handed one short Taskuary line as
its next turn (general.BRIEF_ACTOR, as a passed-in mail is): queued behind a turn at work, an idled-out agent brought back as the same run.
Nothing else moves: the task stays where it is in Tasks, nothing is sent, nobody's phone is written to, and a closed task has none.
"""
from datetime import datetime
from loguru import logger

CLOSED = ('done', 'dropped')
WHAT_CHARS = 300
TURN = ("TASKUARY: the check-back you set on this task is due - {what}. Check it now with your tools, then answer with what you found and "
        "what it means for the owner. If it is still not settled and time will settle it, set another check-back; otherwise say what is left.")
LATE = "the answer you wait on is late ({line}) - draft the chase to whoever owes it as your reply card, or say in one line why not"


def _stamp(at: datetime = None) -> str: return f"{at or datetime.now():%Y-%m-%d %H:%M:%S}"


def of_task(task) -> dict | None:
    "{'at', 'what'} of the check-back waiting on the task, or None."
    t = task or {}
    return {'at': t['CheckBackAt'], 'what': t.get('CheckBackWhat') or ''} if t.get('CheckBackAt') and t.get('Status') not in CLOSED else None


def set_check(store, tid: int, when, what, actor: str = 'agent') -> dict:
    """Schedule it - `when` read as Remind me reads a day ('tomorrow 9am', 'in 2 days', '2026-11-12', 'in 3 hours'). A new one replaces the
    one waiting. Raises ValueError, said to the agent, for a time it cannot read, one gone, no `what`, or a closed task."""
    from . import remind
    from .redact import scrub
    t = store.get_task(int(tid))
    if not t: raise ValueError('no such task')
    if t.get('Status') in CLOSED: raise ValueError('this task is closed - a check-back would wake nobody')
    w = ' '.join(str(what or '').split())[:WHAT_CHARS]
    if not w: raise ValueError('say what to verify - "the refund cleared on the card", "Erin Blake answered the invite"')
    if scrub(w) != w: raise ValueError('the note carries something secret - say what to check, not the login')
    at = remind.parse(when)
    if not at: raise ValueError('say when to check back - "tomorrow 9am", "in 2 days", "2026-11-12"')
    store.update_task(int(tid), {'CheckBackAt': at, 'CheckBackWhat': w}, actor)
    store.audit('task', int(tid), 'check_back', actor, detail={'at': at, 'what': w, 'replaced': t.get('CheckBackAt') or None})
    # ...said on the task, so the owner sees what will wake it and when - a line, no button (the owner rules the UI)
    store.add_comment(int(tid), actor, 'agent', f"The agent will check back {remind.when(at)}: {w}")
    return {'ok': True, 'at': at, 'when': remind.when(at), 'what': w}


def cancel(store, tid: int, actor: str = 'owner') -> dict:
    "The owner's × on the task's check-back chip: nothing wakes the agent then. Said once on the task; a task with none is left alone."
    t = store.get_task(int(tid))
    if not t: raise ValueError('no such task')
    if not t.get('CheckBackAt'): return {'ok': True, 'cancelled': False}
    store.update_task(int(tid), {'CheckBackAt': '', 'CheckBackWhat': ''}, actor)
    store.audit('task', int(tid), 'check_back_cancelled', actor, detail={'at': t['CheckBackAt'], 'what': t.get('CheckBackWhat') or ''})
    return {'ok': True, 'cancelled': True}


# A WAIT GONE LATE WAKES THE TASK'S AGENT, ONCE (the owner, 2026-11-10: "job of agent is to be helpful and do as much as possible. it shoudl
# prompt you"): a late answer lit nothing and woke nobody - only a check-back the agent set itself did. Now the lateness the rail names
# (rulebook.LATE) is a check-back come due, set here on the reminders' clock and handed over by due() below - a full house waits for the
# next tick - where the owner's own line would wake that agent (ingest.wake_why). Its audit row is the record: nothing wakes it again
# until something moves on the task. Where none may wake, the row lights Chase instead (rulebook._recommended).
def woke(store, tid, actor: str = 'late') -> bool:
    "Whether this lateness already woke the task's agent (`actor` 'held': was refused its first one): a record after the task's newest message."
    r = store._one("SELECT MAX(CreatedAt) AS at FROM audit WHERE EntityType='task' AND EntityId=? AND Action='check_back' AND Actor=?", (int(tid), actor)) or {}
    if not r.get('at'): return False
    m = store._one('SELECT MAX(IFNULL(SentAt,CreatedAt)) AS at FROM message WHERE TaskId=?', (int(tid),)) or {}
    return str(m.get('at') or '').replace('T', ' ')[:19] <= str(r['at']).replace('T', ' ')[:19]


def late(store, now: datetime = None) -> int:
    "Each open wait, goal or quiet watch the rail reads as late, set due now for its agent - once per lateness. Run with the reminders."
    from . import advisor, ingest, rulebook
    n = 0
    for t in store._rows("SELECT TaskId FROM task WHERE Status NOT IN ('done','dropped') AND IFNULL(CheckBackAt,'')='' "
                         "AND (Status='waiting' OR IFNULL(WatchBack,'')='quiet' OR IFNULL(DoneWhen,'')<>'')"):
        tid = t['TaskId']
        if woke(store, tid) or woke(store, tid, 'held'): continue
        # ...AND A TASK NO AGENT HAS WORKED GETS ITS FIRST ONE (the owner, 2026-11-10: "yes"): no conversation to wake was a lateness nobody
        # took up. It starts through the check every start passes (auto_start_ok) - a refusal (the switch, a stranger held) said once on the
        # task, and Chase stays lit (woke is False) - with the same turn; a full house queues it as a carry-on turn waits (ingest.queue_turn)
        first = (why := ingest.wake_why(store, tid, {}, None, None, own=True)) == 'no agent conversation'
        if why and not first: continue
        it = advisor._item(store, 'task', tid, build=False)
        f = rulebook.facts(store, it, advisor.offered(store, it)) if it else {}
        if f.get('state') not in rulebook.LATE or not f.get('line'): continue
        what = LATE.format(line=f['line'].rstrip('.'))[:WHAT_CHARS]
        if first:
            m = store._one("SELECT * FROM message WHERE TaskId=? AND IFNULL(Direction,'in')<>'out' ORDER BY MessageId DESC LIMIT 1", (int(tid),))
            ok, no = ingest.auto_start_ok(store, ingest._from_row(m) if m else {}, (m or {}).get('MessageId'), 'general', own=not m)
            if not ok:
                ingest.not_started(store, tid, no); store.audit('task', tid, 'check_back', 'held', 'agent', {'state': f['state'], 'why': str(no)})
                continue
            if not ingest.has_room(store):
                ingest.queue_turn(store, tid, TURN.format(what=what))
                store.audit('task', tid, 'check_back', 'late', 'agent', {'state': f['state'], 'line': f['line'], 'queued': True})
                n += 1; continue
        store.update_task(tid, {'CheckBackAt': _stamp(now), 'CheckBackWhat': what}, 'assistant')
        store.audit('task', tid, 'check_back', 'late', 'agent', {'state': f['state'], 'line': f['line'], **({'first': True} if first else {})})
        n += 1
    return n


def due(store, now: datetime = None, spawn=None) -> int:
    """Each check-back come due, handed to its task's agent once - run with the reminders (remind.tick). With every agent slot full it waits for
    the next tick rather than being dropped. `spawn` runs the hand-off (a thread by default: the clock never waits on a model)."""
    from . import general, ingest
    n = 0
    for t in store._rows("SELECT TaskId, Status, Kind, CheckBackWhat FROM task WHERE IFNULL(CheckBackAt,'')<>'' AND CheckBackAt<=?", (_stamp(now),)):
        tid = t['TaskId']
        if t.get('Status') in CLOSED or not general.handles(t):
            store.update_task(tid, {'CheckBackAt': '', 'CheckBackWhat': ''}, 'assistant'); continue
        if not general.session_for(tid) and not general.idled(tid, store) and not ingest.has_room(store): continue
        store.update_task(tid, {'CheckBackAt': '', 'CheckBackWhat': ''}, 'assistant')        # cleared first: it speaks once
        (spawn or ingest._spawn)(fire, store, tid, t.get('CheckBackWhat') or 'what you said you would verify')
        n += 1
    return n


def fire(store, tid: int, what: str):
    """The agent's next turn: the live session's (queued behind its turn - GeneralSession._take), else the task's conversation carried on."""
    from . import general
    turn = TURN.format(what=what)
    try:
        ses = general.session_for(tid)
        if ses: return ses.send_prompt(turn, brief=True)
        general.OPENING.add(tid)
        try: return general.start_session(store, tid, actor='router').send_prompt(turn, brief=True)
        finally: general.OPENING.discard(tid)
    except general.Stopped: pass
    except Exception as e:
        logger.warning(f'check-back on task {tid} not handed to its agent: {e}')
        store.add_comment(tid, 'router', 'agent', f"The check-back could not wake the agent: {' '.join(str(e).split())[:200]} - {general.CARRY_ON}.")
