"""Work can leave, not only arrive.

A report has always landed on the Timeline and stopped there. An outbound report is the same run
turning around: it goes to an address the owner chose, on a channel they picked, either after
they have read it or - if they say so once, deliberately - straight away.

The gate is the part that matters. Everything else in this app holds to "nothing sends without
you", and a scheduled job that mails people on its own would be the one place that promise did
not hold. So it defaults to review, and choosing otherwise is an explicit act.
"""
import json
import unittest
from unittest import mock

from taskuary import outbound, reports, verdicts
from taskuary.store import MemoryStore


def _src(s, title='Weekly numbers'):
    sid = s.save_source({'Channel': 'report', 'Address': title, 'Active': 1, 'ConfigJson': '{}'}, 't')
    return next(x for x in s.list_sources() if x['SourceId'] == sid)


def _cfg(gate='review', to='dana@example.org', channel='email'):
    return {'title': 'Weekly numbers', 'deliver': {'channel': channel, 'to': to, 'gate': gate}}


class TheGateTests(unittest.TestCase):
    def test_review_is_the_default_when_nobody_said_otherwise(self):
        """A deliver block with no gate must never mean "send it"."""
        s = MemoryStore()
        cfg = {'title': 'x', 'deliver': {'channel': 'email', 'to': 'a@b.com'}}
        with mock.patch.object(outbound, 'send_out') as send:
            out = reports.deliver_report(s, _src(s), cfg, 'x - 1 row', 'body')
        send.assert_not_called()
        self.assertEqual(out['gate'], 'review')

    def test_a_gated_report_waits_as_a_draft_and_sends_on_approval(self):
        s = MemoryStore()
        out = reports.deliver_report(s, _src(s), _cfg(), 'Weekly numbers - 12 rows', 'the numbers')
        row = s.get_message(out['message_id'])
        self.assertEqual((row['Direction'], row['Status']), ('out', 'draft'))
        rv = next(r for r in s.list_reviews() if r['Status'] == 'pending')
        self.assertEqual(rv['Kind'], 'outbound')
        self.assertIn('dana@example.org', rv['Reason'])       # the queue says where it would go
        with mock.patch.object(outbound, 'send_out',
                               return_value={'channel': 'email', 'to': ['dana@example.org']}) as send:
            res = verdicts.decide(s, s.get_review(rv['ReviewId']), 'approve')
        self.assertEqual(res['status'], 'approved')
        self.assertEqual(send.call_args[0][1:3], ('email', ['dana@example.org']))
        self.assertEqual(s.get_message(out['message_id'])['Status'], 'sent')

    def test_editing_before_approving_sends_the_edit(self):
        """The draft is a draft: what leaves is what the owner signed off."""
        s = MemoryStore()
        reports.deliver_report(s, _src(s), _cfg(), 'h', 'the raw wording')
        rv = next(r for r in s.list_reviews() if r['Status'] == 'pending')
        with mock.patch.object(outbound, 'send_out', return_value={'channel': 'email', 'to': ['x']}) as send:
            verdicts.decide(s, s.get_review(rv['ReviewId']), 'approve', final_text='my wording')
        self.assertEqual(send.call_args[0][4] if len(send.call_args[0]) > 4 else send.call_args[0][-1],
                         'my wording')

    def test_rejecting_sends_nothing(self):
        s = MemoryStore()
        reports.deliver_report(s, _src(s), _cfg(), 'h', 'body')
        rv = next(r for r in s.list_reviews() if r['Status'] == 'pending')
        with mock.patch.object(outbound, 'send_out') as send:
            res = verdicts.decide(s, s.get_review(rv['ReviewId']), 'reject')
        send.assert_not_called()
        self.assertEqual(res['status'], 'rejected')

    def test_auto_sends_immediately_and_queues_nothing(self):
        """Opt-in, and the row says it went out unread."""
        s = MemoryStore()
        with mock.patch.object(outbound, 'send_out', return_value={'channel': 'email', 'to': ['x@y.com']}) as send:
            out = reports.deliver_report(s, _src(s), _cfg(gate='auto', to='x@y.com'), 'h', 'body')
        send.assert_called_once()
        self.assertEqual(out['gate'], 'auto')
        self.assertEqual(s.get_message(out['message_id'])['Status'], 'sent')
        self.assertEqual([r for r in s.list_reviews() if r['Status'] == 'pending'], [])
        reason = s.feed(limit=3)[0]['RouteReason']
        self.assertIn('without review', reason)

    def test_a_failed_send_puts_it_back_in_the_queue_wearing_the_error(self):
        """An approved report that never LEFT is not done - the same rule replies already follow."""
        s = MemoryStore()
        reports.deliver_report(s, _src(s), _cfg(), 'h', 'body')
        rv = next(r for r in s.list_reviews() if r['Status'] == 'pending')
        with mock.patch.object(outbound, 'send_out', side_effect=RuntimeError('mailbox refused it')):
            res = verdicts.decide(s, s.get_review(rv['ReviewId']), 'approve')
        self.assertFalse(res['ok'])
        self.assertIn('refused', res['send_error'])
        self.assertEqual(s.get_review(rv['ReviewId'])['Status'], 'pending')   # still waiting


