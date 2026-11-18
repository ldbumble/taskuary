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
    """`read`: the card's own choice (filing.read_mode); None leaves it unset - the default."""
    cid = s.get_connector_by_type('outlook')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sec', 'Active': 1,
                      'ConfigJson': json.dumps({'tenant_id': 't', 'client_id': 'c', **({'mark_read': read} if read else {})})}, 'o')
    s.save_source({'Channel': 'email', 'Address': 'me@myco.example', 'ConnectorId': cid, 'Active': 1}, 'o')
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
        req = _poll(_outlook(MemoryStore(), 'taken'))
        req.patch.assert_called_once()
        self.assertIn('AAMk1', req.patch.call_args[0][0])
        self.assertEqual(req.patch.call_args[1]['json'], {'isRead': True})

    def test_mail_already_read_is_left_alone(self):
        req = _poll(_outlook(MemoryStore(), 'taken'), inbox=({**MAIL, 'isRead': True},))
        self.assertFalse(req.patch.called)

    def test_a_refused_consent_costs_neither_this_mail_nor_the_next(self):
        """Mail.ReadWrite is a consent people forget to grant; a 403 per message must not
        take the ingest down with it, or one missing checkbox empties the whole funnel."""
        s = _outlook(MemoryStore(), 'taken')
        two = [MAIL, {**MAIL, 'id': 'AAMk2', 'subject': 'and the import too', 'conversationId': 'conv2'}]
        with mock.patch.object(channels, 'graph_token', return_value='tok'), \
             mock.patch.object(channels, '_mail_msgs', side_effect=lambda t, u, since, folder='inbox': list(two) if folder == 'inbox' else []), \
             mock.patch.object(channels.requests, 'patch', side_effect=RuntimeError('403 Mail.ReadWrite')) as pt:
            channels.poll_channels(s)
        self.assertEqual(pt.call_count, 2)                                   # tried each, gave up on neither
        self.assertEqual(len(s._rows("SELECT * FROM message WHERE Channel='email'")), 2)
        self.assertIsNone(s.get_connector_by_type('outlook')['LastError'])   # not the card's problem

    def test_the_real_marker_says_a_refusal_and_its_caller_decides(self):
        """Ingest swallows it (above); the read-here write-back keeps it on the card (ReadHereTests)."""
        with mock.patch.object(channels.requests, 'patch', side_effect=RuntimeError('403')), self.assertRaises(RuntimeError):
            channels.mark_mail_read('tok', 'me@myco.example', 'AAMk1')


class SlackTests(unittest.TestCase):
    def _armed(self, read=None):
        s = MemoryStore()
        cid = s.get_connector_by_type('slack')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'xoxb', 'Active': 1, **({'ConfigJson': json.dumps({'mark_read': read})} if read else {})}, 'o')
        s.save_source({'Channel': 'slack', 'Address': 'C123', 'ConnectorId': cid, 'Active': 1}, 'o')
        return s

    def _hist(self):
        return {'messages': [{'ts': '1755700000.000200', 'text': 'newest', 'user': 'U2'},
                             {'ts': '1755690000.000100', 'text': 'older', 'user': 'U1'},
                             {'ts': '1755680000.000000', 'text': 'joined', 'user': 'U3', 'subtype': 'channel_join'}]}

    def test_the_read_cursor_moves_to_the_newest_line_taken(self):
        s = self._armed('taken')
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

    def test_one_channel_failing_does_not_skip_the_channels_after_it(self):
        s = MemoryStore()
        cid = s.get_connector_by_type('slack')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'xoxb', 'Active': 1}, 'o')
        bad = s.save_source({'Channel': 'slack', 'Address': 'C000', 'ConnectorId': cid, 'Active': 1}, 'o')
        good = s.save_source({'Channel': 'slack', 'Address': 'C123', 'ConnectorId': cid, 'Active': 1}, 'o')
        def fake(tok, method, post=False, **p):
            if method == 'conversations.history' and p.get('channel') == 'C000': raise RuntimeError('slack conversations.history: not_in_channel')
            return self._hist() if method == 'conversations.history' else {'ok': True}
        with mock.patch.object(channels, '_slack', fake):
            channels.poll_channels(s)
        self.assertEqual(len(s._rows("SELECT * FROM message WHERE Channel='slack'")), 2)
        self.assertIsNotNone(s.get_source(good)['LastPolledAt'])
        self.assertIsNone(s.get_source(bad)['LastPolledAt'], 'the failed channel keeps its watermark')
        self.assertIn('C000', s.get_connector(cid)['LastError'] or '')


