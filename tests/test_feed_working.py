"""A coder in a live session is working the task - the feed row must not say "needs you"."""
import unittest
from datetime import datetime, timedelta
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


class DigestBriefTests(unittest.TestCase):
    def test_the_brief_reads_the_words_and_names_the_ask_that_slipped(self):
        s = MemoryStore(); s.set_setting('owner_email', 'uri@ours.com', 't'); s.set_setting('calendar_enabled', '0', 't')
        old = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
        mid = s.add_message({'Channel': 'email', 'Subject': 'RE: Stampli Approvers', 'FromName': 'Sam', 'FromEmail': 'teammate@northwind.example',
                             'BodyText': 'Can you send me the GL expense list?', 'Status': 'filed', 'ConversationId': 'cv1', 'SentAt': old})
        s.add_route(mid, None, 'file', None, 'triage: fyi - informational', [], 'triage')
        s.create_task({'Title': 'fix it', 'Kind': 'coding', 'Status': 'open'}, 't')
        text = digest.gather(s, 3)
        for head in ('THEIR ASKS YOU HAVE NOT ANSWERED', 'MY OPEN LOOPS', 'WHAT PEOPLE SAID', 'OPEN WORK',
                     'FINISHED THIS WINDOW', 'WHAT THE ASSISTANT ALREADY RAISED', 'THE WINDOW IN NUMBERS'):
            self.assertIn(head, text)
        slipped = text.split('THEIR ASKS YOU HAVE NOT ANSWERED', 1)[1].split('MY OPEN LOOPS')[0]
        self.assertIn('Sam', slipped); self.assertIn('GL expense list', slipped); self.assertIn('no task, no draft', slipped)
        self.assertIn('Can you send me the GL expense list?', text.split('WHAT PEOPLE SAID', 1)[1].split('OUT OF OFFICE')[0])
        self.assertIn('1 info (a person told you something)', text)
        self.assertIn('open tasks: 1 coding', text)
        self.assertNotIn('THE WINDOW BY TAG', text)          # the counts collapsed to one line

    def test_the_stock_prompt_that_shipped_before_is_healed_to_the_new_one(self):
        # the sections the owner reads first (2026-09-02: in flight, then what people want) - and the
        # previous stock text, "What slipped" leading, is still recognised so it upgrades
        self.assertIn('People want', digest.PROMPT); self.assertIn('New ideas', digest.PROMPT)
        self.assertTrue(any('What slipped' in p and 'The assistant said' in p for p in digest.OLD_PROMPTS))
        self.assertTrue(any("Today's meetings" in p and 'By the tags' in p for p in digest.OLD_PROMPTS))
        self.assertNotIn(digest.PROMPT, digest.OLD_PROMPTS)


if __name__ == '__main__': unittest.main()
