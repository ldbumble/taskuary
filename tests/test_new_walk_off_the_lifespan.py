"""A relaunch opens a new chat (retire_dock + funnel.reset_walk) on a thread, not in the lifespan (P11).

In the lifespan it cost 629 ms the first call and up to 1,061 ms on the owner's machine, every launch, before
uvicorn would accept the window's first connection. Off it, the one rule is that nothing sees the OLD walk:
every /api read waits for the new one, and so do the clocks and the catch-up.
"""
import threading, time, unittest
from unittest import mock
from fastapi.testclient import TestClient

from taskuary import funnel, general, server
from taskuary.processing_unread import WALK_KEY
from taskuary.store import MemoryStore


class NewWalkIsOffTheWindowsPathTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.s.set_setting(WALK_KEY, 'yesterday', 't')
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.gate = threading.Event()
        self.addCleanup(server._WALK_READY.set); self.addCleanup(self.gate.set)

    def _slow_reset(self):
        """The real reset's effect, held until the test lets it go."""
        def reset(store): self.gate.wait(10); store.set_setting(WALK_KEY, 'new chat', 'system')
        return mock.patch.object(general, 'retire_dock', return_value=1), mock.patch.object(funnel, 'reset_walk', reset)

    def test_a_pile_read_before_the_reset_finishes_waits_and_then_sees_the_new_walk(self):
        got = {}
        retire, reset = self._slow_reset()
        with retire, reset, mock.patch.object(server, '_pile_payload', lambda *a, **k: {'walk': self.s.get_setting(WALK_KEY)}):
            t = server._start_new_walk()
            c = TestClient(server.app)
            reader = threading.Thread(target=lambda: got.update(c.get('/api/funnel/pile').json())); reader.start()
            time.sleep(.3)
            self.assertEqual(got, {}, 'the rail was answered from the old walk')
            self.assertEqual(c.get('/api/health').status_code, 200)       # the desktop's "is it up" never waits
            self.gate.set(); t.join(10); reader.join(10)
        self.assertEqual(got, {'walk': 'new chat'})

    def test_the_lifespan_does_not_wait_for_the_reset(self):
        retire, reset = self._slow_reset()
        with retire, reset:
            t0 = time.monotonic(); t = server._start_new_walk(); took = time.monotonic() - t0
            self.assertLess(took, .5); self.assertFalse(server._WALK_READY.is_set())
            self.gate.set(); t.join(10)
        self.assertTrue(server._WALK_READY.is_set())
        self.assertEqual(self.s.get_setting(WALK_KEY), 'new chat')

    def test_a_failed_reset_still_lets_the_app_in(self):
        with mock.patch.object(general, 'retire_dock', side_effect=RuntimeError('locked')):
            server._start_new_walk().join(10)
        self.assertTrue(server._WALK_READY.is_set())

    def _once(self, order):
        def push(s): order.append(('chat', s.get_setting(WALK_KEY))); raise SystemExit   # one tick of the chat clock, then out
        return push

    def test_the_catch_up_and_the_chat_clocks_start_behind_the_new_walk(self):
        order = []
        retire, reset = self._slow_reset()
        self.s.set_setting('startup_sync_days', '1', 't')
        with retire, reset, mock.patch.object(server, '_heal_ended'), mock.patch.object(server, 'report_pass'), \
             mock.patch('taskuary.learn.reflect_if_due'), \
             mock.patch.object(server, '_poll_reports', lambda *a, **k: order.append(('mail', self.s.get_setting(WALK_KEY)))), \
             mock.patch('taskuary.remote_assistant.push_alerts', side_effect=self._once(order)):
            w = server._start_new_walk(); catch = server.catch_up_on_startup()
            chat = threading.Thread(target=lambda: self.assertRaises(SystemExit, server.quick_forever)); chat.start()
            time.sleep(.3)
            self.assertEqual(order, [], 'read before the new chat existed')
            self.gate.set(); w.join(10); catch.join(10); chat.join(10)
        self.assertCountEqual(order, [('mail', 'new chat'), ('chat', 'new chat')])


if __name__ == '__main__':
    unittest.main()
