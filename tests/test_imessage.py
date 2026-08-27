"""Apple Messages, offline on every OS: a synthetic chat.db built per test (never a copy of
anyone's real one) and osascript mocked at the subprocess seam. What is tested is Taskuary's
half - the ROWID watermark that never re-reads, rows that are not messages staying out,
own messages riding along as context, replies going into the SAME chat with the text kept
out of the script source - plus the typedstream reader on blobs we encode ourselves."""
import json, os, sqlite3, subprocess, sys, tempfile, unittest
from unittest import mock
from taskuary import imessage, outbound
from taskuary.store import MemoryStore

DARWIN = {'platform': 'darwin', 'product_version': '15.5', 'major': 15, 'machine': 'arm64', 'support': 'supported'}
NS = 10 ** 9


def typedstream(text: str) -> bytes:
    """The shape of message.attributedBody, as far as the reader looks: streamtyped header,
    an NSString class record, the '+' marker, the length prefix, the utf-8 bytes, then the
    attribute run that must NOT leak into the body."""
    raw = text.encode()
    n = len(raw)
    ln = bytes([n]) if n < 0x81 else b'\x81' + n.to_bytes(2, 'little') if n < 0x10000 else b'\x82' + n.to_bytes(4, 'little')
    return (b'\x04\x0bstreamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84\x12NSAttributedString\x00\x84\x84\x08NSObject'
            b'\x00\x85\x92\x84\x84\x84\x08NSString\x01\x94\x84\x01+' + ln + raw
            + b'\x86\x84\x02iI\x01' + bytes([min(n, 255)]) + b'\x92\x84\x84\x84\x0cNSDictionary\x00\x94\x84\x01i\x01\x92\x84\x96\x96\x1d__kIMMessagePartAttributeName\x86')


