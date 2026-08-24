""""Auto-syncs every 10 min" has to be true when nobody is looking.

It was not. The only clock was a setInterval inside the Timeline tab, so it stopped the
moment you opened Board or Tasks (that tab unmounts), it restarted its ten minutes every time
a filter changed the effect's dependencies, and with the window closed nothing polled at all.
Scheduled reports rode on the same pass, so a report set for 8am Monday only ran if somebody
happened to be sitting on the Timeline at 8am on Monday. The clock belongs to the server.
"""
import time, unittest
from unittest import mock

from taskuary import server


class ClockTests(unittest.TestCase):
    def setUp(self):
        self._saved = server.store.get_settings().get('poll_minutes')
        self.addCleanup(lambda: server.store.set_setting('poll_minutes', self._saved or '10', 't'))

    def _one_cycle(self):
        """Run exactly one pass of the forever-loop: sleep is outside its try, so raising there
        leaves the loop without swallowing the exception."""
        with mock.patch.object(server, '_poll_reports') as poll, \
             mock.patch.object(server.time, 'sleep', side_effect=StopIteration):
            with self.assertRaises(StopIteration): server.poll_forever()
        return poll

    def test_it_polls_once_the_interval_has_passed(self):
        server.store.set_setting('poll_minutes', '10', 't')
        server._LAST_POLL[0] = time.time() - 700          # eleven minutes ago
        self._one_cycle().assert_called_once()

    def test_it_does_not_poll_before_the_interval_is_up(self):
        server.store.set_setting('poll_minutes', '10', 't')
        server._LAST_POLL[0] = time.time() - 60           # one minute ago
        self._one_cycle().assert_not_called()

    def test_zero_turns_background_polling_off(self):
        """A local app that reaches into somebody's mailbox on a timer needs an off switch."""
        server.store.set_setting('poll_minutes', '0', 't')
        server._LAST_POLL[0] = time.time() - 86400        # a day ago, and still no
        self._one_cycle().assert_not_called()

    def test_a_junk_interval_falls_back_to_ten_rather_than_stopping(self):
        server.store.set_setting('poll_minutes', 'soon', 't')
        server._LAST_POLL[0] = time.time() - 700
        self._one_cycle().assert_called_once()

    def test_a_manual_sync_resets_the_clock(self):
        """Otherwise pressing Sync now is followed moments later by an automatic poll over the
        same watermarks - which is what the old timestamp guard existed to stop."""
        server._LAST_POLL[0] = time.time() - 86400
        with mock.patch.object(server, 'poll_channels', create=True), \
             mock.patch.object(server, 'run_due_reports'):
            server._poll_reports(0)
        self.assertLess(time.time() - server._LAST_POLL[0], 5)

    def test_a_failing_cycle_never_ends_the_loop(self):
        """One bad poll must not leave the app with no clock for the rest of the session."""
        server.store.set_setting('poll_minutes', '10', 't')
        server._LAST_POLL[0] = time.time() - 700
        with mock.patch.object(server, '_poll_reports', side_effect=RuntimeError('mailbox down')), \
             mock.patch.object(server.time, 'sleep', side_effect=StopIteration) as slept:
            with self.assertRaises(StopIteration): server.poll_forever()
        slept.assert_called_once()          # it reached the sleep, so the next cycle would come

    def test_the_cadence_is_published_so_the_caption_can_stop_guessing(self):
        from fastapi.testclient import TestClient
        server.store.set_setting('poll_minutes', '4', 't')
        self.assertEqual(TestClient(server.app).get('/api/ingest/status').json()['everyMinutes'], 4)


if __name__ == '__main__':
    unittest.main()
