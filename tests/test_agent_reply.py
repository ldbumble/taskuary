"""The agent that did the work can write the reply itself, and that reply is the one kept.

An agent finished, asked "should I draft the reply to Dana?", the owner said yes, and it wrote a good
one on its own screen - where the task's reply never saw it. The end of the run then had a second
model redraft the answer from the transcript (the owner, 2026-09-23: "sometimes the agent that did
the work is better for response than another ai generating it based off of transcript"). Now the
agent hands it over - `taskuary --reply` from a shell, a [[TASKUARY-REPLY]] block from the general
chat - it becomes the task's pending reply as written, and finishing keeps it.
"""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import coder, selfclose, server
from taskuary.store import MemoryStore

REP = {'summary': 'fixed the export', 'outcome': 'did_work', 'determination': '', 'actions': ''}
OWN = 'Hi Dana - the August export was dropping rows over 10k; fixed and re-run, the file is in the share now.'


def task_with(s, inbound=True):
    tid = s.create_task({'Title': 'August export', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'x-1', 'ConversationId': 'AAQk-x', 'Channel': 'email',
                         'SourceName': 'alex@northwind.example', 'Subject': 'August export', 'FromName': 'Dana',
                         'FromEmail': 'dana@vendor.example', 'SentAt': '2026-09-06 09:00:00',
                         'BodyText': 'Could you fix the August export?', 'Status': 'routed' if inbound else 'context'})
    return tid, mid


class NoHook(unittest.TestCase):
    def setUp(self): self._prev, coder.REFRESH = coder.REFRESH, None
    def tearDown(self): coder.REFRESH = self._prev


class AgentReplyTests(NoHook):
    def test_the_agents_reply_is_the_tasks_pending_reply(self):
        s = MemoryStore(); tid, mid = task_with(s)
        out = coder.agent_reply(s, tid, OWN, 'coder')
        rv = s.get_review(out['review_id'])
        self.assertEqual((rv['Status'], rv['DraftText'], rv['DraftBy'], rv['MessageId']), ('pending', OWN, 'agent:coder', mid))

    def test_finishing_keeps_it_and_no_second_model_redrafts(self):
        s = MemoryStore(); tid, _ = task_with(s)
        coder.agent_reply(s, tid, OWN, 'coder')
        with mock.patch('taskuary.responder.write_draft') as redraft:
            out = coder.finish(s, tid, REP, None, 'coder')
        redraft.assert_not_called()
        self.assertTrue(out['drafting'])
        rvs = s.list_reviews('pending')
        self.assertEqual(len(rvs), 1); self.assertEqual(rvs[0]['DraftText'], OWN)
        self.assertIn("coder's own reply", rvs[0]['Reason'])

    def test_without_one_the_responder_drafts_as_before(self):
        s = MemoryStore(); tid, _ = task_with(s)
        with mock.patch('taskuary.responder.write_draft', return_value='Fixed.') as redraft:
            coder.finish(s, tid, REP, None, 'coder')
        redraft.assert_called_once()

    def test_a_triage_draft_held_for_the_session_is_the_one_it_fills(self):
        s = MemoryStore(); tid, mid = task_with(s)
        held = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'held', 'Reason': 'held while the agent works'})
        out = coder.agent_reply(s, tid, OWN, 'coder')
        self.assertEqual(out['review_id'], held)
        self.assertEqual(s.get_review(held)['Status'], 'pending')
        self.assertEqual(len([r for r in s.list_reviews('pending') if r['TaskId'] == tid]), 1)

    def test_an_ai_redraft_takes_the_mark_off_so_finishing_redrafts_again(self):
        s = MemoryStore(); tid, _ = task_with(s)
        rid = coder.agent_reply(s, tid, OWN, 'coder')['review_id']
        s.update_review_draft(rid, 'An AI rewrite.', None)                       # "Draft with AI" pressed
        self.assertFalse(coder.agent_drafted(s.get_review(rid)))

    def test_nobody_to_answer_means_nothing_is_saved(self):
        s = MemoryStore(); tid, _ = task_with(s, inbound=False)
        out = coder.agent_reply(s, tid, OWN, 'coder')
        self.assertFalse(out['ok']); self.assertEqual(s.list_reviews('pending'), [])

    def test_the_shell_door(self):
        s = MemoryStore(); tid, _ = task_with(s)
        with mock.patch.object(server, 'store', s):
            r = TestClient(server.app).post('/api/agent/reply', json={'task_id': tid, 'text': OWN, 'agent': 'claude'})
        self.assertTrue(r.json()['ok'])
        self.assertEqual(s.list_reviews('pending')[0]['DraftBy'], 'agent:claude')

    def test_the_seed_tells_every_session_how(self):
        self.assertIn('taskuary --reply', selfclose.SEED_LINE)


class ChatBlockTests(unittest.TestCase):
    def test_the_marked_block_is_the_reply_and_stays_readable(self):
        text, said = selfclose.reply_marker(f'Done - here is what I would send.\n[[TASKUARY-REPLY]]\n{OWN}\n[[/TASKUARY-REPLY]]')
        self.assertEqual(said, OWN)
        self.assertNotIn('TASKUARY', text); self.assertIn(OWN, text)

    def test_no_block_no_reply(self):
        self.assertEqual(selfclose.reply_marker('Should I draft the reply to Dana?'), ('Should I draft the reply to Dana?', None))


if __name__ == '__main__':
    unittest.main()
