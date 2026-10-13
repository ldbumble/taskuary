"""LOOP THEM IN (the owner, 2026-10-13): "Can I loop Gail in on this email and ask her if she knows anything about it?" over a
forwarded notice was proposed as a hand-off to a regular agent - the reply tool had no way to copy anyone. It is a reply now, with
the person copied: the card shows the CC line and Approve sends it. A name nobody by it has written as is said, never guessed."""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import concierge, server
from taskuary.store import MemoryStore
from test_funnel import ago


class LoopInTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Certificate expires in 90 days', 'Status': 'open'}, 'owner')
        self.mid = self.s.add_message({'TaskId': self.tid, 'ExternalId': 'x:1', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                                       'Subject': 'Fw: certificate expires in 90 days', 'FromName': 'Ray Colton', 'FromEmail': 'ray@northwind.example',
                                       'SentAt': ago(2), 'BodyText': 'Do we still need this one?', 'Status': 'routed',
                                       'RecipientsJson': json.dumps({'to': ['alex@northwind.example'], 'cc': []})})
        self.s.add_message({'ExternalId': 'x:2', 'Channel': 'email', 'SourceName': 'alex@northwind.example', 'Subject': 'Lunch',
                            'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example', 'SentAt': ago(30), 'BodyText': 'Lunch?', 'Status': 'filed'})
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)

    def deliver(self, rid): return json.loads(self.s.get_review(rid)['Deliver'] or '{}')

    def test_the_reply_tool_carries_who_to_loop_in(self):
        _, d = concierge.parse_decision('Sure.\nCALL: {"kind": "reply", "params": {"text": "ask her if she knows it", "cc": ["Gail"]}}')
        self.assertEqual((d['verb'], d['cc']), ('reply', ['Gail']))
        _, d = concierge.parse_decision('CALL: {"kind": "reply", "params": {"text": "x", "cc": "Gail Moreno"}}')
        self.assertEqual(d['cc'], ['Gail Moreno'])

    def test_a_reply_opened_with_someone_to_loop_in_copies_them(self):
        r = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': True, 'later': True, 'instruction': 'ask Gail', 'cc': ['Gail']})
        self.assertEqual(r.status_code, 200, r.text)
        env = self.deliver(r.json()['reviewId'])
        self.assertEqual((env['kind'], env['to'], env['cc']), ('reply', ['ray@northwind.example'], ['gail@northwind.example']))
        self.assertEqual(r.json()['cc'], ['gail@northwind.example'])

    def test_a_name_nobody_has_written_as_is_said_not_guessed(self):
        r = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': True, 'later': True, 'cc': ['Zelda']})
        self.assertEqual(r.json()['cc_unknown'], ['Zelda'])
        self.assertNotIn('cc', self.deliver(r.json()['reviewId']))

    def test_an_address_is_taken_as_it_is(self):
        r = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': True, 'later': True, 'cc': ['omar@vendor.example']})
        self.assertEqual(self.deliver(r.json()['reviewId'])['cc'], ['omar@vendor.example'])
