"""The cheap ending has to actually be cheap.

Reported (TQ-0252): a CyberHoot security-training reminder went to the coding agent, the agent
correctly found nothing to do - and the wrap-up mailed hoots@cyberhoot.com "Done. This was just
a CyberHoot training reminder, not an engineering or repo issue, so I closed it as FYI with no
further action." A reply nobody asked for, written about our own filing rather than to the
sender. Every task going to the agent is the owner's rule; a no-op ending answering a robot in
our own internal vocabulary was never part of it.

The line drawn here: silence needs BOTH halves - the session did nothing AND the sender is not
a person waiting on an answer. A person who asks and gets "I looked, nothing was wrong" is owed
that sentence, and swallowing it would be the worse bug.
"""
import unittest
from unittest import mock

from taskuary import coder
from taskuary.store import MemoryStore

NOTICE = ('Your CyberHoot assignment "Common Scams and How to Avoid Them" is outstanding, due '
          '2026-09-06. Please complete it.\nYou are receiving this email because you are enrolled.')
NOOP = {'determination': 'a training reminder, not repo work', 'actions': 'nothing changed',
        'summary': 'nothing to do here', 'outcome': 'nothing_to_do'}


def task_with(s, from_email, body=NOTICE, channel='email'):
    tid = s.create_task({'Title': 'Outstanding Assignment', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'x1', 'Channel': channel, 'Subject': 'Outstanding Assignment',
                         'FromEmail': from_email, 'SentAt': '2026-08-30 09:00:00', 'BodyText': body, 'Status': 'routed'})
    return tid, mid


class NoOpEndingTests(unittest.TestCase):
    def test_a_robots_notice_with_nothing_done_drafts_no_reply(self):
        s = MemoryStore(); tid, _ = task_with(s, 'hoots@cyberhoot.com')
        with mock.patch('taskuary.responder.write_draft') as wd:
            out = coder.finish(s, tid, NOOP, None, 'coder')
        wd.assert_not_called()
        self.assertEqual((out['drafting'], out['message_id']), (False, None))
        self.assertEqual((s.list_reviews('pending'), s.get_task(tid)['Status']), ([], 'done'))
        # and the timeline says WHY there is no draft, rather than the task just going quiet
        self.assertTrue(any('no reply drafted' in (c.get('Body') or '') for c in s.list_comments(tid)))

    def test_a_person_who_asked_still_gets_the_answer(self):
        """The half that keeps this honest: "nothing was wrong" IS the reply they are waiting for."""
        s = MemoryStore(); tid, mid = task_with(s, 'ap@client.com', 'Is the importer broken again?')
        with mock.patch('taskuary.responder.write_draft', return_value='I looked - it is running fine.'):
            out = coder.finish(s, tid, NOOP, None, 'coder')
        self.assertEqual((out['drafting'], out['message_id']), (True, mid))
        self.assertEqual(s.get_task(tid)['Status'], 'waiting')

    def test_finished_state_is_visible_before_slow_reply_drafting(self):
        """Closing the terminal is immediate; drafting may not be. The task must stop claiming
        an agent is in progress before the potentially slow AI call begins."""
        s = MemoryStore(); tid, _ = task_with(s, 'ap@client.com', 'Is the importer fixed?')
        seen = []
        def drafting(*_args, **_kwargs):
            seen.append((s.get_task(tid)['Status'], len(s.list_reviews('pending'))))
            return 'It is fixed.'
        with mock.patch('taskuary.responder.write_draft', side_effect=drafting):
            coder.finish(s, tid, {'summary': 'fixed', 'outcome': 'did_work'}, None, 'coder')
        self.assertEqual(seen, [('waiting', 1)])

    def test_work_actually_done_always_drafts_however_it_came_in(self):
        s = MemoryStore(); tid, mid = task_with(s, 'noreply@vendor.com')
        rep = {'summary': 'fixed the feed', 'outcome': 'did_work'}
        with mock.patch('taskuary.responder.write_draft', return_value='Fixed.'):
            self.assertEqual(coder.finish(s, tid, rep, None, 'coder')['message_id'], mid)

    def test_a_report_with_no_outcome_field_drafts_as_before(self):
        """Absent means did_work. An older report, a degraded one, or a model that ignored the
        field must never cost somebody their answer."""
        s = MemoryStore(); tid, mid = task_with(s, 'noreply@vendor.com')
        with mock.patch('taskuary.responder.write_draft', return_value='Fixed.'):
            self.assertEqual(coder.finish(s, tid, {'summary': 'fixed'}, None, 'coder')['message_id'], mid)

    def test_a_held_draft_means_somebody_is_waiting(self):
        """Triage drafted a reply and it was held when the session started - that is standing
        proof there is an answer owed, and a no-op report does not cancel it."""
        s = MemoryStore(); tid, mid = task_with(s, 'hoots@cyberhoot.com')
        s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                            'Reason': 'needs a reply'})
        s.hold_reviews(tid, 'the agent is looking at it')
        with mock.patch('taskuary.responder.write_draft', return_value='hi'):
            self.assertTrue(coder.finish(s, tid, NOOP, None, 'coder')['drafting'])


class ReportOutcomeTests(unittest.TestCase):
    def test_the_flag_is_read_and_never_shown(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Outstanding Assignment', 'Kind': 'coding'}, 'o')
        j = ('{"determination": "a training reminder", "actions": "nothing", '
             '"summary": "nothing to do here", "outcome": "nothing_to_do"}')
        with mock.patch('taskuary.llm.build_llm', return_value=lambda sy, u, **kw: j):
            rep = coder.report_from_transcript(s, tid, 'Read the mail. Nothing to do here.')
        self.assertEqual(rep['outcome'], 'nothing_to_do')
        self.assertNotIn('outcome', coder.resolution_text(rep).lower())   # a flag, not prose

    def test_anything_but_the_flag_reads_as_work_done(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 't', 'Kind': 'coding'}, 'o')
        for val in ('did_work', 'unsure', ''):
            with mock.patch('taskuary.llm.build_llm',
                            return_value=lambda sy, u, **kw: '{"summary": "s", "outcome": "%s"}' % val):
                self.assertNotIn('outcome', coder.report_from_transcript(s, tid, 'did it'))


if __name__ == '__main__':
    unittest.main()
