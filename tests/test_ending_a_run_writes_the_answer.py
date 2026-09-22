"""Ending the run is when the reply gets written - whoever ended it.

An agent that finished by itself drafted the reply (selfclose -> wrap(close=True) -> finish). The
owner pressing "Save and end session" got the report filed and nothing to send, on the one road
where they had just read the work and knew it was done (the owner, 2026-09-22). `close` now decides
only whether the TASK ends with the run; the answer is written either way.
"""
import unittest
from unittest import mock

from taskuary import coder, responder
from taskuary.store import MemoryStore


def _task_with_a_sender(s, body='the importer drops the last row'):
    tid = s.create_task({'Title': 'the importer', 'Kind': 'coding', 'Status': 'in_progress'}, 'router')
    s.add_message({'TaskId': tid, 'ExternalId': f'm{tid}', 'Channel': 'email', 'ConversationId': f'c{tid}',
                   'Subject': 'the importer', 'FromName': 'Dana', 'FromEmail': 'dana@vendor.example',
                   'SentAt': '2026-09-22 09:00:00', 'BodyText': body, 'Status': 'routed'})
    s.add_transcript(tid, f'sid{tid}', 'looked at it, fixed the off-by-one, tests pass', agent='coder', cwd='C:/repo')
    return tid


class EndingTheRunTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.drafted = mock.patch.object(responder, 'write_draft', return_value='Fixed - it was an off-by-one.')
        self.summary = mock.patch.object(coder, 'report_from_transcript',
                                         return_value={'summary': 'fixed the off-by-one', 'done': True})

    def test_save_and_end_session_drafts_the_reply_and_leaves_the_task_open(self):
        tid = _task_with_a_sender(self.s)
        with self.drafted as drafted, self.summary:
            out = coder.wrap(self.s, tid, close=False, actor='owner')
        self.assertTrue(out['drafting'], 'the answer is written when the run ends')
        self.assertTrue(drafted.called)
        self.assertEqual((self.s.get_task(tid) or {})['Status'], 'in_progress', 'the run ended, not the task')
        rv = self.s.pending_review(tid) or {}
        self.assertEqual(rv.get('Kind'), 'draft_reply', 'a reply is waiting for the owner on the task')
        self.assertEqual(drafted.call_args[0][1], tid, 'drafted from THIS task and what the session found')

    def test_ending_it_WITH_the_task_still_closes_it(self):
        tid = _task_with_a_sender(self.s)
        with self.drafted, self.summary:
            out = coder.wrap(self.s, tid, close=True, actor='owner')
        self.assertTrue(out['drafting'])
        self.assertEqual((self.s.get_task(tid) or {})['Status'], 'waiting', 'a reply is owed, so the task waits on it')

    def test_a_run_nobody_is_waiting_on_ends_with_no_draft_and_no_closure(self):
        """A scheduled report's task: nobody sent it, so there is nobody to answer - and ending the
        RUN must not close the task on the owner's behalf either."""
        tid = self.s.create_task({'Title': 'Process Error Check', 'Kind': 'coding', 'Status': 'in_progress'}, 'router')
        self.s.add_message({'TaskId': tid, 'ExternalId': 'r1', 'Channel': 'report', 'Subject': 'Process Error Check',
                            'SentAt': '2026-09-22 09:00:00', 'BodyText': '2 rows', 'Status': 'routed'})
        self.s.add_transcript(tid, 'sidr', 'checked it, nothing to change', agent='coder', cwd='C:/repo')
        with mock.patch.object(responder, 'write_draft', side_effect=AssertionError('nobody to answer')), self.summary:
            out = coder.wrap(self.s, tid, close=False, actor='owner')
        self.assertFalse(out['drafting'])
        self.assertEqual((self.s.get_task(tid) or {})['Status'], 'in_progress')


if __name__ == '__main__':
    unittest.main()
