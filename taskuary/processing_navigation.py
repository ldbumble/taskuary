"""New chat and the walk, one at a time.

The navigation reservation that lived here - a captured selection token, its commit check, NavigationStale and the "list
changed" retries (PW-050, PW-118) - is gone with the walk's one owner (railwalk, 2026-10-30): a press names the row the page
had on screen, and Next from a row is the same answer however often it is asked. What stays is the lock a New chat takes, so
it never lands in the middle of a walk move: the walk's own.
"""
from contextlib import contextmanager


@contextmanager
def chat_change(store):
    """Serialize a New chat with a walk move in flight (railwalk's lock): one waits for the other, never both at once."""
    from .railwalk import _LOCK
    with _LOCK:
        yield
