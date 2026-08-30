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

    def test_first_observation_waiting_pings_once_and_rearms_after_work(self):
        s = MemoryStore()
        s.set_setting('phone_approvals', '1', 't')
        tid = s.create_task({'Title': 'Fix notifications', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
        term = FakeTerm(tid, True, ['Which repository should I use?'])
        pings = []
        with mock.patch.dict(terminal.SESSIONS, {'sid': term}, clear=True), \
             mock.patch.object(outbound, 'notify', side_effect=lambda st, text: pings.append(text)):
            self.assertEqual(handraise.tick(s), 1)
            self.assertEqual(handraise.tick(s), 0)
            term._waiting = False
            self.assertEqual(handraise.tick(s), 0)
            term._waiting = True
            self.assertEqual(handraise.tick(s), 1)
        self.assertEqual(len(pings), 2)
        self.assertIn('codex asked you something', pings[0])
        self.assertIn('[tq0001]', pings[0])

    def test_notifications_off_consumes_the_transition_without_sending(self):
        s = MemoryStore(); s.set_setting('notify_level', 'off', 't')
        tid = s.create_task({'Title': 'quiet', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
        with mock.patch.dict(terminal.SESSIONS, {'sid': FakeTerm(tid, True, ['Done.'])}, clear=True), \
             mock.patch.object(outbound, 'notify') as notify:
            self.assertEqual(handraise.tick(s), 0)
        notify.assert_not_called()


if __name__ == '__main__': unittest.main()
