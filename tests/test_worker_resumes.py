"""A question the owner has spoken since is not still being asked.

A request was closed only by an explicit `answered` event, which the answer ROUTE writes. Answering
in the pane - the ordinary way - writes no such event, so one permission prompt made a session read
"stopped - waiting on you" for the rest of its life. TQ-0500 sat at the top of Work under that
sentence while the coder was mid-search, twenty minutes and four prompts later (the owner,
2026-09-11: "when i input another prompt it does not pick up its coding again").

`working` IS the owner speaking: hooks.py records it on UserPromptSubmit. A request from before the
owner's latest prompt has been overtaken by it.
"""
import unittest
from types import SimpleNamespace

from taskuary import workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.fx = Factory(self.s)
        self.tid = self.fx.task(title='Map consulting team', kind='coding')
        self.sid = 'a0e6326f6352'
        self.sess = SimpleNamespace(task_id=self.tid, sid=self.sid, alive=True)

    def ev(self, kind, text=''):
        ws.record(self.s, self.tid, self.sid, kind, text=text, source='hook')

    def test_a_prompt_submitted_after_the_question_ends_the_wait(self):
        self.ev('working')
        self.ev('approval_needed', 'Claude needs your permission')
        self.assertEqual(ws.status(self.s, self.tid)['state'], 'approval_needed')
        self.assertIs(ws.waiting_of(self.s, self.sess), True)
        self.ev('working')                       # the owner typed the answer into the pane
        self.assertEqual(ws.status(self.s, self.tid)['requests'], [])
        self.assertIsNot(ws.waiting_of(self.s, self.sess), True)
        self.assertIsNone(ws.asking_of(self.s, self.sess))

    def test_the_question_stands_until_the_owner_speaks(self):
        """A turn merely ENDING says nothing about whose ball it is - that rule is not weakened."""
        self.ev('working')
        self.ev('approval_needed', 'Claude needs your permission')
        self.ev('turn_end', 'here is what I found')
        self.assertIs(ws.waiting_of(self.s, self.sess), True)
        self.assertEqual(ws.status(self.s, self.tid)['state'], 'approval_needed')

    def test_a_question_asked_during_the_current_turn_is_open(self):
        """The permission notification arrives AFTER its own turn's prompt, so it must survive it."""
        self.ev('working')
        self.ev('input_needed', 'How do you want to push?')
        self.assertEqual([r['text'] for r in ws.status(self.s, self.tid)['requests']], ['How do you want to push?'])

    def test_the_whole_backlog_clears_on_one_prompt(self):
        """TQ-0500 carried two - an approval from 11:54 and a question from 12:31."""
        self.ev('working')
        self.ev('approval_needed', 'Claude needs your permission')
        self.ev('input_needed', 'The mapping SQL is ready but unapplied. How far do you want to go?')
        self.assertEqual(len(ws.status(self.s, self.tid)['requests']), 2)
        self.ev('working')
        self.assertEqual(ws.status(self.s, self.tid)['requests'], [])

    def test_answering_through_the_route_still_resolves_it(self):
        self.ev('working')
        self.ev('input_needed', 'Which vendor?')
        req = ws.status(self.s, self.tid)['requests'][0]['request_id']
        ws.record(self.s, self.tid, self.sid, 'answered', request_id=req, text='Acme')
        self.assertEqual(ws.status(self.s, self.tid)['requests'], [])

    def test_a_new_question_after_the_prompt_raises_the_hand_again(self):
        self.ev('working')
        self.ev('approval_needed', 'Claude needs your permission')
        self.ev('working')
        self.ev('input_needed', 'Push to main deploys to prod. How do you want to proceed?')
        st = ws.status(self.s, self.tid)
        self.assertEqual(st['state'], 'input_needed')
        self.assertIs(ws.waiting_of(self.s, self.sess), True)
        self.assertEqual(ws.asking_of(self.s, self.sess)['text'],
                         'Push to main deploys to prod. How do you want to proceed?')
