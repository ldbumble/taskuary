"""The UI listens on one socket instead of asking every few seconds.

feed-changed / task-changed / run-tail are invalidation, not payloads: the tab already
knows how to GET /api/feed with an ETag. emit() is safe from a worker thread (the poll,
a pty byte) because the fan-out hops onto the asyncio loop that owns the sockets.
"""
import unittest

from fastapi.testclient import TestClient

from taskuary import live, server


class LiveSocketTests(unittest.TestCase):
    def tearDown(self):
        live.reset()
    def test_a_write_reaches_the_tab(self):
        with TestClient(server.app) as c:
            with c.websocket_connect('/api/events/ws') as ws:
                self.assertEqual(ws.receive_json()['type'], 'hello')
                mid = server.store.add_message({
                    'external_id': 'live-sock-1', 'channel': 'email', 'subject': 'hi',
                    'body': 'there', 'from_email': 'a@b.c', 'status': 'feed'})
                live.flush()
                kinds = [ws.receive_json()['type']]
                for _ in range(3):
                    if 'feed-changed' in kinds: break
                    kinds.append(ws.receive_json()['type'])
                self.assertIn('feed-changed', kinds)
                self.assertTrue(mid)

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
