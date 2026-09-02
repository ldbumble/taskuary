"""Any-provider mail: IMAP in, SMTP out - the protocol layer mocked, Taskuary's half tested:
UID watermarks that never re-ingest, bodies and attachments parsed off real MIME, replies
threaded and sent from the arriving address, and the outlook poller keeping its hands off
sources that belong to an IMAP connector.
"""
import email.message, hashlib, json, ssl, unittest
from unittest import mock
from taskuary import imapmail, outbound
from taskuary.store import MemoryStore


def _mime(frm='Rita Vole <rita@partner.example>', subj='the export is broken', body='it writes empty files\n', png=False):
    m = email.message.EmailMessage()
    m['From'], m['To'], m['Subject'] = frm, 'me@myco.example', subj
    m['Date'] = 'Wed, 20 Aug 2026 15:03:00 -0400'
    m['Message-ID'] = '<abc123@partner.example>'
    m.set_content(body)
    if png:
        m.add_attachment(b'\x89PNG\r\n\x1a\n' + b'x' * 40, maintype='image', subtype='png', filename='shot.png')
    return m.as_bytes()


class FakeImap:
    def __init__(self, msgs):
        self.msgs, self.readonly, self.flagged = msgs, None, []
        # imaplib.IMAP4_SSL keeps the TLS socket here, and _login reads the certificate off it
        self.sock = mock.Mock(getpeercert=mock.Mock(return_value=b'the mail host certificate'))
    def login(self, u, p): return 'OK', []
    def select(self, box, readonly=False):
        self.readonly = readonly
        return 'OK', [str(len(self.msgs)).encode()]
    def uid(self, cmd, *a):
        if cmd == 'search': return 'OK', [' '.join(str(u) for u in sorted(self.msgs)).encode()]
        if cmd == 'fetch':
            u = int(a[0])
            return 'OK', [(f'{u} (RFC822)'.encode(), self.msgs[u])]
        if cmd == 'store':
            self.flagged.append((int(a[0]), a[1], a[2]))
            return 'OK', []
    def logout(self): return 'BYE', []