class SlackFilesTests(unittest.TestCase):
    """A Slack line with a screenshot in it is subtype file_share, and a thread reply sent to the channel too is thread_broadcast: the
    poll dropped every line with a subtype, so both never arrived. Its picture is fetched for triage; one Slack refuses is said."""
    def test_a_picture_line_and_a_broadcast_reply_arrive_and_a_refused_picture_is_said(self):
        s = SlackTests._armed(self)
        hist = {'messages': [
            {'ts': '1755700003.0', 'user': 'U2', 'subtype': 'file_share', 'text': 'export is broken, see this',
             'files': [{'id': 'F1', 'name': 'shot.png', 'mimetype': 'image/png', 'url_private': 'https://files.slack.com/files-pri/T1-F1/shot.png'}]},
            {'ts': '1755700002.0', 'user': 'U3', 'subtype': 'thread_broadcast', 'text': 'fixed it on my side', 'thread_ts': '1755690000.0'},
            {'ts': '1755700001.0', 'user': 'U4', 'subtype': 'file_share', 'text': '',
             'files': [{'id': 'F2', 'name': 'b.png', 'mimetype': 'image/png', 'url_private': 'https://files.slack.com/files-pri/T1-F2/b.png'}]},
            {'ts': '1755700000.0', 'user': 'U5', 'subtype': 'channel_join', 'text': 'joined'}]}
        png = b'\x89PNG\r\n\x1a\nfake'
        def get(url, **kw):
            if 'F2' in url: return mock.Mock(content=b'<html>sign in</html>', headers={'Content-Type': 'text/html; charset=utf-8'}, raise_for_status=lambda: None)
            return mock.Mock(content=png, headers={'Content-Type': 'image/png'}, raise_for_status=lambda: None)
        fake = lambda tok, method, post=False, **p: hist if method == 'conversations.history' else {'ok': True}
        with mock.patch.object(channels, '_slack', fake), mock.patch.object(channels.requests, 'get', side_effect=get):
            channels.poll_channels(s)
        rows = {r['BodyText'].split('\n')[0]: r for r in s._rows("SELECT * FROM message WHERE Channel='slack'")}
        self.assertEqual(set(rows), {'export is broken, see this', 'fixed it on my side', '[A picture in this message could not be read - open the chat in Slack to see it.]'})
        atts = s.list_attachments(rows['export is broken, see this']['MessageId'])
        self.assertEqual([a['ContentType'] for a in atts], ['image/png'])


