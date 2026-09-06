"""Two poll lanes: a slow full sync can no longer hold up fresh chat intake.

PW-001/PW-002/PW-005 (docs/processing-walkthrough-todos.md). The full lane keeps the
one-at-a-time lock that stopped overlapping catch-ups, and still runs channels, triage,
CI and reports in that order. The chat lane has its own short lock and its own clock, so
AI triage over a mail backlog or a slow report leaves Teams/WhatsApp/... arriving on time.
A connector type is fetched by one lane at a time (dedupe never races), the full lane's
own chat fetch counts on the fast clock, and triage stays ONE ordered drain - the fresh
chat channels are judged first, within-channel order untouched.
"""
import json, threading, time, unittest
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

    def full_in_background(self, poll, **kw):
        t = threading.Thread(target=server._poll_reports, kwargs={'what': 'syncing', **kw}, daemon=True)
        with mock.patch('taskuary.channels.poll_channels', poll): t.start(); return t

    def test_a_slow_full_sync_does_not_hold_up_a_chat_poll(self):
        """The full lane is judging a mail backlog (the brain is slow); a Teams poll still reads Teams now."""
        started, release, polled = threading.Event(), threading.Event(), []
        def poll(store, days, progress=None, only=None):
            polled.append(only)
            if only is None: pending_row(store, 'email', 1)
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
        self.assertEqual(polled, [None, ['teams']])

    def test_a_full_sync_counts_as_the_chat_fetch_it_included(self):
        """PW-002: the full pass read Teams too, so the fast clock must not fetch it again a moment later."""
        with mock.patch('taskuary.channels.poll_channels', lambda s, d, progress=None, **k: 0), mock.patch('taskuary.ingest.drain', return_value=0):
            server._poll_reports(0, what='syncing')
        self.assertLess(time.time() - server._QUICK_LAST.get('teams', 0), 5)
        self.assertNotIn('teams', server._quick_due())

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
            if only is None: started.set(); release.wait(10)
            return 0
        with mock.patch('taskuary.channels.poll_channels', poll), mock.patch('taskuary.ingest.drain', return_value=0):
            t = threading.Thread(target=server._poll_reports, kwargs={'what': 'syncing'}, daemon=True); t.start()
            self.assertTrue(started.wait(10))
            got = server._poll_reports(0, what='syncing', only=['teams'])
            release.set(); t.join(10)
        self.assertIs(got, False)
        self.assertEqual(calls, [None], 'teams was fetched by both lanes at once')

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

    def test_the_context_gate_waits_for_an_in_flight_fetch_instead_of_skipping(self):
        """wait=True is the correctness gate before an answer about a chat: it must end with a fresh read."""
        started, calls = threading.Event(), []
        def poll(store, days, progress=None, only=None):
            calls.append(only)
            if only is None: started.set(); time.sleep(0.3)
            return 1
        with mock.patch('taskuary.channels.poll_channels', poll), mock.patch('taskuary.ingest.drain', return_value=0):
            t = threading.Thread(target=server._poll_reports, kwargs={'what': 'syncing'}, daemon=True); t.start()
            self.assertTrue(started.wait(10))
            got = server._poll_reports(0, what='refreshing teams context', only=['teams'], wait=True)
            t.join(10)
        self.assertEqual(got, 1)
        self.assertEqual(calls, [None, ['teams']])

    def test_the_context_gate_reports_still_syncing_when_triage_cannot_catch_up(self):
        """A fetched line that is still waiting its turn behind a long drain is not fresh context."""
        pending_row(self.s, 'teams', 1)
        ingest._DRAIN_LOCK.acquire()
        try:
            with mock.patch('taskuary.channels.poll_channels', lambda *a, **k: 1), mock.patch.object(server, 'DRAIN_WAIT', 0.3):
                self.assertIs(server._poll_reports(0, what='refreshing teams context', only=['teams'], wait=True), False)
        finally: ingest._DRAIN_LOCK.release()

    def test_a_chat_poll_does_not_end_the_full_syncs_banner(self):
        started, release = threading.Event(), threading.Event()
        def poll(store, days, progress=None, only=None):
            if only is None: pending_row(store, 'email', 1)
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


if __name__ == '__main__':
    unittest.main()
