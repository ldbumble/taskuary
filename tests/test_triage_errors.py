"""Failed triage is an error with a retry, not an FYI (PW-036 to PW-041).

A model that raised, an answer that was not a verdict, a queue drain that blew up, and an
install with no AI connector all used to land the message as `filed` - the same face a genuine
"nothing to do" wears - with the failure buried in a route reason. Now the message carries
`Status='error'` with the reason on its route, keeps its content, attachments and any task link,
stays visible, and the existing retry endpoint claims it error -> triaging atomically, so two
clicks cannot make two tasks. A retry that succeeds lands the verdict; one that fails returns
the row to error with the new reason. Historical failures still stored as filed are upgraded
once, by their diagnostic route reason - never genuine FYI, never read state.
"""
import unittest
from unittest import mock
from fastapi.testclient import TestClient

from taskuary import ingest, server
from taskuary.store import MemoryStore

MSG = {'external_id': 'e1', 'channel': 'email', 'from_email': 'someone@partner.example', 'from_name': 'Someone',
       'conversation_id': 'conv-e1', 'subject': 'Refund for Watson', 'body': 'Please look at the attached history.',
       'sent_at': '2026-09-06 10:00:00'}


def boom(*a, **k): raise RuntimeError('model timed out')


def last_reason(s, mid): return s.message_routes(mid)[-1]['Reason']


