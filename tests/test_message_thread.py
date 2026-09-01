"""A row that never became a task still has a history, and your own replies are in it.

Nine Timeline rows all reading "Teams chat with Mindy Gorelick", and opening any one of them
showed a single inbound line. The replies sent from Teams were not missing - channels.py ingests
the owner's own lines as `context` rows, and the assistant reads them when it writes the brief -
they were simply never asked for by the panel, which fetched the one message and wrapped it in a
list. The screen disagreed with what the assistant reasons from, and the screen was wrong.
"""
import unittest

from fastapi.testclient import TestClient

from taskuary import server

c = TestClient(server.app)
CONV = 'teams:19:test-thread-abc'


def _line(who, body, at, status='filed', ext=None):
    return server.store.add_message({
        'ExternalId': ext or f'thr:{who}:{at}', 'ConversationId': CONV, 'Channel': 'teams',
        'SourceName': 'me@ours.com', 'Subject': 'Teams chat with Mindy Gorelick',
        'FromName': who, 'FromEmail': f'{who.lower()}@x.example', 'SentAt': at,
        'BodyText': body, 'Status': status})


class TheWholeConversation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first = _line('Mindy', 'Did you send the document to Devora?', '2026-08-31 12:41:00')
        # the reply the owner typed in TEAMS, not here: ingested, but kept out of the feed
        cls.mine = _line('You', 'Sent it this morning.', '2026-08-31 12:44:00', status='context')
        cls.last = _line('Mindy', 'Ok, how does it work?', '2026-08-31 12:47:00')

    def test_it_returns_the_thread_not_the_one_line(self):
        d = c.get(f'/api/messages/{self.last}/thread').json()
        self.assertEqual(len(d['messages']), 3)
        self.assertEqual(d['conversationId'], CONV)

    def test_your_own_reply_is_in_it(self):
        """The whole point: a reply sent from OUTSIDE the app shows on the original row."""
        bodies = [m['BodyText'] for m in c.get(f'/api/messages/{self.first}/thread').json()['messages']]
        self.assertIn('Sent it this morning.', bodies)

    def test_it_reads_oldest_last(self):
        msgs = c.get(f'/api/messages/{self.first}/thread').json()['messages']
        self.assertEqual([m['FromName'] for m in msgs], ['Mindy', 'You', 'Mindy'])

    def test_any_row_on_the_thread_gives_the_same_history(self):
        a = [m['MessageId'] for m in c.get(f'/api/messages/{self.first}/thread').json()['messages']]
        b = [m['MessageId'] for m in c.get(f'/api/messages/{self.last}/thread').json()['messages']]
        self.assertEqual(a, b)

    def test_a_lone_message_still_answers_with_itself(self):
        mid = server.store.add_message({'ExternalId': 'thr:lone', 'ConversationId': 'teams:19:lonely',
                                        'Channel': 'teams', 'SourceName': 'me@ours.com',
                                        'Subject': 'one off', 'FromName': 'Sam', 'SentAt': '2026-08-31 09:00:00',
                                        'BodyText': 'just this', 'Status': 'filed'})
        self.assertEqual(len(c.get(f'/api/messages/{mid}/thread').json()['messages']), 1)

    def test_an_unknown_message_is_a_404(self):
        self.assertEqual(c.get('/api/messages/99999999/thread').status_code, 404)

    def test_context_rows_stay_out_of_the_feed(self):
        """They belong in a thread, not on the rail: they are not things that happened TO you."""
        feed = c.get('/api/feed?limit=200').json().get('data', [])
        self.assertNotIn(self.mine, [r['MessageId'] for r in feed])


if __name__ == '__main__':
    unittest.main()