class Fixture:
    """A chat.db with the real table names and the columns the connector reads."""
    def __init__(self, dirpath, optional=True):
        self.path = os.path.join(dirpath, 'chat db', 'chat.db')     # a space in the path, on purpose
        os.makedirs(os.path.dirname(self.path))
        self.cx = sqlite3.connect(self.path)
        opt_m = ', attributedBody BLOB, associated_message_type INTEGER DEFAULT 0, item_type INTEGER DEFAULT 0, date_edited INTEGER, date_retracted INTEGER, cache_has_attachments INTEGER DEFAULT 0, service TEXT' if optional else ''
        opt_c = ', display_name TEXT, chat_identifier TEXT, style INTEGER, service_name TEXT' if optional else ''
        self.cx.executescript(f'''
            CREATE TABLE message (ROWID INTEGER PRIMARY KEY, guid TEXT, text TEXT, date INTEGER, is_from_me INTEGER DEFAULT 0, handle_id INTEGER{opt_m});
            CREATE TABLE chat (ROWID INTEGER PRIMARY KEY, guid TEXT{opt_c});
            CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT);
            CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);''')
        self.optional = optional
        self.chat('iMessage;-;+15550001', '+15550001')

    def chat(self, guid, *handles, title=None, style=45):
        cols, vals = ['guid'], [guid]
        if self.optional:
            cols += ['display_name', 'chat_identifier', 'style']; vals += [title, guid.split(';')[-1], style]
        cid = self.cx.execute(f"INSERT INTO chat ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals).lastrowid
        for h in handles:
            if not self.cx.execute('SELECT ROWID FROM handle WHERE id=?', (h,)).fetchone():
                self.cx.execute('INSERT INTO handle (id) VALUES (?)', (h,))
        self.cx.commit()
        return cid

    def msg(self, text, chat='iMessage;-;+15550001', sender='+15550001', me=False, date=800_000_000 * NS,
            blob=None, assoc=0, item=0, retracted=None, attach=0):
        cid = self.cx.execute('SELECT ROWID FROM chat WHERE guid=?', (chat,)).fetchone()[0]
        hid = self.cx.execute('SELECT ROWID FROM handle WHERE id=?', (sender,)).fetchone()
        n = self.cx.execute('SELECT COUNT(*) FROM message').fetchone()[0] + 1
        cols = ['guid', 'text', 'date', 'is_from_me', 'handle_id']
        vals = [f'GUID-{n}', text, date, int(me), hid[0] if hid else None]
        if self.optional:
            cols += ['attributedBody', 'associated_message_type', 'item_type', 'date_retracted', 'cache_has_attachments', 'service']
            vals += [blob, assoc, item, retracted, attach, 'iMessage']
        rid = self.cx.execute(f"INSERT INTO message ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals).lastrowid
        self.cx.execute('INSERT INTO chat_message_join VALUES (?,?)', (cid, rid))
        self.cx.commit()
        return rid


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='imsg_')
        self.fx = Fixture(self.tmp)
        self.s = MemoryStore()
        cid = self.s.get_connector_by_type('imessage')['ConnectorId']
        self.s.save_connector({'ConnectorId': cid, 'Active': 1, 'ConfigJson': json.dumps({'db_path': self.fx.path})}, 'o')
        self.s.save_source({'Channel': 'imessage', 'Address': '*', 'ConnectorId': cid, 'Active': 1}, 'o')
        self.p = mock.patch.object(imessage, 'platform_support', return_value=DARWIN)
        self.p.start(); self.addCleanup(self.p.stop)

    def conn(self): return self.s.get_connector_by_type('imessage', with_secret=True)
    def cfg(self): return json.loads(self.conn()['ConfigJson'])
    def poll(self, llm=None): return imessage.poll(self.s, self.conn(), self.s.list_sources(), llm=llm)
    def rows(self): return self.s._rows("SELECT * FROM message WHERE Channel='imessage' ORDER BY MessageId")


class PollTests(Base):
    def test_first_sync_starts_at_the_newest_row_and_imports_nothing(self):
        self.fx.msg('old news'); self.fx.msg('older news')
        self.assertEqual(self.poll(), 0)
        self.assertEqual(self.cfg()['imessage_rowid'], 2)
        self.assertEqual(self.rows(), [])
        # from here on, new rows come in - and only once
        self.fx.msg('can you send the deck tomorrow?')
        self.assertEqual(self.poll(), 1)
        self.assertEqual(self.poll(), 0)
        r = self.rows()[0]
        self.assertEqual(r['ConversationId'], 'imessage:iMessage;-;+15550001')     # replies know the chat
        self.assertEqual(r['ExternalId'], 'imessage:GUID-3')
        self.assertEqual(r['FromName'], '+15550001')
        self.assertEqual(r['SentAt'], imessage.apple_date(800_000_000 * NS))
        self.assertEqual(self.cfg()['imessage_rowid'], 3)

    def test_lookback_reads_recent_history_on_first_sync(self):
        from datetime import datetime
        now = datetime.now().timestamp() - imessage.APPLE_EPOCH
        self.fx.msg('last month', date=int((now - 40 * 86400) * NS))
        self.fx.msg('yesterday', date=int((now - 86400) * NS))
        self.s.set_connector_config(self.conn()['ConnectorId'], {'db_path': self.fx.path, 'lookback_days': 7})
        self.assertEqual(self.poll(), 1)
        self.assertEqual(self.rows()[0]['BodyText'], 'yesterday')

    def test_rows_that_are_not_messages_stay_out(self):
        self.poll()
        self.fx.msg('', assoc=2000)                       # a tapback
        self.fx.msg('', assoc=3000)                       # its removal
        self.fx.msg('', item=2)                           # group rename / member event
        self.fx.msg('unsent', retracted=700 * NS)         # retracted
        self.fx.msg('')                                   # blank, no attachment
        self.fx.msg(None, attach=1)                       # attachment only: kept, labelled
        self.fx.msg('real one')
        self.assertEqual(self.poll(), 2)
        self.assertEqual([r['BodyText'] for r in self.rows()], ['(attachment - see Messages)', 'real one'])
        self.assertEqual(self.cfg()['imessage_rowid'], 7)  # the cursor walked past the skipped rows too

    def test_text_hidden_in_attributed_body_is_read(self):
        self.poll()
        self.fx.msg(None, blob=typedstream('coffee at 3? ☕'))
        self.assertEqual(self.poll(), 1)
        self.assertEqual(self.rows()[0]['BodyText'], 'coffee at 3? ☕')

    def test_own_messages_ride_along_as_context_not_work(self):
        self.poll()
        self.fx.msg('did you book the table?')
        self.assertEqual(self.poll(llm=lambda a, b: '{"intent": "task", "why": "t"}'), 1)
        task = next(s for s in self.s.snapshots() if 'imessage:iMessage;-;+15550001' in s['conversation_ids'])
        self.fx.msg('yes, 7pm, done', me=True)
        self.assertEqual(self.poll(), 1)
        own = self.rows()[1]
        self.assertEqual((own['Status'], own['FromName'], own['TaskId']), ('context', 'You', task['task_id']))
        self.assertEqual(len(self.s.snapshots()), 1)      # no second task for your own line
        # an own message in a chat with no task: nothing stored, exactly like Outlook sent items
        self.fx.chat('iMessage;-;+15550002', '+15550002')
        self.fx.msg('will do', chat='iMessage;-;+15550002', me=True)
        self.assertEqual(self.poll(), 0)
        self.assertEqual(len(self.rows()), 2)

    def test_group_chats_carry_their_name(self):
        self.poll()
        self.fx.chat('chat123', '+15550003', '+15550004', title='Weekend plans', style=43)
        self.fx.msg('who is bringing the cake', chat='chat123', sender='+15550004')
        self.poll()
        r = self.rows()[0]
        self.assertEqual((r['SourceName'], r['FromName']), ('Weekend plans', '+15550004'))

    def test_specific_sources_limit_which_chats_come_in(self):
        self.poll()
        self.fx.chat('iMessage;-;+15550009', '+15550009')
        cid = self.conn()['ConnectorId']
        self.s.save_source({'Channel': 'imessage', 'Address': 'iMessage;-;+15550009', 'ConnectorId': cid, 'Active': 1}, 'o')
        self.fx.msg('not this one')
        self.fx.msg('this one', chat='iMessage;-;+15550009', sender='+15550009')
        self.assertEqual(self.poll(), 1)
        self.assertEqual(self.rows()[0]['BodyText'], 'this one')

    def test_pages_through_a_backlog_and_moves_the_cursor_per_page(self):
        self.poll()
        for i in range(7): self.fx.msg(f'm{i}')
        with mock.patch.object(imessage, 'POLL_LIMIT', 3):
            self.assertEqual(self.poll(), 7)
        self.assertEqual(self.cfg()['imessage_rowid'], 7)

    def test_one_unreadable_row_does_not_wedge_the_channel(self):
        self.poll()
        self.fx.msg('fine'); self.fx.msg('boom'); self.fx.msg('also fine')
        real = imessage.normalize_row
        def flaky(row):
            if row['text'] == 'boom': raise ValueError('bad row')
            return real(row)
        with mock.patch.object(imessage, 'normalize_row', flaky):
            self.assertEqual(self.poll(), 2)
        self.assertEqual(self.cfg()['imessage_rowid'], 3)

    def test_a_store_failure_keeps_the_watermark_so_nothing_is_lost(self):
        self.poll()
        self.fx.msg('first'); self.fx.msg('second')
        with mock.patch('taskuary.ingest.ingest_message', side_effect=RuntimeError('db locked')):
            with self.assertRaises(RuntimeError): self.poll()
        self.assertEqual(self.cfg()['imessage_rowid'], 0)       # not advanced past the failure
        self.assertEqual(self.poll(), 2)                        # both arrive on the retry

    def test_switching_every_source_off_polls_nothing(self):
        self.poll()
        self.fx.msg('should not arrive')
        star = next(s for s in self.s.list_sources(active_only=False) if s['Channel'] == 'imessage')
        self.s.save_source({'SourceId': star['SourceId'], 'Active': 0}, 'o')
        self.assertEqual(self.poll(), 0)
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.cfg()['imessage_rowid'], 0)       # and nothing was skipped past
        self.s.save_source({'SourceId': star['SourceId'], 'Active': 1}, 'o')
        self.assertEqual(self.poll(), 1)

    def test_older_schema_without_optional_columns_still_polls(self):
        fx = Fixture(tempfile.mkdtemp(prefix='imsg_old_'), optional=False)
        self.s.set_connector_config(self.conn()['ConnectorId'], {'db_path': fx.path})
        self.poll()
        fx.msg('plain text era', date=700_000_000)        # seconds, not nanoseconds
        self.assertEqual(self.poll(), 1)
        self.assertEqual(self.rows()[0]['SentAt'], imessage.apple_date(700_000_000))


