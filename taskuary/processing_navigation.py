"""Process-local automatic navigation admission; durable operation IDs belong to Phase 4.

The short commit lock coordinates this backend's navigation and New chat. It is
not a database transaction against external SQLite writers.
"""
from collections import OrderedDict
from contextlib import contextmanager
import hashlib
import json
import threading
import weakref


_states = weakref.WeakKeyDictionary()
_states_lock = threading.Lock()


class _State:
    def __init__(self):
        self.lock = threading.RLock()
        self.active = None
        self.consumed = OrderedDict()


def _state(store):
    with _states_lock:
        return _states.setdefault(store, _State())


def _chat(store):
    raw = store.get_settings().get('assistant_dock_task_id')
    task = store.get_task(int(raw)) if str(raw or '').isdigit() else None
    return (str(raw or ''), (task or {}).get('Status'))


def fields(store, capture):
    from .funnel_selection import selection_fields
    result = selection_fields(capture)
    binding = json.dumps([capture.revision, _chat(store)], separators=(',', ':'))
    result['selection_revision'] = hashlib.sha256(binding.encode()).hexdigest()
    return result


class NavigationStale(ValueError):
    def __init__(self, detail):
        message = {
            'navigation_in_progress': 'Another navigation is still running. Wait for it to finish.',
            'already_completed': 'This navigation already completed. Review the current conversation.',
            'outcome_uncertain': 'This navigation may have partly completed. Review the conversation before continuing.',
        }.get(detail.get('reason'), 'The next item changed. Review the refreshed list and try again.')
        super().__init__(message)
        self.detail = {'code': 'selection_stale', 'retryable': True, **detail}
        self.detail['message'] = message


def reserve(store, *, selection_revision, expected_next_key, expected_next_members,
            only=None, include_surfaced=False, exclude=None):
    from .funnel_selection import capture_selection
    state = _state(store)
    with state.lock:
        capture = capture_selection(store, only=only, include_surfaced=include_surfaced,
                                    exclude=exclude)
        fresh = fields(store, capture)
        if (selection_revision != fresh['selection_revision']
                or expected_next_key != fresh['expected_next_key']
                or expected_next_members != fresh['expected_next_members']):
            raise NavigationStale(fresh)
        if state.active is not None:
            raise NavigationStale({**fresh, 'reason': 'navigation_in_progress'})
        if selection_revision in state.consumed:
            raise NavigationStale({**fresh, 'reason': state.consumed[selection_revision],
                                   'retryable': False})
        reservation = Reservation(store, state, capture, selection_revision, _chat(store))
        state.active = reservation
        return reservation


class Reservation:
    def __init__(self, store, state, capture, token, chat):
        self.store, self.state, self.capture = store, state, capture
        self.token, self.chat = token, chat
        self.attempted_commit = False
        self.completed = False
        self.closed = False

    def run(self, action, actor='owner'):
        """The worker owns admission until it finishes, even if its client disconnects."""
        from . import general
        try:
            with self.state.lock:
                if _chat(self.store) != self.chat:
                    raise NavigationStale(fields(self.store, self.capture))
                # Initial stale requests never reach dock creation. An accepted request
                # may create an empty dock before model work; bind its identity now.
                dock, _ = general.dock_task(self.store, actor)
                self.chat = _chat(self.store)
            result = action(self.capture, self.commit_guard, dock)
            self.completed = True
            return result
        finally:
            self.close()

    @contextmanager
    def commit_guard(self):
        from .funnel_selection import recheck_selection, SelectionStale
        with self.state.lock:
            if self.closed or _chat(self.store) != self.chat:
                raise NavigationStale(fields(self.store, self.capture))
            try:
                recheck_selection(self.store, self.capture)
            except SelectionStale as error:
                raise NavigationStale({'reason': str(error)}) from error
            # A failed store call can have partially committed. Do not reopen that
            # token merely because response generation or delivery subsequently fails.
            self.attempted_commit = True
            yield

    def close(self):
        with self.state.lock:
            if self.closed:
                return
            self.closed = True
            if self.attempted_commit:
                self.state.consumed[self.token] = ('already_completed' if self.completed
                                                  else 'outcome_uncertain')
                while len(self.state.consumed) > 128:
                    self.state.consumed.popitem(last=False)
            if self.state.active is self:
                self.state.active = None


@contextmanager
def chat_change(store):
    """Serialize a New chat mutation with the short navigation commit group."""
    with _state(store).lock:
        yield
