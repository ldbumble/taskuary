"""Reply opens at once (the owner, 2026-10-01: "Reply opens at once with "Drafting…" and the draft fills in - never waits on
the AI"). The press asked /reply to write the draft before it answered, so the card appeared only when the model was done.
`later` opens the box now and says a draft is owed; the page then asks /api/reviews/{rid}/draft for it, which reads the
provider first (the correctness gate) and carries the owner's own words on what to say."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import responder, server
from taskuary.store import MemoryStore


class ReplyOpensAtOnceTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)
        self.tid = self.s.create_task({'Title': 'Rota for Tuesday', 'Kind': 'task', 'Status': 'open'}, 'owner')
        self.mid = self.s.add_message({'TaskId': self.tid, 'ExternalId': 'rota-1', 'Channel': 'email', 'Subject': 'Rota',
                                       'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example',
                                       'BodyText': 'Can you cover Tuesday?', 'Status': 'routed'})

    def test_later_opens_the_box_without_the_model_and_says_a_draft_is_owed(self):
        with mock.patch.object(responder, 'write_draft', side_effect=AssertionError('the press never waits on the model')), \
             mock.patch.object(server, '_refresh_chat_context', side_effect=AssertionError('nor on the provider')):
            r = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': True, 'later': True})
        self.assertEqual(r.status_code, 200, r.text)
        out = r.json()
        self.assertTrue(out['reviewId'])
        self.assertEqual((out['draft'], out['drafting']), ('', True))
        self.assertEqual(self.s.get_review(out['reviewId'])['Status'], 'pending')

    def test_the_draft_behind_it_carries_the_owners_words(self):
        rid = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': True, 'later': True}).json()['reviewId']
        seen = {}
        def fake(store, tid, rid_, actor=None, nudge=None, **kw):
            seen['nudge'] = nudge
            store.update_review_draft(rid_, 'Yes, I can cover Tuesday.', None)
            return 'Yes, I can cover Tuesday.'
        with mock.patch.object(responder, 'write_draft', side_effect=fake), mock.patch.object(server, '_refresh_chat_context', return_value={}):
            r = self.c.post(f'/api/reviews/{rid}/draft', json={'instruction': 'say yes'})
        self.assertEqual(r.json()['draft'], 'Yes, I can cover Tuesday.')
        self.assertIn('say yes', seen['nudge'])
        # ...and an old caller with no body still redrafts
        with mock.patch.object(responder, 'write_draft', side_effect=fake), mock.patch.object(server, '_refresh_chat_context', return_value={}):
            self.assertEqual(self.c.post(f'/api/reviews/{rid}/draft').status_code, 200)
        self.assertIsNone(seen['nudge'])

    def test_a_box_that_already_has_its_draft_owes_none(self):
        rid = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': False}).json()['reviewId']
        self.s.update_review_draft(rid, 'Already written.', None)
        out = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': True, 'later': True}).json()
        self.assertEqual((out['reviewId'], out['draft'], out['drafting']), (rid, 'Already written.', False))


if __name__ == '__main__':
    unittest.main()
