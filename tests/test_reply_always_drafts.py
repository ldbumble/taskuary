"""A question always gets its draft; sending capability decides only whether it can be sent
(PW-042 to PW-047), and a task whose kind the brain could not name is general, not coding
(PW-067, PW-068).

`reply_only` on a channel with replies switched off used to be FILED - a question the owner
still had to answer, wearing the "nothing to do" face, with no draft anywhere. And the draft
itself waited on auto_draft_enabled. Now every reply-needed item opens (or reuses) its task and
pending review and asks for a draft at once; the review carries why sending is unavailable, so
every surface can hide the send button and say so, while the server keeps refusing to send. A
draft that could not be written says so on the review and can be retried; the item stays
reply-needed. Uncertain kind defaults to `general`: no coding session starts on a guess.
"""
import unittest
from unittest import mock
from fastapi.testclient import TestClient

from taskuary import ingest, routing, server, triage
from taskuary.store import MemoryStore

Q = {'external_id': 'q1', 'channel': 'teams', 'from_email': 'dana@vendor.example', 'from_name': 'Dana',
     'conversation_id': 'teams:19:room@thread.v2', 'subject': '', 'body': 'Are you around Tuesday at 3?', 'sent_at': '2026-09-06 10:00:00'}
ASK = lambda *a, **k: '{"intent": "reply_only", "why": "asks when the owner is free"}'


def store(replies_off=('teams',), auto_draft='1'):
    s = MemoryStore()
    s.set_setting('reply_channels', ','.join(c for c in ('email', 'teams', 'slack', 'telegram', 'whatsapp', 'imessage', 'discord') if c not in replies_off), 't')
    s.set_setting('auto_draft_enabled', auto_draft, 't')
    s.set_setting('coder_auto_enabled', '1', 't')
    s.upsert_agent('coder', 'coding', 'cli', '{}')
    return s


class AlwaysDraftTests(unittest.TestCase):
    def test_a_question_on_a_channel_with_replies_off_still_opens_its_reply_task_and_review(self):
        s = store(); spawned = []
        with mock.patch.object(ingest, '_spawn', side_effect=lambda f, *a: spawned.append((f.__name__, a))):
            out = ingest.ingest_message(s, dict(Q), llm=ASK)
        self.assertEqual(out['status'], 'created')
        tid = out['task_id']
        self.assertEqual(s.get_task(tid)['Kind'], 'reply')
        rv = s.pending_review(tid)
        self.assertIsNotNone(rv); self.assertEqual(rv['MessageId'], out['message_id'])
        self.assertIn(('_auto_draft', (s, tid, rv['ReviewId'])), spawned)
        reason = s.message_routes(out['message_id'])[-1]['Reason']
        self.assertIn('replies are off for teams', reason); self.assertNotIn('filed instead of drafted', reason)

    def test_the_draft_is_requested_even_with_auto_draft_off(self):
        s = store(replies_off=(), auto_draft='0'); spawned = []
        with mock.patch.object(ingest, '_spawn', side_effect=lambda f, *a: spawned.append(f.__name__)):
            ingest.ingest_message(s, dict(Q), llm=ASK)
        self.assertIn('_auto_draft', spawned)

    def test_a_fresh_question_on_an_existing_task_reuses_it_with_one_review(self):
        # an email thread: chat follow-ups take the chat reader's road (chat_continues), which the
        # same-day relationship verdict of PW-031 replaces in its own section
        s = store(replies_off=()); spawned = []
        M = {**Q, 'channel': 'email', 'conversation_id': 'AAQk-export', 'subject': 'The export'}
        first = ingest.ingest_message(s, {**M, 'body': 'Can you send me the export?'}, llm=lambda *a, **k: '{"intent": "task", "kind": "task", "why": "x"}')
        tid = first['task_id']
        with mock.patch.object(ingest, '_spawn', side_effect=lambda f, *a: spawned.append(f.__name__)):
            out = ingest.ingest_message(s, {**M, 'external_id': 'q2', 'subject': 'Re: The export', 'body': 'Also - are you around Tuesday at 3?', 'sent_at': '2026-09-06 10:05:00'}, llm=ASK)
            again = ingest.ingest_message(s, {**M, 'external_id': 'q2', 'subject': 'Re: The export', 'body': 'Also - are you around Tuesday at 3?', 'sent_at': '2026-09-06 10:05:00'}, llm=ASK)
        self.assertEqual((out['status'], out['task_id']), ('attached', tid))
        self.assertEqual(again['status'], 'duplicate')
        reviews = [r for r in s.list_reviews('pending') if r['TaskId'] == tid]
        self.assertEqual(len(reviews), 1); self.assertEqual(reviews[0]['MessageId'], out['message_id'])
        self.assertEqual(spawned.count('_auto_draft'), 1)
        self.assertEqual(len(s.list_tasks()), 1)


