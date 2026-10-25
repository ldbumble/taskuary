"""The drafts' track record (trackrecord.py, 2026-10-25): counted by kind and recipient domain, read-only, and the stale advice
to auto-answer is gone - that rule kind was removed (policy.py), and nothing is sent without the owner's press."""
import unittest

from taskuary import assistant, assistantblocks as B, outcomes, toil, trackrecord
from taskuary.store import MemoryStore


def _sent(s, who, verb, kind='draft_reply'):
    mid = s.add_message({'ExternalId': f'graph:{who}:{verb}:{kind}', 'Channel': 'email', 'Subject': 'invoice 4411', 'FromEmail': who})
    rid = s.add_review({'MessageId': mid, 'Kind': kind, 'DraftText': 'Paid on Friday.', 'Status': 'approved'})
    outcomes.record(s, 'reply.sent', 'message', mid, 'owner', facts={'review': rid, 'verb': verb, 'who': who})


def _rejected(s, who):
    mid = s.add_message({'ExternalId': f'graph:{who}:no', 'Channel': 'email', 'Subject': 'can you sign this', 'FromEmail': who})
    rid = s.add_review({'MessageId': mid, 'Kind': 'draft_reply', 'DraftText': 'Signed.'})
    s.decide_review(rid, 'rejected', None, 'owner')


class TrackRecordTests(unittest.TestCase):
    def test_patterns_group_by_kind_and_recipient_domain(self):
        s = MemoryStore()
        _sent(s, 'erin@vendor.example', 'approve'); _sent(s, 'ray@vendor.example', 'approve'); _sent(s, 'gail@vendor.example', 'edit')
        _rejected(s, 'paula@vendor.example')
        _sent(s, 'omar@northwind.example', 'approve', kind='outbound')
        rows = trackrecord.patterns(s, 30)
        self.assertEqual(rows[0], {'kind': 'reply', 'domain': 'vendor.example', 'as_drafted': 2, 'edited': 1, 'rejected': 1, 'total': 4})
        self.assertEqual((rows[1]['kind'], rows[1]['domain'], rows[1]['as_drafted']), ('new email', 'northwind.example', 1))

    def test_the_assistant_reads_it_as_evidence_never_as_a_reason_to_send(self):
        s = MemoryStore(); _sent(s, 'erin@vendor.example', 'approve')
        b = B.by_id('track_record')
        self.assertIn('never a reason to send', b.heading)
        text, _ = b.build(s, B.defaults(s, b))
        self.assertEqual(text, '- reply to vendor.example: 1 sent as drafted, 0 edited first, 0 rejected')
        self.assertIn('track_record', B.card('memory').blocks)

    def test_nothing_drafted_says_nothing(self):
        self.assertEqual(trackrecord.block(MemoryStore()), '')

    def test_the_settings_numbers_carry_it(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        d = TestClient(server.app).get('/api/working').json()
        self.assertIn('windows', d); self.assertIsInstance(d['record'], list)

    def test_no_advice_to_auto_answer_is_left(self):
        """policy.py removed auto_answer (2026-09-25); the weekly report and the check still recommended it."""
        import hashlib
        for text in (toil.PROMPT, assistant.PROMPT, toil.__doc__.split('Never')[0]):
            self.assertNotRegex(text.lower(), r'auto[_ -]?answer|auto-draft')
        # ...and the shipped copies already saved on a seeded row are healed to today's, not left advising it
        self.assertTrue(all('auto_answer' in p for p in toil.OLD_PROMPTS))
        self.assertIn('1470c920581d783f70e98193ff6d6998fb7ec5f126b1ce4fb855979b8a21a138', assistant.OLD_PROMPT_SHA)
        self.assertNotIn(hashlib.sha256(assistant.PROMPT.encode()).hexdigest(), assistant.OLD_PROMPT_SHA)
        s = MemoryStore()
        for i in range(3): _sent(s, 'erin@vendor.example', 'approve')
        for r in s.list_reviews('approved'): s._exec("UPDATE review SET DecidedAt=datetime('now','localtime') WHERE ReviewId=?", (r['ReviewId'],))
        self.assertNotIn('auto_answer', toil.gather(s))


if __name__ == '__main__': unittest.main()
