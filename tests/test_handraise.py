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


class NoPushTests(unittest.TestCase):
    """The notify pushes are gone (the owner, 2026-10-02: the phone chat speaks only when spoken to). The invariant, not a
    list of call sites: there is no push to call, and no setting that would choose what it sends."""
    def test_there_is_no_push_into_a_chat_any_more(self):
        import pathlib
        self.assertFalse(hasattr(outbound, 'notify') or hasattr(outbound, 'notify_targets'))
        self.assertNotIn('notify_level', (pathlib.Path(handraise.__file__).parent / 'settings_schema.json').read_text(encoding='utf-8'))


if __name__ == '__main__': unittest.main()