class ReadHereTests(unittest.TestCase):
    """A switch on each mail card (the owner, 2026-11-16): mail he reads HERE - the receipt Done, Next, All read and "shown in
    the chat" all write - is marked read in that card's own mailbox. Off by default; one read, one write-back."""
    def setUp(self):
        import tempfile
        from taskuary.store import SQLiteStore
        self.dir = tempfile.mkdtemp()
        self.s = SQLiteStore(f'{self.dir}/readhere.db')
        self.addCleanup(self.s.close)

    def _card(self, kind, cfg, on=True):
        s = self.s
        cid = s.get_connector_by_type(kind)['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'sec', 'Active': 1, 'ConfigJson': json.dumps({**cfg, **({'mark_read': 'read'} if on else {})})}, 'o')
        s.save_source({'Channel': 'email', 'Address': 'alex@northwind.example', 'ConnectorId': cid, 'Active': 1}, 'o')
        return cid

    def _mail(self, ext, subject='the export is broken'):
        s = self.s
        tid = s.create_task({'Title': subject, 'Kind': 'task', 'Status': 'open'}, 'triage')
        mid = s.add_message({'TaskId': tid, 'ExternalId': ext, 'Channel': 'email', 'Subject': subject, 'FromName': 'Erin Blake',
                             'FromEmail': 'erin@vendor.example', 'SourceName': 'alex@northwind.example', 'BodyText': 'it writes empty files',
                             'SentAt': '2026-11-16 09:00:00', 'Status': 'open'})
        return mid, tid

    def _armed(self, *mails):
        """The receipts live once processing reads are on; the switch's clock starts on the first sweep, before any read."""
        from taskuary import filing
        stamp = '2026-11-16 09:00:00'
        self.s.reconcile_processing_membership(fixed_now=stamp)
        self.s.activate_processing_reads(fixed_now=stamp, live_state=[])
        filing.mark_read_back(self.s)
        self.s._exec("UPDATE setting SET Value='read 2000-01-01 00:00:00' WHERE Name LIKE 'mark_read_since:%'")

    def _done(self, tid):
        self.s.reconcile_processing_membership()
        self.s.set_funnel_state(f'task:{tid}', 'done')

    def _graph(self, patch=None):
        from taskuary import filing
        with mock.patch.object(channels, 'graph_token', return_value='tok'), \
             mock.patch.object(channels.requests, 'patch', **({'side_effect': patch} if patch else {})) as pt:
            n = filing.mark_read_back(self.s)
        return pt, n

    def test_off_by_default_nothing_is_written_back(self):
        from taskuary import filing
        cid = self._card('outlook', {'tenant_id': 't', 'client_id': 'c'}, on=False)
        _mid, tid = self._mail('graph:AAMk1'); self._armed(); self._done(tid)
        pt, _n = self._graph()
        pt.assert_not_called()
        self.assertEqual(filing.read_mode(self.s.get_connector(cid)), '0')

    def test_outlook_patches_is_read_once_for_one_read(self):
        self._card('outlook', {'tenant_id': 't', 'client_id': 'c'})
        _mid, tid = self._mail('graph:AAMk1'); _other, _t2 = self._mail('graph:AAMk2', 'not opened yet')
        self._armed(); self._done(tid)
        pt, n = self._graph()
        self.assertEqual(n, 1)
        pt.assert_called_once()                                               # the unopened one is left bold
        self.assertTrue(pt.call_args[0][0].endswith('/users/alex@northwind.example/messages/AAMk1'))
        self.assertEqual(pt.call_args[1]['json'], {'isRead': True})
        self.s.set_funnel_state(f'task:{tid}', 'done')                        # read again: still one write-back
        pt, _n = self._graph()
        pt.assert_not_called()

    def test_imap_sets_seen_on_its_uid_in_the_inbox(self):
        from tests.test_filing import FakeImap
        from taskuary import filing
        self._card('gmail', {'address': 'alex@northwind.example'})
        _mid, tid = self._mail('imap:abc:v7:41'); self._armed(); self._done(tid)
        fake = FakeImap([('\\HasNoChildren', 'INBOX')]); fake.flags = []
        fake.uid = lambda cmd, *a: (fake.flags.append(a), ('OK', []))[1] if cmd == 'store' else ('NO', [])
        with mock.patch('taskuary.imapmail.imaplib.IMAP4_SSL', return_value=fake): self.assertEqual(filing.mark_read_back(self.s), 1)
        self.assertEqual(fake.flags, [('41', '+FLAGS', r'(\Seen)')])
        self.assertFalse(fake.readonly)

    def test_a_sign_in_without_mail_readwrite_says_so_on_the_card_and_calls_nothing(self):
        from taskuary import filing
        cid = self._card('outlook', {'auth': 'user', 'client_id': 'c', 'granted_scope': 'offline_access User.Read Mail.Read Mail.Send'})
        _mid, tid = self._mail('graph:AAMk1'); self._armed(); self._done(tid)
        pt, _n = self._graph()
        pt.assert_not_called()
        line = json.loads(self.s.get_connector(cid)['ConfigJson'])[filing.READ_PROBLEM]
        self.assertIn('sign in with Microsoft again', line)

    def test_a_403_keeps_the_line_and_the_mail_is_tried_again_once_allowed(self):
        import requests
        from taskuary import filing
        cid = self._card('outlook', {'tenant_id': 't', 'client_id': 'c'})
        _mid, tid = self._mail('graph:AAMk1'); self._armed(); self._done(tid)
        refused = requests.HTTPError('403 Client Error: Forbidden', response=mock.Mock(status_code=403))
        self._graph(refused)
        self.assertIn('Mail.ReadWrite', json.loads(self.s.get_connector(cid)['ConfigJson'])[filing.READ_PROBLEM])
        pt, n = self._graph()                                                 # the admin granted it: the same mail goes through
        self.assertEqual(n, 1); pt.assert_called_once()
        self.assertNotIn(filing.READ_PROBLEM, json.loads(self.s.get_connector(cid)['ConfigJson']))

    def test_reads_before_the_switch_went_on_are_left_alone(self):
        from taskuary import filing
        self._card('outlook', {'tenant_id': 't', 'client_id': 'c'})
        _mid, tid = self._mail('graph:AAMk1')
        stamp = '2026-11-16 09:00:00'
        self.s.reconcile_processing_membership(fixed_now=stamp); self.s.activate_processing_reads(fixed_now=stamp, live_state=[])
        self._done(tid)                                                        # read before the first sweep started the clock
        self.s._exec("UPDATE processing_read_receipt SET ReadAt='2000-01-02 00:00:00'")
        filing.mark_read_back(self.s)                                          # the clock starts now
        pt, _n = self._graph()
        pt.assert_not_called()


if __name__ == '__main__':
    unittest.main()
