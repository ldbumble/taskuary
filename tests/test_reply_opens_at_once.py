"""A reply is the task's agent's (the owner, 2026-11-27: "side model should never work in agent canvas"). Reply, Redraft, Draft with AI,
the Assistant's "reply to X" and the phone's Redraft were a one-shot writer drafting in the agent's place. Each press is now his line to the
task's agent (general.to_agent) - his words, else the press's own label - the task made from the message where it has none. Nothing here
drafts: the writer is never called."""
import unittest
from contextlib import ExitStack
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import buttons, general, outbox, responder, server
from taskuary.store import MemoryStore

WRITERS = (('taskuary.responder.draft_reply', 'the reply writer'), ('taskuary.responder.draft_for_message', 'the message writer'),
           ('taskuary.outbox.draft_message', 'the outbox writer'))


def no_writer():
    "Every side-model writer patched to fail the test the moment it is called."
    st = ExitStack()
    for path, who in WRITERS: st.enter_context(mock.patch(path, side_effect=AssertionError(f'{who} drafted in the agent\'s place')))
    return st


class ReplyAsksTheAgentTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)
        self.s.set_setting('owner_email', 'alex@northwind.example', 'owner')
        self.tid = self.s.create_task({'Title': 'Rota for Tuesday', 'Kind': 'task', 'Status': 'open'}, 'owner')
        self.mid = self.s.add_message({'TaskId': self.tid, 'ExternalId': 'rota-1', 'Channel': 'email', 'Subject': 'Rota',
                                       'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example',
                                       'BodyText': 'Can you cover Tuesday?', 'Status': 'routed'})
        self.told = []
        p = mock.patch.object(general, 'to_agent', side_effect=lambda st, tid, said, *a, **k: self.told.append((tid, said, k.get('frm'))) or 'started')
        p.start(); self.addCleanup(p.stop)

    def press(self, mid=None, **body):
        with no_writer(): return self.c.post(f'/api/messages/{mid or self.mid}/reply', json=body)

    def test_reply_is_his_line_to_the_tasks_agent(self):
        r = self.press(verb='reply')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.told, [(self.tid, buttons.label('reply'), 'owner')])
        self.assertTrue(r.json()['asked'])
        self.assertIsNone(self.s.pending_review(self.tid), 'no review is made in his name')

    def test_redraft_with_words_is_those_words_and_without_them_its_label(self):
        self.press(verb='redraft', instruction='shorter, and say Thursday works')
        self.press(verb='redraft')
        self.assertEqual([s for _, s, _ in self.told], ['shorter, and say Thursday works', buttons.label('redraft')])

    def test_a_message_with_no_task_gets_one_and_its_agent_is_asked(self):
        mid = self.s.add_message({'ExternalId': 'loose-1', 'Channel': 'email', 'Subject': 'Lunch', 'FromName': 'Gail Moreno',
                                  'FromEmail': 'gail@northwind.example', 'BodyText': 'Lunch on Friday?', 'Status': 'filed'})
        r = self.press(mid, instruction='yes, Friday')
        tid = r.json()['taskId']
        self.assertEqual(self.s.get_message(mid)['TaskId'], tid)
        self.assertEqual(self.told, [(tid, 'yes, Friday', 'owner')])

    def test_the_old_draft_door_is_gone(self):
        self.assertIn(self.c.post('/api/reviews/1/draft').status_code, (404, 405))
        for gone in ('write_draft', 'to_agent', 'Handed', 'REDRAFT'): self.assertFalse(hasattr(responder, gone), gone)
        for gone in ('redraft_review', 'task_email', 'MODES'): self.assertFalse(hasattr(outbox, gone), gone)

    def test_write_it_yourself_opens_the_box_for_his_words_with_nobody_behind_it(self):
        "No AI connected: the bar's Reply opens a box for his own words - no agent asked, no writer."
        out = self.press(write=True).json()
        self.assertEqual(self.told, [])
        rv = self.s.get_review(out['reviewId'])
        self.assertEqual((rv['Status'], rv.get('DraftText') or ''), ('pending', ''))

    def test_the_phone_and_the_assistant_take_the_same_door(self):
        from taskuary import remote_assistant
        with no_writer(): said = remote_assistant._ask(self.s, {'mid': self.mid}, 'redraft', 'warmer')
        self.assertEqual(self.told, [(self.tid, 'warmer', 'owner')])
        self.assertIn('Asked the agent', said)

    def test_no_card_offers_redraft(self):
        from taskuary import card, concierge
        rid = self.s.add_review({'TaskId': self.tid, 'MessageId': self.mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Yes.'})
        self.assertNotIn('redraft', card.presses(self.s, self.s.get_review(rid)))
        self.assertNotIn('redraft', concierge.CHIPS['review'])


if __name__ == '__main__':
    unittest.main()
