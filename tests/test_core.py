"""Core engine tests - everything runs on the in-memory SQLite store, no network."""
import unittest
from taskuary.store import MemoryStore, task_ref
from taskuary.ingest import ingest_message
from taskuary.routing import route
from taskuary.triage import heuristic_intent
from taskuary.agents import parse_cli_json
from taskuary.coder import parse_coder_result, RESULT_MARKER
from taskuary.reports import is_due, run_report_source, REGISTRY


TASK_LLM = lambda sys, usr: '{"intent": "task", "why": "t"}'
REPLY_LLM = lambda sys, usr: '{"intent": "reply_only", "why": "q"}'


class CoreTests(unittest.TestCase):
    def msg(self, **kw):
        base = {'external_id': kw.get('external_id', 'x1'), 'channel': 'api', 'subject': 's',
                'body': 'please add the new user to the system', 'from_email': 'a@b.com',
                'conversation_id': None, 'sent_at': '2026-08-17 09:00', 'source_link': None, 'from_name': 'A'}
        return {**base, **kw}

    def test_ingest_creates_task_and_feed(self):
        s = MemoryStore()
        out = ingest_message(s, self.msg(), llm=TASK_LLM)
        self.assertEqual(out['status'], 'created')
        self.assertEqual(task_ref(out['task_id']), 'TQ-0001')
        self.assertEqual(len(s.feed()), 1)
        self.assertEqual(ingest_message(s, self.msg(), llm=TASK_LLM)['status'], 'duplicate')

    def test_no_ai_connector_files_instead_of_task_spam(self):
        # without an active AI connector, inbound is FILED (visible, no task) - the AI
        # decides what becomes a task, not the default-to-task heuristic
        s = MemoryStore()
        out = ingest_message(s, self.msg(external_id='noai1'))
        self.assertEqual((out['status'], out['task_id']), ('filed', None))
        self.assertIn('awaiting AI triage', s.feed()[0]['RouteReason'])

    def test_thread_attach(self):
        s = MemoryStore()
        a = ingest_message(s, self.msg(external_id='m1', conversation_id='c1'), llm=TASK_LLM)
        b = ingest_message(s, self.msg(external_id='m2', conversation_id='c1', body='and one more thing'), llm=TASK_LLM)
        self.assertEqual((b['status'], b['task_id']), ('attached', a['task_id']))

    def test_fyi_files_without_task(self):
        s = MemoryStore()
        out = ingest_message(s, self.msg(external_id='f1', subject='report', body='this is an automated summary'))
        self.assertEqual((out['status'], out['task_id']), ('filed', None))

    def test_reply_only_kind(self):
        s = MemoryStore()
        out = ingest_message(s, self.msg(external_id='q1', subject='Tuesday?', body='are you available tuesday?'), llm=REPLY_LLM)
        self.assertEqual(s.get_task(out['task_id'])['Kind'], 'reply')

    def test_reply_only_enters_review_queue(self):
        s = MemoryStore()
        out = ingest_message(s, self.msg(external_id='rq1', subject='Tuesday?', body='are you available tuesday?'), llm=REPLY_LLM)
        pending = s.list_reviews('pending')
        self.assertEqual(len(pending), 1)
        self.assertEqual((pending[0]['TaskId'], pending[0]['Kind']), (out['task_id'], 'draft'))

    def test_coder_auto_dispatch_when_enabled(self):
        from unittest import mock
        import taskuary.ingest as ing

        class InlineThread:
            def __init__(self, target=None, args=(), daemon=None): self.t, self.a = target, args
            def start(self): self.t(*self.a)

        s = MemoryStore()
        s.set_setting('coder_auto_enabled', '1', 't')
        with mock.patch.object(ing, 'threading') as th,              mock.patch('taskuary.coder.run_coding_task') as run,              mock.patch('taskuary.coder.github_cfg', return_value={}):
            th.Thread = InlineThread
            out = ingest_message(s, self.msg(external_id='ac1'), llm=TASK_LLM)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[1], out['task_id'])
        self.assertTrue(any('auto-dispatched' in c['Body'] for c in s.list_comments(out['task_id'])))

    def test_no_auto_dispatch_when_disabled(self):
        from unittest import mock
        s = MemoryStore()
        with mock.patch('taskuary.coder.run_coding_task') as run:
            ingest_message(s, self.msg(external_id='ac2'), llm=TASK_LLM)
        run.assert_not_called()

    def test_triage_heuristics(self):
        self.assertEqual(heuristic_intent({'subject': '', 'body': 'are you available tuesday?'})['intent'], 'reply_only')
        self.assertEqual(heuristic_intent({'subject': 'fyi', 'body': 'this is an automated notice'})['intent'], 'fyi')

    def test_resolve_cmd_wraps_npm_shims(self):
        from unittest import mock
        from taskuary.agents import _resolve_cmd
        shim = 'C:/Users/u/AppData/Roaming/npm/claude.CMD'
        with mock.patch('shutil.which', return_value=shim), mock.patch('taskuary.agents.os') as fake_os:
            fake_os.name = 'nt'
            self.assertEqual(_resolve_cmd('claude'), ['cmd', '/c', shim])
        with mock.patch('shutil.which', return_value='/usr/local/bin/claude'):
            self.assertEqual(len(_resolve_cmd('claude')), 1)
        with mock.patch('shutil.which', return_value=None):
            with self.assertRaises(FileNotFoundError): _resolve_cmd('claude')

    def test_failed_coder_run_escalates_not_empty_report(self):
        from unittest import mock
        from taskuary.coder import run_coding_task
        s = MemoryStore()
        tid = s.create_task({'Title': 'fix it', 'Kind': 'coding'}, 'o')
        s.upsert_agent('coder', 'coding', 'cli', '{}')
        rid = s.start_run(tid, 'coder', 'i', 'o')
        s.update_run(rid, {'Status': 'error', 'LastError': 'claude not found'}, finished=True)
        with mock.patch('taskuary.agents.dispatch', return_value={'run_id': rid, 'status': 'error', 'result': None}):
            out = run_coding_task(s, tid, 'o', None, {})
        self.assertIn('error', out)
        bodies = [c['Body'] for c in s.list_comments(tid)]
        self.assertTrue(any('Coder run FAILED' in b for b in bodies))
        self.assertFalse(any(b.startswith('CODER REPORT') for b in bodies))
        pend = s.list_reviews('pending')
        self.assertEqual((len(pend), pend[0]['Kind']), (1, 'escalation'))

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
