""""Remove the urgent tag" and "once I hand off, the task should close".

Two things the funnel asserted on its own. Priority was a keyword scan, and it matched bare
substrings - so 'down' hit "do not DOWNload attachments", the banner every piece of external
mail carries, and ordinary vendor mail arrived urgent. A priority that lands on every third
task ranks nothing.

And handing a task to a person sent the forward, wrote the note, and left the card open on
'needs you' - asking the owner to decide again about work they had just given away.
"""
import unittest

from taskuary.routing import draft_task_fields

BANNER = ('This email was sent from outside of MFA. ** Do not click links or download '
          'attachments unless you know the content is safe. **\n\nHello Uri,\n\n'
          'Our Docusign is still pending.\n\nThank you,\nAnna')


class PriorityIsNotGuessedTests(unittest.TestCase):
    def test_the_external_mail_banner_is_not_an_emergency(self):
        """The exact mail that came in urgent: 'download' contains 'down'."""
        self.assertEqual(draft_task_fields({'subject': 'RE: Valley Bank', 'body': BANNER})['priority'], 'normal')

    def test_the_word_urgent_in_the_body_is_not_a_priority(self):
        """Senders call their own mail urgent constantly; that is their judgement, not yours."""
        for body in ['This is urgent, please handle today.', 'Need this ASAP.',
                     'The site is down.', 'Please action immediately.']:
            self.assertEqual(draft_task_fields({'subject': 's', 'body': body})['priority'], 'normal', body)

    def test_a_rule_is_what_makes_a_task_urgent(self):
        f = draft_task_fields({'subject': 'RE: Valley Bank', 'body': BANNER}, urgent=True)
        self.assertEqual(f['priority'], 'urgent')

    def test_urgency_does_not_disturb_the_rest_of_the_draft(self):
        a = draft_task_fields({'subject': 'export is broken', 'body': 'the nightly deploy failed'})
        b = draft_task_fields({'subject': 'export is broken', 'body': 'the nightly deploy failed'}, urgent=True)
        self.assertEqual((a['title'], a['summary'], a['kind']), (b['title'], b['summary'], b['kind']))
        self.assertEqual(a['kind'], 'coding')


class EscalateIsTheUrgencyRuleTests(unittest.TestCase):
    """'escalate' sat in the policy precedence, read by nobody. It is the knob."""
    def _ingested(self, policies):
        from taskuary import ingest
        from taskuary.store import MemoryStore
        s = MemoryStore()
        for p in policies: s.save_policy(p, 'owner')
        out = ingest.ingest_message(s, {'external_id': 'e1', 'channel': 'email',
                                        'from_email': 'anna@valley.example', 'subject': 'Docusign',
                                        'body': 'Please add the facility column.'},
                                    llm=lambda sy, u, images=None: '{"intent": "task", "why": "a change was asked for"}')
        return s, out

    def test_no_rule_means_normal(self):
        s, out = self._ingested([])
        self.assertEqual(s.get_task(out['task_id'])['Priority'], 'normal')

    def test_an_escalate_rule_on_the_sender_marks_it_urgent(self):
        s, out = self._ingested([{'Name': 'the bank', 'Kind': 'sender', 'Pattern': 'anna@valley.example',
                                  'Action': 'escalate', 'Reason': 'they only write when it matters'}])
        self.assertEqual(s.get_task(out['task_id'])['Priority'], 'urgent')

    def test_a_rule_on_somebody_else_does_not(self):
        s, out = self._ingested([{'Name': 'someone else', 'Kind': 'sender', 'Pattern': 'other@x.example',
                                  'Action': 'escalate', 'Reason': 'r'}])
        self.assertEqual(s.get_task(out['task_id'])['Priority'], 'normal')


class HandoffClosesTheTaskTests(unittest.TestCase):
    """Through the real endpoint: the send is faked, everything after it is not."""
    def test_handing_it_to_a_person_closes_it_and_retires_the_review(self):
        from unittest import mock
        from fastapi.testclient import TestClient
        from taskuary import server
        s = server.store
        tid = s.create_task({'Title': 'Docusign from Valley', 'Kind': 'reply', 'Status': 'waiting'}, 'router')
        rid = s.add_review({'TaskId': tid, 'Kind': 'reply', 'DraftText': 'here is a draft', 'Status': 'pending'})
        self.assertIn(rid, [r['ReviewId'] for r in s.list_reviews('pending')])

        with mock.patch('taskuary.outbound.send_email', return_value={'id': 'sent-1'}):
            r = TestClient(server.app).post(f'/api/tasks/{tid}/handoff',
                                            json={'to': 'hwhitfield@example.com', 'channel': 'email',
                                                  'text': 'Can you get someone to sign the docusign?'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'done')

        t = s.get_task(tid)
        self.assertEqual(t['Status'], 'done')                 # not 'waiting', not 'needs you'
        self.assertTrue(t['ClosedAt'])
        self.assertEqual(s.get_review(rid)['Status'], 'superseded')
        self.assertNotIn(rid, [r['ReviewId'] for r in s.list_reviews('pending')])
        # the forward itself is still on the record - closing is not forgetting
        self.assertTrue(any('Handed off to hwhitfield@example.com' in (c['Body'] or '')
                            for c in s.list_comments(tid)))

    def test_a_draft_only_preview_changes_nothing(self):
        """Asking the AI to WRITE the forward is not sending it, so nothing may close."""
        from fastapi.testclient import TestClient
        from taskuary import server
        s = server.store
        tid = s.create_task({'Title': 'Still mine', 'Kind': 'reply', 'Status': 'waiting'}, 'router')
        r = TestClient(server.app).post(f'/api/tasks/{tid}/handoff',
                                        json={'draft_only': True, 'text': 'a draft'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(s.get_task(tid)['Status'], 'waiting')


if __name__ == '__main__':
    unittest.main()
