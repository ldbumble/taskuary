"""Core engine tests - everything runs on the in-memory SQLite store, no network."""
import unittest
from taskhub.store import MemoryStore, task_ref
from taskhub.ingest import ingest_message
from taskhub.routing import route
from taskhub.triage import heuristic_intent
from taskhub.agents import parse_cli_json
from taskhub.coder import parse_coder_result, RESULT_MARKER
from taskhub.reports import is_due, run_report_source, REGISTRY


class CoreTests(unittest.TestCase):
    def msg(self, **kw):
        base = {'external_id': kw.get('external_id', 'x1'), 'channel': 'api', 'subject': 's',
                'body': 'please add the new user to the system', 'from_email': 'a@b.com',
                'conversation_id': None, 'sent_at': '2026-08-17 09:00', 'source_link': None, 'from_name': 'A'}
        return {**base, **kw}

    def test_ingest_creates_task_and_feed(self):
        s = MemoryStore()
        out = ingest_message(s, self.msg())
        self.assertEqual(out['status'], 'created')
        self.assertEqual(task_ref(out['task_id']), 'TH-0001')
        self.assertEqual(len(s.feed()), 1)
        self.assertEqual(ingest_message(s, self.msg())['status'], 'duplicate')

    def test_thread_attach(self):
        s = MemoryStore()
        a = ingest_message(s, self.msg(external_id='m1', conversation_id='c1'))
        b = ingest_message(s, self.msg(external_id='m2', conversation_id='c1', body='and one more thing'))
        self.assertEqual((b['status'], b['task_id']), ('attached', a['task_id']))

    def test_fyi_files_without_task(self):
        s = MemoryStore()
        out = ingest_message(s, self.msg(external_id='f1', subject='report', body='this is an automated summary'))
        self.assertEqual((out['status'], out['task_id']), ('filed', None))

    def test_reply_only_kind(self):
        s = MemoryStore()
        out = ingest_message(s, self.msg(external_id='q1', subject='Tuesday?', body='are you available tuesday?'))
        self.assertEqual(s.get_task(out['task_id'])['Kind'], 'reply')

    def test_triage_heuristics(self):
        self.assertEqual(heuristic_intent({'subject': '', 'body': 'are you available tuesday?'})['intent'], 'reply_only')
        self.assertEqual(heuristic_intent({'subject': 'fyi', 'body': 'this is an automated notice'})['intent'], 'fyi')

    def test_cli_json_parse(self):
        self.assertEqual(parse_cli_json('{"result": "OK", "session_id": "abc"}'), ('OK', 'abc'))
        self.assertEqual(parse_cli_json('plain'), ('plain', None))

    def test_coder_report_contract(self):
        out = 'work\n' + RESULT_MARKER + '\n{"summary": "s", "close": true, "email_reply": "r"}'
        rep = parse_coder_result(out)
        self.assertTrue(rep['close']); self.assertEqual(rep['email_reply'], 'r')
        self.assertFalse(parse_coder_result('no marker')['close'])

    def test_orphaned_reviews_never_queue(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 't'}, 'u')
        s.add_review({'TaskId': tid, 'Kind': 'escalation', 'Status': 'pending', 'Reason': 'r'})
        s.delete_task(tid)
        s.add_review({'TaskId': tid, 'Kind': 'escalation', 'Status': 'pending', 'Reason': 'late'})
        self.assertEqual(s.list_reviews('pending'), [])

    def test_audit_chain_verifies(self):
        s = MemoryStore()
        s.audit('task', 1, 'create', 'u'); s.audit('task', 1, 'edit', 'u')
        self.assertTrue(s.verify_audit_chain()['ok'])

    def test_report_schedule_and_run(self):
        from datetime import datetime, timedelta
        now = datetime.now()
        self.assertTrue(is_due({'every_minutes': 30}, (now - timedelta(minutes=45)).isoformat(sep=' ')))
        self.assertFalse(is_due({'every_minutes': 30}, (now - timedelta(minutes=5)).isoformat(sep=' ')))
        s = MemoryStore()
        REGISTRY['_t'] = lambda cfg: ('3 rows', 'a\nb\nc')
        try:
            out = run_report_source(s, {'SourceId': 1, 'Address': 'Census', 'ConfigJson': '{"type": "_t"}'})
            m = s.get_message(out['message_id'])
            self.assertEqual((m['Channel'], m['Status'], m['TaskId']), ('report', 'filed', None))
        finally:
            REGISTRY.pop('_t')


if __name__ == '__main__':
    unittest.main()
