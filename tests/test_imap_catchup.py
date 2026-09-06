"""Gmail/IMAP catch-up drains every pending UID and covers the whole gap (PW-007, PW-008).

Inbox and Sent polling took the 25 HIGHEST qualifying UIDs and moved the watermark to their
maximum, so the lower pending UIDs were skipped for good; and the date window sized from
`backfill_days` excluded mail received during a long absence even though its UID was above the
saved cursor. Now an established cursor asks for `UID cursor+1:*` - the full gap, no date - and
drains it oldest-first in bounded batches, moving the watermark as each batch lands; only the
FIRST import (no cursor) is limited by the date window. A transport failure stops the poll with
the watermark on the last message that made it in, so the rest is retried; one unreadable
message is stepped over as before. A changed UIDVALIDITY makes the saved cursor meaningless,
so the mailbox is imported afresh instead of silently missing everything.
"""
import email.message, imaplib, json, re, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import imapmail
from taskuary.store import MemoryStore

NOW = datetime.now().astimezone()


def mime(uid: int, when: datetime, frm='Rita Vole <rita@partner.example>') -> bytes:
    m = email.message.EmailMessage()
    m['From'], m['To'], m['Subject'] = frm, 'me@myco.example', f'mail {uid}'
    m['Date'] = email.utils.format_datetime(when)
    m['Message-ID'] = f'<{uid}@partner.example>'
    m.set_content(f'body {uid}\n')
    return m.as_bytes()


def mails(uids, when=lambda u: NOW - timedelta(minutes=5), frm=None) -> dict:
    return {u: (mime(u, when(u), **({'frm': frm} if frm else {})), when(u)) for u in uids}


class FakeBox:
    """Enough imaplib to catch up against: LIST, SELECT, UIDVALIDITY, UID SEARCH with real
    criteria (SINCE date, UID range), UID FETCH - plus a transport failure and unreadable UIDs."""
    def __init__(self, inbox: dict, sent: dict = None, validity: int = 7, abort_at: int = None, bad=()):
        self.boxes = {'INBOX': dict(inbox), **({'Sent': dict(sent)} if sent is not None else {})}
        self.validity, self.abort_at, self.bad = validity, abort_at, set(bad)
        self.box, self.fetched, self.searches, self.readonly = 'INBOX', [], [], None
        self.sock = mock.Mock(getpeercert=mock.Mock(return_value=b'the mail host certificate'))

    def login(self, u, p): return 'OK', []
    def list(self):
        rows = [br'(\HasNoChildren) "/" "INBOX"']
        if 'Sent' in self.boxes: rows.append(br'(\HasNoChildren \Sent) "/" "Sent"')
        return 'OK', rows
    def select(self, box, readonly=False):
        self.box, self.readonly = box.strip('"'), readonly
        return 'OK', [str(len(self.boxes[self.box])).encode()]
    def response(self, code):
        return code, ([str(self.validity).encode()] if code == 'UIDVALIDITY' else [None])
    def uid(self, cmd, *a):
        msgs = self.boxes[self.box]
        if cmd == 'search':
            crit = a[1]; self.searches.append((self.box, crit))
            if m := re.fullmatch(r'\(UID (\d+):\*\)', crit):
                hits = [u for u in msgs if u >= int(m.group(1))] or ([max(msgs)] if msgs else [])   # RFC 3501: n:* never comes back empty
            elif m := re.fullmatch(r'\(SINCE (\d{2}-[A-Za-z]{3}-\d{4})\)', crit):
                day = datetime.strptime(m.group(1), '%d-%b-%Y').date()
                hits = [u for u, (_raw, when) in msgs.items() if when.date() >= day]
            else: raise AssertionError(f'unexpected search {crit}')
            return 'OK', [' '.join(str(u) for u in sorted(hits)).encode()]
        if cmd == 'fetch':
            u = int(a[0]); self.fetched.append((self.box, u))
            if self.abort_at == u: raise imaplib.IMAP4.abort('socket error: EOF')
            if u in self.bad: return 'NO', [None]
            return 'OK', [(f'{u} (RFC822)'.encode(), msgs[u][0])]
        if cmd == 'store': return 'OK', []
        raise AssertionError(cmd)
    def logout(self): return 'BYE', []


def store_with(cfg: dict):
    s = MemoryStore()
    cid = s.get_connector_by_type('gmail')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'app-password', 'Active': 1,
                      'ConfigJson': json.dumps({'address': 'me@myco.example', **cfg})}, 'o')
    return s, s.get_connector_by_type('gmail', with_secret=True)


def cfg_of(s): return json.loads(s.get_connector_by_type('gmail')['ConfigJson'])


def inbound(s): return s._rows("SELECT * FROM message WHERE Channel='email' AND Status!='context' ORDER BY MessageId")


