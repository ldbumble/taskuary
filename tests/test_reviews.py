"""Review-queue visibility: a pending review must point at work you can still SEE - a
dropped/done task or a skip-hidden message must not keep the badge at 1 (the reported
bug: a task removed from the Timeline left its review, with '1' on the tab, forever).
"""
import unittest
from taskuary.store import MemoryStore
from taskuary.testing import Factory


class ReviewVisibilityTests(unittest.TestCase):
    def seed(self, s):
        p = Factory(s).pending_draft()
        return p.tid, p.mid, p.rid

    def pending(self, s): return s.list_reviews('pending')

    def test_dropped_task_leaves_the_queue(self):
        s = MemoryStore(); tid, _, _ = self.seed(s)
        self.assertEqual(len(self.pending(s)), 1)
        s.update_task(tid, {'Status': 'dropped'}, 't')
        self.assertEqual(self.pending(s), [])

    def test_skipped_message_leaves_the_queue_and_comes_back(self):
        s = MemoryStore(); _, mid, _ = self.seed(s)
        s.set_message_status(mid, 'skipped')
        self.assertEqual(self.pending(s), [])
        s.set_message_status(mid, 'routed')          # unskip: reversible, review returns
        self.assertEqual(len(self.pending(s)), 1)

    def test_pending_review_agrees_with_the_queue(self):
        """The reported divergence: the queue hid it, the funnel still handed it back - so the
        same draft was both gone and live depending on who asked."""
        s = MemoryStore(); tid, mid, _ = self.seed(s)
        s.set_message_status(mid, 'skipped')
        self.assertEqual((self.pending(s), s.pending_review(tid), s.pending_review(tid, 'draft')), ([], None, None))
        s.set_message_status(mid, 'routed')          # unskip: both see it again
        self.assertEqual((len(self.pending(s)), bool(s.pending_review(tid))), (1, True))

    def test_a_closed_task_hides_a_later_pending_review_from_both(self):
        s = MemoryStore(); tid, _, _ = self.seed(s)
        s.update_task(tid, {'Status': 'done'}, 't')                  # supersedes the seeded one
        rid = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending'})   # ...a late arrival
        self.assertEqual((self.pending(s), s.pending_review(tid)), ([], None))
        self.assertEqual((s.pending_review(tid, live_only=False) or {}).get('ReviewId'), rid)

    def test_decided_history_survives_done_tasks(self):
        s = MemoryStore(); tid, _, rid = self.seed(s)
        s.decide_review(rid, 'approved', 'final', 'me')
        s.update_task(tid, {'Status': 'done'}, 't')
        self.assertEqual(len(s.list_reviews('approved')), 1)


if __name__ == '__main__':
    unittest.main()
