"""A run put away while it was still asking the owner something did not finish - and the reply drafted at its end says so.

The vendor wrote "the outage is fixed, please retry and tell us". The agent could not retry from where it ran, wrote the owner a
note ("only the allowed host can connect; run this check there - nothing goes to them until you've approved it") and ASKED what
the check showed. The owner put the session away without answering, and finish() handed the responder that note as the finished
result under "the work this thread asked for is FINISHED" - so the vendor's draft relayed the agent's notes, in the owner's voice,
as the answer (TQ-1207 shape, the owner, 2026-10-26: "you are responding I did not review. that's not helpful").
"""
import unittest
from unittest import mock

from taskuary import wrapup
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


class OpenQuestionAtWrap(unittest.TestCase):
    def setUp(self): self._prev, wrapup.REFRESH = wrapup.REFRESH, None
    def tearDown(self): wrapup.REFRESH = self._prev

    def finish(self, s, tid):
        with mock.patch('taskuary.responder.write_draft', return_value='draft') as wd:
            out = wrapup.finish(s, tid, {'summary': NOTE}, None, 'assistant', wrapup.reply_source('', NOTE), keep_open=True)
        return out, wd.call_args[0][3], s.list_reviews('pending')[0]

    def test_a_run_ended_on_an_unanswered_question_tells_the_drafter_the_work_did_not_finish(self):
        s = MemoryStore(); tid, mid = vendor_task(s)
        ev(s, tid, 'working'); ev(s, tid, 'turn_end', NOTE); ev(s, tid, 'input_needed', ASK, rid='q1')
        out, src, rv = self.finish(s, tid)
        self.assertTrue(out['drafting'])
        self.assertIn('THE WORK DID NOT FINISH', src); self.assertIn(ASK, src)
        self.assertLess(src.index(NOTE[:40]), src.index('THE WORK DID NOT FINISH'))          # the note is still there, read as a note
        self.assertNotIn('finished the work', rv['Reason']); self.assertIn('question to you', rv['Reason'])

    def test_a_question_the_owner_answered_since_is_not_still_open(self):
        s = MemoryStore(); tid, mid = vendor_task(s)
        ev(s, tid, 'input_needed', ASK, rid='q1'); ev(s, tid, 'working', 'It passed - the files came through.')
        ev(s, tid, 'turn_end', 'Confirmed working.')
        out, src, rv = self.finish(s, tid)
        self.assertNotIn('THE WORK DID NOT FINISH', src)
        self.assertEqual(rv['Reason'], 'the agent finished the work - reply awaiting approval')

    def test_a_question_only_the_turn_judge_read_into_the_screen_does_not_count(self):
        """selfclose's own rule: the model's read of a turn is not the agent asking - its own word outranks it."""
        s = MemoryStore(); tid, mid = vendor_task(s)
        ev(s, tid, 'turn_end', NOTE); ev(s, tid, 'input_needed', ASK, source='judge', rid='q1')
        self.assertEqual(wrapup.unanswered(s, tid), [])
        _, src, _ = self.finish(s, tid)
        self.assertNotIn('THE WORK DID NOT FINISH', src)

    def test_an_approval_it_was_waiting_on_is_unfinished_work_too(self):
        s = MemoryStore(); tid, mid = vendor_task(s)
        ev(s, tid, 'approval_needed', 'Allow it to connect to the file host?', source='hook', rid='p1')
        self.assertEqual([r['kind'] for r in wrapup.unanswered(s, tid)], ['approval_needed'])


if __name__ == '__main__':
    unittest.main()
