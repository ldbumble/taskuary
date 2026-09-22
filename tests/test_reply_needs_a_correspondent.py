"""A reply needs somebody at the other end of it.

The owner typed a task himself ("SAML SSO", channel `own`), pressed Write reply, and the drafter
was handed a thread with no correspondent in it. So it answered HIM: its own analysis of the
vendor's note, and under that a letter it suggested sending - all of it in the box whose button
sends (TQ-0674, 2026-09-22). A finished session has always known better (coder.no_one_behind, which
is why a scheduled report's task gets no draft); the reply door never asked.
"""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import responder, server


class NoOneToAnswerTests(unittest.TestCase):
    def setUp(self):
        self.c, self.s = TestClient(server.app), server.store

    def _message(self, channel, **kw):
        tid = self.s.create_task({'Title': 'SAML SSO', 'Kind': 'coding', 'Status': 'open'}, 'owner')
        return tid, self.s.add_message({'TaskId': tid, 'ExternalId': f'x-{channel}', 'Channel': channel,
                                        'Subject': 'SAML SSO', 'SentAt': '2026-09-22 10:30:12',
                                        'BodyText': 'what would it look like', 'Status': 'routed', **kw})

    def test_a_task_the_owner_typed_himself_has_no_reply_to_open(self):
        _tid, mid = self._message('own')
        with mock.patch.object(responder, 'write_draft', side_effect=AssertionError('nothing to draft')):
            r = self.c.post(f'/api/messages/{mid}/reply', json={'draft': True})
        self.assertEqual(r.status_code, 422)
        self.assertIn('nobody to answer', r.json()['detail'])

    def test_a_report_and_the_assistant_are_the_same(self):
        for channel in ('report', 'assistant'):
            _tid, mid = self._message(channel)
            r = self.c.post(f'/api/messages/{mid}/reply', json={'draft': True})
            self.assertEqual(r.status_code, 422, f'{channel}: {r.text}')

    def test_a_channel_that_cannot_CARRY_a_reply_still_drafts_one(self):
        """PW-237: a real person wrote it. Where the answer leaves from is a different question."""
        _tid, mid = self._message('github', FromEmail='dana@users.noreply.github.com')
        with mock.patch.object(responder, 'write_draft', return_value='Thanks - looking now.') as drafted:
            r = self.c.post(f'/api/messages/{mid}/reply', json={'draft': True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(drafted.called, 'the draft is written; only sending is gated')
        self.assertEqual(r.json()['draft'], 'Thanks - looking now.')


if __name__ == '__main__':
    unittest.main()
