"""Handled mail goes to Archive only when the owner chose it, only once it is handled here, and only for mail handled
after the choice. The mark-read setting's third answer (filing.py, 2026-10-25)."""
import json, unittest
from unittest import mock

from taskuary import channels, filing
from taskuary.store import MemoryStore


def _store(kind='outlook', cfg=None):
    s = MemoryStore()
    cid = s.get_connector_by_type(kind)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sec', 'Active': 1,
                      'ConfigJson': json.dumps(cfg or {'tenant_id': 't', 'client_id': 'c', 'address': 'alex@northwind.example'})}, 'o')
    s.save_source({'Channel': 'email', 'Address': 'alex@northwind.example', 'ConnectorId': cid, 'Active': 1}, 'o')
    return s


def _mail(s, ext, closed=False):
    tid = s.create_task({'Title': 'the export is broken'}, 'o')
    mid = s.add_message({'ExternalId': ext, 'Channel': 'email', 'Subject': 'the export is broken', 'TaskId': tid,
                         'FromEmail': 'erin@vendor.example', 'SourceName': 'alex@northwind.example'})
    if closed: s.update_task(tid, {'Status': 'done'}, 'o')
    return mid, tid


class FakeImap:
    def __init__(self, folders, validity=7):
        self.folders, self.validity, self.moved, self.readonly = folders, validity, [], None
        self.sock = mock.Mock(getpeercert=mock.Mock(return_value=b'cert'))
    def login(self, u, p): return 'OK', []
    def select(self, box, readonly=False): self.readonly = readonly; return 'OK', [b'1']
    def response(self, code): return 'OK', [str(self.validity).encode()]
    def list(self): return 'OK', [f'({f}) "/" "{n}"'.encode() for f, n in self.folders]
    def uid(self, cmd, *a):
        if cmd == 'MOVE': self.moved.append((a[0], a[1])); return 'OK', []
        return 'NO', []
    def logout(self): return 'BYE', []


