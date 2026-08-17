"""Template docs, doc-sync automation, and the cloud-AI llm layer - all offline."""
import unittest
from unittest import mock
from taskuary.store import MemoryStore
from taskuary import docsync, llm


class TemplateTests(unittest.TestCase):
    def test_docs_seeded_from_templates(self):
        s = MemoryStore()
        soul, coder = s.get_doc('soul'), s.get_doc('coder')
        self.assertIn('John Smith', soul); self.assertIn('John Smith', coder)
        self.assertIn(docsync.CONN_START, soul)
        self.assertIn('===RESULT JSON===', coder)
        self.assertTrue(s.get_doc('digest'))

    def test_owner_edits_never_overwritten(self):
        s = MemoryStore()
        s.save_doc('soul', 'my own rules', 'owner')
        s2_content = s.get_doc('soul')  # re-init on same db would use INSERT OR IGNORE
        self.assertEqual(s2_content, 'my own rules')

    def test_connectors_seeded(self):
        types = {c['Type'] for c in MemoryStore().list_connectors()}
        self.assertTrue({'outlook', 'teams', 'slack', 'github', 'anthropic', 'openai', 'azure_openai'} <= types)


class DocSyncTests(unittest.TestCase):
    def test_sync_connections_fills_marker_block(self):
        s = MemoryStore()
        gh = next(c for c in s.list_connectors() if c['Type'] == 'github')
        s.save_connector({'ConnectorId': gh['ConnectorId'], 'Active': 1}, 'o')
        s.save_source({'Channel': 'github', 'Address': 'you/repo', 'ConnectorId': gh['ConnectorId'], 'Active': 1}, 'o')
        s.save_source({'Channel': 'report', 'Address': 'Census', 'Active': 1,
                       'ConfigJson': '{"type": "mssql", "title": "Census", "every_minutes": 30}'}, 'o')
        docsync.sync_connections(s)
        soul = s.get_doc('soul')
        self.assertIn('GitHub: you/repo', soul)
        self.assertIn('Report "Census" (mssql, every 30m)', soul)
        # prose outside the markers untouched
        self.assertIn('John Smith', soul)

    def test_update_repo_map_preserves_notes(self):
        s = MemoryStore()
        docsync.update_repo_map(s, [{'full_name': 'o/one', 'description': 'the app', 'archived': False}])
        s.save_doc('soul', s.get_doc('soul').replace('**o/one**: the app', '**o/one**: MY NOTE'), 'owner')
        docsync.update_repo_map(s, [{'full_name': 'o/one', 'description': 'the app', 'archived': False},
                                    {'full_name': 'o/two', 'description': None, 'archived': True}])
        soul = s.get_doc('soul')
        self.assertIn('MY NOTE', soul)                       # hand edit preserved
        self.assertEqual(soul.count('o/one'), 1)             # no duplicate line
        self.assertIn('**o/two**', soul); self.assertIn('archived - do not touch', soul)


class GraphCredsTests(unittest.TestCase):
    def test_teams_borrows_outlook_creds(self):
        from taskuary.channels import graph_creds
        s = MemoryStore()
        o = next(c for c in s.list_connectors() if c['Type'] == 'outlook')
        s.save_connector({'ConnectorId': o['ConnectorId'], 'Secret': 'graph-secret',
                          'ConfigJson': '{"tenant_id": "t1", "client_id": "c1"}'}, 'o')
        t = s.get_connector_by_type('teams', with_secret=True)
        cfg, sec, borrowed = graph_creds(s, t)
        self.assertEqual((cfg['tenant_id'], cfg['client_id'], sec, borrowed), ('t1', 'c1', 'graph-secret', True))

    def test_teams_own_creds_win(self):
        from taskuary.channels import graph_creds
        s = MemoryStore()
        o = next(c for c in s.list_connectors() if c['Type'] == 'outlook')
        s.save_connector({'ConnectorId': o['ConnectorId'], 'Secret': 'osec', 'ConfigJson': '{"client_id": "oc"}'}, 'o')
        t = next(c for c in s.list_connectors() if c['Type'] == 'teams')
        s.save_connector({'ConnectorId': t['ConnectorId'], 'Secret': 'tsec', 'ConfigJson': '{"client_id": "tc", "tenant_id": "tt"}'}, 'o')
        cfg, sec, borrowed = graph_creds(s, s.get_connector_by_type('teams', with_secret=True))
        self.assertEqual((cfg['client_id'], sec, borrowed), ('tc', 'tsec', False))

    def test_outlook_never_borrows(self):
        from taskuary.channels import graph_creds
        s = MemoryStore()
        cfg, sec, borrowed = graph_creds(s, s.get_connector_by_type('outlook', with_secret=True))
        self.assertEqual((sec, borrowed), (None, False))