class TestProbeTests(Base):
    def test_test_reads_for_real_names_the_automation_step_and_leaves_the_cursor(self):
        self.fx.msg('hi')
        with mock.patch.object(imessage, 'host_process', return_value={'name': 'Terminal', 'recommendation': 'x'}):
            d = imessage.test(self.s, self.conn())
        self.assertIn('1 chats', d); self.assertIn('Terminal may control Messages', d)
        self.assertNotIn('imessage_rowid', self.cfg())
        self.assertTrue(any(s['Address'] == '*' for s in self.s.list_sources()))

    def test_not_a_mac(self):
        with mock.patch.object(imessage, 'platform_support', return_value={'platform': 'linux', 'support': 'unavailable', 'product_version': None}):
            with self.assertRaisesRegex(RuntimeError, 'needs a Mac'):
                imessage.test(self.s, self.conn())

    def test_no_access_says_full_disk_access_and_the_host(self):
        # sqlite refusing the open is what FDA denial looks like from Python
        with mock.patch.object(imessage, 'connect', side_effect=sqlite3.OperationalError('unable to open database file')), \
             mock.patch.dict(os.environ, {'__CFBundleIdentifier': 'com.googlecode.iterm2'}):
            with self.assertRaisesRegex(RuntimeError, 'Full Disk Access.*iTerm') as ctx:
                imessage.test(self.s, self.conn())
        self.assertIn('relaunch', str(ctx.exception))

    def test_bare_python_is_named_by_path(self):
        with mock.patch.dict(os.environ, {'__CFBundleIdentifier': ''}):
            h = imessage.host_process()
        self.assertIsNone(h['name']); self.assertIn(h['python'], h['recommendation'])

    def test_missing_baseline_column_is_a_clear_unsupported_schema(self):
        self.fx.cx.execute('ALTER TABLE handle RENAME TO handle_old'); self.fx.cx.commit()
        with self.assertRaisesRegex(RuntimeError, 'not one Taskuary understands.*handle.ROWID'):
            imessage.test(self.s, self.conn())

    def test_missing_database(self):
        self.s.set_connector_config(self.conn()['ConnectorId'], {'db_path': os.path.join(self.tmp, 'nope.db')})
        with self.assertRaisesRegex(RuntimeError, 'sign in to Messages.app'):
            imessage.test(self.s, self.conn())

    def test_version_tiers(self):
        self.p.stop()
        with mock.patch.object(sys, 'platform', 'darwin'):
            for ver, tier in (('13.6', 'supported'), ('27.0', 'supported'), ('28.0', 'experimental_future_version'),
                              ('12.7', 'best_effort'), ('11.2', 'unsupported')):
                with mock.patch('platform.mac_ver', return_value=(ver, ('', '', ''), '')):
                    self.assertEqual(imessage.platform_support()['support'], tier, ver)
        with mock.patch.object(sys, 'platform', 'win32'):
            self.assertEqual(imessage.platform_support()['support'], 'unavailable')
        self.p.start()


