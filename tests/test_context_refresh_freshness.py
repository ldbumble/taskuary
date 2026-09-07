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

    def test_grace_skips_the_poll_but_an_action_still_reads_the_provider(self):
        from unittest import mock
        from taskuary.store import MemoryStore
        s = MemoryStore()
        cid = s.get_connector_by_type('teams')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1, 'ConfigJson': '{}'}, 'test')
        tid = s.create_task({'Title': 'A chat'}, 'test')
        mid = s.add_message({'ExternalId': 'x1', 'ConversationId': 'c1', 'TaskId': tid, 'Channel': 'teams', 'SourceName': 'teams',
                             'FromName': 'Dana', 'FromEmail': '', 'Subject': 'hi', 'BodyText': 'hi', 'Status': 'routed',
                             'SentAt': '2026-09-06 12:00:00'})
        server._QUICK_LAST['teams'] = time.time() - 5
        server._QUICK_LAST_STORE['teams'] = id(s)
        with mock.patch.object(server, 'store', s), mock.patch.object(server, '_poll_reports', return_value=0) as poll:
            intro = server._refresh_chat_context(task_id=tid, message_id=mid, grace=True)
            self.assertFalse(poll.called); self.assertTrue(intro.get('fresh')); self.assertFalse(intro['polled'])
            action = server._refresh_chat_context(task_id=tid, message_id=mid)
            self.assertTrue(poll.called); self.assertTrue(action['polled'])

    def test_one_stale_type_makes_the_refresh_run(self):
        server._QUICK_LAST.update(imap=time.time() - 5, teams=time.time() - server.CONTEXT_FRESH_SECONDS - 1)
        self.assertFalse(server._recently_fetched(['imap', 'teams']))


if __name__ == '__main__': unittest.main()