class OutboundMailTests(unittest.TestCase):
    def _sent(self, conv=None, i='sm1'):
        return {'id': i, 'subject': 'RE: Financial Request', 'conversationId': conv,
                'bodyPreview': 'March thru June attached.', 'sentDateTime': '2026-08-17T15:00:00Z'}

    def test_sent_mail_files_never_tasks(self):
        from taskuary.channels import ingest_outbound_mail
        s = MemoryStore()
        n = ingest_outbound_mail(s, 'me@x.com', self._sent())
        self.assertEqual(n, 1)
        row = s.feed()[0]
        self.assertEqual((row['TaskId'], row['MsgStatus'], row['FromName']), (None, 'filed', 'You'))
        self.assertIn('your sent reply', row['RouteReason'])
        self.assertEqual(s.list_tasks(), [])
        # dedup on second poll
        self.assertEqual(ingest_outbound_mail(s, 'me@x.com', self._sent()), 0)

    def test_sent_mail_attaches_to_conversation_task(self):
        from taskuary.channels import ingest_outbound_mail
        from taskuary.ingest import ingest_message
        s = MemoryStore()
        out = ingest_message(s, {'external_id': 'in1', 'channel': 'email', 'subject': 'Financial Request',
                                 'body': 'please send March thru June', 'from_email': 'client@y.com',
                                 'conversation_id': 'c9', 'sent_at': '2026-08-17 14:00', 'from_name': 'Client'},
                             llm=lambda a, b: '{"intent": "task", "why": "t"}')
        ingest_outbound_mail(s, 'me@x.com', self._sent(conv='c9', i='sm2'))
        msgs = s.list_messages(out['task_id'])
        self.assertEqual(len(msgs), 2)                       # both sides on the thread
        self.assertEqual({m['FromName'] for m in msgs}, {'Client', 'You'})
        self.assertEqual(len(s.list_tasks()), 1)             # no new task from the reply

    def test_ai_failure_files_instead_of_task(self):
        from taskuary.ingest import ingest_message
        def boom(a, b): raise RuntimeError('azure 400: max_tokens')
        s = MemoryStore()
        out = ingest_message(s, {'external_id': 'e1', 'channel': 'email', 'subject': 'please fix the report',
                                 'body': 'please fix the report', 'from_email': 'a@b.com', 'sent_at': '2026-08-17 14:00'},
                             llm=boom)
        self.assertEqual((out['status'], out['task_id']), ('filed', None))
        self.assertIn('AI triage failed', s.feed()[0]['RouteReason'])


class LlmTests(unittest.TestCase):
    def test_build_llm_none_without_active_key(self):
        self.assertIsNone(llm.build_llm(MemoryStore()))

    def test_build_llm_picks_first_active_with_key(self):
        s = MemoryStore()
        oa = next(c for c in s.list_connectors() if c['Type'] == 'openai')
        s.save_connector({'ConnectorId': oa['ConnectorId'], 'Active': 1, 'Secret': 'sk-x',
                          'ConfigJson': '{"model": "gpt-4o-mini"}'}, 'o')
        fn = llm.build_llm(s)
        self.assertTrue(callable(fn))
        with mock.patch('taskuary.llm.requests.post') as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {'choices': [{'message': {'content': '{"intent": "fyi"}'}}]}
            self.assertEqual(fn('sys', 'usr'), '{"intent": "fyi"}')

    def test_make_llm_validates(self):
        with self.assertRaises(RuntimeError): llm.make_llm('openai', {}, None)
        with self.assertRaises(RuntimeError): llm.make_llm('azure_openai', {}, 'k')


if __name__ == '__main__':
    unittest.main()
