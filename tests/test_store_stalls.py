"""THE FREEZES OF 2026-10-23: three times in a day every request waited 20-150 s and they all finished in the same second.

The Advisor's rule-promotion evidence asked the message table one full scan per sender, hundreds of them back to back on the
writer's lock, so every request's every statement queued behind it. What this pins:
  - the evidence is read in a fixed number of queries, however many senders there are (promote.py)
  - a background job's reads inside store.reads_off_writer never wait on the writer's lock
  - a wait on store.lock over a second is logged with the holder's call site, and a slow request says how long it waited vs ran
  - a request stuck behind the store never stops the loop: /api/health still answers, async routes included
"""
import asyncio, json, os, tempfile, threading, time, unittest
from unittest import mock
from loguru import logger
from taskuary import promote, server, store as store_mod
from taskuary.store import MemoryStore, SQLiteStore
from taskuary.testing import Factory
from tests.memlines import note as put_note


class Logs:
    "loguru lines while the block runs."
    def __enter__(self): self.lines = []; self.id = logger.add(lambda m: self.lines.append(m.record['message']), level='DEBUG'); return self
    def __exit__(self, *a): logger.remove(self.id)
    def having(self, s): return [l for l in self.lines if s in l]


def slow_holder(s, held, release, most=3.0):
    "A background job sitting on the writer's lock - the name is what the log must point at."
    with s.lock: held.set(); release.wait(most)


def hold(s, most=3.0):
    held, release = threading.Event(), threading.Event()
    threading.Thread(target=slow_holder, args=(s, held, release, most), daemon=True).start(); held.wait(2)
    return release


class LockEvidence(unittest.TestCase):
    def test_a_long_wait_names_the_waiter_and_the_holder(self):
        s = MemoryStore()
        with mock.patch.object(store_mod, 'LOCK_SLOW_WAIT', 0.05), Logs() as log:
            release = hold(s); threading.Timer(0.2, release.set).start()
            s.get_setting('anything')
        line, = log.having('store.lock:')[:1] or [None]
        self.assertIsNotNone(line, log.lines)
        self.assertIn('waited', line); self.assertIn('slow_holder', line, 'the holder is named by its call site')
        self.assertIn('test_store_stalls.py', line); self.assertIn('hand-off', line)

    def test_a_long_hold_is_logged_when_it_ends(self):
        s = MemoryStore()
        with mock.patch.object(store_mod, 'LOCK_SLOW_HOLD', 0.05), Logs() as log:
            with s.lock: time.sleep(0.1)
        self.assertTrue(any('held' in l and 'test_a_long_hold_is_logged_when_it_ends' in l for l in log.having('store.lock:')), log.lines)

    def test_a_free_lock_logs_nothing_and_stays_reentrant(self):
        s = MemoryStore()
        with Logs() as log:
            with s.lock:
                with s.lock: s.set_setting('k', 'v', 't')
            self.assertTrue(s.lock.acquire(blocking=False)); s.lock.release()
        self.assertEqual(log.having('store.lock:'), [])
        self.assertEqual(s.get_setting('k'), 'v')

    def test_the_meter_counts_only_this_requests_wait(self):
        s = MemoryStore()
        release = hold(s); threading.Timer(0.3, release.set).start()
        with store_mod.lock_wait_meter() as m: s.get_setting('x')
        self.assertGreater(m[0], 0.15)
        with store_mod.lock_wait_meter() as m2: s.get_setting('x')
        self.assertLess(m2[0], 0.05)


