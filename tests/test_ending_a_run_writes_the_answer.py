"""Ending the run is when the reply is raised - whoever ended it - and it is the agent's to write.

An agent that finished by itself drafted the reply (selfclose -> wrap(close=True) -> finish). The
owner pressing "Stop and save" got the report filed and nothing to send, on the one road
where they had just read the work and knew it was done (the owner, 2026-09-22). `close` now decides
only whether the TASK ends with the run; the reply is raised either way. Since 2026-11-10 nobody but the agent writes it: one it did not
write waits as the reply owed, and an agent that ended its own run is asked for it once.
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
        self.drafted = mock.patch.object(responder, 'write_draft', side_effect=AssertionError('a second voice drafted the reply'))
        self.summary = mock.patch.object(wrapup, 'report_from_transcript',
                                          return_value={'summary': 'fixed the off-by-one', 'done': True})
        self.told = mock.patch.object(general, 'tell', return_value='told')

    def test_save_and_end_session_raises_the_reply_owed_and_leaves_the_task_open(self):
        tid = _task_with_a_sender(self.s)
        with self.drafted, self.summary, self.told as told:
            out = wrapup.wrap(self.s, tid, close=False, actor='owner')
        self.assertTrue(out['drafting'], 'the reply is raised when the run ends')
        # the run ended, not the task: open and `session saved`, not in progress with nobody on it (A1/A2, 2026-09-25)
        self.assertEqual((self.s.get_task(tid) or {})['Status'], 'open', 'the run ended, not the task')
        from taskuary import funnel; self.assertTrue(funnel.session_saved(self.s, tid))
        rv = self.s.pending_review(tid) or {}
        # ...as the reply owed, the agent's to write: no words on it, the same shape as one owed at arrival, so its agent's start is lit
        self.assertEqual((rv.get('Kind'), rv.get('DraftText') or ''), ('draft', ''))
        self.assertIn("Dana is owed - it is the agent's to write", rv.get('Reason'))
        from taskuary import advisor; self.assertTrue(advisor.reply_unwritten(self.s, {'tid': tid}))
        told.assert_not_called()                    # ...and the owner's Stop is not undone: the agent they ended is not reopened for it

    def test_ending_it_WITH_the_task_still_closes_it(self):
        tid = _task_with_a_sender(self.s)
        with self.drafted, self.summary, self.told:
            out = wrapup.wrap(self.s, tid, close=True, actor='owner')
        self.assertTrue(out['drafting'])
        self.assertEqual((self.s.get_task(tid) or {})['Status'], 'waiting', 'a reply is owed, so the task waits on it')

    def test_an_agent_that_ends_its_run_without_the_reply_is_asked_for_it_once(self):
        """`taskuary --done` with nobody's reply written: the agent that did the work is told, by the road every Taskuary word to it
        takes (general.tell), that Dana is owed one - and never twice, however often it ends again without it."""
        tid = _task_with_a_sender(self.s)
        ws.record(self.s, tid, f'sid{tid}', 'finished', text='Fixed the off-by-one.', source='cli')
        with self.drafted, self.summary, self.told as told:
            wrapup.wrap(self.s, tid, close=False, actor='coding')
            rid = self.s.pending_review(tid)['ReviewId']
            self.assertEqual(wrapup.ask_for_reply(self.s, tid, rid), '')            # ...asked once: a second ending says nothing again
        told.assert_called_once()
        self.assertEqual(told.call_args[0][:2], (self.s, tid))
        self.assertIn('Dana is owed a reply that nobody has written', told.call_args[0][2])
        self.assertIn('--reply-not-needed', told.call_args[0][2])
        self.assertEqual(self.s.get_review(rid)['Reason'], 'reply owed to Dana - its agent was asked to write it')
        self.assertFalse(str(self.s.get_review(rid).get('DraftText') or ''))

    def test_where_no_agent_can_be_asked_the_reply_waits_owed_and_says_so(self):
        tid = _task_with_a_sender(self.s)
        ws.record(self.s, tid, f'sid{tid}', 'finished', text='Fixed the off-by-one.', source='cli')
        with self.drafted, self.summary, mock.patch.object(general, 'tell', return_value=''):
            wrapup.wrap(self.s, tid, close=False, actor='coding')
        rv = self.s.pending_review(tid)
        self.assertEqual((rv['Status'], rv.get('DraftText') or ''), ('pending', ''))
        self.assertIn('A reply to Dana is owed and no agent could be asked to write it.', [c['Body'] for c in self.s.list_comments(tid)])

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