class DraftFailureTests(unittest.TestCase):
    def setUp(self):
        self.s = store(replies_off=())
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)

    def test_a_draft_that_could_not_be_written_says_so_and_keeps_the_item_reply_needed(self):
        with mock.patch.object(ingest, '_spawn', side_effect=lambda f, *a: f(*a)):     # run the draft inline
            out = ingest.ingest_message(self.s, dict(Q), llm=ASK)                        # no responder brain: the draft fails
        rv = self.s.pending_review(out['task_id'])
        self.assertEqual(rv['Status'], 'pending'); self.assertFalse(rv.get('DraftText'))
        self.assertIn('no AI connector', rv['DraftError'])
        row = next(r for r in self.s.feed(limit=10) if r['MessageId'] == out['message_id'])
        self.assertEqual(row['HasDraft'], 0); self.assertIn('no AI connector', row['DraftError'])
        self.assertEqual(row['ReviewStatus'], 'pending')

    def test_a_successful_redraft_clears_the_failure(self):
        with mock.patch.object(ingest, '_spawn', side_effect=lambda f, *a: f(*a)):
            out = ingest.ingest_message(self.s, dict(Q), llm=ASK)
        rv = self.s.pending_review(out['task_id'])
        self.assertTrue(rv['DraftError'])
        def written(store_, tid, rid_, **k):
            store_.update_review_draft(rid_, 'Tuesday at 3 works.', None); return 'Tuesday at 3 works.'
        with mock.patch('taskuary.responder.write_draft', side_effect=written):
            r = self.c.post(f"/api/reviews/{rv['ReviewId']}/draft")
        self.assertEqual(r.status_code, 200)
        rv = self.s.get_review(rv['ReviewId'])
        self.assertEqual(rv['DraftText'], 'Tuesday at 3 works.'); self.assertFalse(rv['DraftError'])


class SendBlockedTests(unittest.TestCase):
    def setUp(self):
        self.s = store(replies_off=('teams',))
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)
        with mock.patch.object(ingest, '_spawn'):
            self.out = ingest.ingest_message(self.s, dict(Q), llm=ASK)
        self.rv = self.s.pending_review(self.out['task_id'])
        self.s.update_review_draft(self.rv['ReviewId'], 'Tuesday at 3 works.', None)

    def test_reviews_and_feed_rows_carry_the_concrete_reason_sending_is_unavailable(self):
        rv = next(r for r in self.c.get('/api/reviews', params={'status': 'pending'}).json()['data'] if r['ReviewId'] == self.rv['ReviewId'])
        self.assertFalse(rv['CanSend']); self.assertIn('replies are off for teams', rv['SendBlock'])
        row = next(r for r in self.c.get('/api/feed').json()['data'] if r['MessageId'] == self.out['message_id'])
        self.assertFalse(row['CanSend']); self.assertIn('replies are off for teams', row['SendBlock'])
        self.s.set_setting('reply_channels', 'email,teams', 't')
        rv = next(r for r in self.c.get('/api/reviews', params={'status': 'pending'}).json()['data'] if r['ReviewId'] == self.rv['ReviewId'])
        self.assertTrue(rv['CanSend']); self.assertEqual(rv['SendBlock'], '')

    def test_the_server_still_refuses_to_send_on_a_blocked_channel(self):
        sent = []
        with mock.patch('taskuary.outbound.reply_to_message', side_effect=lambda *a, **k: sent.append(1) or {'ok': True}):
            r = self.c.post(f"/api/reviews/{self.rv['ReviewId']}/decide", json={'verb': 'approve', 'final_text': 'Tuesday at 3 works.', 'note': None})
        # refused either way the API says it: an error status, or a 200 carrying send_error (the
        # verdict door reports a channel it cannot use without throwing the owner's decision away)
        self.assertTrue(r.status_code >= 400 or r.json().get('send_error'), r.text[:200])
        self.assertEqual(sent, [])
        rv = self.s.get_review(self.rv['ReviewId'])
        self.assertEqual(rv['Status'], 'pending'); self.assertEqual(rv['DraftText'], 'Tuesday at 3 works.')


