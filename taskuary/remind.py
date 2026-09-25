"""Remind me: an open task put away until a day, then back on the work rail that morning.

The owner, 2026-09-25: Tomorrow and Later are gone - Next on open work comes back after a few hours - and
"bring this back in two weeks" is a date on the TASK. Until it, the task is Upcoming (the Tasks tab's own
filter) and off the rail and the walk; on the day it is back at MORNING, saying it was asked for. One
road for the task page's picker, the Assistant's tool (task.defer) and the typed words.
"""
import re
from datetime import datetime, timedelta

MORNING = '07:00:00'
NONE_WORDS = ('', 'none', 'never', 'clear', 'off', 'no')


def parse(until, now: datetime = None) -> str | None:
    """'2026-10-09', '2 weeks', '3 days', 'tomorrow', 'monday' -> 'YYYY-MM-DD 07:00:00'; None clears it.
    Raises ValueError for anything else, and for a day that is not after today."""
    now = now or datetime.now()
    s = str(until or '').strip().lower()
    if s in NONE_WORDS: return None
    m = re.fullmatch(r'(\d{4}-\d{2}-\d{2})(?:[ t].*)?', s)
    if m: day = datetime.strptime(m.group(1), '%Y-%m-%d')
    elif s == 'tomorrow': day = now + timedelta(days=1)
    elif m := re.fullmatch(r'(?:in\s+)?(\d+|a|an|one|two|three|four)\s+(day|week|month)s?', s):
        n = {'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4}.get(m.group(1)) or int(m.group(1))
        day = now + timedelta(days=n * {'day': 1, 'week': 7, 'month': 30}[m.group(2)])
    elif s.rstrip('s') in DAYS:
        ahead = (DAYS.index(s.rstrip('s')) - now.weekday()) % 7 or 7
        day = now + timedelta(days=ahead)
    else: raise ValueError(f'"{until}" is not a day I can read - say a date (2026-10-09) or "in 2 weeks"')
    if day.date() <= now.date(): raise ValueError('pick a day after today')
    return f"{day:%Y-%m-%d} {MORNING}"

DAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')


def when(remind_at) -> str:
    """'Thu 9 Oct' - the day as the page and the receipt say it."""
    try: d = datetime.strptime(str(remind_at)[:10], '%Y-%m-%d')
    except ValueError: return str(remind_at or '')
    return f"{d:%a} {d.day} {d:%b}"


def waiting(task: dict, now: datetime = None) -> bool:
    """Put away and not due yet - Upcoming, off the rail."""
    r = str((task or {}).get('RemindAt') or '')
    return bool(r) and (task or {}).get('Status') not in ('done', 'dropped') and r > f"{now or datetime.now():%Y-%m-%d %H:%M:%S}"


def set_reminder(store, tid: int, until, actor: str = 'owner') -> dict:
    """Put the task away until `until` (or bring it back now with none). The receipt carries the undo."""
    t = store.get_task(tid)
    if not t: raise ValueError('task not found')
    if t.get('Status') in ('done', 'dropped'): raise ValueError('that task is done - reopen it first')
    at, prev = parse(until), t.get('RemindAt') or None
    store.update_task(tid, {'RemindAt': at or ''}, actor)
    store.audit('task', tid, 'remind', actor, detail={'from': prev, 'to': at})
    return {'taskId': tid, 'remindAt': at, 'when': when(at) if at else '',
            'undo': {'kind': 'task.defer', 'target': tid, 'params': {'until': prev[:10] if prev else 'none'},
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
        store.update_task(t['TaskId'], {'RemindAt': ''}, 'assistant')
    return n
