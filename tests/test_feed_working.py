"""A coder in a live session is working the task - the feed row must not say "needs you"."""
import unittest
from unittest import mock

from taskuary import terminal, digest
from taskuary.store import MemoryStore


class WorkingTests(unittest.TestCase):
    def _task_with_mail(self, s):
        tid = s.create_task({'Title': 'ldbumble/taskuary#32 People identities', 'Kind': 'coding', 'Status': 'open'}, 't')
        s.add_message({'TaskId': tid, 'Channel': 'github', 'Subject': 'ldbumble/taskuary#32', 'BodyText': '[pull request by ldbumble - association: OWNER]', 'Status': 'routed'})
        return tid

    def test_a_live_session_clears_needs_you_and_names_the_agent(self):
        s = MemoryStore(); tid = self._task_with_mail(s)
        row = s.feed()[0]
        self.assertEqual((row['NeedsYou'], row.get('Working')), (1, None))          # nobody has it: yours
        with mock.patch.object(terminal, 'live_sessions', return_value=[{'taskId': tid, 'agent': 'claude', 'label': 'coder'}]):
            row = s.feed()[0]
        self.assertEqual((row['NeedsYou'], row['Working']), (0, 'claude'))

    def test_a_pending_review_still_needs_you_even_with_an_agent_on_it(self):
        s = MemoryStore(); tid = self._task_with_mail(s)
        mid = s.feed()[0]['MessageId']
        s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'r'})
        with mock.patch.object(terminal, 'live_sessions', return_value=[{'taskId': tid, 'agent': 'claude'}]):
            row = s.feed()[0]
        self.assertEqual((row['NeedsYou'], row['Working']), (1, 'claude'))


class DigestTagTests(unittest.TestCase):
    def test_the_brief_opens_with_the_window_by_tag_and_what_people_said(self):
        s = MemoryStore(); s.set_setting('owner_email', 'uri@ours.com', 't')
        mid = s.add_message({'Channel': 'email', 'Subject': 'RE: Stampli Approvers', 'FromName': 'Leah', 'FromEmail': 'leah@ours.com',
                             'BodyText': 'It can be looked up by GL expense.', 'Status': 'filed'})
        s.add_route(mid, None, 'file', None, 'triage: fyi - informational', [], 'triage')
        s.add_message({'Channel': 'email', 'Subject': 'CI failed', 'FromEmail': 'notifications@github.com', 'BodyText': 'Run failed', 'Status': 'ignored'})
        s.create_task({'Title': 'fix it', 'Kind': 'coding', 'Status': 'open'}, 't')
        text = digest.gather(s, 3)
        self.assertIn('THE WINDOW BY TAG', text); self.assertIn('info (a person told you something): 1', text); self.assertIn('ignored: 1', text)
        self.assertIn('OPEN TASKS BY KIND:\n  coding: 1', text)
        self.assertIn('INFO FROM PEOPLE', text); self.assertIn('Leah: RE: Stampli Approvers - It can be looked up by GL expense.', text)

    def test_the_stock_prompt_that_shipped_before_is_healed_to_the_new_one(self):
        self.assertIn('By the tags', digest.PROMPT); self.assertIn('Info from people', digest.PROMPT)
        self.assertTrue(any('Every TQ-ref keeps the link' in p and 'By the tags' not in p for p in digest.OLD_PROMPTS))
        self.assertNotIn(digest.PROMPT, digest.OLD_PROMPTS)


if __name__ == '__main__': unittest.main()
