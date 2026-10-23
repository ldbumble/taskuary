"""The general agent reads what the coding agent's context file holds (context.for_prompt): the sender's history with the owner,
past work and how this task's last run ended, today's meetings, the open goals - capped, in the user turn, and never on a
stranger's task (the owner picked the richer read, 2026-10-22). Offline: the calendar is mocked."""
import unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import context, general, wrapup
from taskuary.store import MemoryStore

ERIN = 'erin@northwind.example'
def _ago(days=0): return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')


def _mail(s, subject, body, days, tid):
    return s.add_message({'TaskId': tid, 'ExternalId': f'x:{subject}:{days}', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                          'Subject': subject, 'FromName': 'Erin Blake', 'FromEmail': ERIN, 'SentAt': _ago(days), 'BodyText': body, 'Status': 'routed'})


TODAY = {'events': [{'start': datetime.now().strftime('%Y-%m-%d') + 'T14:00', 'end': datetime.now().strftime('%Y-%m-%d') + 'T14:30',
                     'subject': 'Vendor renewal review', 'who': ['Gail Moreno']}]}


class GeneralReadsTheHubTests(unittest.TestCase):
    def _store(self, origin='owner'):
        s = MemoryStore(); s.set_setting('coding_auto_enabled', '0', 't'); s.set_setting('owner_email', 'alex@northwind.example', 't')
        old = s.create_task({'Title': 'Renewal quote for Payworth', 'Kind': 'general', 'Status': 'done'}, 't')
        _mail(s, 'Renewal quote for Payworth', 'the original ask', 30, old)
        s.add_comment(old, 'agent', 'agent', f'{wrapup.REPORT}\nPayworth agreed to hold the 2025 price for one more year.')
        goal = s.create_task({'Title': 'Close the vendor review', 'Kind': 'general', 'Status': 'open', 'DoneWhen': 'every renewal signed'}, 't')
        s.set_task_checklist(goal, ['Collect the Payworth quote', 'Sign the Trainly renewal'], 't')
        tid = s.create_task({'Title': 'Draft the Payworth renewal note', 'Kind': 'general', 'Status': 'open'}, 't')
        _mail(s, 'Payworth renewal', 'Can you draft the note for the renewal?', 0, tid)
        s.add_comment(tid, 'agent', 'agent', f'{wrapup.REPORT}\nDrafted half; waiting on the signed quote.')
        s.cx.execute('UPDATE task SET OriginBase=? WHERE TaskId=?', (origin, tid)); s.cx.commit()
        return s, tid

    def test_the_general_prompt_carries_past_work_the_last_run_meetings_and_goals(self):
        s, tid = self._store()
        with mock.patch('taskuary.calendar.today', return_value=TODAY):
            system, user = general._prompt(s, tid)
        self.assertIn('WHAT THE HUB KNOWS ABOUT THIS TASK', user)
        for known in ('hold the 2025 price', 'waiting on the signed quote', 'Vendor renewal review', 'Close the vendor review',
                      'Collect the Payworth quote'): self.assertIn(known, user, known)
        self.assertNotIn('hold the 2025 price', system)       # other people's mail rides in the user turn, never the system prompt
        self.assertNotIn('## About the owner', user)          # the system prompt already opens on SOUL.md

    def test_a_strangers_task_reads_none_of_it(self):
        s, tid = self._store('stranger')
        with mock.patch('taskuary.calendar.today', return_value=TODAY):
            user = general._prompt(s, tid)[1]
        for private in ('WHAT THE HUB KNOWS', 'Vendor renewal review', 'Close the vendor review'): self.assertNotIn(private, user, private)

    def test_capped_like_the_file(self):
        s, tid = self._store()
        with mock.patch('taskuary.calendar.today', return_value=TODAY):
            whole, cut = context.for_prompt(s, tid), context.for_prompt(s, tid, chars=200)
        self.assertGreater(len(whole), 200); self.assertLessEqual(len(cut), 200 + len('\n[...cut to fit]'))
        self.assertTrue(cut.endswith('[...cut to fit]'))

    def test_the_coding_file_gains_the_meetings_and_goals_too(self):
        s, tid = self._store()
        with mock.patch('taskuary.calendar.today', return_value=TODAY): text = context.build(s, tid)
        self.assertIn("## Today's meetings", text); self.assertIn('## Open goals', text)
        self.assertNotIn('## How the last run on this task ended', text)   # the coding seed carries it as PREVIOUS SESSION RESULT


if __name__ == '__main__':
    unittest.main()