class ReadsOffTheWriter(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(); self.s = SQLiteStore(os.path.join(self.dir, 'db.sqlite'))
        self.s.set_setting('owner_email', 'alex@northwind.example', 'test')

    def tearDown(self): self.s.close()

    def test_a_select_inside_does_not_wait_for_a_held_writer(self):
        release = hold(self.s)
        try:
            t0 = time.perf_counter()
            with self.s.reads_off_writer(): v = self.s.get_setting('owner_email')
            took = time.perf_counter() - t0
        finally: release.set()
        self.assertEqual(v, 'alex@northwind.example'); self.assertLess(took, 1.0, 'it read on a reader connection')

    def test_outside_it_reads_still_queue_on_the_writer(self):
        release = hold(self.s); threading.Timer(0.3, release.set).start()
        t0 = time.perf_counter(); self.s.get_setting('owner_email')
        self.assertGreater(time.perf_counter() - t0, 0.2)

    def test_writes_and_reads_in_a_writer_transaction_stay_on_the_writer(self):
        with self.s.reads_off_writer():
            self.s.set_setting('k', 'one', 't')
            self.assertEqual(self.s.get_setting('k'), 'one', 'a committed write is read back')
            with self.s.lock:
                self.s.cx.execute('BEGIN IMMEDIATE')
                self.s.cx.execute("UPDATE setting SET Value='two' WHERE Name='k'")
                self.assertEqual(self.s._one("SELECT Value FROM setting WHERE Name='k'")['Value'], 'two', 'its own uncommitted write')
                self.s.cx.rollback()
        self.assertEqual(self.s.get_setting('k'), 'one')

    def test_the_advisor_run_reads_off_the_writer(self):
        from taskuary import assistant
        seen = []
        def spy(*a, **k): seen.append(getattr(store_mod._OFF_WRITER, 'on', False)); return {'ran': True, 'said': 0}
        with mock.patch.object(assistant, '_run', spy), mock.patch.object(assistant, 'retry_stuck_ideas', lambda *a: None):
            assistant.run(self.s, None, force=True, instruction='x', watch_source_ids=[], watch_sources=[])
        self.assertEqual(seen, [True])
        self.assertFalse(getattr(store_mod._OFF_WRITER, 'on', False), 'and only for the run')


class PromotionReadsOnce(unittest.TestCase):
    def test_the_evidence_is_a_fixed_number_of_queries_however_many_senders(self):
        def count(n):
            s = MemoryStore(); s.set_setting('calendar_enabled', '0', 'test')
            for i in range(n):
                em = f'news{i}@vendor{i}.example'
                mid = s.add_message({'ConversationId': f'email:{em}', 'Channel': 'email', 'Subject': 'Issue', 'FromEmail': em,
                                     'BodyText': 'news', 'Status': 'filed', 'SenderClass': 'automated'})
                s.add_route(mid, None, 'ignore', None, 'not ours', [], 'owner')
            calls = []
            real = s._rows
            with mock.patch.object(s, '_rows', lambda q, p=(): calls.append(q) or real(q, p)): ev = promote.evidence(s)
            self.assertEqual(len(ev), n); self.assertTrue(all(r['down'] for r in ev.values()))
            return len(calls)
        self.assertEqual(count(3), count(40), 'one scan per question, not one per sender')

    def test_a_mail_made_work_is_taken_up_on_its_own_thread(self):
        """The owner's own moves, read off the route log (the notes table is gone, 2026-10-27): a put-down and a mail made work."""
        s, em = MemoryStore(), 'digest@vendor.example'
        old, new = (s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': 'Weekly digest', 'FromEmail': em.upper(),
                                   'BodyText': 'x', 'Status': 'filed'}) for cid in ('email:old', 'email:new'))
        s.add_route(old, None, 'ignore', None, 'not ours', [], 'owner')
        s.add_route(new, None, 'create', None, 'made a task', [], 'owner')
        ev = promote.evidence(s)[em]
        self.assertEqual((ev['down'], ev['up']), ({'email:old'}, {'email:new'}))


class TheLoopStaysFree(unittest.TestCase):
    """A route stuck behind the store waits in the thread pool; the loop - and /api/health with it - keeps answering."""
    def setUp(self):
        import httpx
        self.s = MemoryStore(); self.tid = Factory(self.s).task(title='Renew the vendor contract')
        hdr = {'X-Taskuary-Token': server.cfg['server'].get('token') or ''}
        t = httpx.ASGITransport(app=server.app)
        self.send = lambda m, path, **kw: t.handle_async_request(httpx.Request(m, 'http://testserver' + path, headers={**hdr, **kw.pop('headers', {})}, **kw))

    def beside(self, method, path, **kw):
        "(the stuck request, still in flight?, how much later than asked /api/health answered meanwhile)"
        release = hold(self.s, most=5)
        async def main():
            t0 = time.monotonic(); stuck = asyncio.create_task(self.send(method, path, **kw))
            await asyncio.sleep(0.3)            # on the loop, the stuck one would hold this sleep, and the health check behind it
            h = await self.send('GET', '/api/health'); took = time.monotonic() - t0 - 0.3
            in_flight = not stuck.done(); release.set()
            r = await asyncio.wait_for(stuck, 10); await r.aread()
            return r, in_flight, took, h.status_code
        with mock.patch.object(server, 'store', self.s): return asyncio.run(main())

    def test_a_task_read_behind_the_lock(self):
        r, in_flight, took, health = self.beside('GET', f'/api/tasks/{self.tid}')
        self.assertTrue(in_flight); self.assertLess(took, 1.0); self.assertEqual((r.status_code, health), (200, 200))

    def test_an_image_paste_behind_the_lock(self):
        r, in_flight, took, health = self.beside('POST', f'/api/tasks/{self.tid}/waitroom/image', content=b'\x89PNG....',
                                                 headers={'content-type': 'image/png'})
        self.assertTrue(in_flight, 'it waited on the store - off the loop'); self.assertLess(took, 1.0)
        self.assertEqual(r.status_code, 200)

    def test_a_transcription_never_holds_the_loop(self):
        from taskuary import voice
        def slow(store, data, mime, name): time.sleep(1.0); return {'text': 'call Erin back'}
        with mock.patch.object(voice, 'transcribe', slow):
            r, in_flight, took, health = self.beside('POST', '/api/voice/transcribe', content=b'audio', headers={'content-type': 'audio/webm'})
        self.assertLess(took, 0.6, 'the loop answered while the service was still talking')
        self.assertEqual(json.loads(r.content), {'text': 'call Erin back'})

    def test_a_slow_request_says_what_it_waited_on(self):
        with mock.patch.object(server, 'SLOW_REQUEST', 0.1), Logs() as log:
            r, *_ = self.beside('GET', f'/api/tasks/{self.tid}')
        line = next((l for l in log.having(f'GET /api/tasks/{self.tid} -> 200')), '')
        self.assertIn('store.lock wait', line); self.assertIn('ran', line)
        waited = float(line.split('store.lock wait ')[1].split('s')[0])
        self.assertGreater(waited, 0.1, 'the wait rode into the thread pool with the request')


if __name__ == '__main__': unittest.main()
