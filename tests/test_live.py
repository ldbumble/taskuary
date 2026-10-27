"""The UI listens on one socket instead of asking every few seconds.

feed-changed / task-changed / run-tail are invalidation, not payloads: the tab already
knows how to GET /api/feed with an ETag. emit() is safe from a worker thread (the poll,
a pty byte) because the fan-out hops onto the asyncio loop that owns the sockets.
"""
import asyncio, time, unittest
from unittest import mock

from taskuary import funnel, live
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


class _Clock:
    """threading.Timer on a clock the test turns by hand: a debounce window opens at one advance() and closes at the
    advance() that passes its delay, whatever the host's load. A fired timer runs on the caller's thread, as the real
    one would on its own."""
    def __init__(self): self.now,self.timers = 0.0,[]
    def Timer(self, interval, fn):
        clock = self
        class _T:
            daemon = True
            def __init__(t): t.at,t.fn,t.dead = None,fn,False
            def start(t): t.at = clock.now+interval; clock.timers.append(t)
            def cancel(t): t.dead = True
        return _T()
    def advance(self, dt):
        self.now += dt
        due = sorted((t for t in self.timers if not t.dead and t.at <= self.now+1e-9), key=lambda t: t.at)
        self.timers = [t for t in self.timers if t not in due and not t.dead]
        for t in due: t.fn()


