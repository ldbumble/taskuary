"""A CLI hook writes the store, and it must never do that ON the event loop (P16).

The loop carries every terminal pane, websocket and screencast. A hook that ran hooks.receive there stalled all of
them whenever another thread held the store's lock - measured p99 45-60 ms, ~20 calls at 300-900 ms, one at 2 s,
and a hook past curl's 3 s was dropped. Off the loop it must still apply in ARRIVAL order: a PermissionRequest and
the PostToolUse that closes it, run the other way round, leave "needs your approval" over an agent that has moved on.
"""
import asyncio, json, threading, time, unittest
from types import SimpleNamespace
from unittest import mock
from fastapi.testclient import TestClient
from starlette.requests import Request

from taskuary import hooks, remote_assistant, server, terminal as term, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory

CWD = r'C:\code\repo'


def req(payload: dict) -> Request:
    "A hook's POST as the endpoint sees it: the body read once, then the client is gone."
    scope = {'type': 'http', 'method': 'POST', 'path': '/api/hooks/claude', 'headers': [], 'query_string': b'', 'client': ('127.0.0.1', 1)}
    sent = []
    async def receive():
        if sent: return {'type': 'http.disconnect'}
        sent.append(1); return {'type': 'http.request', 'body': json.dumps(payload).encode(), 'more_body': False}
    return Request(scope, receive)


def on_loop() -> bool:
    try: asyncio.get_running_loop(); return True
    except RuntimeError: return False


class HookOffLoopTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task(title='Fix the cron', kind='coding')
        self._sessions = dict(term.SESSIONS); term.SESSIONS.clear()
        term.SESSIONS['run1'] = SimpleNamespace(sid='run1', alive=True, task_id=self.tid, cwd=CWD, agent='coding', label='coding', argv=['claude'],
                                                last=1.0, ext_id='c-sess', started='2026-09-20 09:00:00', files=lambda: [], tail=lambda n=3: [],
                                                idle=lambda: 0.0, witness=SimpleNamespace(note=lambda n: None), store=self.s)

    def tearDown(self): term.SESSIONS.clear(); term.SESSIONS.update(self._sessions)

    def hook(self, event, **f): return server.cli_hook('claude', req({'hook_event_name': event, 'session_id': 'c-sess', 'cwd': CWD, **f}))

    def hold_lock(self, release: threading.Event, held: threading.Event, most: float = 3.0):
        "Another thread sits on the store's lock - a poll, a settle - until told to let go (or `most` seconds, so the old code fails, not hangs)."
        def sit():
            with self.s.lock: held.set(); release.wait(most)
        threading.Thread(target=sit, daemon=True).start(); held.wait(2)

    def test_the_loop_keeps_answering_while_a_hook_waits_on_the_store(self):
        release, held = threading.Event(), threading.Event()
        self.hold_lock(release, held)
        async def main():
            hook = asyncio.create_task(self.hook('UserPromptSubmit', prompt='go'))
            # a pane's heartbeat: every tick must come back promptly while the hook is stuck behind the lock
            gaps, last = [], time.monotonic()
            for _ in range(20):
                await asyncio.sleep(0.01); now = time.monotonic(); gaps.append(now - last); last = now
            in_flight = not hook.done()
            release.set()
            return max(gaps), in_flight, await asyncio.wait_for(hook, 5)
        gap, in_flight, out = asyncio.run(main())
        self.assertLess(gap, 0.5, 'the event loop froze behind the store lock')
        self.assertTrue(in_flight)                                                # it really was waiting on the store
        self.assertEqual(out, {'bound': True, 'sid': 'run1'})                    # ...and it still landed, same answer as before
        self.assertEqual(ws.status(self.s, self.tid)['state'], 'working')

    def test_a_trivial_endpoint_answers_while_a_hook_is_stuck(self):
        "The same through the whole app on ONE loop: a hook POST stuck behind the lock, and a plain GET beside it still answers."
        import httpx
        release, held = threading.Event(), threading.Event()
        self.hold_lock(release, held)
        hdr = {'X-Taskuary-Token': server.cfg['server'].get('token') or ''}
        t = httpx.ASGITransport(app=server.app)      # the transport itself: the suite's guard rightly refuses a client's "network" call
        send = lambda m, path, **kw: t.handle_async_request(httpx.Request(m, 'http://testserver' + path, headers=hdr, **kw))
        async def main():
            hook = asyncio.create_task(send('POST', '/api/hooks/claude', json={'hook_event_name': 'UserPromptSubmit', 'session_id': 'c-sess', 'cwd': CWD}))
            await asyncio.sleep(0.2)
            t0 = time.monotonic(); r = await send('GET', '/api/version'); took = time.monotonic() - t0
            in_flight = not hook.done(); release.set()
            h = await asyncio.wait_for(hook, 5); await h.aread()
            return r, took, in_flight, json.loads(h.content)
        with mock.patch.object(server, 'store', self.s): r, took, in_flight, out = asyncio.run(main())
        self.assertEqual(r.status_code, 200); self.assertLess(took, 1.0)
        self.assertTrue(in_flight); self.assertEqual(out, {'bound': True, 'sid': 'run1'})

    def test_hooks_from_one_session_apply_in_arrival_order(self):
        "Earlier hooks are made SLOWER, so any pool would let a later one overtake; one worker never does."
        seen = []
        def receive(p, cli='claude'):
            self.assertFalse(on_loop()); time.sleep((10 - p['n']) * 0.005); seen.append(p['n']); return {'bound': True}
        async def main(): return await asyncio.gather(*(self.hook('PostToolUse', n=i) for i in range(10)))
        with mock.patch.object(hooks, 'receive', receive): outs = asyncio.run(main())
        self.assertEqual(seen, list(range(10))); self.assertTrue(all(o == {'bound': True} for o in outs))

    def test_a_permission_and_the_tool_that_ran_it_stay_in_order(self):
        "The real chain, both stuck behind the lock: PostToolUse must still find the request open and close it."
        release, held = threading.Event(), threading.Event()
        self.hold_lock(release, held)
        async def main():
            both = asyncio.gather(self.hook('PermissionRequest', tool_name='Bash', tool_input={'command': 'rm -rf build'}),
                                  self.hook('PostToolUse', tool_name='Bash', tool_input={'command': 'rm -rf build'}))
            await asyncio.sleep(0.1); release.set(); return await asyncio.wait_for(both, 5)
        asyncio.run(main())
        self.assertEqual([e['Kind'] for e in ws.events(self.s, self.tid)], ['approval_needed', 'answered'])
        self.assertEqual(ws.status(self.s, self.tid)['requests'], [])

    def test_a_hook_that_raises_is_still_quiet(self):
        def boom(p, cli='claude'): raise RuntimeError('store went away')
        with mock.patch.object(hooks, 'receive', boom): self.assertEqual(asyncio.run(self.hook('Stop')), {'bound': False})


class HandsOffTests(unittest.TestCase):
    def test_the_stream_never_asks_where_the_walk_is_a_phone_locks_nothing(self):
        # the owner, 2026-10-23: "we used to have that if we were talking on the phone it would lock the screen on desktop but we
        # should probably get rid of that" - the stream's admission no longer reads the hand-off at all
        where = []
        def handoff(st): where.append(on_loop()); return {'channel': 'whatsapp', 'chat': 'x'}
        with mock.patch.object(remote_assistant, 'handoff', handoff), mock.patch.object(server, '_navigation_reservation', return_value=None), \
             mock.patch('taskuary.concierge.brain', return_value=None):
            r = TestClient(server.app).post('/api/concierge/stream', json={'mode': 'next'})
        self.assertNotEqual(r.status_code, 409)


if __name__ == '__main__': unittest.main()
