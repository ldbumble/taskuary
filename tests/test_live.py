"""The UI listens on one socket instead of asking every few seconds.

feed-changed / task-changed / run-tail are invalidation, not payloads: the tab already
knows how to GET /api/feed with an ETag. emit() is safe from a worker thread (the poll,
a pty byte) because the fan-out hops onto the asyncio loop that owns the sockets.
"""
import asyncio, unittest

from taskuary import live
from taskuary.store import MemoryStore


class _Tab:
    """A socket the bus can send_json to, without standing up FastAPI."""
    def __init__(self):
        self.sent = []
    async def send_json(self, msg):
        self.sent.append(msg)
    async def receive_text(self):
        await asyncio.Event().wait()


def _run(coro):
    return asyncio.run(coro)


class LiveSocketTests(unittest.TestCase):
    def setUp(self):
        live.reset()

    def tearDown(self):
        live.reset()

    def test_serve_says_hello(self):
        tab = _Tab()
        async def once():
            t = asyncio.create_task(live.serve(tab))
            try:
                for _ in range(20):
                    await asyncio.sleep(0)
                    if tab.sent: break
            finally:
                t.cancel()
                try: await t
                except (asyncio.CancelledError, Exception): pass
                live.reset()
        _run(once())
        self.assertEqual(tab.sent[0]['type'], 'hello')

    def test_a_write_reaches_the_tab(self):
        tab, s = _Tab(), MemoryStore()
        async def once():
            live.bind(asyncio.get_running_loop())
            live.attach(tab)
            try:
                mid = s.add_message({
                    'external_id': 'live-sock-1', 'channel': 'email', 'subject': 'hi',
                    'body': 'there', 'from_email': 'a@b.c', 'status': 'feed'})
                live.flush()
                for _ in range(20):
                    await asyncio.sleep(0)
                    if any(m.get('type') == 'feed-changed' for m in tab.sent): break
                return mid
            finally:
                live.reset()
        mid = _run(once())
        self.assertIn('feed-changed', [m['type'] for m in tab.sent])
        self.assertTrue(mid)

    def test_a_task_write_reaches_the_tab(self):
        tab, s = _Tab(), MemoryStore()
        async def once():
            live.bind(asyncio.get_running_loop())
            live.attach(tab)
            try:
                tid = s.create_task({'Title': 'live-task', 'Status': 'open'}, 't')
                live.flush()
                for _ in range(20):
                    await asyncio.sleep(0)
                    if any(m.get('type') == 'task-changed' for m in tab.sent): break
                return tid
            finally:
                live.reset()
        tid = _run(once())
        self.assertIn('task-changed', [m['type'] for m in tab.sent])
        self.assertTrue(tid)

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

    def test_no_listeners_means_no_timer(self):
        """A poll writing forty rows must not spawn forty Timers when nobody has the UI open."""
        live.emit('feed-changed', message_id=1)
        self.assertEqual(live._pending, {})
        self.assertEqual(live._timers, {})


if __name__ == '__main__':
    unittest.main()
