"""A new task started from the owner's own words is its own thing - not the item on the table (2026-10-01).

Typed while one task was open on the table ("stop sending me the vendor-create mails" over the GL task), the assistant rightly
started a NEW task - and its card, both receipts and the settle named the task on the table. And the new task wore the Advisor's
mark on the rail though the owner had asked for it."""
import unittest
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
            return concierge.propose_for(self.s, self.dock, {'verb': 'coder', 'text': d_text}, self.table, text)

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
