"""The hovering guide: one hidden durable chat, grounded in fresh workspace state."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import general, server
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


if __name__ == '__main__':
    unittest.main()
