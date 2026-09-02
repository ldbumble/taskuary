"""Full session artifacts remain available beside compact Agent work summaries."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import server, session_artifacts
from taskuary.store import MemoryStore


class SessionArtifactTests(unittest.TestCase):
    def test_coding_artifact_keeps_the_compact_result_and_full_transcript(self):
        store = MemoryStore()
        tid = store.create_task({'Title': 'Research Azure deployments', 'Kind': 'coding'}, 'owner')
        artifact = session_artifacts.coding(
            store, tid, 'Summary: deployments were unavailable.',
            'Investigated every resource.\nThe full evidence and follow-up details are here.', 'coder')
        saved = session_artifacts.confined(artifact['Path']).read_text(encoding='utf-8')
        self.assertIn('deployments were unavailable', saved)
        self.assertIn('full evidence and follow-up details', saved)
        self.assertEqual(store.list_task_artifacts(tid)[0]['Kind'], 'coding_session')

    def test_task_detail_returns_safe_agent_artifact_link(self):
        store = MemoryStore()
        tid = store.create_task({'Title': 'Market research agent', 'Kind': 'coding'}, 'owner')
        session_artifacts.coding(store, tid, 'Summary: research complete.', 'Full agent findings.', 'coder')
        with mock.patch.object(server, 'store', store):
            client = TestClient(server.app)
            detail = client.get(f'/api/tasks/{tid}').json()
            opened = client.get(detail['artifacts'][0]['url'])
        self.assertEqual(opened.status_code, 200)
        self.assertIn('Full agent findings', opened.text)
        self.assertEqual(detail['artifacts'][0]['kind'], 'coding_session')
        self.assertNotIn('Path', detail['artifacts'][0])
        self.assertTrue(detail['artifacts'][0]['url'].startswith('/api/task-artifacts/'))


if __name__ == '__main__':
    unittest.main()
