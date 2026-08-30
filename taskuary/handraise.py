"""Server-side hand raises for live coding sessions.

The browser also watches sessions so it can show a toast and play a sound. This watcher is the
independent path to Telegram/WhatsApp/Teams: it still runs when no browser is open, notices a
fast question on its first look, and emits once per working-to-waiting cycle.
"""
from loguru import logger

from .store import task_ref


_state = {}


def _identity(sid, term) -> str:
    return f'{sid}:{getattr(term, "started", "") or id(term)}'


def _line(term, waitroom) -> str:
    lines = [str(x).strip() for x in term.tail(6) if str(x).strip()]
    questions = [x for x in lines if waitroom.looks_like_question([x])]
    return (questions[-1] if questions else lines[-1])[:300] if lines else ''


def tick(store) -> int:
    """Push newly waiting sessions to notify chats. Returns the number of events attempted;
    outbound.notify owns per-connector delivery errors and never lets this clock fail."""
    from . import outbound, phone, terminal, waitroom
    global _state
    current, events = {}, []
    for sid, term in list(terminal.SESSIONS.items()):
        if not getattr(term, 'alive', False) or not getattr(term, 'task_id', None): continue
        ident = _identity(sid, term)
        waiting = term.waiting() if hasattr(term, 'waiting') else terminal.waiting_of(term)
        current[ident] = bool(waiting)
        if waiting and not _state.get(ident):
            asking = waitroom.looks_like_question(term.tail(waitroom.TAIL_LINES))
            events.append((term, asking, _line(term, waitroom)))
    _state = current

    if store.get_settings().get('notify_level', 'needs_me') == 'off': return 0
    for term, asking, tail in events:
        tid = int(term.task_id)
        task = store.get_task(tid) or {}
        agent = getattr(term, 'agent', None) or getattr(term, 'label', None) or 'agent'
        what = f'{agent} asked you something' if asking else f'{agent} stopped and is waiting on you'
        detail = f'\n\n{tail}' if tail else ''
        try:
            outbound.notify(store, f'{task_ref(tid)} · {what}: {task.get("Title") or "untitled"}'
                             f'{detail}{phone.task_ping_tail(store, tid)}')
        except Exception as e:
            logger.warning(f'hand raise: {task_ref(tid)}: {e}')
    return len(events)


def reset():
    """Discard process-local transition history (used by tests and deliberate restarts)."""
    global _state
    _state = {}
