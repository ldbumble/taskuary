"""A reply draft's choices are Close out, Redraft or Mark done (the owner, 2026-10-01: "rejected is useless - it should be
redraft or close task"). review.reject still works for an old caller; nothing offers it."""
import unittest

from taskuary import concierge
from taskuary.store import MemoryStore


class DraftChoicesTests(unittest.TestCase):
    def test_a_draft_offers_redraft_and_mark_done_and_never_reject(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'Answer the rota question', 'Kind': 'task', 'Status': 'open'}, 'o')
        item = {'key': 'review:4', 'kind': 'review', 'rid': 4, 'mid': 7, 'tid': t, 'ref': f'TQ-{t:04d}', 'draft': 'Yes, Tuesday works.',
                'title': 'Rota', 'who': 'Erin Blake'}
        chips = concierge.chips_for(s, item)
        self.assertEqual([c['verb'] for c in chips][:3], ['approve', 'redraft', 'close'], "Close out first: it is the one that sends")
        self.assertEqual(chips[2]['label'], 'Mark done')
        self.assertNotIn('reject', [c['verb'] for c in chips])
        self.assertNotIn('redraft', [c['verb'] for c in concierge.chips_for(s, {**item, 'rid': None})], 'no draft to write again')

    def test_reject_is_still_an_operation_for_an_old_caller(self):
        from taskuary import operations
        self.assertIn('review.reject', operations.KINDS)


if __name__ == '__main__': unittest.main()
