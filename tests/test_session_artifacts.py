"""Readable session results remain available beside compact Agent work summaries."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import responder, server, session_artifacts
from taskuary.store import MemoryStore


class SessionArtifactTests(unittest.TestCase):
    def test_coding_artifact_keeps_result_and_final_response_without_terminal_transcript(self):
        store = MemoryStore()
        tid = store.create_task({'Title': 'Research Azure deployments', 'Kind': 'coding'}, 'owner')
        artifact = session_artifacts.coding(
            store, tid, 'Summary: deployments were unavailable.',
            'Investigated every resource.\nThe full evidence and follow-up details are here.', 'coding',
            final_message='1. Checked production.\n2. Checked staging.\n3. Documented both results.')
        saved = session_artifacts.confined(artifact['Path']).read_text(encoding='utf-8')
        self.assertIn('deployments were unavailable', saved)
        self.assertNotIn('full evidence and follow-up details', saved)
        self.assertIn('1. Checked production.', saved)
        self.assertIn('3. Documented both results.', saved)
        self.assertEqual(store.list_task_artifacts(tid)[0]['Kind'], 'coding_session')

    def test_task_detail_returns_safe_agent_artifact_link(self):
        store = MemoryStore()
        tid = store.create_task({'Title': 'Market research agent', 'Kind': 'coding'}, 'owner')
        session_artifacts.coding(store, tid, 'Summary: research complete.', 'raw terminal repaint', 'coding',
                                 final_message='Full agent findings.')
        with mock.patch.object(server, 'store', store):
            client = TestClient(server.app)
            detail = client.get(f'/api/tasks/{tid}').json()
            opened = client.get(detail['artifacts'][0]['url'])
        self.assertEqual(opened.status_code, 200)
        self.assertIn('Full agent findings', opened.text)
        self.assertNotIn('raw terminal repaint', opened.text)
        self.assertEqual(detail['artifacts'][0]['kind'], 'coding_session')
        self.assertNotIn('Path', detail['artifacts'][0])
        self.assertTrue(detail['artifacts'][0]['url'].startswith('/api/task-artifacts/'))

    def test_redraft_recovers_the_complete_final_response(self):
        store = MemoryStore()
        tid = store.create_task({'Title': 'Eight questions', 'Kind': 'coding'}, 'owner')
        store.add_comment(tid, 'coding', 'agent', 'AGENT REPORT\nSummary: only the first item fit here.')
        final = '\n'.join(f'{n}. Full outcome {n}.' for n in range(1, 9))
        session_artifacts.coding(store, tid, 'Summary: compact.', 'transcript fallback', 'coding',
                                 final_message=final)
        recovered = responder.resolution_of(store, tid)
        for n in range(1, 9):
            self.assertIn(f'Full outcome {n}.', recovered)
        # the full answer leads; the compact report rides after it, never instead of it
        self.assertLess(recovered.index('Full outcome 8.'), recovered.index('only the first item'))

    def test_a_final_line_that_only_points_back_still_gives_the_drafter_what_was_decided(self):
        """The agent's last line was "The reply above is ready for you to review" and its `--done` was refused; the draft came
        out generic. The report and the done note always ride with the final response (2026-10-13)."""
        from taskuary.selfclose import DONE_SAID
        store = MemoryStore()
        tid = store.create_task({'Title': 'Vendor sample', 'Kind': 'coding'}, 'owner')
        store.add_comment(tid, 'coding', 'agent', f"{DONE_SAID}The vendor's sample is an empty backup, not the export we import.")
        store.add_comment(tid, 'coding', 'agent', 'AGENT REPORT\nDetermination: the sample was rejected; the reply asks for the monthly export.')
        session_artifacts.coding(store, tid, 'Summary: compact.', 'transcript', 'coding',
                                 final_message='The reply above is ready for you to review and send.')
        got = responder.resolution_of(store, tid)
        self.assertIn('the sample was rejected', got)
        self.assertIn('an empty backup, not the export', got)


if __name__ == '__main__':
    unittest.main()