class GeneralDefaultTests(unittest.TestCase):
    def test_a_task_whose_kind_the_brain_did_not_name_is_general(self):
        s = store(replies_off=()); spawned = []
        with mock.patch.object(ingest, '_spawn', side_effect=lambda f, *a: spawned.append(f.__name__)):
            out = ingest.ingest_message(s, {**Q, 'body': 'Please sort out the badge situation.'}, llm=lambda *a, **k: '{"intent": "task", "why": "an ask"}')
        self.assertEqual(s.get_task(out['task_id'])['Kind'], 'general')
        self.assertNotIn('_auto_code', spawned)                          # no coding session on a guess (PW-068)

    def test_an_invalid_kind_is_general_too(self):
        s = store(replies_off=())
        with mock.patch.object(ingest, '_spawn'):
            out = ingest.ingest_message(s, {**Q, 'body': 'Please sort out the badge situation.'}, llm=lambda *a, **k: '{"intent": "task", "kind": "robot", "why": "x"}')
        self.assertEqual(s.get_task(out['task_id'])['Kind'], 'general')

    def test_explicit_coding_and_owner_task_decisions_are_kept(self):
        s = store(replies_off=()); spawned = []
        with mock.patch.object(ingest, '_spawn', side_effect=lambda f, *a: spawned.append(f.__name__)):
            coding = ingest.ingest_message(s, {**Q, 'external_id': 'c', 'conversation_id': 'c', 'body': 'Fix the export job.'}, llm=lambda *a, **k: '{"intent": "task", "kind": "coding", "why": "x"}')
            own = ingest.ingest_message(s, {**Q, 'external_id': 'o', 'conversation_id': 'o', 'body': 'Sign the lease form in person.'}, llm=lambda *a, **k: '{"intent": "task", "kind": "task", "why": "x"}')
        self.assertEqual(s.get_task(coding['task_id'])['Kind'], 'coding'); self.assertIn('_auto_code', spawned)
        self.assertEqual(s.get_task(own['task_id'])['Kind'], 'task')

    def test_the_keyword_fallback_no_longer_guesses_coding(self):
        f = routing.draft_task_fields({'subject': 'Stack trace in the nightly export', 'body': 'Traceback (most recent call last): the export crashed with a KeyError again, can someone fix'})
        self.assertEqual(f['kind'], 'general')
        self.assertEqual(routing.draft_task_fields({'subject': 'x', 'body': 'Are you free Tuesday?'})['kind'], 'reply')
        self.assertEqual(routing.draft_task_fields({'subject': 'x', 'body': 'x'}, kind='coding')['kind'], 'coding')

    def test_the_classifier_instructions_default_to_general(self):
        self.assertNotIn('Cannot tell? Say coding', triage.INTENT_SYSTEM)
        self.assertIn('Cannot tell? Say general', triage.INTENT_SYSTEM)
        from pathlib import Path
        doc = (Path(__file__).parent.parent / 'taskuary' / 'templates' / 'triage.md').read_text(encoding='utf-8')
        self.assertNotIn('say coding', doc.lower()); self.assertIn('say general', doc.lower())


if __name__ == '__main__':
    unittest.main()
