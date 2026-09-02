"""Full session artifacts remain available beside compact Agent work summaries."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import responder, server, session_artifacts
from taskuary.store import MemoryStore


class SessionArtifactTests(unittest.TestCase):
    def test_coding_artifact_keeps_compact_result_final_response_and_full_transcript(self):
        store = MemoryStore()
        tid = store.create_task({'Title': 'Research Azure deployments', 'Kind': 'coding'}, 'owner')
        artifact = session_artifacts.coding(
            store, tid, 'Summary: deployments were unavailable.',
            'Investigated every resource.\nThe full evidence and follow-up details are here.', 'coder',
            final_message='1. Checked production.\n2. Checked staging.\n3. Documented both results.')
        saved = session_artifacts.confined(artifact['Path']).read_text(encoding='utf-8')
        self.assertIn('deployments were unavailable', saved)
        self.assertIn('full evidence and follow-up details', saved)
        self.assertIn('1. Checked production.', saved)
        self.assertIn('3. Documented both results.', saved)
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

    def test_redraft_recovers_the_complete_final_response(self):
        store = MemoryStore()
        tid = store.create_task({'Title': 'Eight questions', 'Kind': 'coding'}, 'owner')
        store.add_comment(tid, 'coder', 'agent', 'CODER REPORT\nSummary: only the first item fit here.')
        final = '\n'.join(f'{n}. Full outcome {n}.' for n in range(1, 9))
        session_artifacts.coding(store, tid, 'Summary: compact.', 'transcript fallback', 'coder',
                                 final_message=final)
        recovered = responder.resolution_of(store, tid)
        self.assertNotIn('only the first item', recovered)
        for n in range(1, 9):
            self.assertIn(f'Full outcome {n}.', recovered)


if __name__ == '__main__':
    unittest.main()
