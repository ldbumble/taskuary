"""A new task started from the owner's own words is its own thing - not the item on the table (2026-10-01).

Typed while one task was open on the table ("stop sending me the vendor-create mails" over the GL task), the assistant rightly
started a NEW task - and its card, both receipts and the settle named the task on the table. And the new task wore the Advisor's
mark on the rail though the owner had asked for it."""
import json, unittest
from unittest import mock

from taskuary import concierge, general, processing_all
from taskuary.store import MemoryStore


class NewTaskFromWordsTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.dock = general.dock_task(self.s)[0]['TaskId']
        self.table_tid = self.s.create_task({'Title': 'Build the GL version', 'Kind': 'coding', 'Status': 'open'}, 'owner')
        self.table = {'key': f'task:{self.table_tid}', 'kind': 'task', 'lane': 'asked', 'title': 'Build the GL version',
                      'tid': self.table_tid, 'ref': 'TQ-%04d' % self.table_tid}

    def propose(self, text, d_text=''):
        with mock.patch('taskuary.terminal.known_repo', return_value=None), mock.patch('taskuary.terminal.known_repos', return_value=[]):
            return concierge.propose_for(self.s, self.dock, {'verb': 'coding_agent', 'text': d_text}, self.table, text)

    def test_words_make_a_proposal_that_names_none_of_the_table(self):
        p = self.propose('Stop sending me the vendor-create mails unless there is an error')
        self.assertEqual(p['kind'], 'task.create_from_text')
        self.assertEqual((p['key'], p['ref'], p['tid'], p['settles']), (None, None, None, False))
        self.assertNotIn(self.table['ref'], p['say'])
        self.assertNotIn('Build the GL version', p['summary'])

    def test_a_button_with_no_words_still_hands_on_the_item_itself(self):
        p = self.propose('')
        self.assertEqual((p['key'], p['tid']), (self.table['key'], self.table_tid))
        self.assertIn('Build the GL version', p['params']['text'])


class NewsBoxIsTheOneStartTests(unittest.TestCase):
    """F1, the walks 2026-11-18: New's box went through the Assistant's model, which picked a form - "send me this every Monday" with a CSV
    attached landed on an empty SQL "New report" form, his words and his file gone - and refused a code fix "No coding tool is connected"
    behind Developer mode. His words and files go to the one start (POST /api/start -> concierge.handoff_task); the agent does the kind."""
    def setUp(self):
        from fastapi.testclient import TestClient
        from taskuary import config, server
        self.s = MemoryStore()
        for p in (mock.patch.object(server, 'store', self.s), mock.patch.object(general, 'start_session'),
                  mock.patch('taskuary.concierge.brain', return_value=None)):
            p.start(); self.addCleanup(p.stop)
        self.c, self.up = TestClient(server.app), config.home() / 'attachments' / 'new-box' / 'october-spend.csv'
        self.up.parent.mkdir(parents=True, exist_ok=True); self.up.write_text('vendor,amount' + chr(10) + 'Payworth,1200' + chr(10), encoding='utf-8')

    def start(self, text, ai=True, **kw):
        with mock.patch('taskuary.capabilities.has_ai', return_value=ai):
            return self.c.post('/api/start', json={'text': text, **kw})

    def test_a_weekly_summary_with_a_csv_is_a_task_with_his_words_and_his_file_its_agent_at_work(self):
        ask = 'Send me the vendor spend summary from this every Monday morning'
        r = self.start(ask, images=[str(self.up)])
        self.assertEqual(r.status_code, 200, r.text)
        t = self.s.get_task(r.json()['taskId'])
        self.assertEqual((t['Kind'], general.split_files(t['Summary'])['text'].strip()), ('general', ask))
        from taskuary import outputs
        self.assertTrue((outputs.folder(t['TaskId']) / 'october-spend.csv').exists() or 'october-spend.csv' in t['Summary'])
        self.assertTrue(r.json()['started']); general.start_session.assert_called_once()
        self.assertNotIn('the Assistant chat', ' '.join(str(c.get('Body')) for c in self.s.list_comments(t['TaskId'], internal=True)))

    def test_a_code_fix_starts_its_agent_whatever_developer_mode_says(self):
        r = self.start('Fix the rounding bug in the ledger totals, checkout at C:/work/ledger')
        self.assertEqual(r.status_code, 200, r.text); self.assertTrue(r.json()['started'])

    def test_with_no_ai_nothing_is_made_and_the_line_carries_its_way_past(self):
        r = self.start('Find three caterers near the office', ai=False)
        self.assertEqual(r.status_code, 422); self.assertEqual(self.s.list_tasks(None), [])
        self.assertIn('No AI is connected', r.json()['detail']); self.assertEqual(r.json()['fix']['label'], 'Connect an AI')

    def test_the_same_work_open_already_hears_it_there(self):
        there = self.s.create_task({'Title': 'Find caterers for the offsite', 'Kind': 'general', 'Status': 'open'}, 'owner')
        llm = lambda system, user, **k: json.dumps({'same_as': there})
        with mock.patch('taskuary.concierge.brain', return_value=llm), mock.patch.object(general, 'take_line') as told:
            r = self.start('Find three caterers near the office for the offsite')
        self.assertEqual((r.json()['taskId'], r.json()['joined']), (there, True)); self.assertEqual(len(self.s.list_tasks(None)), 1)
        self.assertEqual(told.call_args.args[1:3], (there, 'Find three caterers near the office for the offsite'))


class AgentsNewTaskIsTheSameRoadTests(unittest.TestCase):
    """The owner's live app, 2026-11-18: an agent on one task started "the bed board" as a new task while a chat's task for the same work was
    open - two tasks, one job. The new_task tool asks the model first, as every start does (samework): the same work hears it there."""
    def test_the_same_work_open_already_is_told_and_nothing_is_made(self):
        from taskuary import server
        s = MemoryStore()
        there = s.create_task({'Title': 'Add a daily rate to the bed boards', 'Kind': 'coding', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        here = s.create_task({'Title': 'Weekly census review', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        llm = lambda system, user, **k: json.dumps({'same_as': there})
        body = server.AgentNewTaskBody(task_id=here, title='Bed board daily rate', ask='Add the daily rate column to the bed board', kind='coding')
        with mock.patch.object(server, 'store', s), mock.patch.object(server, '_own_task_only'), mock.patch('taskuary.concierge.brain', return_value=llm),              mock.patch.object(general, 'take_line') as told, mock.patch.object(server, '_start_new_task') as started:
            out = server.agent_new_task(body, None)
        self.assertEqual((out['task'], out['already']), ('TQ-%04d' % there, True)); self.assertEqual(len(s.list_tasks(None)), 2)
        started.assert_not_called(); self.assertEqual(told.call_args.args[1], there)


class AdvisorMarkTests(unittest.TestCase):
    def test_only_an_advisor_idea_wears_the_advisor_mark(self):
        idea = {'Source': 'assistant', 'SourceRef': 'assistant:idea:42'}
        self.assertTrue(processing_all.advisor_task(idea))
        for ref in ('assistant:handoff', 'assistant:agent', 'assistant:setup', 'assistant:playbook'):
            self.assertFalse(processing_all.advisor_task({'Source': 'assistant', 'SourceRef': ref}), ref)
        self.assertEqual(processing_all.task_mark([idea]), 'assistant')
        self.assertIsNone(processing_all.task_mark([{'Source': 'assistant', 'SourceRef': 'assistant:handoff'}]))
        self.assertEqual(processing_all.task_mark([{'Source': 'email'}]), 'email')


if __name__ == '__main__':
    unittest.main()
