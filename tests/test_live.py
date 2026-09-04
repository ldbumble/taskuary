"""The UI listens on one socket instead of asking every few seconds.

feed-changed / task-changed / run-tail are invalidation, not payloads: the tab already
knows how to GET /api/feed with an ETag. emit() is safe from a worker thread (the poll,
a pty byte) because the fan-out hops onto the asyncio loop that owns the sockets.
"""
import asyncio, time, unittest

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


async def _await_kind(tab, kind, n=1, seconds=2.0):
    """The timer thread plus run_coroutine_threadsafe is not a 40ms sleep. CI hosts
    miss a single short wait; poll until the fan-out lands."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        got = [m for m in tab.sent if m.get('type') == kind]
        if len(got) >= n:
            return got
        await asyncio.sleep(0.01)
    return [m for m in tab.sent if m.get('type') == kind]


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

    def test_a_task_update_pokes_the_feed_and_task_views(self):
        tab, s = _Tab(), MemoryStore()
        async def once():
            live.bind(asyncio.get_running_loop())
            live.attach(tab)
            try:
                tid = s.create_task({'Title': 'live-task', 'Status': 'open'}, 't')
                live.flush(); await asyncio.sleep(0); tab.sent.clear()
                s.update_task(tid, {'Status': 'done'}, 't')
                live.flush()
                await _await_kind(tab, 'feed-changed')
                await _await_kind(tab, 'task-changed')
                return {m['type'] for m in tab.sent}
            finally:
                live.reset()
        self.assertEqual(_run(once()), {'feed-changed', 'task-changed'})

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

    def test_later_writes_ride_the_open_window(self):
        """Sliding debounce spawned a thread per emit and cancelled it; a fixed window
        keeps the first timer and only updates the payload."""
        dummy = object()
        live.attach(dummy)
        try:
            live.emit('feed-changed', message_id=1)
            first = live._timers['feed-changed']
            live.emit('feed-changed', message_id=2)
            self.assertIs(live._timers.get('feed-changed'), first)
            self.assertEqual(live._pending['feed-changed']['message_id'], 2)
        finally:
            live.reset()

    def test_the_timer_folds_a_burst_into_one(self):
        """Delivery tests used to call flush() and never wait out the timer. A burst
        inside one window must still land as a single event on the timer path."""
        tab = _Tab()
        orig = dict(live._DELAY)
        live._DELAY[live.FEED] = 0.04
        async def once():
            live.bind(asyncio.get_running_loop())
            live.attach(tab)
            try:
                live.emit('feed-changed', message_id=1)
                live.emit('feed-changed', message_id=2)
                live.emit('feed-changed', message_id=3)
                return await _await_kind(tab, 'feed-changed')
            finally:
                live.reset()
        try:
            events = _run(once())
        finally:
            live._DELAY.clear()
            live._DELAY.update(orig)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['message_id'], 3)

    def test_sustained_writes_deliver_during_the_stream(self):
        """A write every 20ms into a 50ms window used to re-arm forever and deliver 0
        until the stream paused. The Studio tail (pty poke 200ms, delay 250ms) froze
        for the same reason. A fixed window must flush while the writes are still coming."""
        tab = _Tab()
        orig = dict(live._DELAY)
        live._DELAY[live.FEED] = 0.05
        live._DELAY[live.RUN] = 0.05
        async def once():
            live.bind(asyncio.get_running_loop())
            live.attach(tab)
            try:
                i = 0
                until = time.monotonic() + 0.6
                while time.monotonic() < until:
                    live.emit('feed-changed', message_id=i)
                    live.emit('run-tail', run_id=i)
                    i += 1
                    await asyncio.sleep(0.02)
                    if (any(m.get('type') == 'feed-changed' for m in tab.sent)
                            and any(m.get('type') == 'run-tail' for m in tab.sent)):
                        break
                during = list(tab.sent)
                more = time.monotonic() + 0.15
                while time.monotonic() < more:
                    live.emit('feed-changed', message_id=i)
                    live.emit('run-tail', run_id=i)
                    i += 1
                    await asyncio.sleep(0.02)
                # A threading.Timer on a loaded runner can slide past _await_kind's window: this
                # failed only ever on macos-latest, with one delivery instead of two, while the
                # during-the-stream assertions below (the actual regression guard) passed. flush()
                # is the module's own affordance for exactly this - deliver what the burst left
                # pending instead of racing the clock for it.
                live.flush()
                await _await_kind(tab, 'feed-changed', n=max(2, len([m for m in during if m.get('type') == 'feed-changed']) + 1))
                return during, list(tab.sent)
            finally:
                live.reset()
        try:
            during, after = _run(once())
        finally:
            live._DELAY.clear()
            live._DELAY.update(orig)
        feed_during = [m for m in during if m.get('type') == 'feed-changed']
        run_during = [m for m in during if m.get('type') == 'run-tail']
        self.assertGreaterEqual(len(feed_during), 1,
            'sliding debounce would deliver nothing until the stream paused')
        self.assertGreaterEqual(len(run_during), 1,
            'run-tail must reach the Studio while the pty is still printing')
        self.assertGreaterEqual(len([m for m in after if m.get('type') == 'feed-changed']), 2)
        self.assertGreaterEqual(len([m for m in after if m.get('type') == 'run-tail']), 2)

    def test_a_closed_loop_is_a_noop(self):
        """The poll thread can emit after a TestClient's asyncio.run has finished. That used
        to surface as 'Event loop is closed' on the next test."""
        tab = _Tab()
        async def once():
            live.bind(asyncio.get_running_loop())
            live.attach(tab)
        _run(once())
        live.emit('feed-changed', message_id=1)   # loop is gone
        live.flush()                              # must not raise

    def test_a_dead_tab_is_dropped(self):
        class Dead:
            async def send_json(self, msg):
                raise RuntimeError('gone')
        dead = Dead()
        async def once():
            live.bind(asyncio.get_running_loop())
            live.attach(dead)
            live.emit('feed-changed', message_id=1)
            live.flush()
            for _ in range(20):
                await asyncio.sleep(0)
                if dead not in live._clients: break
        _run(once())
        self.assertNotIn(dead, live._clients)

    def test_a_worker_thread_reaches_the_tab(self):
        """The mailbox clock and a pty byte both emit off the asyncio thread."""
        import threading
        tab = _Tab()
        async def once():
            live.bind(asyncio.get_running_loop())
            live.attach(tab)
            def poke():
                live.emit('run-tail', run_id=3)
                live.flush()
            threading.Thread(target=poke).start()
            for _ in range(40):
                await asyncio.sleep(0.01)
                if any(m.get('type') == 'run-tail' for m in tab.sent): break
        _run(once())
        self.assertIn('run-tail', [m['type'] for m in tab.sent])

    def test_feed_and_task_coalesce_separately(self):
        dummy = object()
        live.attach(dummy)
        try:
            live.emit('feed-changed', message_id=1)
            live.emit('task-changed', task_id=2)
            live.emit('feed-changed', message_id=9)
            self.assertEqual(live._pending['feed-changed']['message_id'], 9)
            self.assertEqual(live._pending['task-changed']['task_id'], 2)
        finally:
            live.detach(dummy)

    def test_ingest_status_pokes_the_timeline(self):
        tab, s = _Tab(), MemoryStore()
        async def once():
            live.bind(asyncio.get_running_loop())
            live.attach(tab)
            try:
                s.set_setting('ingest_status', '{"state":"running"}', 't')
                live.flush()
                for _ in range(20):
                    await asyncio.sleep(0)
                    if any(m.get('type') == 'feed-changed' for m in tab.sent): break
            finally:
                live.reset()
        _run(once())
        self.assertIn('feed-changed', [m['type'] for m in tab.sent])

    def test_a_run_pokes_the_studio(self):
        tab, s = _Tab(), MemoryStore()
        async def once():
            live.bind(asyncio.get_running_loop())
            live.attach(tab)
            try:
                tid = s.create_task({'Title': 'run-poke', 'Status': 'open'}, 't')
                live.flush()
                tab.sent.clear()
                s.start_run(tid, 'coder', 'go', 't')
                live.flush()
                for _ in range(20):
                    await asyncio.sleep(0)
                    if any(m.get('type') == 'run-tail' for m in tab.sent): break
            finally:
                live.reset()
        _run(once())
        kinds = [m['type'] for m in tab.sent]
        self.assertIn('run-tail', kinds)
        self.assertIn('task-changed', kinds)

    def test_review_writes_poke_the_message_and_task(self):
        """A background draft can finish after the event that created its review. The
        completed text must wake both views now that neither one polls."""
        tab, s = _Tab(), MemoryStore()
        async def once():
            live.bind(asyncio.get_running_loop())
            live.attach(tab)
            try:
                tid = s.create_task({'Title': 'reply', 'Status': 'waiting'}, 't')
                mid = s.add_message({'external_id': 'review-poke', 'channel': 'email',
                                     'subject': 'question', 'body': 'can you help?',
                                     'task_id': tid, 'status': 'routed'})
                live.flush(); await asyncio.sleep(0); tab.sent.clear()
                rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft',
                                    'Status': 'pending'})
                live.flush()
                await _await_kind(tab, 'feed-changed')
                await _await_kind(tab, 'task-changed')
                created = {m['type'] for m in tab.sent}
                tab.sent.clear()
                s.update_review_draft(rid, 'Yes.', None)
                live.flush()
                await _await_kind(tab, 'feed-changed')
                await _await_kind(tab, 'task-changed')
                drafted = {m['type'] for m in tab.sent}
                return created, drafted
            finally:
                live.reset()
        created, drafted = _run(once())
        self.assertEqual(created, {'feed-changed', 'task-changed'})
        self.assertEqual(drafted, {'feed-changed', 'task-changed'})

    def test_deleting_a_task_pokes_the_feed_and_task_views(self):
        tab, s = _Tab(), MemoryStore()
        async def once():
            live.bind(asyncio.get_running_loop())
            live.attach(tab)
            try:
                tid = s.create_task({'Title': 'not work', 'Status': 'open'}, 't')
                s.add_message({'external_id': 'delete-poke', 'channel': 'email',
                               'subject': 'fyi', 'body': 'nothing to do',
                               'task_id': tid, 'status': 'routed'})
                live.flush(); await asyncio.sleep(0); tab.sent.clear()
                s.delete_task(tid)
                live.flush()
                await _await_kind(tab, 'feed-changed')
                await _await_kind(tab, 'task-changed')
                return {m['type'] for m in tab.sent}
            finally:
                live.reset()
        self.assertEqual(_run(once()), {'feed-changed', 'task-changed'})


class EventsSocketTests(unittest.TestCase):
    """The real FastAPI socket, not the bus unit tests above."""

    def tearDown(self):
        live.reset()

    def test_the_events_socket_says_hello(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        saved = server.cfg['server'].pop('token', None)
        try:
            with TestClient(server.app) as c:
                with c.websocket_connect('/api/events/ws') as ws:
                    self.assertEqual(ws.receive_json()['type'], 'hello')
                    server.store.create_task({'Title': 'ws-task', 'Status': 'open'}, 't')
                    live.flush()
                    self.assertEqual(ws.receive_json()['type'], 'task-changed')
        finally:
            if saved is not None:
                server.cfg['server']['token'] = saved

    def test_the_events_socket_wants_the_same_token_as_the_rest(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        from starlette.websockets import WebSocketDisconnect
        server.cfg['server']['token'] = 's3cret'
        try:
            with TestClient(server.app) as c:
                with self.assertRaises(WebSocketDisconnect):
                    with c.websocket_connect('/api/events/ws') as ws:
                        ws.receive_json()
                with c.websocket_connect('/api/events/ws?token=s3cret') as ws:
                    self.assertEqual(ws.receive_json()['type'], 'hello')
        finally:
            server.cfg['server'].pop('token', None)


if __name__ == '__main__':
    unittest.main()