def poll(s, c, box, backfill_days=0):
    with mock.patch.object(imapmail.imaplib, 'IMAP4_SSL', return_value=box):
        return imapmail.poll_imap(s, c, [], llm=None, backfill_days=backfill_days)


class DrainTests(unittest.TestCase):
    def test_every_pending_uid_is_read_oldest_first_not_only_the_top_twenty_five(self):
        s, c = store_with({'imap_uid': 100, 'imap_uidvalidity': 7})
        box = FakeBox(mails(range(101, 181)))
        self.assertEqual(poll(s, c, box), 80)
        self.assertEqual([u for _b, u in box.fetched], list(range(101, 181)))
        self.assertEqual(cfg_of(s)['imap_uid'], 180)

    def test_a_transport_failure_keeps_the_watermark_on_the_last_mail_that_landed(self):
        s, c = store_with({'imap_uid': 100, 'imap_uidvalidity': 7})
        broken = FakeBox(mails(range(101, 181)), abort_at=140)
        with self.assertRaises(imaplib.IMAP4.abort): poll(s, c, broken)
        self.assertEqual(len(inbound(s)), 39)
        self.assertEqual(cfg_of(s)['imap_uid'], 139)
        healthy = FakeBox(mails(range(101, 181)))
        c = s.get_connector_by_type('gmail', with_secret=True)     # the poller re-reads the card each poll
        self.assertEqual(poll(s, c, healthy), 41)
        self.assertEqual([u for _b, u in healthy.fetched], list(range(140, 181)))
        self.assertEqual(len(inbound(s)), 80)
        self.assertEqual(cfg_of(s)['imap_uid'], 180)

    def test_one_unreadable_message_is_stepped_over_and_the_rest_still_arrive(self):
        s, c = store_with({'imap_uid': 100, 'imap_uidvalidity': 7})
        box = FakeBox(mails(range(101, 131)), bad={110})
        self.assertEqual(poll(s, c, box), 29)
        self.assertEqual(cfg_of(s)['imap_uid'], 130)


class GapTests(unittest.TestCase):
    def test_an_established_cursor_asks_for_the_whole_gap_not_a_date_window(self):
        """PW-008: closed for two weeks, startup catch-up is capped at 3 days - the mail from days 4-14 must still come."""
        s, c = store_with({'imap_uid': 100, 'imap_uidvalidity': 7})
        box = FakeBox(mails(range(101, 141), when=lambda u: NOW - timedelta(days=14) + timedelta(hours=u - 100)))
        self.assertEqual(poll(s, c, box, backfill_days=3), 40)
        self.assertEqual(box.searches[0], ('INBOX', '(UID 101:*)'))

    def test_the_first_import_is_still_bounded_by_the_date_window(self):
        s, c = store_with({})
        old, new = mails(range(1, 51), when=lambda u: NOW - timedelta(days=30)), mails(range(51, 61), when=lambda u: NOW - timedelta(hours=2))
        box = FakeBox({**old, **new})
        self.assertEqual(poll(s, c, box, backfill_days=3), 10)
        self.assertTrue(box.searches[0][1].startswith('(SINCE '), box.searches)
        self.assertEqual(cfg_of(s)['imap_uid'], 60)
        self.assertEqual(cfg_of(s)['imap_uidvalidity'], 7)

    def test_a_changed_uidvalidity_makes_the_saved_cursor_meaningless(self):
        s, c = store_with({'imap_uid': 500, 'imap_uidvalidity': 7})
        box = FakeBox(mails(range(1, 6)), validity=8)            # the server renumbered: five recent mails, all below 500
        self.assertEqual(poll(s, c, box), 5)
        self.assertEqual(cfg_of(s)['imap_uidvalidity'], 8)
        self.assertEqual(cfg_of(s)['imap_uid'], 5)

    def test_a_server_that_does_not_report_validity_keeps_the_cursor(self):
        s, c = store_with({'imap_uid': 100})
        box = FakeBox(mails(range(101, 104)))
        box.response = lambda code: (code, [None])
        self.assertEqual(poll(s, c, box), 3)
        self.assertEqual(cfg_of(s)['imap_uid'], 103)


class SentTests(unittest.TestCase):
    def test_the_sent_folder_drains_its_whole_gap_too(self):
        s, c = store_with({'imap_uid': 10, 'imap_sent_uid': 200, 'imap_uidvalidity': 7})
        sent = mails(range(201, 261), when=lambda u: NOW - timedelta(days=10) + timedelta(hours=u - 200), frm='Me <me@myco.example>')
        box = FakeBox(mails(range(11, 12)), sent=sent)
        poll(s, c, box, backfill_days=1)
        self.assertEqual(len(s._rows("SELECT * FROM message WHERE Status='context'")), 60)
        self.assertEqual(cfg_of(s)['imap_sent_uid'], 260)
        self.assertIn(('Sent', '(UID 201:*)'), box.searches)


if __name__ == '__main__':
    unittest.main()