class ReaderTests(unittest.TestCase):
    def test_typedstream_lengths_and_junk(self):
        for text in ('hi', 'x' * 200, 'é' * 300, 'y' * 70000, 'emoji 🎉 and\nnewlines'):
            self.assertEqual(imessage.extract_attributed_text(typedstream(text)), text.strip())
        self.assertIsNone(imessage.extract_attributed_text(None))
        self.assertIsNone(imessage.extract_attributed_text(b'not a stream'))
        self.assertIsNone(imessage.extract_attributed_text(b'\x04\x0bstreamtyped no string here'))
        self.assertIsNone(imessage.extract_attributed_text(typedstream('ok')[:-40][:30]))   # truncated before the payload
        self.assertIsNone(imessage.extract_attributed_text(b'\x04\x0bstreamtyped' + b'x' * imessage.MAX_BLOB))
        # the attribute run after the string never becomes the body
        self.assertNotIn('kIMMessagePart', imessage.extract_attributed_text(typedstream('short')))
        # NSString without the string preamble is some other record, not the body
        self.assertIsNone(imessage.extract_attributed_text(b'\x04\x0bstreamtyped\x84NSString\x00\x00\x00\x00\x00\x05hello'))
        # a length that points at bytes which are not UTF-8 is not text
        bad = typedstream('abcd').replace(b'abcd', b'\xff\xfe\xfd\xfc')
        self.assertIsNone(imessage.extract_attributed_text(bad))

    def test_dates_by_magnitude(self):
        self.assertEqual(imessage.apple_date(700_000_000), imessage.apple_date(700_000_000 * NS))
        self.assertTrue(imessage.apple_date(0))

    def test_chunks_split_at_paragraphs(self):
        self.assertEqual(imessage.chunks('short'), ['short'])
        self.assertEqual(imessage.chunks(''), [])
        body = 'a' * 30 + '\n\n' + 'b' * 30 + '\n\n' + 'c' * 30
        self.assertEqual(imessage.chunks(body, 65), ['a' * 30 + '\n\n' + 'b' * 30, 'c' * 30])
        one = ('line\n' * 20).strip()
        self.assertTrue(all(len(c) <= 24 for c in imessage.chunks(one, 24)))
        self.assertEqual(''.join(imessage.chunks(one, 24)).replace('\n', ''), one.replace('\n', ''))


