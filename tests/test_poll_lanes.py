"""Two poll lanes: a slow full sync can no longer hold up fresh chat intake.

PW-001/PW-002/PW-005 (docs/processing-walkthrough-todos.md). The full lane keeps the
one-at-a-time lock that stopped overlapping catch-ups, and still runs channels, triage,
CI and reports in that order. The chat lane has its own short lock and its own clock, so
AI triage over a mail backlog or a slow report leaves Teams/WhatsApp/... arriving on time.
A connector type is fetched by one lane at a time (dedupe never races), the full lane's
own chat fetch counts on the fast clock, and triage stays ONE ordered drain - the fresh
chat channels are judged first, within-channel order untouched.
"""
import contextlib, json, threading, time, unittest
from unittest import mock

from taskuary import channels, ingest, server
from taskuary.store import MemoryStore


def arm(s, typ, cfg=None):
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1, 'ConfigJson': json.dumps(cfg or {})}, 't')
    ch = channels.CH2SRC[typ]
    s.save_source({'Channel': ch, 'Address': 'me@x.example' if ch == 'email' else 'C1', 'Owner': 'me', 'Active': 1, 'ConnectorId': cid}, 't')
    return cid


def pending_row(s, ch, i):
    return s.add_message({'ExternalId': f'{ch}:{i}', 'Channel': ch, 'ConversationId': f'{ch}-conv-{i}', 'Subject': f'row {i}',
                          'BodyText': 'please look at this', 'FromName': 'A', 'FromEmail': f'a{i}@partner.example',
                          'SentAt': '2026-09-06 09:00:00', 'Status': 'triaging'})


class LaneTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        arm(self.s, 'teams'); arm(self.s, 'outlook')
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        server._QUICK_LAST.clear(); self.addCleanup(server._QUICK_LAST.clear)
        self.no_reports = mock.patch.object(server, 'run_due_reports')
        self.no_reports.start(); self.addCleanup(self.no_reports.stop)
        self.addCleanup(lambda: server._close_drain_workers(10))

    def full_in_background(self, poll, **kw):
        t = threading.Thread(target=server._poll_reports, kwargs={'what': 'syncing', **kw}, daemon=True)
        with mock.patch('taskuary.channels.poll_channels', poll): t.start(); return t

    def test_a_slow_full_sync_does_not_hold_up_a_chat_poll(self):
        """The full lane is judging a mail backlog (the brain is slow); a Teams poll still reads Teams now."""
        started, release, polled = threading.Event(), threading.Event(), []
        def poll(store, days, progress=None, only=None):
            polled.append(only)
            if 'outlook' in (only or []): pending_row(store, 'email', 1)
            return 1
        def slow_brain(*a, **k):
            started.set(); release.wait(10)
            return '{"intent": "fyi", "why": "t"}'
        with mock.patch('taskuary.channels.poll_channels', poll), mock.patch.object(server, '_llm', return_value=slow_brain):
            t = threading.Thread(target=server._poll_reports, kwargs={'what': 'syncing'}, daemon=True); t.start()
            self.assertTrue(started.wait(10))
            t0 = time.time(); got = server._poll_reports(0, what='syncing', only=['teams']); took = time.time() - t0
            release.set(); t.join(10)
        self.assertEqual(got, 1)
        self.assertLess(took, 2, 'the chat lane waited on the full lane')
        self.assertEqual(len(polled), 2)
        self.assertCountEqual(polled[0], ['teams', 'outlook'])
        self.assertEqual(polled[1], ['teams'])

    def test_a_full_sync_counts_as_the_chat_fetch_it_included(self):
        """PW-002: the full pass read Teams too, so the fast clock must not fetch it again a moment later."""
        with mock.patch('taskuary.channels.poll_channels', lambda s, d, progress=None, **k: 0), mock.patch('taskuary.ingest.drain', return_value=0):
            server._poll_reports(0, what='syncing')
        self.assertLess(time.time() - server._QUICK_LAST.get('teams', 0), 5)
        self.assertNotIn('teams', server._quick_due())

    def test_full_chat_attempt_is_stamped_before_its_fetch_claim_is_released(self):
        observed = []
        real_claim = server._claim_fetch
        @contextlib.contextmanager
        def observe_claim(types, lane, **kw):
            with real_claim(types, lane, **kw) as claimed:
                yield claimed
                observed.append(server._QUICK_LAST.get('teams'))
        with mock.patch.object(server, '_claim_fetch', observe_claim), \
             mock.patch('taskuary.channels.poll_channels', return_value=0):
            server._poll_reports()
        self.assertTrue(observed and observed[0])
        self.assertLess(time.time() - observed[0], 5)

    def test_a_blank_saved_interval_means_the_default_not_zero(self):
        """The card says blank = 30: a field cleared and saved as '' must not quietly mean 'background sync only'."""
        cid = self.s.get_connector_by_type('teams')['ConnectorId']
        self.s.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps({'poll_seconds': ''})}, 't')
        self.assertIn('teams', server._quick_due())
        self.s.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps({'poll_seconds': '0'})}, 't')
        self.assertNotIn('teams', server._quick_due())
        self.s.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps({'poll_seconds': ' 45 '})}, 't')
        self.assertIn('teams', server._quick_due())

    def test_a_failed_chat_fetch_waits_its_interval_before_retrying(self):
        """Explicit retry rule: an attempt that ran (and failed) is stamped; the next try is one interval later."""
        def boom(*a, **k): raise RuntimeError('teams down')
        with mock.patch('taskuary.channels.poll_channels', boom):
            got = server._poll_reports(0, what='syncing', only=['teams'])
        self.assertIs(got, False)
        self.assertLess(time.time() - server._QUICK_LAST['teams'], 5)

    def test_a_skipped_chat_poll_is_retried_on_the_next_tick(self):
        """...but an attempt that never ran (the lane was busy) is not stamped, so it is still due."""
        server._QUICK_BUSY.acquire()
        try: self.assertIs(server._poll_reports(0, what='syncing', only=['teams']), False)
        finally: server._QUICK_BUSY.release()
        self.assertNotIn('teams', server._QUICK_LAST)
        self.assertIn('teams', server._quick_due())

    def test_a_chat_the_full_sync_is_reading_is_not_fetched_twice(self):
        started, release, calls = threading.Event(), threading.Event(), []
        def poll(store, days, progress=None, only=None):
            calls.append(only)
            if 'outlook' in (only or []): started.set(); release.wait(10)
            return 0
        with mock.patch('taskuary.channels.poll_channels', poll), mock.patch('taskuary.ingest.drain', return_value=0):
            t = threading.Thread(target=server._poll_reports, kwargs={'what': 'syncing'}, daemon=True); t.start()
            self.assertTrue(started.wait(10))
            got = server._poll_reports(0, what='syncing', only=['teams'])
            release.set(); t.join(10)
        self.assertIs(got, False)
        self.assertEqual(len(calls), 1, 'teams was fetched by both lanes at once')
        self.assertCountEqual(calls[0], ['teams', 'outlook'])

    def test_a_full_sync_leaves_a_chat_the_quick_lane_is_reading_alone(self):
        started, release, calls = threading.Event(), threading.Event(), []
        def poll(store, days, progress=None, only=None):
            calls.append(only)
            if only == ['teams']: started.set(); release.wait(10)
            return 0
        with mock.patch('taskuary.channels.poll_channels', poll), mock.patch('taskuary.ingest.drain', return_value=0):
            t = threading.Thread(target=server._poll_reports, kwargs={'what': 'syncing', 'only': ['teams']}, daemon=True); t.start()
            self.assertTrue(started.wait(10))
            server._poll_reports(0, what='syncing')
            release.set(); t.join(10)
        self.assertEqual(calls, [['teams'], ['outlook']])

    def test_connector_claim_is_one_atomic_check_and_owned_release(self):
        """Both lanes arrive together; only one can own Teams, and only its token releases it."""
        barrier, release = threading.Barrier(3), threading.Event()
        claims = []
        def contender(lane):
            barrier.wait()
            with server._claim_fetch(['teams'], lane) as got:
                claims.append((lane, got))
                if got: release.wait(10)
        threads = [threading.Thread(target=contender, args=(lane,), daemon=True)
                   for lane in ('full', 'quick')]
        for thread in threads: thread.start()
        barrier.wait()
        end = time.time() + 10
        while len(claims) < 2 and time.time() < end: time.sleep(0.01)
        self.assertEqual(len(claims), 2)
        self.assertEqual(sorted(bool(got) for _, got in claims), [False, True])
        self.assertIn('teams', server._FETCHING)
        release.set()
        for thread in threads: thread.join(10)
        self.assertNotIn('teams', server._FETCHING)

    def test_quick_fetch_clock_keeps_running_while_its_triage_is_slow(self):
        """The second Teams fetch lands while the one ordered worker is judging the first line."""
        judging, release, fetched, judged = threading.Event(), threading.Event(), [], []
        def poll(target, days, progress=None, only=None):
            fetched.append(list(only or []))
            pending_row(target, 'teams', len(fetched))
            return 1
        def slow_judge(target, msg, llm=None, **kw):
            judged.append(msg['_mid'])
            if len(judged) == 1:
                judging.set(); release.wait(10)
            target.place_message(msg['_mid'], None, 'filed')
            return {'status': 'filed', 'task_id': None, 'message_id': msg['_mid']}
        with mock.patch('taskuary.channels.poll_channels', poll), \
             mock.patch.object(ingest, 'ingest_message', slow_judge):
            self.assertEqual(server._poll_reports(0, only=['teams']), 1)
            self.assertTrue(judging.wait(10))
            self.assertEqual(server._poll_reports(0, only=['teams']), 1)
            self.assertEqual(fetched, [['teams'], ['teams']], 'triage blocked the next fetch')
            self.assertEqual(len(self.s.pending_triage()), 2)
            release.set()
            self.assertTrue(server.join_drains(self.s, 10))
        self.assertEqual(len(judged), 2)
        self.assertEqual(self.s.pending_triage(), [])

    def test_waiting_context_gate_releases_fetch_lane_during_slow_triage(self):
        judging, release, fetched, first_result = threading.Event(), threading.Event(), [], []
        def poll(target, days, progress=None, only=None):
            fetched.append(list(only or [])); pending_row(target, 'teams', len(fetched)); return 1
        def slow_judge(target, msg, llm=None, **kw):
            if not judging.is_set(): judging.set(); release.wait(10)
            target.place_message(msg['_mid'], None, 'filed')
            return {'status': 'filed', 'task_id': None, 'message_id': msg['_mid']}
        with mock.patch('taskuary.channels.poll_channels', poll), \
             mock.patch.object(ingest, 'ingest_message', slow_judge):
            gate = threading.Thread(target=lambda: first_result.append(
                server._poll_reports(0, only=['teams'], wait=True)), daemon=True)
            gate.start(); self.assertTrue(judging.wait(10))
            self.assertEqual(server._poll_reports(0, only=['teams']), 1)
            self.assertEqual(fetched, [['teams'], ['teams']])
            self.assertTrue(gate.is_alive())
            release.set(); gate.join(10)
            self.assertTrue(server.join_drains(self.s, 10))
        self.assertEqual(first_result, [1])

    def test_zero_new_context_fetch_does_not_wait_for_unrelated_active_drain(self):
        started, release, result = threading.Event(), threading.Event(), []
        pending_row(self.s, 'email', 1)
        def slow(target, msg, llm=None, **kw):
            started.set(); release.wait(10)
            target.place_message(msg['_mid'], None, 'filed')
            return {'status': 'filed', 'task_id': None, 'message_id': msg['_mid']}
        with mock.patch.object(ingest, 'ingest_message', slow), \
             mock.patch('taskuary.channels.poll_channels', return_value=0):
            worker = server._drain_worker(self.s)
            worker.submit()
            self.assertTrue(started.wait(10))
            gate = threading.Thread(target=lambda: result.append(
                server._poll_reports(0, only=['teams'], wait=True)), daemon=True)
            gate.start(); gate.join(2)
            self.assertEqual(result, [0])
            release.set(); self.assertTrue(server.join_drains(self.s, 10))

    def test_quick_override_maps_connector_types_to_stored_message_channels(self):
        """Outlook/IMAP overrides fetch by connector type but wait and drain their email rows."""
        arm(self.s, 'imap', {'poll_seconds': 1})
        outlook = self.s.get_connector_by_type('outlook')['ConnectorId']
        self.s.save_connector({'ConnectorId': outlook, 'ConfigJson': json.dumps({'poll_seconds': 1})}, 't')
        seen = []
        def poll(target, days, progress=None, only=None):
            for i, typ in enumerate(only or []): pending_row(target, 'email', f'{typ}-{i}')
            return len(only or [])
        def judged(target, msg, llm=None, **kw):
            seen.append(msg['_mid']); target.place_message(msg['_mid'], None, 'filed')
            return {'status': 'filed', 'task_id': None, 'message_id': msg['_mid']}
        self.assertCountEqual(server._quick_due(), ['teams', 'outlook', 'imap'])
        with mock.patch('taskuary.channels.poll_channels', poll), \
             mock.patch.object(ingest, 'ingest_message', judged):
            self.assertEqual(server._poll_reports(0, only=['outlook', 'imap'], wait=True), 2)
            self.assertTrue(server.join_drains(self.s, 10))
        self.assertEqual(len(seen), 2)
        self.assertEqual(self.s.pending_triage(), [])

    def test_the_context_gate_waits_for_an_in_flight_fetch_instead_of_skipping(self):
        """wait=True is the correctness gate before an answer about a chat: it must end with a fresh read."""
        started, calls = threading.Event(), []
        def poll(store, days, progress=None, only=None):
            calls.append(only)
            if 'outlook' in (only or []): started.set(); time.sleep(0.3)
            return 1
        with mock.patch('taskuary.channels.poll_channels', poll), mock.patch('taskuary.ingest.drain', return_value=0):
            t = threading.Thread(target=server._poll_reports, kwargs={'what': 'syncing'}, daemon=True); t.start()
            self.assertTrue(started.wait(10))
            got = server._poll_reports(0, what='refreshing teams context', only=['teams'], wait=True)
            t.join(10)
        self.assertEqual(got, 1)
        self.assertEqual(len(calls), 2)
        self.assertCountEqual(calls[0], ['teams', 'outlook'])
        self.assertEqual(calls[1], ['teams'])

    def test_the_context_gate_reports_still_syncing_when_triage_cannot_catch_up(self):
        """A fetched line that is still waiting its turn behind a long drain is not fresh context."""
        pending_row(self.s, 'teams', 1)
        ingest._DRAIN_LOCK.acquire()
        try:
            with mock.patch('taskuary.channels.poll_channels', lambda *a, **k: 1), mock.patch.object(server, 'DRAIN_WAIT', 0.3):
                self.assertIs(server._poll_reports(0, what='refreshing teams context', only=['teams'], wait=True), False)
        finally: ingest._DRAIN_LOCK.release()

    def test_context_gate_waits_for_the_submitted_route_to_finish(self):
        """Leaving pending_triage is not completion: the route/review writes can still be running."""
        routed, release, result = threading.Event(), threading.Event(), []
        def poll(target, days, progress=None, only=None):
            pending_row(target, 'teams', 1)
            return 1
        def halfway(target, msg, llm=None, **kw):
            target.place_message(msg['_mid'], None, 'filed')
            routed.set(); release.wait(10)
            target.add_route(msg['_mid'], None, 'file', None, 'finished', [], 'triage')
            return {'status': 'filed', 'task_id': None, 'message_id': msg['_mid']}
        with mock.patch('taskuary.channels.poll_channels', poll), \
             mock.patch.object(ingest, 'ingest_message', halfway):
            thread = threading.Thread(target=lambda: result.append(
                server._poll_reports(0, only=['teams'], wait=True)), daemon=True)
            thread.start()
            self.assertTrue(routed.wait(10))
            self.assertEqual(self.s.pending_triage(), [])
            self.assertTrue(thread.is_alive(), 'gate returned between placement and final route writes')
            release.set(); thread.join(10)
        self.assertEqual(result, [1])

    def test_context_gate_finishes_after_fresh_route_before_unrelated_backlog(self):
        """DRAIN_WAIT covers the requested Teams route, not the rest of a full mail catch-up."""
        first_mail, release_first = threading.Event(), threading.Event()
        later_mail, release_later, quick_result = threading.Event(), threading.Event(), []
        def poll(target, days, progress=None, only=None):
            if 'outlook' in (only or []):
                pending_row(target, 'email', 1); pending_row(target, 'email', 2)
            if only == ['teams']: pending_row(target, 'teams', 3)
            return 1
        def judged(target, msg, llm=None, **kw):
            if msg['channel'] == 'email' and not first_mail.is_set():
                first_mail.set(); release_first.wait(10)
            elif msg['channel'] == 'email':
                later_mail.set(); release_later.wait(10)
            target.place_message(msg['_mid'], None, 'filed')
            return {'status': 'filed', 'task_id': None, 'message_id': msg['_mid']}
        with mock.patch('taskuary.channels.poll_channels', poll), \
             mock.patch.object(ingest, 'ingest_message', judged):
            full = threading.Thread(target=server._poll_reports, daemon=True); full.start()
            self.assertTrue(first_mail.wait(10))
            quick = threading.Thread(target=lambda: quick_result.append(
                server._poll_reports(0, only=['teams'], wait=True)), daemon=True)
            quick.start()
            release_first.set()
            self.assertTrue(later_mail.wait(10), 'fresh Teams did not move ahead of mail')
            quick.join(2)
            self.assertEqual(quick_result, [1], 'fresh route waited for unrelated mail backlog')
            self.assertTrue(full.is_alive())
            release_later.set(); full.join(10)
            self.assertTrue(server.join_drains(self.s, 10))

    def test_a_chat_poll_does_not_end_the_full_syncs_banner(self):
        started, release = threading.Event(), threading.Event()
        def poll(store, days, progress=None, only=None):
            if 'outlook' in (only or []): pending_row(store, 'email', 1)
            return 1
        def slow_brain(*a, **k):
            started.set(); release.wait(10)
            return '{"intent": "fyi", "why": "t"}'
        with mock.patch('taskuary.channels.poll_channels', poll), mock.patch.object(server, '_llm', return_value=slow_brain):
            t = threading.Thread(target=server._poll_reports, kwargs={'what': 'catching up'}, daemon=True); t.start()
            self.assertTrue(started.wait(10))
            server._poll_reports(0, what='syncing', only=['teams'])
            st = json.loads(self.s.get_settings()['ingest_status'])
            healed = server.ingest_status()['status']
            release.set(); t.join(10)
        self.assertEqual(st['state'], 'running')
        self.assertTrue(st['what'].startswith('catching up'), st)
        self.assertEqual(healed['state'], 'running')
        self.assertEqual(json.loads(self.s.get_settings()['ingest_status']), {'state': 'idle'})

    def test_banner_owner_is_truthful_for_quick_then_full_interleaving(self):
        """Quick progress cannot overwrite full, and full finishing reveals a still-active quick."""
        quick = server._status_begin(self.s, 'quick', 'reading teams')
        full = server._status_begin(self.s, 'full', 'catching up')
        try:
            server._status_progress(self.s, quick, 'triaging teams')
            self.assertEqual(json.loads(self.s.get_settings()['ingest_status'])['what'], 'catching up')
            server._status_end(self.s, full)
            self.assertEqual(json.loads(self.s.get_settings()['ingest_status'])['what'], 'triaging teams')
        finally:
            server._status_end(self.s, full)
            server._status_end(self.s, quick)
        self.assertEqual(json.loads(self.s.get_settings()['ingest_status']), {'state': 'idle'})

    def test_actual_quick_progress_and_full_finish_keep_the_right_banner_owner(self):
        quick_started, quick_progressed, release_quick = threading.Event(), threading.Event(), threading.Event()
        full_started, release_full = threading.Event(), threading.Event()
        def poll(target, days, progress=None, only=None):
            if only == ['teams']:
                quick_started.set()
                self.assertTrue(full_started.wait(10))
                progress('teams', 1); quick_progressed.set()
                release_quick.wait(10)
            elif only == ['outlook']:
                full_started.set(); release_full.wait(10)
            return 0
        with mock.patch('taskuary.channels.poll_channels', poll):
            quick = threading.Thread(target=lambda: server._poll_reports(0, only=['teams']), daemon=True)
            quick.start(); self.assertTrue(quick_started.wait(10))
            full = threading.Thread(target=lambda: server._poll_reports(0, what='catching up'), daemon=True)
            full.start(); self.assertTrue(full_started.wait(10)); self.assertTrue(quick_progressed.wait(10))
            self.assertEqual(json.loads(self.s.get_settings()['ingest_status'])['what'], 'catching up')
            release_full.set(); full.join(10)
            status = json.loads(self.s.get_settings()['ingest_status'])
            self.assertEqual(status['state'], 'running')
            self.assertIn('reading teams', status['what'])
            release_quick.set(); quick.join(10)
        self.assertEqual(json.loads(self.s.get_settings()['ingest_status']), {'state': 'idle'})

    def test_shutdown_closes_admission_before_a_held_fetch_can_submit_a_worker(self):
        fetched, release, result = threading.Event(), threading.Event(), []
        def poll(target, days, progress=None, only=None):
            pending_row(target, 'teams', 1); fetched.set(); release.wait(10); return 1
        with mock.patch('taskuary.channels.poll_channels', poll):
            thread = threading.Thread(target=lambda: result.append(
                server._poll_reports(0, only=['teams'])), daemon=True)
            thread.start(); self.assertTrue(fetched.wait(10))
            self.assertTrue(server._close_drain_workers(0.1, target_store=self.s))
            release.set(); thread.join(10)
        self.assertEqual(result, [False])
        self.assertNotIn(id(self.s), server._DRAIN_WORKERS)
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            server._drain_worker(self.s)
        self.assertTrue(server._open_drain_workers(self.s))

    def test_timed_out_shutdown_keeps_the_live_worker_tracked(self):
        started, release = threading.Event(), threading.Event()
        pending_row(self.s, 'teams', 1)
        def slow(target, msg, llm=None, **kw):
            started.set(); release.wait(10)
            target.place_message(msg['_mid'], None, 'filed')
        with mock.patch.object(ingest, 'ingest_message', slow):
            worker = server._drain_worker(self.s)
            worker.submit(fresh=['teams'], only_fresh=True)
            self.assertTrue(started.wait(10))
            self.assertFalse(server._close_drain_workers(0.01, target_store=self.s))
            self.assertIs(server._DRAIN_WORKERS[id(self.s)], worker)
            self.assertFalse(server.join_drains(self.s, 0.01))
            with self.assertRaisesRegex(RuntimeError, 'closed'):
                server._drain_worker(self.s)
            release.set(); self.assertTrue(server.join_drains(self.s, 10))
        self.assertTrue(server._open_drain_workers(self.s))

    def test_a_running_chat_poll_is_not_healed_into_idle(self):
        server._QUICK_BUSY.acquire()
        try:
            self.s.set_setting('ingest_status', json.dumps({'state': 'running', 'what': 'syncing · reading teams'}), 'system')
            self.assertEqual(server.ingest_status()['status']['state'], 'running')
        finally: server._QUICK_BUSY.release()
        self.assertEqual(server.ingest_status()['status']['state'], 'idle')     # nobody holds either lane: a ghost

    def test_the_chat_clock_has_its_own_loop_and_the_off_switch_still_covers_it(self):
        calls = []
        class Stop(Exception): pass
        with mock.patch.object(server, '_poll_reports', side_effect=lambda *a, **k: calls.append(k)), \
             mock.patch.object(server.time, 'sleep', side_effect=Stop):
            self.s.set_setting('poll_minutes', '0', 't')
            with self.assertRaises(Stop): server.quick_forever()
            self.assertEqual(calls, [])
            self.s.set_setting('poll_minutes', '10', 't')
            with self.assertRaises(Stop): server.quick_forever()
        self.assertEqual(calls, [{'what': 'syncing', 'only': ['teams']}])

    def test_the_full_clock_no_longer_carries_the_chat_clock(self):
        """One clock per lane: with the full loop inside a long sync, a quick branch there would never fire anyway."""
        class Stop(Exception): pass
        server._LAST_POLL[0] = time.time()
        with mock.patch.object(server, '_poll_reports') as poll, mock.patch.object(server.time, 'sleep', side_effect=Stop):
            with self.assertRaises(Stop): server.poll_forever()
        poll.assert_not_called()


