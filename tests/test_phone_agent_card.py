"""The phone's agent card (2026-10-06): what the agent RETURNED is shown, its question is the agent's line and not the
owner's, a task the owner asked for is never the Advisor's idea, and a receipt that says "open it" can be opened."""
import unittest
from unittest import mock

from taskuary import remote_assistant as ra
from taskuary.store import MemoryStore


class PhoneAgentCardTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Count the event log runs', 'Kind': 'general', 'Source': 'assistant',
                                       'SourceRef': 'assistant:agent', 'Status': 'in_progress'}, 'owner')
        self.s._exec('UPDATE task SET AskedVia=? WHERE TaskId=?', ('whatsapp:chat1', self.tid))
        self.s._exec("INSERT INTO worker_event (TaskId, Sid, Kind, Text, Source, CreatedAt) VALUES (?, 's1', 'turn_end', ?, 'api', '2026-10-06 16:06:35')",
                     (self.tid, '158 events came in today; 107 processed, 51 pending.'))
        self.item = {'kind': 'agent', 'tid': self.tid, 'ref': f'TQ-{self.tid:04d}', 'title': 'Count the event log runs', 'lane': 'blocked',
                     'asking': True, 'tail': ['Where do the run results get reported?'], 'agent': 'analyst', 'who': 'You', 'channel': 'own'}

    def test_the_result_leads_and_the_question_is_the_agents(self):
        story = ra.story_block(self.s, self.item)
        self.assertIn('158 events came in today', story)
        self.assertIn('asks: **Where do the run results get reported?**', story)
        self.assertNotIn('Advisor', story)                                   # the owner asked for it on the phone
        move = ra.move_block(self.s, self.item)
        self.assertNotIn('Where do the run results get reported?', move)       # under You: only what to do about it

    def test_a_done_receipt_that_made_a_task_offers_to_open_it(self):
        with mock.patch('taskuary.concierge.receipt', return_value='Done - Start a regular agent on it. Open it from here.'):
            text = ra.receipt_text(self.s, {'status': 'done', 'outcome': {'taskId': self.tid, 'ref': f'TQ-{self.tid:04d}'}})
        self.assertIn(f'Open TQ-{self.tid:04d}', text)


if __name__ == '__main__':
    unittest.main()
