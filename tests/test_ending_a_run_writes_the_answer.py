"""Ending the run is when the reply is raised - whoever ended it - and it is the agent's to write.

An agent that finished by itself drafted the reply (selfclose -> wrap(close=True) -> finish). The
owner pressing "Stop and save" got the report filed and nothing to send, on the one road
where they had just read the work and knew it was done (the owner, 2026-09-22). `close` now decides
only whether the TASK ends with the run. Since 2026-11-10 nobody but the agent writes the reply, and since 2026-11-27 nothing at a run's end
puts up a card for it either: the reply owed is a fact the agent holds, its card its own to raise - and nobody chases it for one.
"""
import unittest
from unittest import mock

from taskuary import general, wrapup, responder, workerstate as ws
from taskuary.store import MemoryStore


def _task_with_a_sender(s, body='the importer drops the last row'):
    tid = s.create_task({'Title': 'the importer', 'Kind': 'coding', 'Status': 'in_progress'}, 'router')
    s.add_message({'TaskId': tid, 'ExternalId': f'm{tid}', 'Channel': 'email', 'ConversationId': f'c{tid}',
                   'Subject': 'the importer', 'FromName': 'Dana', 'FromEmail': 'dana@vendor.example',
                   'SentAt': '2026-09-22 09:00:00', 'BodyText': body, 'Status': 'routed'})
    s.add_transcript(tid, f'sid{tid}', 'looked at it, fixed the off-by-one, tests pass', agent='coding', cwd='C:/repo')
    return tid


class EndingTheRunTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        # nothing at a run's end asks the tool-less writer any more (the owner, 2026-11-10: "no more triage creates draft. agent should be
        # doing it") - a call to it is the bug
        self.drafted = mock.patch.object(responder, 'draft_for_review', side_effect=AssertionError('a second voice drafted the reply'))
        self.summary = mock.patch.object(wrapup, 'report_from_transcript',
                                          return_value={'summary': 'fixed the off-by-one', 'done': True})
        self.told = mock.patch.object(general, 'to_agent', return_value='told')

    def test_save_and_end_session_raises_the_reply_owed_and_leaves_the_task_open(self):
        tid = _task_with_a_sender(self.s)
        with self.drafted, self.summary, self.told as told:
            out = wrapup.wrap(self.s, tid, close=False, actor='owner')
        self.assertTrue(out['drafting'], 'the reply is raised when the run ends')
        # the run ended, not the task: open and `session saved`, not in progress with nobody on it (A1/A2, 2026-09-25)
        self.assertEqual((self.s.get_task(tid) or {})['Status'], 'open', 'the run ended, not the task')
        from taskuary import funnel; self.assertTrue(funnel.session_saved(self.s, tid))
        # ...and no empty card is put up for the reply owed: the agent's to raise (the owner, 2026-11-27)
        self.assertIsNone(self.s.pending_review(tid))
        told.assert_not_called()                    # ...and the owner's Stop is not undone: the agent they ended is not reopened for it

    def test_ending_it_WITH_the_task_still_closes_it(self):
        tid = _task_with_a_sender(self.s)
        with self.drafted, self.summary, self.told:
            out = wrapup.wrap(self.s, tid, close=True, actor='owner')
        self.assertTrue(out['drafting'])
        self.assertEqual((self.s.get_task(tid) or {})['Status'], 'waiting', 'a reply is owed, so the task waits on it')

    def test_an_agent_that_ends_its_run_without_the_reply_is_not_chased_for_it(self):
        """`taskuary --done` with nobody's reply written: no empty card is raised in its place, and no Taskuary line chases the agent for it
        (the owner, 2026-11-27) - the reply owed was a fact in its context from the start."""
        tid = _task_with_a_sender(self.s)
        ws.record(self.s, tid, f'sid{tid}', 'finished', text='Fixed the off-by-one.', source='cli')
        with self.drafted, self.summary, self.told as told:
            wrapup.wrap(self.s, tid, close=False, actor='coding')
        told.assert_not_called()
        self.assertIsNone(self.s.pending_review(tid))

    def test_the_agents_own_reply_stands_and_nobody_is_asked(self):
        tid = _task_with_a_sender(self.s)
        ws.record(self.s, tid, f'sid{tid}', 'finished', text='Fixed the off-by-one.', source='cli')
        self.assertTrue(wrapup.agent_reply(self.s, tid, 'Fixed - it was an off-by-one.', agent='coding')['ok'])
        with self.drafted, self.summary, self.told as told:
            wrapup.wrap(self.s, tid, close=False, actor='coding')
        told.assert_not_called()
        self.assertEqual(self.s.pending_review(tid)['DraftText'], 'Fixed - it was an off-by-one.')

    def test_a_run_nobody_is_waiting_on_ends_with_no_draft_and_no_closure(self):
        """A scheduled report's task: nobody sent it, so there is nobody to answer - and ending the
        RUN must not close the task on the owner's behalf either."""
        tid = self.s.create_task({'Title': 'Process Error Check', 'Kind': 'coding', 'Status': 'in_progress'}, 'router')
        self.s.add_message({'TaskId': tid, 'ExternalId': 'r1', 'Channel': 'report', 'Subject': 'Process Error Check',
                            'SentAt': '2026-09-22 09:00:00', 'BodyText': '2 rows', 'Status': 'routed'})
        self.s.add_transcript(tid, 'sidr', 'checked it, nothing to change', agent='coding', cwd='C:/repo')
        with self.drafted, self.summary, self.told as told:
            out = wrapup.wrap(self.s, tid, close=False, actor='owner')
        self.assertFalse(out['drafting']); told.assert_not_called()
        self.assertEqual((self.s.get_task(tid) or {})['Status'], 'open')          # not closed - and nobody is working it


if __name__ == '__main__':
    unittest.main()
