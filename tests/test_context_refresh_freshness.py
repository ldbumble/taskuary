"""The context gate before a chat turn polls the provider - but not again within the minute.

Every Next and every named pull re-read Outlook/Teams before speaking, so a walk through ten
items was ten provider round trips (2026-09-06: "first one might take time but every response
after that should be quick")."""
import time
import unittest

from taskuary import server


class RecentlyFetched(unittest.TestCase):
    def setUp(self):
        self.saved = dict(server._QUICK_LAST); server._QUICK_LAST.clear()
    def tearDown(self):
        server._QUICK_LAST.clear(); server._QUICK_LAST.update(self.saved)

    def test_never_fetched_is_not_fresh(self):
        self.assertFalse(server._recently_fetched(['imap']))

    def test_a_fetch_moments_ago_is_fresh_for_every_type_asked(self):
        server._QUICK_LAST.update(imap=time.time() - 5, teams=time.time() - 5)
        self.assertTrue(server._recently_fetched(['imap', 'teams']))

    def test_one_stale_type_makes_the_refresh_run(self):
        server._QUICK_LAST.update(imap=time.time() - 5, teams=time.time() - server.CONTEXT_FRESH_SECONDS - 1)
        self.assertFalse(server._recently_fetched(['imap', 'teams']))


if __name__ == '__main__': unittest.main()
