"""One switch decides whether reading something HERE marks it read THERE. Off by default,
because a mailbox that empties its own bold rows because you connected it is a surprise;
on, the bold rows left over are exactly the ones the funnel never saw. Every marker is
best-effort and runs after the message is stored - a refused consent costs nothing.
"""
import json, unittest
from unittest import mock

from taskuary import channels
from taskuary.store import MemoryStore

MAIL = {'id': 'AAMk1', 'subject': 'the export is broken', 'isRead': False,
        'from': {'emailAddress': {'name': 'Rita Vole', 'address': 'rita@partner.example'}},
        'body': {'content': 'it writes empty files'}, 'conversationId': 'conv1',
        'receivedDateTime': '2026-08-20T19:03:00Z', 'webLink': 'https://outlook/1'}


def _outlook(s, read=None):
    cid = s.get_connector_by_type('outlook')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sec', 'Active': 1,
                      'ConfigJson': json.dumps({'tenant_id': 't', 'client_id': 'c'})}, 'o')
    s.save_source({'Channel': 'email', 'Address': 'me@myco.example', 'ConnectorId': cid, 'Active': 1}, 'o')
    if read is not None: s.set_setting('mark_read_enabled', read, 'o')
    return s


def _poll(s, inbox=(MAIL,)):
    """poll_channels with Graph mocked at the two doors it uses: the token and the fetch."""
    with mock.patch.object(channels, 'graph_token', return_value='tok'), \
         mock.patch.object(channels, '_mail_msgs', side_effect=lambda t, u, since, folder='inbox': list(inbox) if folder == 'inbox' else []), \
         mock.patch.object(channels, 'requests') as req:
        channels.poll_channels(s)
    return req


class MailTests(unittest.TestCase):
    def test_off_by_default_the_mailbox_is_never_written_to(self):
        req = _poll(_outlook(MemoryStore()))
        self.assertFalse(req.patch.called)

    def test_on_it_marks_what_it_took(self):
        req = _poll(_outlook(MemoryStore(), '1'))
        req.patch.assert_called_once()
        self.assertIn('AAMk1', req.patch.call_args[0][0])
        self.assertEqual(req.patch.call_args[1]['json'], {'isRead': True})

    def test_mail_already_read_is_left_alone(self):
        req = _poll(_outlook(MemoryStore(), '1'), inbox=({**MAIL, 'isRead': True},))
        self.assertFalse(req.patch.called)

    def test_a_refused_consent_costs_neither_this_mail_nor_the_next(self):
        """Mail.ReadWrite is a consent people forget to grant; a 403 per message must not
        take the ingest down with it, or one missing checkbox empties the whole funnel."""
        s = _outlook(MemoryStore(), '1')
        two = [MAIL, {**MAIL, 'id': 'AAMk2', 'subject': 'and the import too', 'conversationId': 'conv2'}]
        with mock.patch.object(channels, 'graph_token', return_value='tok'), \
             mock.patch.object(channels, '_mail_msgs', side_effect=lambda t, u, since, folder='inbox': list(two) if folder == 'inbox' else []), \
             mock.patch.object(channels.requests, 'patch', side_effect=RuntimeError('403 Mail.ReadWrite')) as pt:
            channels.poll_channels(s)
        self.assertEqual(pt.call_count, 2)                                   # tried each, gave up on neither
        self.assertEqual(len(s._rows("SELECT * FROM message WHERE Channel='email'")), 2)
        self.assertIsNone(s.get_connector_by_type('outlook')['LastError'])   # not the card's problem

    def test_the_real_marker_swallows_a_graph_refusal(self):
        with mock.patch.object(channels.requests, 'patch', side_effect=RuntimeError('403')):
            channels.mark_mail_read('tok', 'me@myco.example', 'AAMk1')          # no raise


class SlackTests(unittest.TestCase):
    def _armed(self, read=None):
        s = MemoryStore()
        cid = s.get_connector_by_type('slack')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'xoxb', 'Active': 1}, 'o')
        s.save_source({'Channel': 'slack', 'Address': 'C123', 'ConnectorId': cid, 'Active': 1}, 'o')
        if read is not None: s.set_setting('mark_read_enabled', read, 'o')
        return s

    def _hist(self):
        return {'messages': [{'ts': '1755700000.000200', 'text': 'newest', 'user': 'U2'},
                             {'ts': '1755690000.000100', 'text': 'older', 'user': 'U1'},
                             {'ts': '1755680000.000000', 'text': 'joined', 'user': 'U3', 'subtype': 'channel_join'}]}

    def test_the_read_cursor_moves_to_the_newest_line_taken(self):
        s = self._armed('1')
        calls = []
        def fake(tok, method, post=False, **p):
            calls.append((method, p))
            return self._hist() if method == 'conversations.history' else {'ok': True}
        with mock.patch.object(channels, '_slack', fake):
            channels.poll_channels(s)
        marks = [p for m, p in calls if m == 'conversations.mark']
        self.assertEqual(len(marks), 1)
        self.assertEqual(marks[0]['ts'], '1755700000.000200')   # newest REAL message, not the join

    def test_off_nothing_is_marked(self):
        s, calls = self._armed(), []
        def fake(tok, method, post=False, **p):
            calls.append(method)
            return self._hist() if method == 'conversations.history' else {'ok': True}
        with mock.patch.object(channels, '_slack', fake):
            channels.poll_channels(s)
        self.assertNotIn('conversations.mark', calls)


if __name__ == '__main__':
    unittest.main()
