"""Remind me: an open task put away until a day, then back on the work rail that morning.

The owner, 2026-09-25: Tomorrow and Later are gone - Next on open work comes back after a few hours - and
"bring this back in two weeks" is a date on the TASK. Until it, the task is Upcoming (the Tasks tab's own
filter) and off the rail and the walk; on the day it is back at MORNING, saying it was asked for. One
road for the task page's picker, the Assistant's tool (task.defer) and the typed words.
"""
import re, threading
from datetime import datetime, timedelta
from loguru import logger

MORNING = '07:00:00'
NONE_WORDS = ('', 'none', 'never', 'clear', 'off', 'no')
AFTER_WORDS = ('after my meetings', 'after meetings', 'after my meeting', 'after the meeting', 'after my calls')


_SOON = re.compile(r'(?:in\s+)?(\d+|a|an|one|two|three|four|half an?)\s+(hour|hr|minute|min)s?')
_BARE_TIME = re.compile(r'(?:at\s+)?(?:\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)|\d{1,2}:\d{2})')


def parse(until, now: datetime = None) -> str | None:
    """'2026-10-09', '2 weeks', '3 days', 'tomorrow', 'monday' -> 'YYYY-MM-DD 07:00:00'; None clears it. Later TODAY
    takes a time - 'today 3pm', '3pm', 'in 2 hours' (the owner could only pick tomorrow, 2026-10-06). Raises ValueError
    for anything else, for a day already gone, and for a time today that has passed."""
    now = now or datetime.now()
    s = str(until or '').strip().lower()
    if s in NONE_WORDS: return None
    unreadable = f'"{until}" is not a day I can read - say a date (2026-10-09), "in 2 weeks" or "today 3pm"'
    if m := _SOON.fullmatch(s):
        n = {'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4}.get(m.group(1)) or (0.5 if m.group(1).startswith('half') else int(m.group(1)))
        if not n: raise ValueError(unreadable)
        back = (now + timedelta(**{'hours' if m.group(2).startswith('h') else 'minutes': n})).replace(second=0, microsecond=0)
        return f"{back:%Y-%m-%d %H:%M:%S}"
    if _BARE_TIME.fullmatch(s): s = 'today ' + re.sub(r'^at\s+', '', s)
    # a time on the end keeps its hour: "tomorrow 9am" was the whole phrase and nothing matched it (2026-10-06)
    at, timed = MORNING, False
    if t := re.fullmatch(r'(.+?)\s*(?:,|\bat\b)?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)|(.+?)\s*(?:,|\bat\b)?\s*(\d{1,2}):(\d{2})', s):
        g = t.groups()
        s, h, mi, half = (g[0], int(g[1]), int(g[2] or 0), g[3]) if g[0] else (g[4], int(g[5]), int(g[6]), None)
        if half and not 1 <= h <= 12: raise ValueError(unreadable)
        if half: h = h % 12 + (12 if half.startswith('p') else 0)
        if not (0 <= h < 24 and 0 <= mi < 60): raise ValueError(unreadable)
        at, timed = f'{h:02d}:{mi:02d}:00', True
    s = re.sub(r'\s+(morning|in the morning)$', '', s.strip())
    m = re.fullmatch(r'(\d{4}-\d{2}-\d{2})(?:[ t].*)?', s)
    if m:
        try: day = datetime.strptime(m.group(1), '%Y-%m-%d')
        except ValueError: raise ValueError(unreadable) from None     # 2026-02-30 has the shape, not the day
    elif s == 'today': day = now
    elif s == 'tomorrow': day = now + timedelta(days=1)
    elif m := re.fullmatch(r'(?:in\s+)?(\d+|a|an|one|two|three|four)\s+(day|week|month)s?', s):
        n = {'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4}.get(m.group(1)) or int(m.group(1))
        day = now + timedelta(days=n * {'day': 1, 'week': 7, 'month': 30}[m.group(2)])
    elif s.rstrip('s') in DAYS:
        ahead = (DAYS.index(s.rstrip('s')) - now.weekday()) % 7 or 7
        day = now + timedelta(days=ahead)
    else: raise ValueError(unreadable)
    if day.date() < now.date(): raise ValueError('that day has gone - pick today with a time, or a day after today')
    if day.date() == now.date():
        if not timed: raise ValueError('say a time later today ("today 3pm"), or pick a day after today')
        if f"{day:%Y-%m-%d} {at}" <= f"{now:%Y-%m-%d %H:%M:%S}": raise ValueError('that time has already gone today - pick a later one')
    return f"{day:%Y-%m-%d} {at}"

DAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')


def clock(at: datetime) -> str: return f"{at.hour % 12 or 12}:{at.minute:02d}"


def when(remind_at, now: datetime = None) -> str:
    """'Thu 9 Oct' - the day as the page and the receipt say it; 'today at 2:35' for a reminder later today."""
    try: d = datetime.strptime(str(remind_at)[:10], '%Y-%m-%d')
    except ValueError: return str(remind_at or '')
    if d.date() == (now or datetime.now()).date():
        try: return f"today at {clock(datetime.strptime(str(remind_at)[:16], '%Y-%m-%d %H:%M'))}"
        except ValueError: return 'today'
    return f"{d:%a} {d.day} {d:%b}"


# ── after your meetings: the calendar's busy blocks, where a calendar is connected ────────
GAP_MIN, AFTER_MIN = 10, 5      # meetings this close are one run; back this long after the run ends


def busy_run(events: list, at: datetime, ahead: bool = False):
    """(end, last start) of the run of meetings `at` falls in - or, `ahead`, the next run starting later that same day.
    Meetings closer than GAP_MIN count as one run: nobody does a task in the eight minutes between two calls."""
    def dt(s):
        try: return datetime.strptime(str(s or '')[:16].replace('T', ' '), '%Y-%m-%d %H:%M')
        except ValueError: return None
    spans = sorted((a, b) for a, b in ((dt(e.get('start')), dt(e.get('end'))) for e in events or [] if not e.get('all_day')) if a and b and b > a)
    end = last = None
    for a, b in spans:
        if end is None:
            if a <= at < b or (ahead and at <= a and a.date() == at.date()): end, last = b, a
        elif a <= end + timedelta(minutes=GAP_MIN): end, last = max(end, b), a
        else: break
    return (end, last) if end else None


def agenda(store) -> list:
    """Today's meetings as already read - never a live calendar call in front of a press (assistant._agenda)."""
    from .assistant import _agenda
    try: return _agenda(store, block=False)
    except Exception as e:
        logger.debug(f'no calendar for the reminder: {e}'); return []


def after_meetings(store, now: datetime = None) -> dict | None:
    """The next free moment after the meetings in front of the owner today - {'until', 'label', 'says'} - or None when
    the calendar shows none (or no calendar is connected). What the picker and the Assistant offer as "after your 2:00"."""
    now = now or datetime.now()
    run = busy_run(agenda(store), now, ahead=True)
    if not run: return None
    back = run[0] + timedelta(minutes=AFTER_MIN)
    if back.date() != now.date(): return None
    return {'until': f"{back:%Y-%m-%d %H:%M}", 'label': f"After your {clock(run[1])}",
            'says': f"You're in meetings until {clock(run[0])}. I'll bring it back at {clock(back)}."}


def waiting(task: dict, now: datetime = None) -> bool:
    """Put away and not due yet - Upcoming, off the rail."""
    r = str((task or {}).get('RemindAt') or '')
    return bool(r) and (task or {}).get('Status') not in ('done', 'dropped') and r > f"{now or datetime.now():%Y-%m-%d %H:%M:%S}"


class AgentOpen(ValueError):
    """Remind me on a task whose agent session is still open: the doors answer 409 with this."""


OPEN_SAYS = 'An agent session is still open on this task - Save and end session first, then put it away.'


def agent_open(tid: int) -> bool:
    """A live session on the task (the same truth Mark done's "Stop the agent and mark done?" reads)."""
    from . import terminal as term
    try: return bool(term.for_task(tid, details=False))
    except Exception: return False


def set_reminder(store, tid: int, until, actor: str = 'owner') -> dict:
    """Put the task away until `until` (or bring it back now with none). The receipt carries the undo."""
    t = store.get_task(tid)
    if not t: raise ValueError('task not found')
    if t.get('Status') in ('done', 'dropped'): raise ValueError('that task is done - reopen it first')
    # "after my meetings" is the calendar's to answer; with no meetings in front of her there is nothing to wait for
    if str(until or '').strip().lower() in AFTER_WORDS:
        free = after_meetings(store)
        if not free: raise ValueError('your calendar shows no more meetings today - say a time ("today 3pm")')
        until = free['until']
    at, prev = parse(until), t.get('RemindAt') or None
    # Put away with an agent still open, it was deferred anyway and its row stayed under "agent waiting on you" (press
    # audit, 2026-10-01). The owner: the agent is open - save and end it first. Bringing it back is never refused.
    if at and agent_open(tid): raise AgentOpen(OPEN_SAYS)
    store.update_task(tid, {'RemindAt': at or ''}, actor)
    if at:
        from . import asks
        asks.reminder_set(store, tid)       # said at the door it was set from when it comes due
    store.audit('task', tid, 'remind', actor, detail={'from': prev, 'to': at})
    # the undo keeps the hour too: a reminder for later today, put back as its date alone, was "today" with no time
    back = (prev[:10] if prev[11:19] in ('', MORNING) else prev[:16]) if prev else 'none'
    return {'taskId': tid, 'remindAt': at, 'when': when(at) if at else '',
            'undo': {'kind': 'task.defer', 'target': tid, 'params': {'until': back},
                     'label': f"Put the reminder back to {when(prev)}" if prev else 'Bring it back now'}}


DUE_NOTE = 'You asked to be reminded about this today.'


def due(store, now: datetime = None) -> int:
    """The morning's reminders, filed on each task as a note - run on every sync. The note is what brings it back:
    it is new activity on the task, so a task put away for longer than the rail looks back still returns, unread.
    The date is cleared with it, so each reminder speaks once."""
    stamp, n = f"{now or datetime.now():%Y-%m-%d %H:%M:%S}", 0
    for t in store._rows("SELECT TaskId, Status FROM task WHERE RemindAt IS NOT NULL AND RemindAt != '' AND RemindAt <= ?", (stamp,)):
        if t.get('Status') not in ('done', 'dropped'):
            store.add_comment(t['TaskId'], 'assistant', 'agent', DUE_NOTE); n += 1
            from . import asks
            try: asks.remind_due(store, t['TaskId'])      # ...and said where it was set: the phone, or the desktop chat
            except Exception as e: logger.warning(f"reminder on {t['TaskId']} not said: {e}")
        store.update_task(t['TaskId'], {'RemindAt': ''}, 'assistant')
    return n


# ── deadlines kept: the day triage read from the mail (triage.DUE), said as it nears ──────
# Triage recorded only urgent yes/no, so "the form is due Friday" was forgotten by Thursday (2026-10-06). The day before
# it goes to the top of the list; on the day it says so; once it has passed it asks, once. In the app only - the phone
# never speaks first (the owner, 2026-10-02), so none of this reaches a chat she did not open.
STEPS = ('eve', 'today', 'late')


def step(due_at, now: datetime = None) -> str | None:
    """Where a due day stands: 'eve' (tomorrow), 'today', 'late' - or None while it is further off."""
    try: d = (datetime.strptime(str(due_at or '')[:10], '%Y-%m-%d').date() - (now or datetime.now()).date()).days
    except ValueError: return None
    return 'late' if d < 0 else 'today' if d == 0 else 'eve' if d == 1 else None


def due_line(task: dict, now: datetime = None) -> str:
    """The one sentence for where this task's due day stands ('' when it is not near) - the note on the task, the chat
    line, and what the Assistant says about it."""
    at, now = (task or {}).get('DueAt'), now or datetime.now()
    s = step(at, now)
    if s == 'eve': return "This one's due tomorrow, so it's at the top of your list."
    if s == 'today': return "This one's today."
    if s != 'late': return ''
    yday = (now - timedelta(days=1)).strftime('%Y-%m-%d') == str(at)[:10]
    return f"This was due {'yesterday' if yday else when(at, now)}. Want the note ready?"


def set_due(store, tid: int, day: str, actor: str = 'triage'):
    """The day this work is due. A new day starts its steps again; a closed task is left alone."""
    t = store.get_task(tid) or {}
    if not t or not day or t.get('Status') in ('done', 'dropped') or str(t.get('DueAt') or '') == day: return
    store.update_task(tid, {'DueAt': day}, actor)
    store._exec('UPDATE task SET DueSaid=NULL WHERE TaskId=?', (tid,))


def deadlines(store, now: datetime = None) -> int:
    """Each open task whose due day is near, said once per step: a note on the task (new activity, so it is back on the
    rail unread) and a line in the desktop chat. The day before and on the day it is urgent - the top of the list."""
    now, n = now or datetime.now(), 0
    for t in store._rows("SELECT * FROM task WHERE IFNULL(DueAt,'')<>'' AND Status NOT IN ('done','dropped')"):
        s = step(t['DueAt'], now)
        if not s or (t.get('DueSaid') in STEPS and STEPS.index(t['DueSaid']) >= STEPS.index(s)): continue
        line = due_line(t, now)
        if s in ('eve', 'today') and t.get('Priority') != 'urgent': store.update_task(t['TaskId'], {'Priority': 'urgent'}, 'assistant')
        store.add_comment(t['TaskId'], 'assistant', 'agent', line)
        from . import asks
        try: asks.say_due(store, t['TaskId'], line)
        except Exception as e: logger.warning(f"due day on {t['TaskId']} not said: {e}")
        store._exec('UPDATE task SET DueSaid=? WHERE TaskId=?', (s, t['TaskId'])); n += 1
    return n


_TICK = threading.Lock()


def tick(store, now: datetime = None) -> int:
    """Reminders and due days together - on app start, at the head of every sync (before the mail is read, so a slow
    catch-up never makes a reminder late) and on the asks watcher's five-minute sweep, so "today at 2:35" is not left
    for a sync half an hour off. One at a time: two lanes reading the same due row would file its note twice."""
    with _TICK:
        n = due(store, now)
        try: n += deadlines(store, now)
        except Exception as e: logger.warning(f'due days not checked: {e}')
    return n
