"""Starting a new outbound email: arbitrary/multiple recipients and durable CC."""
import json
import unittest
from unittest import mock

from taskuary import outbox, verdicts
from taskuary.store import MemoryStore


class OutboxEmailTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()

    def test_multiple_to_and_cc_are_saved_on_the_review_and_shown_to_the_drafter(self):
        self.s.save_doc('style', '### Greeting & sign-off\n- Always end with:\n  Best,\n  Uri\n  MFA Heritage\n'
                                    '### Tone & length\n- concise but complete\n', 'test')
        seen = {}
        def llm(system, user, max_tokens=0):
            seen['system'], seen['user'] = system, user
            return 'Hi all,\n\nThe report is ready.\n\nBest,\nUri'
        result = outbox.compose(self.s, 'email', ['a@example.com', 'b@example.com'], 'share the report',
                                subject='Monthly report', cc=['copy@example.com'], llm=llm)
        review = self.s.get_review(result['reviewId'])
        deliver = json.loads(review['Deliver'])
        self.assertEqual(deliver['to'], ['a@example.com', 'b@example.com'])
        self.assertEqual(deliver['cc'], ['copy@example.com'])
        self.assertIn('TO: a@example.com, b@example.com', seen['user'])
        self.assertIn('CC: copy@example.com', seen['user'])
        self.assertIn('exact recurring signature STYLE.md', seen['system'])
        self.assertIn('MFA Heritage', seen['system'])

    def test_a_new_address_is_allowed_and_bad_or_missing_addresses_are_refused(self):
        made = outbox.compose(self.s, 'email', 'never-seen@example.com', 'say hello',
                              subject='Hello', llm=lambda *_a, **_k: 'Hello')
        self.assertTrue(made['reviewId'])
        with self.assertRaisesRegex(ValueError, 'valid email'):
            outbox.compose(self.s, 'email', ['not-an-address'], 'say hello', subject='Hello',
                           llm=lambda *_a, **_k: 'Hello')
        with self.assertRaisesRegex(ValueError, 'at least one'):
            outbox.compose(self.s, 'email', [], 'say hello', subject='Hello',
                           llm=lambda *_a, **_k: 'Hello')

    def test_comma_pasted_addresses_are_split_and_to_cc_duplicates_are_removed(self):
        made = outbox.compose(self.s, 'email', 'One@example.com, two@example.com', 'say hello',
                              subject='Hello', cc=['one@example.com', 'three@example.com'],
                              llm=lambda *_a, **_k: 'Hello')
        deliver = json.loads(self.s.get_review(made['reviewId'])['Deliver'])
        self.assertEqual(deliver['to'], ['One@example.com', 'two@example.com'])
        self.assertEqual(deliver['cc'], ['three@example.com'])

    def test_saved_cc_is_used_when_an_approval_client_does_not_override_it(self):
        made = outbox.compose(self.s, 'email', ['to@example.com'], 'say hello', subject='Hello',
                              cc=['copy@example.com'], llm=lambda *_a, **_k: 'Hello')
        sent = {}
        def send(_store, channel, to, subject, body, cc=None):
            sent.update(channel=channel, to=to, subject=subject, body=body, cc=cc)
            return {'channel': channel, 'to': to, 'cc': cc}
        with mock.patch('taskuary.outbound.send_out', side_effect=send):
            verdicts.decide(self.s, self.s.get_review(made['reviewId']), 'approve', 'Hello')
        self.assertEqual(sent['to'], ['to@example.com'])
        self.assertEqual(sent['cc'], ['copy@example.com'])

    def test_redraft_uses_the_saved_recipient_envelope(self):
        made = outbox.compose(self.s, 'email', ['one@example.com', 'two@example.com'], 'send the result',
                              subject='Result', cc=['copy@example.com'], llm=lambda *_a, **_k: 'First')
        seen = {}
        def llm(_system, user, max_tokens=0): seen['user'] = user; return 'Rewritten'
        draft = outbox.redraft_review(self.s, self.s.get_review(made['reviewId']),
                                      resolution='The result is 42.', llm=llm)
        self.assertEqual(draft, 'Rewritten')
        self.assertIn('TO: one@example.com, two@example.com', seen['user'])
        self.assertIn('CC: copy@example.com', seen['user'])
        self.assertIn('The result is 42.', seen['user'])


if __name__ == '__main__':
    unittest.main()