class FilingTests(unittest.TestCase):
    def _arm(self, s):
        s.set_setting('mark_read_enabled', 'archive', 'o')
        s.set_setting(filing.SINCE, '2000-01-01 00:00:00', 'o')

    def test_archive_still_marks_read_as_mark_read_did(self):
        s = MemoryStore()
        for v, want in (('0', False), ('1', True), ('archive', True)):
            s.set_setting('mark_read_enabled', v, 'o')
            self.assertEqual(channels.wants_read(s), want, v)

    def test_leave_and_mark_read_never_move_anything(self):
        for v in ('0', '1'):
            s = _store(); s.set_setting('mark_read_enabled', v, 'o'); _mail(s, 'graph:AAMk1', closed=True)
            with mock.patch.object(filing, 'graph_archive') as mv: filing.file_handled(s)
            mv.assert_not_called()

    def test_first_sweep_only_starts_the_clock(self):
        """Choosing archive must not empty a year of closed work: what was handled before it is left alone."""
        s = _store(); s.set_setting('mark_read_enabled', 'archive', 'o'); _mail(s, 'graph:AAMk1', closed=True)
        with mock.patch.object(filing, 'graph_archive') as mv: self.assertEqual(filing.file_handled(s), 0)
        mv.assert_not_called()
        self.assertTrue(s.get_setting(filing.SINCE))

    def test_a_closed_task_moves_its_mail_once_and_open_work_stays(self):
        s = _store(); self._arm(s)
        done, _ = _mail(s, 'graph:AAMk1', closed=True)
        _mail(s, 'graph:AAMk2')
        with mock.patch.object(channels, 'graph_token', return_value='tok'), mock.patch.object(filing, 'graph_archive') as mv:
            self.assertEqual(filing.file_handled(s), 1)
            filing.file_handled(s)                                                   # a second poll moves nothing again
        mv.assert_called_once_with('tok', 'alex@northwind.example', 'AAMk1')
        self.assertEqual(s._one('SELECT Result FROM mail_filed WHERE MessageId=?', (done,))['Result'], 'archived')

    def test_an_fyi_put_down_with_no_task_stays_in_the_inbox(self):
        """Archive covers closed tasks only (the owner, 2026-10-25): reading an FYI here is not filing it in the mailbox."""
        s = _store(); self._arm(s)
        mid = s.add_message({'ExternalId': 'graph:AAMk3', 'Channel': 'email', 'Subject': 'fyi: the office is closed Friday',
                             'SourceName': 'alex@northwind.example'})
        s._exec("INSERT INTO funnel_state (Key, Status, By, At) VALUES (?, 'done', 'owner', '2026-10-25 09:00:00')", (f'msg:{mid}',))
        done, _ = _mail(s, 'graph:AAMk4', closed=True)
        self.assertEqual([r['MessageId'] for r in filing.handled(s, '2000-01-01 00:00:00')], [done])

    def test_a_refused_move_is_written_down_and_not_retried_every_poll(self):
        s = _store(); self._arm(s); mid, _ = _mail(s, 'graph:AAMk1', closed=True)
        with mock.patch.object(channels, 'graph_token', return_value='tok'), \
             mock.patch.object(filing, 'graph_archive', side_effect=RuntimeError('403 Mail.ReadWrite')) as mv:
            filing.file_handled(s); filing.file_handled(s)
        self.assertEqual(mv.call_count, 1)
        self.assertIn('403', s._one('SELECT Result FROM mail_filed WHERE MessageId=?', (mid,))['Result'])

    def test_a_poll_never_fails_on_filing(self):
        s = _store(); self._arm(s)
        with mock.patch.object(filing, 'file_handled', side_effect=RuntimeError('boom')):
            self.assertEqual(channels._file_after(s, 3), 3)

    def test_imap_moves_to_the_special_use_archive(self):
        s = _store('imap', {'address': 'alex@northwind.example', 'imap_host': 'imap.northwind.example'}); self._arm(s)
        _mail(s, 'imap:abc:v7:41', closed=True)
        fake = FakeImap([('\\HasNoChildren', 'INBOX'), ('\\Archive', 'Old mail')])
        with mock.patch('taskuary.imapmail.imaplib.IMAP4_SSL', return_value=fake): filing.file_handled(s)
        self.assertEqual(fake.moved, [('41', '"Old mail"')])
        self.assertFalse(fake.readonly)

    def test_gmail_archive_is_all_mail(self):
        s = _store('gmail', {'address': 'alex@northwind.example'}); self._arm(s)
        _mail(s, 'imap:abc:v7:5', closed=True)
        fake = FakeImap([('\\HasNoChildren', 'INBOX'), ('\\All \\HasNoChildren', '[Gmail]/All Mail')])
        with mock.patch('taskuary.imapmail.imaplib.IMAP4_SSL', return_value=fake): filing.file_handled(s)
        self.assertEqual(fake.moved, [('5', '"[Gmail]/All Mail"')])

    def test_no_archive_folder_leaves_the_mail_and_a_renumbered_box_is_not_guessed(self):
        s = _store('imap', {'address': 'alex@northwind.example', 'imap_host': 'imap.northwind.example'}); self._arm(s)
        a, _ = _mail(s, 'imap:abc:v7:41', closed=True)
        fake = FakeImap([('\\HasNoChildren', 'INBOX')])
        with mock.patch('taskuary.imapmail.imaplib.IMAP4_SSL', return_value=fake): filing.file_handled(s)
        self.assertEqual(fake.moved, [])
        self.assertIn('no Archive', s._one('SELECT Result FROM mail_filed WHERE MessageId=?', (a,))['Result'])
        b, _ = _mail(s, 'imap:abc:v6:42', closed=True)
        fake = FakeImap([('\\Archive', 'Archive')])
        with mock.patch('taskuary.imapmail.imaplib.IMAP4_SSL', return_value=fake): filing.file_handled(s)
        self.assertEqual(fake.moved, [])                                           # UIDVALIDITY 6 is not today's 7
        self.assertIn('renumbered', s._one('SELECT Result FROM mail_filed WHERE MessageId=?', (b,))['Result'])

    def test_turning_it_off_restarts_the_clock(self):
        s = _store(); self._arm(s)
        s.set_setting('mark_read_enabled', '1', 'o'); filing.file_handled(s)
        self.assertFalse(s.get_setting(filing.SINCE))


if __name__ == '__main__': unittest.main()
