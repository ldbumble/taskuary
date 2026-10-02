"""Server-side hand raises for live coding sessions.

The browser watches sessions too, for its toast and sound. This watcher runs with no browser open: it turns a question
only the screen shows into a real request (so the rail, the walk and the phone card all see it) and counts each
working-to-waiting cycle once. It PUSHES nothing - the notify pings it used to send are gone (the owner, 2026-10-02:
the phone chat speaks only when spoken to; an agent's question reaches you on the walk).
"""
from loguru import logger


_state = {}


def _identity(sid, term) -> str:
    return f'{sid}:{getattr(term, "started", "") or id(term)}'


def tick(store) -> int:
    """Note the sessions that just went from working to waiting. Returns how many hands went up."""
    from . import terminal, workerstate as ws
    global _state
    current, events = {}, []
    for sid, term in list(terminal.SESSIONS.items()):
        if not getattr(term, 'alive', False) or not getattr(term, 'task_id', None): continue
        ident = _identity(sid, term)
        # the run's own word first (workerstate.py, PW-228): an open request is the hand, a working run raises
        # none however quiet its screen; a run whose word is silent - it never reported, or its turn just
        # ended - keeps the screen heuristic, and a question ON the screen raises a hand whatever the word
        # says (terminal.worker_fields). One rule, so the hand and the card never disagree.
        # ...and a chooser the CLI never reported becomes a real request first, so the hand that goes
        # up carries the question and its answers rather than four lines of screen (workerstate)
        try: ws.reconcile_screen_request(store, term, terminal.screen_asking(term))
        except Exception as e: logger.debug(f'screen question for {sid}: {e}')
        fields = terminal.worker_fields(store, term)
        current[ident] = bool(fields['waiting'])
        if fields['waiting'] and not _state.get(ident): events.append(term)
    _state = current
    return len(events)


def reset():
    """Discard process-local transition history (used by tests and deliberate restarts)."""
    global _state
    _state = {}
