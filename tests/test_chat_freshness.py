"""A live chat is refreshed before use, and an old draft can never race a newer line."""
import json
import unittest
from datetime import datetime, timedelta
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import funnel, server
from taskuary.store import MemoryStore


def stamp(seconds=0):
    return (datetime.now() + timedelta(seconds=seconds)).strftime('%Y-%m-%d %H:%M:%S')


class ChatFreshnessTests(unittest.TestCase):
    def setUp(self):
        funnel.invalidate()

    def thread(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Teams chat with Mindy', 'Kind': 'reply', 'Status': 'open',
                             'Priority': 'normal', 'Source': 'teams'}, 'router')
        first = s.add_message({'TaskId': tid, 'ExternalId': 'teams:first', 'ConversationId': 'teams:mindy',
                               'Channel': 'teams', 'SourceName': 'Mindy', 'Subject': 'Teams chat with Mindy',
                               'FromName': 'Mindy', 'SentAt': stamp(-20), 'BodyText': 'yes', 'Status': 'routed'})
        rid = s.add_review({'TaskId': tid, 'MessageId': first, 'Kind': 'draft', 'Status': 'pending',
                            'DraftText': 'ok give me 5 mins', 'Reason': 'needs a reply'})
        return s, tid, first, rid

    def add_later(self, s, tid):
        return s.add_message({'TaskId': tid, 'ExternalId': 'teams:later', 'ConversationId': 'teams:mindy',
                              'Channel': 'teams', 'SourceName': 'Mindy', 'Subject': 'Teams chat with Mindy',
                              'FromName': 'Mindy', 'SentAt': stamp(),
                              'BodyText': 'Actually, the account works now. No need to reset it.', 'Status': 'routed'})

    def test_review_card_speaks_with_newest_message_and_marks_old_draft_stale(self):
        s, tid, _first, rid = self.thread()
        later = self.add_later(s, tid)
        item = next(i for i in funnel.build(s, keep_surfaced=True)['items'] if i['key'] == f'review:{rid}')
        self.assertEqual(item['mid'], later)
        self.assertTrue(item['stale'])
        self.assertIn('works now', item['preview'])

    def test_approve_refreshes_stale_draft_and_requires_another_yes(self):
        s, tid, _first, rid = self.thread()
        later = self.add_later(s, tid)
        with mock.patch.object(server, 'store', s), \
             mock.patch('taskuary.responder.draft_reply', return_value='Glad it is working — I will leave it alone.'), \
             mock.patch('taskuary.outbound.reply_to_message') as send:
            data = TestClient(server.app).post(
                f'/api/reviews/{rid}/decide',
                json={'verb': 'approve', 'final_text': 'ok give me 5 mins', 'note': None}).json()
        self.assertTrue(data['stale'])
        self.assertFalse(data['ok'])
        self.assertFalse(send.called)
        self.assertEqual(s.get_review(rid)['MessageId'], later)
        self.assertIn('Glad it is working', s.get_review(rid)['DraftText'])

    def test_action_refresh_detects_a_message_that_lands_during_the_sync(self):
        s, tid, first, _rid = self.thread()
        cid = s.get_connector_by_type('teams')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1, 'ConfigJson': '{}'}, 'test')
        with mock.patch.object(server, 'store', s), \
             mock.patch.object(server, '_poll_reports', side_effect=lambda *a, **k: (self.add_later(s, tid) and 1)) as poll:
            got = server._refresh_chat_context(task_id=tid, message_id=first)
        self.assertTrue(got['newer'])
        self.assertEqual(got['added'], 1)
        self.assertEqual(poll.call_args.kwargs['only'], ['teams'])
        self.assertTrue(poll.call_args.kwargs['wait'])

    def test_the_owner_hears_that_retriage_started_when_the_lines_land_not_after_their_triage(self):
        """PW-052/057: the notice used to be built after the poll had waited for triage, so the owner heard the
        RESULT and never that a re-evaluation had begun. The fetch now reports its new lines the moment they
        land, before the drain wait; the existing result line follows."""
        s, tid, first, _rid = self.thread()
        cid = s.get_connector_by_type('teams')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1, 'ConfigJson': '{}'}, 'test')
        heard, order = [], []
        def poll(*a, **k):
            order.append('fetched'); k['on_fetched'](2)
            order.append('drained'); self.add_later(s, tid); return 2
        with mock.patch.object(server, 'store', s), mock.patch.object(server, '_poll_reports', side_effect=poll):
            got = server._refresh_chat_context(task_id=tid, message_id=first, on_fetched=lambda n: heard.append((n, list(order))))
        self.assertEqual(heard, [(2, ['fetched'])], 'told once, with the count, before the drain')
        self.assertTrue(got['newer'])
        self.assertIn('sending it through triage again', server.RETRIAGE_STARTED)
        heard.clear()
        with mock.patch.object(server, 'store', s), mock.patch.object(server, '_poll_reports', side_effect=lambda *a, **k: 0):
            server._refresh_chat_context(task_id=tid, message_id=first, on_fetched=lambda n: heard.append(n))
        self.assertEqual(heard, [], 'nothing landed, nothing said')

    def test_chat_connectors_default_to_fast_polling(self):
        s = MemoryStore()
        cid = s.get_connector_by_type('teams')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1, 'ConfigJson': '{}'}, 'test')
        with mock.patch.object(server, 'store', s), mock.patch.object(server.time, 'time', return_value=100):
            server._QUICK_LAST.clear()
            self.assertEqual(server._quick_due(), ['teams'])
            server._QUICK_LAST['teams'] = 100
            self.assertEqual(server._quick_due(), [])



class ConcurrentSyncTests(unittest.TestCase):
    """PW-056: the owner's yes is on the pile they were SHOWN. A line that lands while the turn is in
    flight changes that pile, so the commit is refused and the client re-captures - the action never
    lands on a picture nobody saw."""
    def setUp(self): funnel.invalidate()

    def _reserved(self, s):
        from taskuary.funnel_selection import capture_selection
        from taskuary.processing_navigation import fields, reserve
        f = fields(s, capture_selection(s))          # the revision the client echoes is bound to the chat
        return reserve(s, selection_revision=f['selection_revision'], expected_next_key=f['expected_next_key'],
                       expected_next_members=f['expected_next_members'])

    def test_a_sync_between_the_capture_and_the_commit_makes_the_action_stale(self):
        from taskuary.processing_navigation import NavigationStale
        chat = ChatFreshnessTests()
        s, tid, _first, _rid = chat.thread()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            held = self._reserved(s)
            def landed(selected, guard, dock):
                chat.add_later(s, tid); funnel.invalidate()          # the poll lands a newer line mid-turn
                with guard(): return 'acted'
            with self.assertRaises(NavigationStale) as e: held.run(landed)
            self.assertIn('selection changed', e.exception.detail.get('reason') or '')   # the guard, not the door
            self.assertTrue(e.exception.detail.get('retryable'))
            quiet = self._reserved(s)
            def unchanged(selected, guard, dock):
                with guard(): return 'acted'
            self.assertEqual(quiet.run(unchanged), 'acted')          # nothing moved, the same shape commits

if __name__ == '__main__':
    unittest.main()