class ImapTests(unittest.TestCase):
    def _store(self, typ='gmail', cfg=None):
        s = MemoryStore()
        cid = s.get_connector_by_type(typ)['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'app-password', 'Active': 1,
                          'ConfigJson': json.dumps(cfg or {'address': 'me@myco.example'})}, 'o')
        return s, s.get_connector_by_type(typ, with_secret=True)

    def test_poll_parses_real_mime_keeps_the_uid_and_never_rereads(self):
        s, c = self._store()
        fake = FakeImap({101: _mime(), 102: _mime(subj='and the import too', body='same again\n')})
        with mock.patch.object(imapmail.imaplib, 'IMAP4_SSL', return_value=fake):
            n = imapmail.poll_imap(s, c, [], llm=None)
        self.assertEqual(n, 2)
        rows = s._rows("SELECT * FROM message WHERE Channel='email' ORDER BY MessageId")
        self.assertEqual(rows[0]['FromEmail'], 'rita@partner.example')
        self.assertEqual(rows[0]['FromName'], 'Rita Vole')
        self.assertIn('empty files', rows[0]['BodyText'])
        self.assertEqual(rows[0]['ConversationId'], '<abc123@partner.example>')   # what a reply threads on
        self.assertEqual(rows[0]['SentAt'][:10], '2026-08-20')
        c2 = s.get_connector_by_type('gmail', with_secret=True)
        self.assertEqual(json.loads(c2['ConfigJson'])['imap_uid'], 102)
        with mock.patch.object(imapmail.imaplib, 'IMAP4_SSL', return_value=fake):
            self.assertEqual(imapmail.poll_imap(s, c2, [], llm=None), 0)          # watermark holds

    def test_the_mailbox_is_left_untouched_unless_the_switch_is_on(self):
        s, c = self._store()
        fake = FakeImap({101: _mime()})
        with mock.patch.object(imapmail.imaplib, 'IMAP4_SSL', return_value=fake):
            imapmail.poll_imap(s, c, [], llm=None)
        self.assertTrue(fake.readonly)          # readonly is what stops RFC822 setting \Seen
        self.assertEqual(fake.flagged, [])

    def test_mark_read_flags_seen_on_what_it_took(self):
        s, c = self._store()
        s.set_setting('mark_read_enabled', '1', 'o')
        fake = FakeImap({101: _mime(), 102: _mime(frm='Me <me@myco.example>')})
        with mock.patch.object(imapmail.imaplib, 'IMAP4_SSL', return_value=fake):
            imapmail.poll_imap(s, c, [], llm=None)
        self.assertFalse(fake.readonly)         # the box has to be writable to flag anything
        self.assertEqual(fake.flagged, [(101, '+FLAGS', r'(\Seen)')])   # my own mail is skipped whole

    def test_a_refused_flag_never_costs_the_ingest(self):
        s, c = self._store()
        s.set_setting('mark_read_enabled', '1', 'o')
        fake = FakeImap({101: _mime()})
        fake.uid = lambda cmd, *a: (_ for _ in ()).throw(OSError('read-only mailbox'))             if cmd == 'store' else FakeImap.uid(fake, cmd, *a)
        with mock.patch.object(imapmail.imaplib, 'IMAP4_SSL', return_value=fake):
            self.assertEqual(imapmail.poll_imap(s, c, [], llm=None), 1)
        self.assertEqual(len(s._rows("SELECT * FROM message WHERE Channel='email'")), 1)

    def test_my_own_mail_is_never_inbound_work(self):
        s, c = self._store()
        fake = FakeImap({7: _mime(frm='Me <me@myco.example>')})
        with mock.patch.object(imapmail.imaplib, 'IMAP4_SSL', return_value=fake):
            self.assertEqual(imapmail.poll_imap(s, c, [], llm=None), 0)

    def test_attachments_ride_the_one_pipeline(self):
        s, c = self._store()
        fake = FakeImap({5: _mime(png=True)})
        with mock.patch.object(imapmail.imaplib, 'IMAP4_SSL', return_value=fake):
            imapmail.poll_imap(s, c, [], llm=None)
        mid = s._rows("SELECT * FROM message")[0]['MessageId']
        atts = s.list_attachments(mid)
        self.assertEqual([a['ContentType'] for a in atts], ['image/png'])
        self.assertTrue(atts[0]['Path'])                        # the bytes landed on disk

    def test_replies_go_back_over_smtp_in_thread_from_the_same_address(self):
        s, _ = self._store()
        sent = {}
        class FakeSmtp:
            def __init__(self, host, port, timeout=None):
                sent['host'], sent['port'] = host, port
                self.sock = mock.Mock(getpeercert=mock.Mock(return_value=b'the mail host certificate'))
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def starttls(self, context=None): pass
            def login(self, u, p): sent['login'] = u
            def sendmail(self, frm, to, data): sent['from'], sent['to'], sent['data'] = frm, to, data
        msg = {'Channel': 'email', 'ExternalId': 'imap:me@myco.example:101', 'Subject': 'the export is broken',
               'FromEmail': 'rita@partner.example', 'SourceName': 'me@myco.example',
               'ConversationId': '<abc123@partner.example>'}
        with mock.patch.object(imapmail.smtplib, 'SMTP', FakeSmtp):
            out = outbound.reply_to_message(s, msg, 'Fixed - it exports again.')
        self.assertEqual(sent['host'], 'smtp.gmail.com')        # gmail's twin, derived
        self.assertEqual(sent['from'], 'me@myco.example')
        self.assertEqual(sent['to'], ['rita@partner.example'])
        self.assertIn('In-Reply-To: <abc123@partner.example>', sent['data'])
        self.assertTrue(out['threaded'])

    def test_the_graph_poller_keeps_its_hands_off_imap_sources(self):
        """Both are channel 'email' - without ownership the outlook branch tried to fetch the
        Gmail address from Graph and errored the card every poll."""
        s, c = self._store()
        src = [x for x in s.list_sources(active_only=False) if x['Channel'] == 'email']
        self.assertEqual(src, [])                               # only test_imap adds the source
        fake = FakeImap({})
        with mock.patch.object(imapmail.imaplib, 'IMAP4_SSL', return_value=fake):
            detail = imapmail.test_imap(s, c)
        self.assertIn('me@myco.example', detail)
        src = [x for x in s.list_sources() if x['Channel'] == 'email'][0]
        self.assertEqual(src['ConnectorId'], c['ConnectorId'])  # owned, so outlook skips it


class SourceOwnershipTests(unittest.TestCase):
    def test_orphaned_sources_adopt_their_legacy_owner_at_init(self):
        """Sources written before ownership existed had no ConnectorId, so the new Gmail card
        claimed the Outlook mailboxes - same channel, nobody's sources. Init adopts each orphan
        to the channel's legacy owner; reports keep their own rules."""
        import tempfile, os
        path = os.path.join(tempfile.mkdtemp(), 't.db')
        from taskuary.store import SQLiteStore
        a = SQLiteStore(path)
        a._exec("INSERT INTO source (Channel, Address, Active) VALUES ('email', 'me@corp.example', 1)")
        a._exec("INSERT INTO source (Channel, Address, Active) VALUES ('report', 'Census', 1)")
        b = SQLiteStore(path)                                    # a second init runs the heal
        row = b._one("SELECT * FROM source WHERE Address='me@corp.example'")
        self.assertEqual(row['ConnectorId'], b.get_connector_by_type('outlook')['ConnectorId'])
        self.assertIsNone(b._one("SELECT * FROM source WHERE Address='Census'")['ConnectorId'])