async def _turns(n=5):
    """A fired window reaches the tab through run_coroutine_threadsafe: a callback, then the fan-out task. A few turns
    of the loop land it; no wall clock is involved."""
    for _ in range(n): await asyncio.sleep(0)


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

    def test_a_feed_or_task_write_invalidates_the_expensive_assistant_pile(self):
        s = MemoryStore()
        funnel._CACHE.update(at=time.time(), pile={'rev': 'old'})
        s.create_task({'Title': 'new work', 'Status': 'open'}, 't')
        self.assertIsNone(funnel._CACHE['pile'])

    def test_a_setting_the_owner_changed_invalidates_that_pile_too(self):
        """A setting is an INPUT to the pile (mutes, feed_days, the owner's own address), so leaving the
        cache alone meant a change the owner just made showed up to thirty seconds later, or on the next
        New chat (2026-09-10 audit). The ephemeral clocks are exempt: they are written constantly and
        no projection reads them."""
        s = MemoryStore()
        funnel._CACHE.update(at=time.time(), pile={'rev': 'old'})
        s.set_setting('feed_days', '30', 'owner')
        self.assertIsNone(funnel._CACHE['pile'])
        funnel._CACHE.update(at=time.time(), pile={'rev': 'old'})
        s.set_setting('ingest_status', '{"stage": "reading Outlook"}', 'owner')
        self.assertEqual(funnel._CACHE['pile'], {'rev': 'old'})       # a progress clock rebuilds nothing

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
        # The windows run on a hand-turned clock. On real threading.Timers a loaded macOS runner failed this twice: the stream
        # loop raced a 0.6 s wall-clock budget, and then the second run-tail was still in its timer thread when the test, which
        # waited only for feed-changed, took its snapshot ("1 not greater than or equal to 2"). Now every write is 20ms after
        # the last by construction, a window closes exactly when its delay has passed, and both kinds are counted after the
        # same turns of the loop - a debounce that re-arms on each write still never fires while they keep coming.
        tab, clock = _Tab(), _Clock()
        orig = dict(live._DELAY)
        live._DELAY[live.FEED] = 0.05
        live._DELAY[live.RUN] = 0.05
        kinds = lambda sent, k: [m for m in sent if m.get('type') == k]
        async def once():
            live.bind(asyncio.get_running_loop())
            live.attach(tab)
            try:
                i = 0
                async def write():
                    nonlocal i
                    live.emit('feed-changed', message_id=i)
                    live.emit('run-tail', run_id=i)
                    i += 1
                    clock.advance(0.02)
                    await _turns()
                for _ in range(30):             # 600ms of stream, the budget the wall-clock version had
                    await write()
                    if kinds(tab.sent, 'feed-changed') and kinds(tab.sent, 'run-tail'): break
                during = list(tab.sent)
                # the stream KEEPS going after the first delivery, so a second window opens and closes while it does
                for _ in range(3): await write()
                return during, list(tab.sent)
            finally:
                live.reset()
        try:
            with mock.patch.object(live.threading, 'Timer', clock.Timer):
                during, after = _run(once())
        finally:
            live._DELAY.clear()
            live._DELAY.update(orig)
        self.assertGreaterEqual(len(kinds(during, 'feed-changed')), 1,
            'sliding debounce would deliver nothing until the stream paused')
        self.assertGreaterEqual(len(kinds(during, 'run-tail')), 1,
            'run-tail must reach the Studio while the pty is still printing')
        self.assertGreaterEqual(len(kinds(after, 'feed-changed')), 2)
        self.assertGreaterEqual(len(kinds(after, 'run-tail')), 2)

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

    def test_one_window_names_every_task_it_touched(self):
        """A mail splitting off its thread wrote the thread's task and a new one inside one 80 ms window; the event named only the
        new one, and a tab holding the thread's task kept its old read (the intake walk, 2026-10-26)."""
        dummy = object()
        live.attach(dummy)
        try:
            live.emit('task-changed', task_id=32, message_id=1)
            live.emit('task-changed', task_id=42, message_id=2)
            live.emit('task-changed', task_id=32)
            got = live._pending['task-changed']
            self.assertEqual((got['task_id'], got['task_ids'], got['message_id']), (32, [32, 42], 2))
            live.emit('task-changed')                                # a write that names no task is about all of them
            self.assertNotIn('task_id', live._pending['task-changed'])
            self.assertNotIn('task_ids', live._pending['task-changed'])
            live.emit('task-changed', task_id=7)
            self.assertNotIn('task_id', live._pending['task-changed'], 'the window stays about every task')
            live.flush()
            live.emit('task-changed', task_id=7)
            self.assertEqual({k: v for k, v in live._pending['task-changed'].items() if k != 'seq'}, {'task_id': 7, 'type': 'task-changed'})
        finally:
            live.detach(dummy)
            live.reset()

    def test_a_wake_up_says_which_writes_a_read_has_seen_and_whose_they_were(self):
        """THE LOAD-ONCE PASS (2026-10-27): every write's wake-up carries a stamp taken after the write, and a read begun later holds a
        stamp at least as new (live.seq) - so the page skips reading again what it already holds. A window is covered only when every
        write in it was stamped; a write still inside a transaction is not; and it is one tab's only when every write in it was that tab's."""
        dummy = object()
        live.attach(dummy)
        try:
            before = live.seq()
            live.emit('feed-changed', message_id=1)
            stamped = live._pending['feed-changed']['seq']
            self.assertGreater(stamped, before)
            self.assertGreaterEqual(live.seq(), stamped, 'a read begun now has seen it')
            live.emit('feed-changed', message_id=2, seq=None)                # unstampable (store._poke inside a transaction)
            self.assertNotIn('seq', live._pending['feed-changed'], 'one unstamped write leaves the window uncovered')
            live.flush()
            token = live.TAB.set('tab-a')
            try:
                live.emit('task-changed', task_id=3)
                self.assertEqual(live._pending['task-changed']['by'], 'tab-a')
                live.emit('task-changed', task_id=3)
                self.assertEqual(live._pending['task-changed']['by'], "tab-a", "two writes of one tab stay that tab's")
            finally: live.TAB.reset(token)
            live.emit('task-changed', task_id=4)                            # a poll's write in the same window
            self.assertNotIn("by", live._pending["task-changed"], "a window with anyone else's write is nobody's own")
            live.emit('ingest-status', ingest={})
            self.assertNotIn('seq', live._pending['ingest-status'], 'only a write to the rows is stamped')
        finally:
            live.detach(dummy)
            live.reset()

    def test_a_rail_says_the_newest_stamp_it_was_built_after_and_a_cached_one_keeps_its_own(self):
        s = MemoryStore()
        dummy = object()
        live.attach(dummy)
        try:
            s.create_task({'Title': 'Check the ledger export', 'Status': 'todo'}, 'owner')
            stamp = live._pending['task-changed']['seq']
            built = funnel.pile(s, force=True)
            self.assertGreaterEqual(built['live_seq'], stamp, 'built after the write: it holds it')
            live.stamp()                                                     # a write the cache did not see
            again = funnel.pile(s)
            if again is built: self.assertEqual(again['live_seq'], built['live_seq'], 'a cached rail never claims a newer stamp')
        finally:
            funnel.invalidate()
            live.detach(dummy)
            live.reset()

    def test_a_poke_inside_a_transaction_is_never_stamped_and_a_held_batch_keeps_its_stamps(self):
        s = MemoryStore()
        dummy = object()
        live.attach(dummy)
        try:
            s.cx.execute('BEGIN')
            try: s._poke('feed-changed', message_id=5)
            finally: s.cx.rollback()
            self.assertNotIn('seq', live._pending['feed-changed'])
            live.flush()
            with s.one_poke():
                s._poke('feed-changed', message_id=6)
                held = live.seq()
                s._poke('feed-changed', message_id=6)
            self.assertEqual(live._pending['feed-changed']['seq'], held + 1, 'a held write keeps the stamp it was poked with, the newest of its copies')
        finally:
            live.detach(dummy)
            live.reset()

    def test_ingest_status_pokes_the_clock_without_claiming_the_feed_changed(self):
        tab, s = _Tab(), MemoryStore()
        async def once():
            live.bind(asyncio.get_running_loop())
            live.attach(tab)
            try:
                s.set_setting('ingest_status', '{"state":"running"}', 't')
                live.flush()
                for _ in range(20):
                    await asyncio.sleep(0)
                    if any(m.get('type') == 'ingest-status' for m in tab.sent): break
            finally:
                live.reset()
        _run(once())
        self.assertIn('ingest-status', [m['type'] for m in tab.sent])
        self.assertNotIn('feed-changed', [m['type'] for m in tab.sent])

    def test_a_run_pokes_the_studio(self):
        tab, s = _Tab(), MemoryStore()
        async def once():
            live.bind(asyncio.get_running_loop())
            live.attach(tab)
            try:
                tid = s.create_task({'Title': 'run-poke', 'Status': 'open'}, 't')
                live.flush()
                tab.sent.clear()
                s.start_run(tid, 'coding', 'go', 't')
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
        # NOT `with TestClient(...)`: entering it runs the lifespan, which starts the poll thread,
        # the startup catch-up and the waitroom - and any of them can emit a feed-changed that
        # reaches the socket before the task-changed this test caused. That is what failed on
        # macos-latest ('feed-changed' != 'task-changed'), intermittently, for no reason to do with
        # the socket. live.serve() binds the loop itself on connect, so the socket needs no
        # lifespan at all, and without one this is the only writer.
        client = TestClient(server.app)
        try:
            with client.websocket_connect('/api/events/ws') as ws:
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
        saved = server.cfg['server'].get('token')
        server.cfg['server']['token'] = 's3cret'
        try:
            with TestClient(server.app) as c:
                with self.assertRaises(WebSocketDisconnect):
                    with c.websocket_connect('/api/events/ws', headers={'X-Taskuary-Token': ''}) as ws:
                        ws.receive_json()
                with c.websocket_connect('/api/events/ws?token=s3cret') as ws:
                    self.assertEqual(ws.receive_json()['type'], 'hello')
                with self.assertRaises(WebSocketDisconnect):
                    with c.websocket_connect('/api/events/ws?token=s3cret',
                                             headers={'Origin': 'http://evil.example'}) as ws:
                        ws.receive_json()
        finally:
            # ...put back the token it found: popping it left the app open to every later test (test_sharing's 401s read 200)
            if saved is None: server.cfg['server'].pop('token', None)
            else: server.cfg['server']['token'] = saved


if __name__ == '__main__':
    unittest.main()
