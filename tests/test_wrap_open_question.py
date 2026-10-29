"""A run put away while it was still asking the owner something did not finish: it drafts no reply, and its result says
what was left open.

The vendor wrote "the outage is fixed, please retry and tell us". The agent could not retry from where it ran, wrote the owner a
note ("only the allowed host can connect; run this check there - nothing goes to them until you've approved it") and ASKED what
the check showed. The owner put the session away without answering, and finish() handed the responder that note as the finished
result - so the vendor's draft relayed the agent's notes, in the owner's voice, as the answer (TQ-1207 shape, the owner,
2026-10-26: "you are responding I did not review. that's not helpful"). Ruled the same day: "if they end it there it should
close and summarize the session with what was left off as question".
"""
import unittest
from unittest import mock

from taskuary import general, wrapup
from taskuary.store import MemoryStore

NOTE = ("I couldn't retry the login from here - only the allowed host can connect. Run the check there. "
        "Nothing goes to them until you've approved it.\n\nWhat did the check show on the allowed host?")
ASK = 'What did the check show on the allowed host?'


def vendor_task(s):
    tid = s.create_task({'Title': 'Retry the file login', 'Kind': 'general', 'Status': 'in_progress'}, 't')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'v-1', 'ConversationId': 'AAQk-v', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                         'Subject': 'RE: File transfer login', 'FromName': 'Payworth Support', 'FromEmail': 'support@vendor.example',
                         'SentAt': '2026-10-26 12:17:00', 'BodyText': 'The interruption is fixed. Please retry the login and let us know.',
                         'Status': 'routed'})
    return tid, mid


def ev(s, tid, kind, text='', source='api', rid=None):
    s.add_worker_event({'TaskId': tid, 'Sid': 'g1', 'Kind': kind, 'RequestId': rid, 'Text': text, 'Source': source})


def reports(s, tid): return [c['Body'] for c in s.list_comments(tid) if wrapup.is_report(c['Body'])]


class OpenQuestionAtWrap(unittest.TestCase):
    def setUp(self): self._prev, wrapup.REFRESH = wrapup.REFRESH, None
    def tearDown(self): wrapup.REFRESH = self._prev

    def finish(self, s, tid):
        with mock.patch('taskuary.responder.write_draft', return_value='draft') as wd:
            out = wrapup.finish(s, tid, {'summary': NOTE}, None, 'assistant', wrapup.reply_source('', NOTE), keep_open=True)
        return out, wd

    def test_a_run_ended_on_an_unanswered_question_drafts_no_reply(self):
        s = MemoryStore(); tid, mid = vendor_task(s)
        ev(s, tid, 'working'); ev(s, tid, 'turn_end', NOTE); ev(s, tid, 'input_needed', ASK, rid='q1')
        out, wd = self.finish(s, tid)
        wd.assert_not_called(); self.assertFalse(out['drafting'])
        self.assertEqual(s.list_reviews('pending'), [])
        self.assertTrue(any('waiting on your answer - no reply drafted' in c['Body'] for c in s.list_comments(tid)))

    def test_finished_work_still_drafts_as_before(self):
        s = MemoryStore(); tid, mid = vendor_task(s)
        ev(s, tid, 'working'); ev(s, tid, 'turn_end', 'Retried from the allowed host - it connects and the files came through.')
        out, wd = self.finish(s, tid)
        wd.assert_called_once(); self.assertTrue(out['drafting'])
        self.assertEqual(s.list_reviews('pending')[0]['Reason'], 'the agent finished the work - reply awaiting approval')

    def test_a_question_the_owner_answered_since_is_not_still_open(self):
        s = MemoryStore(); tid, mid = vendor_task(s)
        ev(s, tid, 'input_needed', ASK, rid='q1'); ev(s, tid, 'working', 'It passed - the files came through.')
        ev(s, tid, 'turn_end', 'Confirmed working.')
        self.assertEqual(wrapup.unanswered(s, tid), [])
        self.assertTrue(self.finish(s, tid)[0]['drafting'])

    def test_a_question_only_the_turn_judge_read_into_the_screen_does_not_count(self):
        """selfclose's own rule: the model's read of a turn is not the agent asking - its own word outranks it."""
        s = MemoryStore(); tid, mid = vendor_task(s)
        ev(s, tid, 'turn_end', NOTE); ev(s, tid, 'input_needed', ASK, source='judge', rid='q1')
        self.assertEqual(wrapup.unanswered(s, tid), [])
        self.assertTrue(self.finish(s, tid)[0]['drafting'])

    def test_an_approval_it_was_waiting_on_is_unfinished_work_too(self):
        s = MemoryStore(); tid, mid = vendor_task(s)
        ev(s, tid, 'approval_needed', 'Allow it to connect to the file host?', source='hook', rid='p1')
        self.assertEqual([r['kind'] for r in wrapup.unanswered(s, tid)], ['approval_needed'])

    def test_stop_and_save_on_a_chat_leads_its_result_with_the_question_once_and_drafts_nothing(self):
        s = MemoryStore(); tid, mid = vendor_task(s)
        s.add_comment(tid, 'owner', general.USER_TYPE, 'Payworth says it is fixed - retry the login.')
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, NOTE)
        ev(s, tid, 'turn_end', NOTE); ev(s, tid, 'input_needed', ASK, rid='q1')
        with mock.patch('taskuary.responder.write_draft') as wd, mock.patch('taskuary.playbooks.draft', return_value=None):
            out = wrapup.wrap(s, tid, close=False, actor='owner')
        wd.assert_not_called(); self.assertFalse(out['drafting'])
        general.report_note(s, tid)                                    # the session's own close, after: the same answer, not a second note
        self.assertEqual(reports(s, tid), [f'AGENT REPORT\nLEFT OPEN - the agent was waiting on your answer: {ASK}\n\n{NOTE}'])

    def test_a_result_filed_plain_before_the_wrap_is_superseded_by_one_that_says_what_was_left_open(self):
        s = MemoryStore(); tid, mid = vendor_task(s)
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, NOTE)
        general.report_note(s, tid)
        general.report_note(s, tid, lead=wrapup.left_open([{'text': ASK}]))
        self.assertEqual(len(reports(s, tid)), 2); self.assertTrue(wrapup.report_body(reports(s, tid)[-1]).startswith('LEFT OPEN'))


    def test_the_question_is_on_the_first_line_and_no_question_is_no_clause(self):
        # the Agent column shows a result's first line: it read "...your answer to:" and nothing (the email walk, 2026-10-29)
        self.assertEqual(wrapup.left_open([{'text': ASK}]).splitlines()[0], f'LEFT OPEN - the agent was waiting on your answer: {ASK}')
        self.assertEqual(wrapup.left_open([{'text': ASK}, {'text': 'Which host?'}]).splitlines()[1], '- Which host?')
        self.assertEqual(wrapup.left_open([{'text': '  '}]), '')


if __name__ == '__main__':
    unittest.main()