class ErrorStateTests(unittest.TestCase):
    def test_a_model_that_raises_lands_the_message_as_an_error_not_fyi(self):
        s = MemoryStore()
        out = ingest.ingest_message(s, dict(MSG), llm=boom)
        self.assertEqual(out['status'], 'error'); self.assertIsNone(out['task_id'])
        m = s.get_message(out['message_id'])
        self.assertEqual(m['Status'], 'error'); self.assertEqual(m['BodyText'], MSG['body'])
        self.assertIn('model timed out', last_reason(s, out['message_id']))
        row = next(r for r in s.feed(limit=10) if r['MessageId'] == out['message_id'])
        self.assertEqual(row['MsgStatus'], 'error'); self.assertEqual(row['NeedsYou'], 0)

    def test_an_answer_that_is_not_a_verdict_is_an_error_with_the_raw_output_kept(self):
        s = MemoryStore()
        out = ingest.ingest_message(s, dict(MSG), llm=lambda *a, **k: 'I think this is probably a task?')
        self.assertEqual(out['status'], 'error')
        route = s.message_routes(out['message_id'])[-1]
        self.assertEqual(route['RawOutput'], 'I think this is probably a task?')
        self.assertIn('JSONDecodeError', route['ParseError'])

    def test_a_drain_that_blows_up_leaves_an_error_not_a_filed_row(self):
        s = MemoryStore()
        with ingest.deferred(): out = ingest.ingest_message(s, dict(MSG), llm=boom)
        self.assertEqual(out['status'], 'queued')
        with mock.patch.object(ingest, 'ingest_message', side_effect=RuntimeError('drain exploded')):
            ingest.drain(s, llm=boom)
        self.assertEqual(s.get_message(out['message_id'])['Status'], 'error')
        self.assertIn('drain exploded', last_reason(s, out['message_id']))

    def test_no_ai_connector_is_an_explicit_awaiting_state_not_a_successful_fyi(self):
        s = MemoryStore()
        out = ingest.ingest_message(s, dict(MSG), llm=None)
        self.assertEqual(out['status'], 'error')
        self.assertIn('awaiting AI triage', last_reason(s, out['message_id']))

    def test_genuine_fyi_is_still_filed(self):
        s = MemoryStore()
        out = ingest.ingest_message(s, dict(MSG), llm=lambda *a, **k: '{"intent": "fyi", "why": "a notice"}')
        self.assertEqual(out['status'], 'filed')

    def test_a_follow_up_whose_triage_fails_keeps_its_task_link_and_says_so(self):
        """It used to be attached as ordinary work with nothing saying triage never read it."""
        s = MemoryStore()
        first = ingest.ingest_message(s, dict(MSG), llm=lambda *a, **k: '{"intent": "task", "kind": "task", "why": "x"}')
        tid = first['task_id']
        out = ingest.ingest_message(s, {**MSG, 'external_id': 'e2', 'body': 'And here is the second file.'}, llm=boom)
        self.assertEqual((out['status'], out['task_id']), ('error', tid))
        m = s.get_message(out['message_id'])
        self.assertEqual((m['Status'], m['TaskId']), ('error', tid))
        self.assertIn('model timed out', last_reason(s, out['message_id']))

    def test_the_brains_last_error_is_recorded_and_cleared_when_it_answers(self):
        s = MemoryStore()
        ingest.ingest_message(s, dict(MSG), llm=boom)
        self.assertIn('model timed out', s.get_settings().get('triage_last_error', ''))
        ingest.ingest_message(s, {**MSG, 'external_id': 'e3', 'conversation_id': 'conv-e3'}, llm=lambda *a, **k: '{"intent": "fyi", "why": "ok"}')
        self.assertEqual(s.get_settings().get('triage_last_error', ''), '')


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)

    def failed(self, ext='e1', **over):
        out = ingest.ingest_message(self.s, {**MSG, 'external_id': ext, **over}, llm=boom)
        self.assertEqual(out['status'], 'error')
        return out['message_id']

    def test_claim_moves_only_an_error_row_into_triage(self):
        mid = self.failed()
        self.assertTrue(self.s.claim_retriage(mid))
        self.assertEqual(self.s.get_message(mid)['Status'], 'triaging')
        self.assertFalse(self.s.claim_retriage(mid))                      # already claimed
        ok = ingest.ingest_message(self.s, {**MSG, 'external_id': 'ok'}, llm=lambda *a, **k: '{"intent": "fyi", "why": "n"}')
        self.assertFalse(self.s.claim_retriage(ok['message_id']))          # a genuine FYI is not retriable

    def test_a_successful_retry_lands_the_verdict_and_clears_the_error(self):
        mid = self.failed()
        verdict = lambda *a, **k: '{"intent": "task", "kind": "task", "why": "the owner must do it"}'
        with mock.patch.object(server, '_llm', return_value=verdict):
            first = self.c.post(f'/api/messages/{mid}/retriage')
            second = self.c.post(f'/api/messages/{mid}/retriage')
        self.assertEqual(first.status_code, 200)
        tid = first.json()['task_id']
        m = self.s.get_message(mid)
        self.assertEqual((m['Status'], m['TaskId']), ('routed', tid))
        self.assertEqual(second.status_code, 409)                          # a task already has it
        self.assertEqual(len(self.s.list_tasks()), 1)

    def test_another_failure_returns_to_error_with_the_new_reason(self):
        mid = self.failed()
        def worse(*a, **k): raise RuntimeError('still down, differently')
        with mock.patch.object(server, '_llm', return_value=worse):
            r = self.c.post(f'/api/messages/{mid}/retriage')
        self.assertEqual(r.status_code, 200); self.assertEqual(r.json()['status'], 'error')
        self.assertEqual(self.s.get_message(mid)['Status'], 'error')
        self.assertIn('still down, differently', last_reason(self.s, mid))

    def test_two_clicks_at_once_make_one_task(self):
        import threading
        mid = self.failed()
        gate, results = threading.Event(), []
        def slow_verdict(*a, **k):
            gate.wait(5); return '{"intent": "task", "kind": "task", "why": "x"}'
        def click():
            with mock.patch.object(server, '_llm', return_value=slow_verdict):
                results.append(self.c.post(f'/api/messages/{mid}/retriage').status_code)
        ts = [threading.Thread(target=click) for _ in range(2)]
        for t in ts: t.start()
        import time; time.sleep(0.3); gate.set()
        for t in ts: t.join(10)
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(len(self.s.list_tasks()), 1)

    def test_a_linked_message_can_be_retried_and_rejoins_its_task(self):
        first = ingest.ingest_message(self.s, dict(MSG), llm=lambda *a, **k: '{"intent": "task", "kind": "task", "why": "x"}')
        tid = first['task_id']
        mid = self.failed(ext='e2', body='And the second file.')
        self.assertEqual(self.s.get_message(mid)['TaskId'], tid)
        with mock.patch.object(server, '_llm', return_value=lambda *a, **k: '{"intent": "fyi", "why": "just the file"}'):
            r = self.c.post(f'/api/messages/{mid}/retriage')
        self.assertEqual(r.status_code, 200)
        m = self.s.get_message(mid)
        self.assertEqual(m['TaskId'], tid); self.assertNotEqual(m['Status'], 'error')
        self.assertEqual(len(self.s.list_tasks()), 1)

    def test_a_legacy_filed_failure_is_still_retriable(self):
        mid = self.s.add_message({**{k: v for k, v in MSG.items() if k in ('subject',)}, 'ExternalId': 'legacy', 'Channel': 'email',
                                  'ConversationId': 'legacy-conv', 'Subject': 'old failure', 'BodyText': 'do the thing',
                                  'FromEmail': 'x@y.example', 'Status': 'filed'})
        self.s.add_route(mid, None, 'file', None, 'AI triage returned an answer it could not read as a verdict - filed rather than assumed to be work', [], 'triage')
        with mock.patch.object(server, '_llm', return_value=lambda *a, **k: '{"intent": "task", "kind": "task", "why": "x"}'):
            self.assertEqual(self.c.post(f'/api/messages/{mid}/retriage').status_code, 200)
        self.assertEqual(self.s.get_message(mid)['Status'], 'routed')

    def test_retry_without_a_brain_says_so_and_keeps_the_error(self):
        mid = self.failed()
        with mock.patch.object(server, '_llm', return_value=None):
            r = self.c.post(f'/api/messages/{mid}/retriage')
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.s.get_message(mid)['Status'], 'error')


