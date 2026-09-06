"""Gmail/IMAP catch-up drains every pending UID and covers the whole gap (PW-007, PW-008).

Inbox and Sent polling took the 25 HIGHEST qualifying UIDs and moved the watermark to their
maximum, so the lower pending UIDs were skipped for good; and the date window sized from
`backfill_days` excluded mail received during a long absence even though its UID was above the
saved cursor. Now an established cursor asks for `UID cursor+1:*` - the full gap, no date - and
drains it oldest-first in bounded batches, moving the watermark as each batch lands; only the
FIRST import (no cursor) is limited by the date window. A transport failure stops the poll with
the watermark on the last message that made it in, so the rest is retried. An unreadable UID is
retained as an epoch-scoped hole while later messages still land, and the connector reports the
partial failure until that UID succeeds. A changed UIDVALIDITY makes the saved cursor and old
holes meaningless, so the mailbox is imported afresh under a distinct identity.
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
    def __init__(self, inbox: dict, sent: dict = None, validity: int = 7, abort_at: int = None,
                 bad=(), malformed=(), select_bad=(), search_bad=(), list_bad=False):
        self.boxes = {'INBOX': dict(inbox), **({'Sent': dict(sent)} if sent is not None else {})}
        self.validity, self.abort_at, self.bad, self.malformed = validity, abort_at, set(bad), set(malformed)
        self.select_bad, self.search_bad, self.list_bad = set(select_bad), set(search_bad), list_bad
        self.box, self.fetched, self.searches, self.readonly = 'INBOX', [], [], None
        self.sock = mock.Mock(getpeercert=mock.Mock(return_value=b'the mail host certificate'))

    def login(self, u, p): return 'OK', []
    def list(self):
        if self.list_bad: return 'NO', [b'synthetic LIST failure']
        rows = [br'(\HasNoChildren) "/" "INBOX"']
        if 'Sent' in self.boxes: rows.append(br'(\HasNoChildren \Sent) "/" "Sent"')
        return 'OK', rows
    def select(self, box, readonly=False):
        self.box, self.readonly = box.strip('"'), readonly
        if self.box in self.select_bad: return 'NO', [b'synthetic SELECT failure']
        return 'OK', [str(len(self.boxes[self.box])).encode()]
    def response(self, code):
        validity = self.validity.get(self.box) if isinstance(self.validity, dict) else self.validity
        return code, ([str(validity).encode()] if code == 'UIDVALIDITY' and validity is not None else [None])
    def uid(self, cmd, *a):
        msgs = self.boxes[self.box]
        if cmd == 'search':
            crit = a[1]; self.searches.append((self.box, crit))
            if self.box in self.search_bad: return 'NO', [b'synthetic SEARCH failure']
            if m := re.fullmatch(r'\(UID (\d+):\*\)', crit):
                hits = [u for u in msgs if u >= int(m.group(1))] or ([max(msgs)] if msgs else [])   # RFC 3501: n:* never comes back empty
            elif m := re.fullmatch(r'\(SINCE (\d{2}-[A-Za-z]{3}-\d{4})\)', crit):
                day = datetime.strptime(m.group(1), '%d-%b-%Y').date()
                hits = [u for u, (_raw, when) in msgs.items() if when.date() >= day]
            else: raise AssertionError(f'unexpected search {crit}')
            return 'OK', [' '.join(str(u) for u in sorted(hits)).encode()]
        if cmd == 'fetch':
            u = int(a[0]); self.fetched.append((self.box, u))
            if self.abort_at == u or self.abort_at == (self.box, u): raise imaplib.IMAP4.abort('socket error: EOF')
            if u in self.bad or (self.box, u) in self.bad: return 'NO', [None]
            if u in self.malformed or (self.box, u) in self.malformed: return 'OK', [b'not an RFC822 tuple']
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
        with self.assertRaises(imapmail.IMAPPartialFailure) as failed:
            poll(s, c, box)
        self.assertEqual(failed.exception.ingested, 29)
        self.assertEqual(cfg_of(s)['imap_uid'], 130)
        self.assertEqual(cfg_of(s)['imap_retry_uids']['uids'], [110])

        # FETCH NO is retryable, not a permanent omission. Later UIDs already landed; a healthy
        # poll fills exactly the durable hole without duplicating any of those 29 messages.
        healthy = FakeBox(mails(range(101, 131)))
        c = s.get_connector_by_type('gmail', with_secret=True)
        self.assertEqual(poll(s, c, healthy), 1)
        self.assertEqual([uid for _box, uid in healthy.fetched], [110])
        self.assertEqual(len(inbound(s)), 30)
        self.assertEqual(cfg_of(s)['imap_retry_uids']['uids'], [])


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

    def test_a_reused_uid_after_uidvalidity_reset_is_not_deduped_against_history(self):
        s, c = store_with({'imap_uid': 500, 'imap_uidvalidity': 7})
        old_mid = s.add_message({'ExternalId': 'imap:me@myco.example:1', 'Channel': 'email',
                                 'Subject': 'old epoch', 'BodyText': 'historical body',
                                 'Status': 'surfaced'})
        before = dict(s.get_message(old_mid))
        box = FakeBox(mails([1]), validity=8)
        self.assertEqual(poll(s, c, box), 1)
        rows = inbound(s)
        self.assertEqual(len(rows), 2)
        self.assertEqual(dict(s.get_message(old_mid)), before)
        self.assertRegex(rows[-1]['ExternalId'], r'^imap:[0-9a-f]{24}:v8:1$')

    def test_an_unchanged_established_epoch_keeps_the_legacy_external_id(self):
        s, c = store_with({'imap_uid': 100, 'imap_uidvalidity': 7})
        self.assertEqual(poll(s, c, FakeBox(mails([101]), validity=7)), 1)
        self.assertEqual(inbound(s)[0]['ExternalId'], 'imap:me@myco.example:101')

    def test_a_fresh_unknown_epoch_is_still_scoped_to_the_actual_mailbox(self):
        s, c = store_with({})
        box = FakeBox(mails([1]), validity=None)
        self.assertEqual(poll(s, c, box), 1)
        self.assertRegex(inbound(s)[0]['ExternalId'], r'^imap:[0-9a-f]{24}:vunknown:1$')
        self.assertNotEqual(imapmail._scope('a.example', 993, 'same@example.invalid', 'INBOX'),
                            imapmail._scope('b.example', 993, 'same@example.invalid', 'INBOX'))
        self.assertNotEqual(imapmail._scope('a.example', 993, 'same@example.invalid', 'INBOX'),
                            imapmail._scope('a.example', 994, 'same@example.invalid', 'INBOX'))
        self.assertNotEqual(imapmail._scope('a.example', 993, 'same@example.invalid', 'INBOX'),
                            imapmail._scope('a.example', 993, 'same@example.invalid', 'Sent'))

    def test_retry_holes_survive_unknown_to_known_validity_without_a_confirmed_reset(self):
        scope = imapmail._scope('imap.gmail.com', 993, 'me@myco.example', 'INBOX')
        retry = {'scope': scope, 'uidvalidity': None, 'identity': 'scoped-v1', 'uids': [5]}
        s, c = store_with({'imap_uid': 10, 'imap_uid_scope': scope,
                           'imap_uid_identity': 'scoped-v1', 'imap_retry_uids': retry})
        self.assertEqual(poll(s, c, FakeBox(mails([5]), validity=7)), 1)
        self.assertEqual(cfg_of(s)['imap_retry_uids']['uids'], [])
        self.assertRegex(inbound(s)[0]['ExternalId'], r'^imap:[0-9a-f]{24}:v7:5$')

    def test_an_empty_new_epoch_durably_resets_the_old_cursor(self):
        s, c = store_with({'imap_uid': 500, 'imap_uidvalidity': 7})
        self.assertEqual(poll(s, c, FakeBox({}, validity=8)), 0)
        reset = cfg_of(s)
        self.assertEqual((reset['imap_uidvalidity'], reset['imap_uid']), (8, 0))
        self.assertEqual(reset['imap_retry_uids']['uids'], [])
        c = s.get_connector_by_type('gmail', with_secret=True)
        self.assertEqual(poll(s, c, FakeBox(mails([1]), validity=8)), 1)

    def test_a_changed_mailbox_scope_resets_even_when_validity_number_matches(self):
        old_scope = imapmail._scope('imap.gmail.com', 993, 'me@myco.example', 'INBOX')
        s, c = store_with({'imap_host': 'new.mail.example', 'imap_uid': 500,
                           'imap_uidvalidity': 7, 'imap_uid_scope': old_scope,
                           'imap_uid_identity': 'scoped-v1',
                           'imap_retry_uids': {'scope': old_scope, 'uidvalidity': 7,
                                               'identity': 'scoped-v1', 'uids': [499]}})
        self.assertEqual(poll(s, c, FakeBox(mails([1]), validity=7)), 1)
        saved = cfg_of(s)
        self.assertEqual(saved['imap_uid'], 1)
        self.assertEqual(saved['imap_retry_uids']['uids'], [])
        self.assertNotEqual(saved['imap_uid_scope'], old_scope)


class SentTests(unittest.TestCase):
    def test_the_sent_folder_drains_its_whole_gap_too(self):
        s, c = store_with({'imap_uid': 10, 'imap_sent_uid': 200, 'imap_uidvalidity': 7})
        sent = mails(range(201, 261), when=lambda u: NOW - timedelta(days=10) + timedelta(hours=u - 200), frm='Me <me@myco.example>')
        box = FakeBox(mails(range(11, 12)), sent=sent)
        poll(s, c, box, backfill_days=1)
        self.assertEqual(len(s._rows("SELECT * FROM message WHERE Status='context'")), 60)
        self.assertEqual(cfg_of(s)['imap_sent_uid'], 260)
        self.assertIn(('Sent', '(UID 201:*)'), box.searches)

    def test_sent_empty_epoch_reset_is_atomic_and_later_reused_uid_arrives(self):
        cfg = {'imap_uid': 10, 'imap_uidvalidity': 7,
               'imap_sent_uid': 500, 'imap_sent_uidvalidity': 7}
        s, c = store_with(cfg)
        empty = FakeBox({}, sent={}, validity={'INBOX': 7, 'Sent': 8})
        self.assertEqual(poll(s, c, empty), 0)
        reset = cfg_of(s)
        self.assertEqual((reset['imap_sent_uidvalidity'], reset['imap_sent_uid']), (8, 0))
        self.assertEqual(reset['imap_sent_retry_uids']['uids'], [])
        c = s.get_connector_by_type('gmail', with_secret=True)
        sent = mails([1], frm='Me <me@myco.example>')
        self.assertEqual(poll(s, c, FakeBox({}, sent=sent, validity={'INBOX': 7, 'Sent': 8})), 1)
        row = s._one("SELECT * FROM message WHERE Status='context'")
        self.assertRegex(row['ExternalId'], r'^imap-sent:[0-9a-f]{24}:v8:1$')

    def test_sent_transport_failure_propagates_with_its_last_completed_cursor_and_resumes(self):
        cfg = {'imap_uid': 10, 'imap_uidvalidity': 7,
               'imap_sent_uid': 200, 'imap_sent_uidvalidity': 7}
        s, c = store_with(cfg)
        sent = mails(range(201, 231), frm='Me <me@myco.example>')
        broken = FakeBox({}, sent=sent, abort_at=('Sent', 215))
        with self.assertRaises(imaplib.IMAP4.abort): poll(s, c, broken)
        self.assertEqual(cfg_of(s)['imap_sent_uid'], 214)
        self.assertEqual(len(s._rows("SELECT * FROM message WHERE Status='context'")), 14)
        c = s.get_connector_by_type('gmail', with_secret=True)
        self.assertEqual(poll(s, c, FakeBox({}, sent=sent)), 16)
        self.assertEqual(cfg_of(s)['imap_sent_uid'], 230)

    def test_sent_fetch_hole_does_not_block_later_replies_and_retries_exactly_once(self):
        cfg = {'imap_uid': 10, 'imap_uidvalidity': 7,
               'imap_sent_uid': 200, 'imap_sent_uidvalidity': 7}
        s, c = store_with(cfg)
        sent = mails(range(201, 211), frm='Me <me@myco.example>')
        with self.assertRaises(imapmail.IMAPPartialFailure) as failed:
            poll(s, c, FakeBox({}, sent=sent, bad={('Sent', 203)}))
        self.assertEqual(failed.exception.ingested, 9)
        self.assertEqual(cfg_of(s)['imap_sent_uid'], 210)
        self.assertEqual(cfg_of(s)['imap_sent_retry_uids']['uids'], [203])
        c = s.get_connector_by_type('gmail', with_secret=True)
        healthy = FakeBox({}, sent=sent)
        self.assertEqual(poll(s, c, healthy), 1)
        self.assertEqual([uid for box, uid in healthy.fetched if box == 'Sent'], [203])
        self.assertEqual(len(s._rows("SELECT * FROM message WHERE Status='context'")), 10)


class FailureTests(unittest.TestCase):
    def test_malformed_fetch_is_a_durable_hole_while_later_mail_progresses(self):
        s, c = store_with({'imap_uid': 100, 'imap_uidvalidity': 7})
        with self.assertRaises(imapmail.IMAPPartialFailure) as failed:
            poll(s, c, FakeBox(mails(range(101, 111)), malformed={103}))
        self.assertEqual(failed.exception.ingested, 9)
        self.assertEqual(cfg_of(s)['imap_uid'], 110)
        self.assertEqual(cfg_of(s)['imap_retry_uids']['uids'], [103])

    def test_partial_fetch_failure_is_visible_on_the_connector_card(self):
        from taskuary import channels
        s, _c = store_with({'imap_uid': 100, 'imap_uidvalidity': 7})
        cid = s.get_connector_by_type('gmail')['ConnectorId']
        sid = s.save_source({'Channel': 'email', 'Address': 'me@myco.example',
                             'ConnectorId': cid, 'Active': 1}, 'fixture')
        box = FakeBox(mails(range(101, 106)), bad={103})
        with mock.patch.object(imapmail.imaplib, 'IMAP4_SSL', return_value=box):
            self.assertEqual(channels._poll_one(s, s.get_connector_by_type('gmail'),
                                                False, 0, None, False), 0)
        card = s.get_connector(cid)
        self.assertIn('uid 103 FETCH returned NO', card['LastError'])
        self.assertIsNone(s.get_source(sid)['LastPolledAt'])
        self.assertEqual(cfg_of(s)['imap_uid'], 105)
        self.assertEqual(len(inbound(s)), 4)

    def test_select_and_search_failures_do_not_masquerade_as_empty_mailboxes(self):
        for box in (FakeBox({}, select_bad={'INBOX'}), FakeBox({}, search_bad={'INBOX'})):
            with self.subTest(kind='select' if box.select_bad else 'search'):
                s, c = store_with({'imap_uid': 100, 'imap_uidvalidity': 7})
                with self.assertRaises(imapmail.IMAPCommandError): poll(s, c, box)
                self.assertEqual(cfg_of(s)['imap_uid'], 100)

    def test_sent_list_and_search_failures_propagate(self):
        cases = [('list', FakeBox({}, sent={}, list_bad=True)),
                 ('select', FakeBox({}, sent={}, select_bad={'Sent'})),
                 ('search', FakeBox({}, sent={}, search_bad={'Sent'}))]
        for kind, box in cases:
            with self.subTest(kind=kind):
                s, c = store_with({'imap_uid': 10, 'imap_uidvalidity': 7,
                                   'imap_sent_uid': 20, 'imap_sent_uidvalidity': 7})
                with self.assertRaises(imapmail.IMAPCommandError): poll(s, c, box)
                self.assertEqual(cfg_of(s)['imap_sent_uid'], 20)

    def test_ingest_failure_aborts_and_replays_instead_of_becoming_a_hole(self):
        s, c = store_with({'imap_uid': 100, 'imap_uidvalidity': 7})
        from taskuary import ingest
        real = ingest.ingest_message
        def fail_110(store, *, file_only, msg, llm):
            if msg['external_id'].endswith(':110'): raise OSError('synthetic database write failure')
            return real(store, file_only=file_only, msg=msg, llm=llm)
        with mock.patch.object(ingest, 'ingest_message', side_effect=fail_110):
            with self.assertRaisesRegex(OSError, 'database write failure'):
                poll(s, c, FakeBox(mails(range(101, 121))))
        self.assertEqual(cfg_of(s)['imap_uid'], 109)
        self.assertEqual(cfg_of(s)['imap_retry_uids']['uids'], [])
        c = s.get_connector_by_type('gmail', with_secret=True)
        self.assertEqual(poll(s, c, FakeBox(mails(range(101, 121)))), 11)
        self.assertEqual(len(inbound(s)), 20)

    def test_checkpoint_cas_rejects_a_mailbox_changed_during_fetch(self):
        s, c = store_with({'imap_uid': 100, 'imap_uidvalidity': 7, 'owner_note': 'keep'})
        from taskuary import ingest
        real = ingest.ingest_message
        changed = False
        def change_mailbox(store, *, file_only, msg, llm):
            nonlocal changed
            out = real(store, file_only=file_only, msg=msg, llm=llm)
            if not changed:
                changed = True
                current = cfg_of(store)
                store.set_connector_config(c['ConnectorId'], {**current, 'address': 'other@example.invalid'})
            return out
        with mock.patch.object(ingest, 'ingest_message', side_effect=change_mailbox):
            with self.assertRaisesRegex(RuntimeError, 'mailbox changed'):
                poll(s, c, FakeBox(mails(range(101, 126))))
        saved = cfg_of(s)
        self.assertEqual(saved['address'], 'other@example.invalid')
        self.assertEqual(saved['owner_note'], 'keep')
        self.assertEqual(saved['imap_uid'], 100)

    def test_checkpoint_cas_does_not_overwrite_an_owner_rewind_during_fetch(self):
        s, c = store_with({'imap_uid': 100, 'imap_uidvalidity': 7})
        from taskuary import ingest
        real = ingest.ingest_message
        changed = False
        def rewind(store, *, file_only, msg, llm):
            nonlocal changed
            out = real(store, file_only=file_only, msg=msg, llm=llm)
            if not changed:
                changed = True
                current = cfg_of(store)
                store.set_connector_config(c['ConnectorId'], {
                    **current, 'imap_uid': 0, 'imap_retry_uids': {'owner': 'reset'}})
            return out
        with mock.patch.object(ingest, 'ingest_message', side_effect=rewind):
            with self.assertRaisesRegex(RuntimeError, 'mailbox changed'):
                poll(s, c, FakeBox(mails(range(101, 126))))
        saved = cfg_of(s)
        self.assertEqual(saved['imap_uid'], 0)
        self.assertEqual(saved['imap_retry_uids'], {'owner': 'reset'})

    def test_checkpoint_merge_preserves_an_owner_edit_made_during_fetch(self):
        s, c = store_with({'imap_uid': 100, 'imap_uidvalidity': 7, 'owner_note': 'before'})
        from taskuary import ingest
        real = ingest.ingest_message
        changed = False
        def owner_edit(store, *, file_only, msg, llm):
            nonlocal changed
            out = real(store, file_only=file_only, msg=msg, llm=llm)
            if not changed:
                changed = True
                current = cfg_of(store)
                store.set_connector_config(c['ConnectorId'], {**current, 'owner_note': 'during'})
            return out
        with mock.patch.object(ingest, 'ingest_message', side_effect=owner_edit):
            self.assertEqual(poll(s, c, FakeBox(mails(range(101, 126)))), 25)
        saved = cfg_of(s)
        self.assertEqual(saved['owner_note'], 'during')
        self.assertEqual(saved['imap_uid'], 125)

    def test_checkpoint_write_failure_replays_landed_rows_without_duplicates(self):
        s, c = store_with({'imap_uid': 100, 'imap_uidvalidity': 7})
        real_patch = s.patch_connector_poll_state
        calls = 0
        def fail_progress(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2: raise OSError('synthetic checkpoint disk failure')
            return real_patch(*args, **kwargs)
        with mock.patch.object(s, 'patch_connector_poll_state', side_effect=fail_progress):
            with self.assertRaisesRegex(OSError, 'checkpoint disk failure'):
                poll(s, c, FakeBox(mails(range(101, 131))))
        self.assertEqual(cfg_of(s)['imap_uid'], 100)
        self.assertEqual(len(inbound(s)), 25)
        c = s.get_connector_by_type('gmail', with_secret=True)
        self.assertEqual(poll(s, c, FakeBox(mails(range(101, 131)))), 5)
        self.assertEqual(len(inbound(s)), 30)


if __name__ == '__main__':
    unittest.main()
