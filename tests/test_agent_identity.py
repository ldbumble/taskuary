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

    def test_the_agent_card_projects_tasks_playbooks_and_report_skills(self):
        store = MemoryStore()
        store.upsert_agent('Atlas', 'coding', 'cli', json.dumps({'cmd': 'codex'}))
        tid = store.create_task({'Title': 'Review all repositories', 'Kind': 'coding',
                                 'Tags': 'playbook:repo-review'}, 'owner')
        store.start_run(tid, 'Atlas', 'find three ideas', 'owner')
        sid = store.save_source({'Channel': 'report', 'Address': 'Overnight repo ideas', 'Active': 1,
                                 'ConfigJson': json.dumps({'type': 'agent', 'title': 'Overnight repo ideas',
                                                          'agent': 'Atlas', 'skill': '/repo-ideas'})}, 'owner')

        work = server._agent_work(store, {'repo-review': {
            'slug': 'repo-review', 'title': 'Repository review', 'uses': ['github'],
        }})['Atlas']

        self.assertEqual(work['tasks'][0]['taskId'], tid)
        self.assertEqual(work['tasks'][0]['playbook'], {
            'slug': 'repo-review', 'title': 'Repository review', 'uses': ['github'], 'missing': False,
        })
        self.assertEqual(work['reports'], [{
            'sourceId': sid, 'title': 'Overnight repo ideas', 'kind': 'report',
            'skills': ['repo-ideas'], 'active': True,
        }])

    def test_plain_prompt_reports_do_not_invent_agent_skills(self):
        store = MemoryStore()
        store.upsert_agent('Scout', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        store.save_source({'Channel': 'report', 'Address': 'Morning research', 'Active': 0,
                           'ConfigJson': json.dumps({'type': 'agent', 'agent': 'Scout',
                                                    'prompt': 'Find three useful ideas'})}, 'owner')

        report = server._agent_work(store, {})['Scout']['reports'][0]
        self.assertEqual(report['skills'], [])
        self.assertFalse(report['active'])

    def test_task_detail_normalizes_a_playbooks_uses_line_for_the_ui(self):
        task = {'Tags': 'playbook:bill'}
        with mock.patch('taskuary.playbooks.for_task', return_value={
                'title': 'Post the bill', 'uses': 'quickbooks (write: bills) · teller (read)' }):
            brief = server._playbook_brief(task)
        self.assertEqual(brief['uses'], ['quickbooks', 'teller'])


if __name__ == '__main__':
    unittest.main()
