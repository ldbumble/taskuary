"""Server-side hand raises: no browser, chat APIs, PTY, or clock required."""
import unittest
from unittest import mock

from taskuary import handraise, outbound, terminal
from taskuary.store import MemoryStore


class FakeTerm:
    def __init__(self, tid, waiting=False, tail=()):
        self.task_id, self.alive, self.agent = tid, True, 'codex'
        self.started, self._waiting, self._tail = '2026-08-30 12:00:00', waiting, list(tail)

    def waiting(self): return self._waiting
    def tail(self, n=3): return self._tail[-n:]


class ChatHandRaiseTests(unittest.TestCase):
    def setUp(self): handraise.reset()

    def test_a_hand_goes_up_once_per_wait_and_rearms_after_work(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
        term = FakeTerm(tid, True, ['Which repository should I use?'])
        with mock.patch.dict(terminal.SESSIONS, {'sid': term}, clear=True):
            self.assertEqual(handraise.tick(s), 1)
            self.assertEqual(handraise.tick(s), 0)
            term._waiting = False
            self.assertEqual(handraise.tick(s), 0)
            term._waiting = True
            self.assertEqual(handraise.tick(s), 1)


class TransitionsWakeTheViewsTests(unittest.TestCase):
    """A change only the screen saw writes no event, so nothing woke the Board or the task page (G7, 2026-10-20): every change of
    a live session's waiting or sub-state between two ticks is a task-changed, and a session that stays put is quiet."""
    def setUp(self): handraise.reset()

    def test_each_change_is_announced_once_and_a_steady_session_says_nothing(self):
        from taskuary import live
        s = MemoryStore()
        tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
        term = FakeTerm(tid, False, ['working'])
        with mock.patch.dict(terminal.SESSIONS, {'sid': term}, clear=True), mock.patch.object(live, 'emit') as emit:
            handraise.tick(s); handraise.tick(s)
            self.assertEqual(emit.call_count, 0)                    # first sight, then no change
            term._waiting = True; handraise.tick(s)
            emit.assert_called_once_with('task-changed', task_id=tid)
            handraise.tick(s); self.assertEqual(emit.call_count, 1)
            term._waiting = False; handraise.tick(s)
            self.assertEqual(emit.call_count, 2)


class NoPushTests(unittest.TestCase):
    """The notify pushes are gone (the owner, 2026-10-02: the phone chat speaks only when spoken to). The invariant, not a
    list of call sites: there is no push to call, and no setting that would choose what it sends."""
    def test_there_is_no_push_into_a_chat_any_more(self):
        import pathlib
        self.assertFalse(hasattr(outbound, 'notify') or hasattr(outbound, 'notify_targets'))
        self.assertNotIn('notify_level', (pathlib.Path(handraise.__file__).parent / 'settings_schema.json').read_text(encoding='utf-8'))


if __name__ == '__main__': unittest.main()
