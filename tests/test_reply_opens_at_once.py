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
            r = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': True, 'later': True, 'ai': True})
        self.assertEqual(r.status_code, 200, r.text)
        out = r.json()
        self.assertTrue(out['reviewId'])
        self.assertEqual((out['draft'], out['drafting']), ('', True))
        self.assertEqual(self.s.get_review(out['reviewId'])['Status'], 'pending')

    def test_the_draft_behind_it_carries_the_owners_words(self):
        rid = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': True, 'later': True, 'ai': True}).json()['reviewId']
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

    def test_draft_reply_on_a_task_no_agent_worked_drafts(self):
        """The owner, 2026-11-03: "drafting reply is broken ... if its still working stay spinning until done". The press reads
        "Draft reply" and spins, and on a task no agent had worked it opened a signature-only box with Draft with AI under it - no
        draft owed, nothing coming (the 2026-10-28 rule). The press drafts wherever there is someone to answer; a writer with
        nothing to go on says what it needs (responder.NotDrafted). Writing by hand is the empty box's own press (`draft: False`)."""
        with mock.patch.object(responder, 'write_draft', side_effect=AssertionError('the press never waits on the model')):
            out = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': True, 'later': True}).json()
        self.assertEqual((out['draft'], out['drafting']), ('', True))
        self.assertEqual(self.s.get_review(out['reviewId'])['Status'], 'pending')
        self.assertTrue(self.s.review_envelope(out['reviewId']))                            # To and Cc are filled at once
        out2 = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': False}).json()    # the box pressed to write it yourself
        self.assertEqual((out2['reviewId'], out2['draft'], out2['drafting']), (out['reviewId'], '', False))

    def test_reply_pressed_while_the_arrivals_draft_is_written_says_drafting(self):
        """"Sometimes it just fills out the text 10 seconds later": a Reply pressed while the arrival's own draft was still being
        written (ingest._auto_draft) reused that review, said nothing was coming, and the draft landed later on its own. The press
        says drafting, and the task's read marks the review `Drafting` so a page opened meanwhile waits on it too."""
        import threading
        from taskuary import ingest
        rid = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': False}).json()['reviewId']
        ingest.DRAFTING[rid] = threading.Event()
        try:
            out = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': True, 'later': True}).json()
            self.assertEqual((out['reviewId'], out['drafting']), (rid, True))
            rv = next(r for r in self.c.get(f'/api/tasks/{self.tid}').json()['reviews'] if r['ReviewId'] == rid)
            self.assertTrue(rv['Drafting'])
            self.assertTrue(next(r for r in self.c.get('/api/reviews').json()['data'] if r['ReviewId'] == rid)['Drafting'])
        finally: ingest.DRAFTING.pop(rid, None)
        rv = next(r for r in self.c.get(f'/api/tasks/{self.tid}').json()['reviews'] if r['ReviewId'] == rid)
        self.assertFalse(rv['Drafting'])

    def test_a_press_after_the_arrivals_writer_said_what_it_needs_reads_that(self):
        """The arrival's writer could not answer (NotDrafted): the press that waited on it says what it needs - no second call."""
        import threading
        from taskuary import ingest
        rid = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': False}).json()['reviewId']
        done = ingest.DRAFTING[rid] = threading.Event()
        self.s.set_review_draft_needs(rid, 'NEEDS: the Tuesday rota from Gail Moreno')
        done.set()
        try:
            with mock.patch.object(responder, 'write_draft', side_effect=AssertionError('a second model call')):
                r = self.c.post(f'/api/reviews/{rid}/draft')
        finally: ingest.DRAFTING.pop(rid, None)
        self.assertEqual((r.status_code, r.json()['draft']), (200, ''))
        self.assertIn('Tuesday rota', r.json()['needs'])

    def test_a_box_that_already_has_its_draft_owes_none(self):
        rid = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': False}).json()['reviewId']
        self.s.update_review_draft(rid, 'Already written.', None)
        out = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': True, 'later': True}).json()
        self.assertEqual((out['reviewId'], out['draft'], out['drafting']), (rid, 'Already written.', False))


    def test_the_owners_words_for_it_owe_a_new_draft_over_the_old_one(self):
        # "reply to Marcus: yes, Thursday at 2 works" found the draft written before and showed it unchanged (2026-10-06)
        rid = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': False}).json()['reviewId']
        self.s.update_review_draft(rid, 'I will check my calendar.', None)
        out = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': True, 'later': True, 'instruction': 'yes, Tuesday works'}).json()
        self.assertEqual((out['reviewId'], out['draft'], out['drafting']), (rid, '', True))

    def test_a_press_while_the_arrivals_own_draft_is_written_waits_for_it(self):
        """A reply task's draft is written at arrival (ingest._auto_draft); the card says "No draft yet" until it lands, and a Draft
        with AI pressed meanwhile wrote a second one over it - two model calls for one reply (the intake walk, 2026-10-26)."""
        import threading
        from taskuary import ingest
        rid = self.c.post(f'/api/messages/{self.mid}/reply', json={'draft': False}).json()['reviewId']
        go, calls = threading.Event(), []
        def slow(store, tid, rid_, actor=None, nudge=None, **kw):
            calls.append(actor); go.wait(10)
            store.update_review_draft(rid_, 'Yes, I can cover Tuesday.', None)
            return 'Yes, I can cover Tuesday.'
        with mock.patch.object(responder, 'write_draft', side_effect=slow), mock.patch.object(server, '_refresh_chat_context', return_value={}):
            arrival = threading.Thread(target=ingest._auto_draft, args=(self.s, self.tid, rid)); arrival.start()
            while not calls: pass
            threading.Timer(0.3, go.set).start()
            r = self.c.post(f'/api/reviews/{rid}/draft')
            arrival.join(10)
            self.assertEqual((r.status_code, r.json()['draft']), (200, 'Yes, I can cover Tuesday.'))
            self.assertEqual(calls, ['auto-draft'], 'the press wrote a second draft')
            self.assertNotIn(rid, ingest.DRAFTING)
            # ...and once it has landed, a press is a real redraft again
            self.c.post(f'/api/reviews/{rid}/draft')
            self.assertEqual(len(calls), 2)

if __name__ == '__main__':
    unittest.main()