class SendTests(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(sys, 'platform', 'darwin'); self.p.start(); self.addCleanup(self.p.stop)
        self.s = MemoryStore()
        self.s.save_connector({'ConnectorId': self.s.get_connector_by_type('imessage')['ConnectorId'], 'Active': 1}, 'o')

    def test_a_switched_off_connection_does_not_send(self):
        self.s.save_connector({'ConnectorId': self.s.get_connector_by_type('imessage')['ConnectorId'], 'Active': 0}, 'o')
        with mock.patch.object(subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'is off'):
                imessage.send_text(self.s, 'chat1', 'hello')
        run.assert_not_called()

    def test_text_and_chat_are_argv_never_script_source(self):
        with mock.patch.object(subprocess, 'run', return_value=mock.Mock(returncode=0, stderr='')) as run:
            r = imessage.send_text(self.s, 'iMessage;-;+15550001', 'tell application "Finder" to quit')
        args, kw = run.call_args
        self.assertEqual(args[0], ['osascript', '-', 'tell application "Finder" to quit', 'iMessage;-;+15550001'])
        self.assertEqual(kw['input'], imessage.SEND_SCRIPT)
        self.assertNotIn('shell', kw); self.assertEqual(kw['timeout'], imessage.SEND_TIMEOUT)
        self.assertEqual(r, {'channel': 'imessage', 'chat': 'iMessage;-;+15550001', 'parts': 1})

    def test_automation_denied_is_explained(self):
        with mock.patch.object(subprocess, 'run', return_value=mock.Mock(returncode=1, stderr='execution error: Not authorized to send Apple events to Messages. (-1743)')):
            with self.assertRaisesRegex(RuntimeError, 'Automation'):
                imessage.send_text(self.s, 'chat1', 'hello')

    def test_long_reply_goes_in_parts_and_a_failure_reports_partial(self):
        body = ('p' * 3000 + '\n\n') * 3
        calls = []
        def run(argv, **kw):
            calls.append(argv[2])
            return mock.Mock(returncode=0 if len(calls) < 3 else 1, stderr='(-1728)')
        with mock.patch.object(subprocess, 'run', run):
            with self.assertRaisesRegex(RuntimeError, '2 of 3 parts were sent'):
                imessage.send_text(self.s, 'chat1', body)
        self.assertEqual(len(calls), 3)

    def test_timeout(self):
        with mock.patch.object(subprocess, 'run', side_effect=subprocess.TimeoutExpired('osascript', 15)):
            with self.assertRaisesRegex(RuntimeError, 'did not answer'):
                imessage.send_text(self.s, 'chat1', 'hello')

    def test_not_a_mac(self):
        self.p.stop()
        with mock.patch.object(sys, 'platform', 'linux'):
            with self.assertRaisesRegex(RuntimeError, 'needs a Mac'):
                imessage.send_text(self.s, 'chat1', 'hello')
        self.p.start()

    def test_reply_goes_back_into_the_same_chat(self):
        s = MemoryStore()
        msg = {'Channel': 'imessage', 'ExternalId': 'imessage:GUID-1', 'ConversationId': 'imessage:iMessage;-;+15550001'}
        with mock.patch.object(imessage, 'send_text', return_value={'ok': 1}) as send:
            outbound.reply_to_message(s, msg, 'on my way')
        send.assert_called_once_with(s, 'iMessage;-;+15550001', 'on my way')
        with mock.patch.object(imessage, 'send_text', return_value={'ok': 1}) as send:
            outbound.send_out(s, 'imessage', 'chat9', 'Report', 'body')
        send.assert_called_once_with(s, 'chat9', 'Report\n\nbody')
        self.assertTrue(outbound.can_reply(s, 'imessage'))


if __name__ == '__main__':
    unittest.main()


class OnboardingTests(Base):
    """PR 1b: the structured half of a setup failure - stable codes, the right pane, the host
    macOS will list - and the two fixed-URL Settings openers, on every OS."""
    def test_no_access_carries_code_pane_and_host(self):
        with mock.patch.object(imessage, 'connect', side_effect=sqlite3.OperationalError('unable to open database file')), \
             mock.patch.dict(os.environ, {'__CFBundleIdentifier': 'com.apple.Terminal'}):
            with self.assertRaises(imessage.SetupError) as ctx: imessage.test(self.s, self.conn())
        s = ctx.exception.setup
        self.assertEqual((s['code'], s['pane'], s['host_name'], s['restart_may_be_required']),
                         ('full_disk_access_required', 'full_disk_access', 'Terminal', True))
        self.assertIsNone(s['host_path'])                         # an app host: no path to drag in
        self.assertIn('Full Disk Access', s['breadcrumb'])

    def test_bare_python_host_carries_its_path(self):
        with mock.patch.object(imessage, 'connect', side_effect=sqlite3.OperationalError('unable to open database file')), \
             mock.patch.dict(os.environ, {'__CFBundleIdentifier': ''}):
            with self.assertRaises(imessage.SetupError) as ctx: imessage.test(self.s, self.conn())
        self.assertEqual(ctx.exception.setup['host_path'], os.path.realpath(sys.executable))

    def test_every_setup_failure_has_a_stable_code(self):
        from taskuary.channels import test_connector
        cid = self.conn()['ConnectorId']
        with mock.patch.object(imessage, 'platform_support', return_value={'platform': 'linux', 'support': 'unavailable', 'product_version': None}):
            self.assertEqual(test_connector(self.s, cid)['setup']['code'], 'macos_required')
        with mock.patch.object(imessage, 'platform_support', return_value={**DARWIN, 'product_version': '11.6', 'major': 11, 'support': 'unsupported'}):
            self.assertEqual(test_connector(self.s, cid)['setup']['code'], 'unsupported_macos_version')
        with mock.patch.object(imessage, 'connect', side_effect=sqlite3.OperationalError('database is locked')):
            self.assertEqual(test_connector(self.s, cid)['setup']['code'], 'messages_database_busy')
        self.s.set_connector_config(cid, {'db_path': os.path.join(self.tmp, 'nope.db')})
        self.assertEqual(test_connector(self.s, cid)['setup']['code'], 'messages_database_missing')
        # the plain contract every other card uses is untouched
        out = test_connector(self.s, cid)
        self.assertEqual(set(out), {'ok', 'ms', 'detail', 'setup'}); self.assertFalse(out['ok'])
        self.s.set_connector_config(cid, {'db_path': self.fx.path})
        self.assertNotIn('setup', test_connector(self.s, cid))     # success: no setup half

    def test_settings_urls_by_version_and_only_known_panes(self):
        self.assertIn('PrivacySecurity.extension?Privacy_AllFiles', imessage.settings_url('full_disk_access'))
        with mock.patch.object(imessage, 'platform_support', return_value={**DARWIN, 'major': 12}):
            self.assertIn('preference.security?Privacy_AllFiles', imessage.settings_url('full_disk_access'))
            self.assertIn('Privacy_Automation', imessage.settings_url('automation'))
        with self.assertRaises(ValueError): imessage.settings_url('anything_else')

    def test_open_settings_is_open_plus_a_fixed_url(self):
        with mock.patch.object(sys, 'platform', 'darwin'), mock.patch.object(subprocess, 'run') as run:
            r = imessage.open_settings('automation')
        self.assertEqual(run.call_args[0][0], ['open', imessage.SETTINGS_URLS[('automation', 'modern')]])
        self.assertNotIn('shell', run.call_args[1]); self.assertTrue(r['ok'])
        with mock.patch.object(sys, 'platform', 'linux'):
            with self.assertRaises(imessage.SetupError): imessage.open_settings('automation')

    def test_automation_probe_sends_nothing_and_maps_denial(self):
        with mock.patch.object(sys, 'platform', 'darwin'):
            with mock.patch.object(subprocess, 'run', return_value=mock.Mock(returncode=0, stdout='Messages\n', stderr='')) as run:
                self.assertTrue(imessage.automation_probe()['ok'])
            self.assertEqual(run.call_args[0][0], ['osascript', '-'])
            self.assertEqual(run.call_args[1]['input'], imessage.PROBE_SCRIPT)
            self.assertNotIn('send', imessage.PROBE_SCRIPT)
            with mock.patch.object(subprocess, 'run', return_value=mock.Mock(returncode=1, stdout='', stderr='(-1743)')):
                with self.assertRaises(imessage.SetupError) as ctx: imessage.automation_probe()
            self.assertEqual((ctx.exception.setup['code'], ctx.exception.setup['pane']), ('automation_denied', 'automation'))

    def test_a_denied_send_is_a_setup_error_too(self):
        s = MemoryStore()
        s.save_connector({'ConnectorId': s.get_connector_by_type('imessage')['ConnectorId'], 'Active': 1}, 'o')
        with mock.patch.object(sys, 'platform', 'darwin'), \
             mock.patch.object(subprocess, 'run', return_value=mock.Mock(returncode=1, stderr='(-1743)')):
            with self.assertRaises(imessage.SetupError) as ctx: imessage.send_text(s, 'chat1', 'hi')
        self.assertEqual(ctx.exception.setup['code'], 'automation_denied')


class ApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        self.c = TestClient(server.app)

    def test_open_settings_takes_an_enum_never_a_url(self):
        self.assertEqual(self.c.post('/api/platform/macos/open-settings', json={'pane': 'x-apple.systempreferences:evil'}).status_code, 422)
        with mock.patch.object(imessage, 'open_settings', return_value={'ok': True, 'pane': 'automation'}) as op:
            self.assertTrue(self.c.post('/api/platform/macos/open-settings', json={'pane': 'automation'}).json()['ok'])
        op.assert_called_once_with('automation')
        with mock.patch.object(sys, 'platform', 'linux'):
            r = self.c.post('/api/platform/macos/open-settings', json={'pane': 'automation'}).json()
        self.assertEqual((r['ok'], r['setup']['code']), (False, 'macos_required'))

    def test_probe_endpoint(self):
        self.assertEqual(self.c.post('/api/platform/macos/probe', json={'what': 'send_a_message'}).status_code, 422)
        with mock.patch.object(imessage, 'automation_probe', side_effect=imessage.SetupError('automation_denied', 'no', 'automation')):
            r = self.c.post('/api/platform/macos/probe', json={'what': 'messages_automation'}).json()
        self.assertEqual((r['ok'], r['setup']['pane']), (False, 'automation'))


class QuickPollTests(unittest.TestCase):
    """poll_seconds on a connector's config: that one is read on its own faster clock, the
    rest stay on poll_minutes."""
    def test_only_filters_poll_channels(self):
        from taskuary import channels
        s = MemoryStore()
        for t in ('imessage', 'telegram'):
            s.save_connector({'ConnectorId': s.get_connector_by_type(t)['ConnectorId'], 'Active': 1, 'Secret': 'x'}, 'o')
        seen = []
        with mock.patch.object(imessage, 'poll', side_effect=lambda *a, **k: seen.append('imessage') or 0), \
             mock.patch('taskuary.messengers.poll_telegram', side_effect=lambda *a, **k: seen.append('telegram') or 0):
            channels.poll_channels(s, only=['imessage'])
            self.assertEqual(seen, ['imessage'])
            channels.poll_channels(s)
        self.assertEqual(sorted(seen), ['imessage', 'imessage', 'telegram'])

    def test_quick_due_reads_poll_seconds_and_spaces_itself(self):
        from taskuary import server
        cid = server.store.get_connector_by_type('imessage')['ConnectorId']
        server.store.save_connector({'ConnectorId': cid, 'Active': 1, 'ConfigJson': json.dumps({'poll_seconds': 60})}, 'o')
        try:
            server._QUICK_LAST.clear()
            self.assertIn('imessage', server._quick_due())
            server._QUICK_LAST['imessage'] = __import__('time').time()
            self.assertNotIn('imessage', server._quick_due())
            server.store.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps({'poll_seconds': 'lots'})}, 'o')
            server._QUICK_LAST.clear()
            self.assertNotIn('imessage', server._quick_due())     # garbage = no fast clock
        finally:
            server.store.save_connector({'ConnectorId': cid, 'Active': 0, 'ConfigJson': '{}'}, 'o')
