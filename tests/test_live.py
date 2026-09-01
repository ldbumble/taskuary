"""The UI listens on one socket instead of asking every few seconds.

emit() is safe from a worker thread because the fan-out hops onto the asyncio loop
that owns the sockets. Unknown kinds are ignored so a typo cannot wedge the queue.
"""
import unittest

from taskuary import live


class LiveBusTests(unittest.TestCase):
    def tearDown(self):
        live.reset()

    def test_unknown_kinds_are_dropped(self):
        live.emit('not-a-kind')
        live.flush()          # must not raise, must not send

    def test_coalesce_folds_a_burst_into_one(self):
        dummy = object()
        live.attach(dummy)
        try:
            live.emit('feed-changed', message_id=1)
            live.emit('feed-changed', message_id=2)
            self.assertEqual(live._pending['feed-changed']['message_id'], 2)
            live.flush()
            self.assertEqual(live._pending, {})
        finally:
            live.detach(dummy)


if __name__ == '__main__':
    unittest.main()
