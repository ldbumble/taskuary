"""The hovering guide: one hidden durable chat, grounded in fresh workspace state."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import general, server, terminal
from taskuary.store import MemoryStore


class FloatingAssistantTests(unittest.TestCase):
    def test_dock_is_idempotent_and_never_becomes_an_outstanding_task(self):
        store = MemoryStore()
        with mock.patch.object(server, 'store', store):
            client = TestClient(server.app)
            first = client.post('/api/assistant/dock')
            second = client.post('/api/assistant/dock')
            visible = client.get('/api/tasks').json()['data']
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()['created'])
        self.assertFalse(second.json()['created'])
        self.assertEqual(first.json()['task']['TaskId'], second.json()['task']['TaskId'])
        self.assertEqual(first.json()['task']['SourceRef'], general.DOCK_TAG)
        self.assertEqual(visible, [])

    def test_new_chat_archives_the_old_dock_and_returns_an_empty_one(self):
        store = MemoryStore()
        with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            client = TestClient(server.app)
            old = client.post('/api/assistant/dock').json()['task']
            store.add_comment(old['TaskId'], 'owner', general.USER_TYPE, 'A long conversation')
            store.add_comment(old['TaskId'], 'assistant', general.ASSISTANT_TYPE, 'Its answer')
            fresh = client.post('/api/assistant/dock/new')
            again = client.post('/api/assistant/dock').json()['task']
        self.assertEqual(fresh.status_code, 200)
        self.assertEqual(fresh.json()['archivedTaskId'], old['TaskId'])
        self.assertEqual(store.get_task(old['TaskId'])['Status'], 'done')
        self.assertNotEqual(fresh.json()['task']['TaskId'], old['TaskId'])
        self.assertEqual(fresh.json()['task']['TaskId'], again['TaskId'])
        self.assertEqual(general.history(store, again['TaskId']), [])

    def test_new_chat_refuses_to_cut_off_an_answer_in_progress(self):
        store = MemoryStore()
        with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            client = TestClient(server.app)
            old = client.post('/api/assistant/dock').json()['task']
            session = general.GeneralSession(store, old['TaskId'])
            session.busy = True
            terminal.SESSIONS[session.sid] = session
            response = client.post('/api/assistant/dock/new')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(store.get_task(old['TaskId'])['Status'], 'open')

    def test_guide_gets_live_attention_tasks_reviews_timeline_and_agent_output(self):
        store = MemoryStore()
        tid = store.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'waiting',
                                 'Priority': 'high'}, 'owner')
        mid = store.add_message({'TaskId': tid, 'ExternalId': 'mail:export', 'Channel': 'email',
                                 'Subject': 'Export still broken', 'FromName': 'Dana',
                                 'SentAt': '2026-09-02 09:00:00', 'BodyText': 'Can you send the corrected file?',
                                 'Status': 'routed'})
        store.add_route(mid, tid, 'create', .9, 'Dana asked for a corrected file', [], 'router')
        store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'reply', 'DraftText': 'Attached.',
                          'Status': 'pending'})
        store.add_comment(tid, 'coder', 'agent', 'CODER REPORT\nCorrected the CSV escaping and added a regression test.')
        snapshot = general.dock_snapshot(store)
        self.assertIn('NEEDS THE OWNER NOW', snapshot)
        self.assertIn('Export still broken', snapshot)
        self.assertIn('ACTIVE TASKS', snapshot)
        self.assertIn('TQ-0001 | waiting | high | Fix the export', snapshot)
        self.assertIn('PENDING REVIEW', snapshot)
        self.assertIn('rv1 | TQ-0001', snapshot)
        self.assertIn('Draft ready: Attached.', snapshot)
        self.assertIn('RECENT TIMELINE', snapshot)
        self.assertIn('RECENT AGENT OUTPUT', snapshot)
        self.assertIn('Corrected the CSV escaping', snapshot)

    def test_dock_prompt_teaches_links_and_contains_the_fresh_snapshot(self):
        store = MemoryStore()
        tid = store.create_task({'Title': 'Taskuary guide', 'Kind': 'general', 'Status': 'open',
                                 'SourceRef': general.DOCK_TAG}, 'owner')
        work = store.create_task({'Title': 'Review launch plan', 'Kind': 'general', 'Status': 'open'}, 'owner')
        system, user = general._prompt(store, tid)
        self.assertIn('HOVERING GUIDE', system)
        self.assertIn('WALKTHROUGH MODE', system)
        self.assertIn('ACTION SURFACE', system)
        self.assertIn('Commentary explains; the clearly labelled owner button acts.', system)
        self.assertIn('exactly ONE unresolved item', system)
        self.assertIn('[TQ-0001](#task=1)', system)
        self.assertIn('WORKSPACE SNAPSHOT', user)
        self.assertIn(f'TQ-{work:04d}', user)

    def test_starting_the_dock_session_does_not_put_it_on_the_timeline(self):
        store = MemoryStore()
        tid = store.create_task({'Title': 'Taskuary guide', 'Kind': 'general', 'Status': 'open',
                                 'SourceRef': general.DOCK_TAG}, 'owner')
        from taskuary import terminal
        with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            general.start_session(store, tid)
            client = TestClient(server.app)
            self.assertEqual(client.get('/api/terminals').json()['data'], [])
            self.assertEqual(client.get('/api/runs/live').json()['data'], [])
            self.assertEqual(store.list_messages(tid), [])
            self.assertEqual(store.feed(), [])

    def test_dock_ai_choice_is_visible_configuration_shared_with_whatsapp(self):
        store = MemoryStore()
        connector = store.get_connector_by_type('openai')
        store.save_connector({'ConnectorId': connector['ConnectorId'], 'Active': 1, 'Secret': 'test-key',
                              'Name': 'Fast assistant', 'ConfigJson': '{"model":"gpt-fast"}'}, 'owner')
        with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            client = TestClient(server.app)
            task = client.post('/api/assistant/dock').json()['task']
            response = client.post(f"/api/tasks/{task['TaskId']}/assistant/session",
                                   json={'pick': f"connector:{connector['ConnectorId']}", 'model': 'gpt-fast-2'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(store.get_settings()['assistant_ai'], f"connector:{connector['ConnectorId']}")
        self.assertEqual(store.get_settings()['assistant_model'], 'gpt-fast-2')
        self.assertEqual(response.json()['session']['model'], 'gpt-fast-2')


if __name__ == '__main__':
    unittest.main()