class CertificateTests(unittest.TestCase):
    """Shared hosting: you connect to smtp.yourdomain.com and the certificate names the host's own
    server. Outlook lets you dismiss that; tls_accept is how the same mailbox says it here."""

    def _sock(self, der):
        return mock.Mock(getpeercert=mock.Mock(return_value=der))

    def test_the_default_is_still_strict(self):
        ctx = imapmail.ssl_ctx({})
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)

    def test_an_accepted_certificate_turns_the_name_check_off(self):
        for accept in ('any', 'a' * 64):
            ctx = imapmail.ssl_ctx({'tls_accept': accept})
            self.assertFalse(ctx.check_hostname, accept)
            self.assertEqual(ctx.verify_mode, ssl.CERT_NONE, accept)

    def test_a_pin_accepts_that_certificate_and_only_that_one(self):
        der = b'the certificate this mailbox was set up against'
        fp = hashlib.sha256(der).hexdigest()
        imapmail.verify_pin(self._sock(der), {'tls_accept': fp}, 'smtp.mine.example')
        imapmail.verify_pin(self._sock(der), {'tls_accept': f'{fp.upper()}'}, 'smtp.mine.example')
        # ...which is the half that "just turn verification off" throws away
        with self.assertRaisesRegex(RuntimeError, 'different certificate'):
            imapmail.verify_pin(self._sock(b'somebody else'), {'tls_accept': fp}, 'smtp.mine.example')

    def test_nothing_to_check_when_the_owner_asked_for_no_checking(self):
        imapmail.verify_pin(self._sock(b'whatever'), {'tls_accept': 'any'}, 'h')
        imapmail.verify_pin(self._sock(b'whatever'), {}, 'h')          # the context already verified

    def test_the_refusal_says_whose_certificate_it_is_and_what_to_do(self):
        err = ssl.SSLCertVerificationError("certificate is not valid for 'smtp.mine.example'")
        with mock.patch.object(imapmail, 'peer_cert', return_value=(['mail.bighost.net', '*.bighost.net'], 'ab' * 32)):
            msg = str(imapmail.tls_error(err, 'smtp.mine.example', 587, True))
        self.assertIn('mail.bighost.net', msg)          # whose it is, so the owner can judge it
        self.assertIn('sha256:' + 'ab' * 32, msg)       # the value to paste
        self.assertIn('tls_accept', msg)                # and where to paste it

    def test_the_send_path_uses_the_mailbox_context_and_checks_the_pin(self):
        der = b'shared host certificate'
        c = {'Type': 'imap', 'Secret': 'pw', 'ConfigJson': json.dumps(
            {'address': 'me@mine.example', 'imap_host': 'imap.mine.example', 'tls_accept': hashlib.sha256(der).hexdigest()})}
        S = mock.MagicMock()
        S.__enter__.return_value = S
        S.sock = self._sock(der)
        with mock.patch.object(imapmail.smtplib, 'SMTP', return_value=S):
            out = imapmail.send_smtp(MemoryStore(), c, ['them@partner.example'], 'hello', 'body')
        self.assertEqual(out['to'], ['them@partner.example'])
        self.assertFalse(S.starttls.call_args.kwargs['context'].check_hostname)   # accepted, so not by name
        S.login.assert_called_once(); S.sendmail.assert_called_once()

    def test_a_swapped_certificate_stops_the_send(self):
        c = {'Type': 'imap', 'Secret': 'pw', 'ConfigJson': json.dumps(
            {'address': 'me@mine.example', 'imap_host': 'imap.mine.example', 'tls_accept': 'cd' * 32})}
        S = mock.MagicMock()
        S.__enter__.return_value = S
        S.sock = self._sock(b'not the one that was accepted')
        with mock.patch.object(imapmail.smtplib, 'SMTP', return_value=S):
            with self.assertRaisesRegex(RuntimeError, 'different certificate'):
                imapmail.send_smtp(MemoryStore(), c, ['them@partner.example'], 'hello', 'body')
        S.sendmail.assert_not_called()

if __name__ == '__main__':
    unittest.main()