def test_lifespan_starts_the_chat_clock_as_its_own_guarded_boundary(test_safety_events):
    from fastapi.testclient import TestClient
    start = len(test_safety_events)
    with TestClient(server.app) as client:
        assert client.get('/api/health').status_code == 200
    assert ('lifespan boundary', 'chat poll scheduler') in set(test_safety_events[start:])


class DrainOrderTests(unittest.TestCase):
    """drain() is the one place triage happens, in arrival order per conversation. Fresh chat
    channels move to the front of the line; nothing else about the order changes."""
    def setUp(self):
        self.s = MemoryStore()
        self.order = []
        def judged(store, msg, llm=None, **k):
            self.order.append(msg['_mid']); store.place_message(msg['_mid'], None, 'filed')
            return {'status': 'filed', 'task_id': None, 'message_id': msg['_mid']}
        self.judged = judged
        p = mock.patch.object(ingest, 'ingest_message', judged); p.start(); self.addCleanup(p.stop)
        self.addCleanup(ingest._FRESH.clear)

    def test_fresh_channels_are_judged_first_and_in_their_own_order(self):
        rows = [pending_row(self.s, ch, i) for i, ch in enumerate(('email', 'email', 'teams', 'teams'))]
        ingest.drain(self.s, fresh=['teams'])
        self.assertEqual(self.order, [rows[2], rows[3], rows[0], rows[1]])

    def test_without_fresh_channels_the_order_is_arrival(self):
        rows = [pending_row(self.s, ch, i) for i, ch in enumerate(('email', 'teams', 'email'))]
        ingest.drain(self.s)
        self.assertEqual(self.order, rows)

    def test_a_chat_that_lands_during_a_drain_is_judged_next(self):
        rows = [pending_row(self.s, 'email', i) for i in range(3)]
        landed = []
        def judged(store, msg, llm=None, **k):
            if msg['_mid'] == rows[0]:
                landed.append(pending_row(store, 'teams', 9)); ingest.mark_fresh(['teams'])
            return self.judged(store, msg, llm)
        with mock.patch.object(ingest, 'ingest_message', judged): ingest.drain(self.s)
        self.assertEqual(self.order, [rows[0], landed[0], rows[1], rows[2]])

    def test_only_fresh_leaves_the_rest_of_the_queue_for_the_full_lane(self):
        rows = [pending_row(self.s, ch, i) for i, ch in enumerate(('email', 'teams'))]
        ingest.drain(self.s, fresh=['teams'], only_fresh=True)
        self.assertEqual(self.order, [rows[1]])
        self.assertEqual([r['MessageId'] for r in self.s.pending_triage()], [rows[0]])

    def test_a_second_drain_does_not_run_beside_the_first(self):
        rows = [pending_row(self.s, 'teams', 1)]
        ingest._DRAIN_LOCK.acquire()
        try:
            self.assertEqual(ingest.drain(self.s, fresh=['teams'], wait=False), 0)
            self.assertEqual(self.order, [])
            self.assertIn('teams', ingest._FRESH)          # the running drain is told to take teams next
        finally: ingest._DRAIN_LOCK.release()
        ingest.drain(self.s)
        self.assertEqual(self.order, rows)

    def test_await_quiet_watches_the_named_channels_only(self):
        pending_row(self.s, 'email', 1); teams = pending_row(self.s, 'teams', 2)
        self.assertFalse(ingest.await_quiet(self.s, ['teams'], timeout=0.2))
        self.s.place_message(teams, None, 'filed')
        self.assertTrue(ingest.await_quiet(self.s, ['teams'], timeout=0.2))

    def test_worker_start_failure_completes_the_request_and_remains_reusable(self):
        worker = ingest.DrainWorker(self.s, lambda: None)
        row = pending_row(self.s, 'teams', 1)
        with mock.patch.object(threading.Thread, 'start', side_effect=RuntimeError('no thread')):
            with self.assertRaisesRegex(RuntimeError, 'no thread'):
                worker.submit(fresh=['teams'], only_fresh=True)
        self.assertTrue(worker.join(0.1), 'failed start left an unreachable queued request')
        ticket = worker.submit(fresh=['teams'], only_fresh=True)
        self.assertTrue(ticket.wait(10))
        self.assertIsNone(ticket.error)
        self.assertEqual(self.order, [row])
        self.assertTrue(worker.close(10))


if __name__ == '__main__':
    unittest.main()