class WhichWayItWentTests(unittest.TestCase):
    def test_an_outbound_row_is_marked_and_an_inbound_one_is_not(self):
        s = MemoryStore()
        s.add_message({'ExternalId': 'in1', 'Channel': 'email', 'Subject': 'from somebody',
                       'FromEmail': 'a@b.com', 'BodyText': 'x', 'Status': 'filed'})
        reports.deliver_report(s, _src(s), _cfg(), 'Weekly numbers - 12 rows', 'body')
        rows = {r['Subject']: r['Direction'] for r in s.feed(limit=9)}
        self.assertEqual(rows['from somebody'], 'in')          # the default, for everything before this
        self.assertEqual(rows['Weekly numbers - 12 rows'], 'out')


class SendingWhereNobodyWroteFirstTests(unittest.TestCase):
    """send_out is not reply_to_message: there is no arriving row to read a mailbox or chat id
    off, so the destination has to be given - and the channel switches still govern it."""
    def test_a_channel_switched_off_for_replies_is_off_for_reports_too(self):
        s = MemoryStore()
        s.set_setting('reply_channels', 'teams', 't')          # email not among them
        with self.assertRaises(RuntimeError) as e:
            outbound.send_out(s, 'email', ['a@b.com'], 'subject', 'body')
        self.assertIn('Settings', str(e.exception))

    def test_no_recipient_is_refused_rather_than_sent_nowhere(self):
        s = MemoryStore()
        s.set_setting('reply_channels', 'email,teams', 't')
        with self.assertRaises(RuntimeError) as e:
            outbound.send_out(s, 'email', [], 'subject', 'body')
        self.assertIn('recipient', str(e.exception))

    def test_a_tracker_is_refused_by_the_channel_gate_before_it_gets_near_a_sender(self):
        s = MemoryStore()
        s.set_setting('reply_channels', 'email,teams,github,jira', 't')
        with self.assertRaises(RuntimeError) as e:
            outbound.send_out(s, 'jira', ['PROJ-1'], 's', 'b')
        self.assertIn('is off', str(e.exception))       # can_reply never admits a read-only tracker

    def test_a_channel_with_no_sender_behind_it_says_which_ones_can_carry_a_report(self):
        """slack is offered as a reply channel and has no sender in outbound - a pre-existing
        gap, and the message has to name what DOES work rather than fail obscurely."""
        s = MemoryStore()
        s.set_setting('reply_channels', 'email,slack', 't')
        with self.assertRaises(RuntimeError) as e:
            outbound.send_out(s, 'slack', ['C123'], 's', 'b')
        self.assertIn('cannot send on slack', str(e.exception))
        self.assertIn('email', str(e.exception))


if __name__ == '__main__':
    unittest.main()