class LegacyUpgradeTests(unittest.TestCase):
    def rows(self, s):
        fail = s.add_message({'ExternalId': 'l1', 'Channel': 'email', 'ConversationId': 'l1', 'Subject': 'a', 'BodyText': 'b', 'FromEmail': 'x@y.example', 'Status': 'filed'})
        s.add_route(fail, None, 'file', None, 'AI triage failed (boom) - filed; fix the AI connector and it will classify new mail', [], 'triage')
        fyi = s.add_message({'ExternalId': 'l2', 'Channel': 'email', 'ConversationId': 'l2', 'Subject': 'a', 'BodyText': 'b', 'FromEmail': 'x@y.example', 'Status': 'filed'})
        s.add_route(fyi, None, 'file', None, 'triage: fyi - a newsletter', [], 'triage')
        fixed = s.add_message({'ExternalId': 'l3', 'Channel': 'email', 'ConversationId': 'l3', 'Subject': 'a', 'BodyText': 'b', 'FromEmail': 'x@y.example', 'Status': 'filed'})
        s.add_route(fixed, None, 'file', None, 'AI triage failed (boom) - filed', [], 'triage')
        s.add_route(fixed, None, 'ignore', None, 'not ours - the owner said so', [], 'owner')   # the owner ruled after the failure
        noai = s.add_message({'ExternalId': 'l4', 'Channel': 'email', 'ConversationId': 'l4', 'Subject': 'a', 'BodyText': 'b', 'FromEmail': 'x@y.example', 'Status': 'filed'})
        s.add_route(noai, None, 'file', None, 'awaiting AI triage - connect an AI connector (Connections → AI) to classify inbound automatically', [], 'triage')
        s.set_funnel_state(f'msg:{fail}', 'surfaced', 'owner')
        return fail, fyi, fixed, noai

    def test_identifiable_failures_become_errors_and_nothing_else_moves(self):
        s = MemoryStore(); fail, fyi, fixed, noai = self.rows(s)
        n = s.upgrade_triage_failures()
        self.assertEqual(n, 1)
        self.assertEqual(s.get_message(fail)['Status'], 'error')
        self.assertEqual(s.get_message(fyi)['Status'], 'filed')          # genuine FYI untouched
        self.assertEqual(s.get_message(fixed)['Status'], 'filed')        # the owner's later ruling stands
        self.assertEqual(s.get_message(noai)['Status'], 'filed')         # a no-AI install's history is not bulk-flipped
        self.assertEqual(s.funnel_states()[f'msg:{fail}']['Status'], 'surfaced')   # read state is not reset
        self.assertEqual(s.upgrade_triage_failures(), 0)                 # once

    def test_the_upgrade_runs_once_at_startup(self):
        s = MemoryStore(); self.rows(s)
        with mock.patch.object(server, 'store', s):
            with TestClient(server.app) as c: c.get('/api/health')
        self.assertEqual(s.get_message(1)['Status'], 'error')


if __name__ == '__main__':
    unittest.main()
