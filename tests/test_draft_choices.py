"""A reply draft's choices are Close out, Redraft or Mark done (the owner, 2026-10-01: "rejected is useless - it should be
redraft or close task"). review.reject still works for an old caller; nothing offers it."""
import unittest

from taskuary import concierge
from taskuary.store import MemoryStore


class DraftChoicesTests(unittest.TestCase):

    def test_reject_is_still_an_operation_for_an_old_caller(self):
        from taskuary import operations
        self.assertIn('review.reject', operations.KINDS)


if __name__ == '__main__': unittest.main()
