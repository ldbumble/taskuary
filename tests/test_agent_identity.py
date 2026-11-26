"""Named workers are durable task owners, not labels that exist only while a pane is open."""
import json, unittest
from unittest import mock

from taskuary import server
from taskuary.store import MemoryStore


class AgentIdentityTests(unittest.TestCase):
    def test_a_headless_worker_owns_the_task_it_runs(self):
        store = MemoryStore()
        tid = store.create_task({'Title': 'Prepare the digest', 'Kind': 'report'}, 'owner')

        store.start_run(tid, 'Scout', 'prepare it', 'router')

        self.assertEqual(store.get_task(tid)['Assignee'], 'agent:Scout')

    def test_a_queued_worker_already_owns_the_task(self):
        store = MemoryStore()
        tid = store.create_task({'Title': 'Reconcile the export', 'Kind': 'coding'}, 'owner')

        store.enqueue_dispatch(tid, None, 'Atlas', 'waiting for a free desk')

        self.assertEqual(store.get_task(tid)['Assignee'], 'agent:Atlas')
        self.assertEqual(store.queued_dispatches()[0]['Agent'], 'Atlas')

    def test_task_detail_normalizes_a_skills_uses_line_for_the_ui(self):
        task = {'Tags': 'skill:bill'}
        with mock.patch('taskuary.skills.for_task', return_value={
                'title': 'Post the bill', 'uses': 'quickbooks (write: bills) · teller (read)' }):
            brief = server._skill_brief(task)
        self.assertEqual(brief['uses'], ['quickbooks', 'teller'])


if __name__ == '__main__':
    unittest.main()
