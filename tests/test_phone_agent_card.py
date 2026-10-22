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


class RunEndedTests(unittest.TestCase):
    """F5: the agent's line said "is waiting on you" over a run that had failed, and a finished one read the same. The card
    reads how the run ended by its own word (workerstate.ended) - failed with its reason (owner-approved R2), or finished."""
    def setUp(self):
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Reconcile the March ledger', 'Kind': 'general', 'Status': 'open'}, 'owner')
        self.item = {'kind': 'agent', 'tid': self.tid, 'ref': f'TQ-{self.tid:04d}', 'title': 'Reconcile the March ledger', 'lane': 'blocked',
                     'agent': 'assistant', 'who': 'Gail Moreno', 'channel': 'email'}

    def event(self, kind, text):
        self.s._exec("INSERT INTO worker_event (TaskId, Sid, Kind, Text, Source, CreatedAt) VALUES (?, 's1', ?, ?, 'api', '2026-10-21 09:00:00')",
                     (self.tid, kind, text))

    def agent_line(self):
        story = ra.story_block(self.s, self.item)
        return next(l for l in story.splitlines() if l.startswith(ra.DOT_AGENT))

    def test_a_failed_run_says_why_and_never_that_it_waits_on_you(self):
        self.event('failed', 'no AI is connected to run on')
        line = self.agent_line()
        self.assertIn('· failed - ', line)
        self.assertNotIn('waiting on you', ra.story_block(self.s, self.item))

    def test_a_finished_run_says_finished(self):
        self.event('finished', 'The ledger balances.')
        self.assertTrue(self.agent_line().endswith('· finished'), self.agent_line())

    def test_a_run_that_is_parked_still_says_it_waits_on_you(self):
        self.assertTrue(self.agent_line().endswith('· is waiting on you'), self.agent_line())

    def test_a_failed_run_with_no_row_left_comes_back_to_the_chat(self):
        import json
        from taskuary import funnel, messengers
        self.s.set_setting(ra.PROMISES_KEY, json.dumps([{'tid': self.tid, 'channel': 'whatsapp', 'chat': 'c1', 'at': __import__('time').time(),
                                                          'lane': 'working', 'armed': True}]), 't')
        self.event('failed', 'no AI is connected to run on')
        with mock.patch.object(funnel, 'pile', return_value={'items': [], 'alerts': []}), mock.patch.object(messengers, 'wa_send') as sent:
            self.assertEqual(ra.keep_promises(self.s, force=True), 1)
        self.assertIn(f'TQ-{self.tid:04d} is back: the agent failed - ', sent.call_args.args[2])


if __name__ == '__main__':
    unittest.main()
