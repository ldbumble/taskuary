"""Whether a reply is drafted, and whether the UI may promise one, must be the SAME answer.

The reported bug: a GitHub task closed with no draft (replies off on that card) while the
task page still offered "Read the draft in Review" - because the wrap-up endpoint recomputed
'drafting' from reply_target alone and skipped the can-this-channel-reply rule.
"""
import json, unittest
from unittest import mock

from taskuary import coder, outbound
from taskuary.store import MemoryStore


def task_with(s, channel, status='routed'):
    tid = s.create_task({'Title': 't', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
    mid = s.add_message({'TaskId': tid, 'ExternalId': f'x{channel}', 'Channel': channel,
                         'Subject': 's', 'FromEmail': 'a@b.c', 'SentAt': '2026-08-23 10:00:00',
                         'Status': status})
    return tid, mid


class CanReplyTests(unittest.TestCase):
    def test_defaults(self):
        s = MemoryStore()
        for ch in ('email', 'teams', 'slack', 'telegram', 'whatsapp', 'discord'):
            self.assertTrue(outbound.can_reply(s, ch), ch)
        # read-only by design: nothing is written back to a tracker or an alert feed
        for ch in ('jira', 'linear', 'sentry', 'pagerduty', 'report', 'aws', 'azure', ''):
            self.assertFalse(outbound.can_reply(s, ch), ch)

    def test_github_needs_its_own_card_switch(self):
        s = MemoryStore()
        self.assertFalse(outbound.can_reply(s, 'github'))       # off by default
        cid = s.get_connector_by_type('github')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps({'reply_comments': True})}, 't')
        self.assertTrue(outbound.can_reply(s, 'github'))

    def test_the_setting_switches_a_channel_off(self):
        s = MemoryStore()
        s.set_setting('reply_channels', 'email,teams', 't')
        self.assertTrue(outbound.can_reply(s, 'email'))
        self.assertFalse(outbound.can_reply(s, 'slack'))
        self.assertFalse(outbound.can_reply(s, 'discord'))

    def test_case_and_blank_are_handled(self):
        s = MemoryStore()
        self.assertTrue(outbound.can_reply(s, 'EMAIL'))
        self.assertFalse(outbound.can_reply(s, None))


class FinishTests(unittest.TestCase):
    """coder.finish is the truth: no reply road means no review, and it SAYS so."""
    def test_github_replies_off_drafts_nothing(self):
        s = MemoryStore(); tid, _ = task_with(s, 'github')
        out = coder.finish(s, tid, {'summary': 'fixed'}, None, 'coder')
        self.assertEqual((out['drafting'], out['message_id']), (False, None))
        self.assertEqual(s.list_reviews('pending'), [])
        self.assertEqual(s.get_task(tid)['Status'], 'done')      # closed, not left waiting

    def test_a_channel_switched_off_drafts_nothing(self):
        s = MemoryStore(); s.set_setting('reply_channels', 'email', 't')
        tid, _ = task_with(s, 'slack')
        with mock.patch('taskuary.responder.write_draft') as wd:
            out = coder.finish(s, tid, {'summary': 'fixed'}, None, 'coder')
        wd.assert_not_called()
        self.assertFalse(out['drafting'])

    def test_email_still_drafts(self):
        s = MemoryStore(); tid, mid = task_with(s, 'email')
        with mock.patch('taskuary.responder.write_draft', return_value='hi'):
            out = coder.finish(s, tid, {'summary': 'fixed'}, None, 'coder')
        self.assertEqual((out['drafting'], out['message_id']), (True, mid))
        self.assertEqual(len(s.list_reviews('pending')), 1)
        self.assertEqual(s.get_task(tid)['Status'], 'waiting')


class WrapEndpointTests(unittest.TestCase):
    """The end-to-end shape of the bug: what the task page is TOLD after a wrap-up."""
    def _wrap(self, channel):
        from fastapi.testclient import TestClient
        from taskuary import server, terminal
        c = TestClient(server.app)
        tid, _ = task_with(server.store, channel)
        with mock.patch.object(terminal, 'transcript_for', return_value=('did the work', 'claude', None)), \
             mock.patch.object(server, 'report_from_transcript', return_value={'summary': 'fixed', 'determination': '', 'actions': ''}), \
             mock.patch('taskuary.responder.write_draft', return_value='hi'):
            return c.post(f'/api/tasks/{tid}/wrap', json={'close': True}).json()

    def test_github_wrap_does_not_promise_a_draft(self):
        out = self._wrap('github')
        self.assertFalse(out['drafting'])          # the button must not render

    def test_email_wrap_does_promise_one(self):
        self.assertTrue(self._wrap('email')['drafting'])


if __name__ == '__main__':
    unittest.main()
