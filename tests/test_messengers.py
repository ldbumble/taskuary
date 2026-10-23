"""Telegram and WhatsApp: both offline - the Telegram API and the Baileys bridge are mocked at
the HTTP seam, so what is tested is Taskuary's half: watermarks that never re-ingest, chat
replies that go back into the SAME chat, and the owner-name flow the docs hang off."""
import base64, json, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import messengers, outbound, server
from taskuary.store import MemoryStore, retoken_doc

c_api = TestClient(server.app)

PNG = base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'x' * 20).decode()


def _tg_update(uid, cid=777, mid=1, text='fix the importer', first='Rita', photo=False):
    m = {'message_id': mid, 'date': 1755700000, 'chat': {'id': cid, 'type': 'private'},
         'from': {'first_name': first, 'username': 'rita', 'is_bot': False}}
    if text: m['text'] = text
    if photo: m['photo'] = [{'file_id': 'small'}, {'file_id': 'big'}]
    return {'update_id': uid, 'message': m}


class TelegramTests(unittest.TestCase):
    def _store(self):
        s = MemoryStore()
        # the row is seeded at init (like every connector) - a test configures it, not creates it.
        # Chat 777 (the fixtures' chat) is switched ON: only approved chat ids ingest now -
        # the '*' row is a listening marker, never a catch-all (test_pm covers the lockdown).
        cid = s.get_connector_by_type('telegram')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'TOKEN', 'Active': 1}, 'o')
        s.save_source({'Channel': 'telegram', 'Address': '*', 'ConnectorId': cid, 'Active': 1}, 'o')
        s.save_source({'Channel': 'telegram', 'Address': '777', 'ConnectorId': cid, 'Active': 1}, 'o')
        return s, s.get_connector_by_type('telegram', with_secret=True)

    def test_poll_ingests_keeps_the_cursor_and_never_rereads(self):
        s, c = self._store()
        calls = {}
        def fake_tg(tok, method, **p):
            calls[method] = p
            if method == 'getUpdates': return [_tg_update(100), _tg_update(101, mid=2, text='and the export too')]
            raise AssertionError(method)
        with mock.patch.object(messengers, 'tg', fake_tg):
            n = messengers.poll_telegram(s, c, s.list_sources(), llm=None)
        self.assertEqual(n, 2)
        msgs = s._rows("SELECT * FROM message WHERE Channel='telegram'")
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]['ConversationId'], 'telegram:777')     # replies know where to go
        self.assertEqual(msgs[0]['FromName'], 'Rita')
        # the watermark moved to Telegram's own cursor...
        c2 = s.get_connector_by_type('telegram', with_secret=True)
        self.assertEqual(json.loads(c2['ConfigJson'])['tg_offset'], 102)
        # ...so the same updates never ingest twice even if the API repeats them
        with mock.patch.object(messengers, 'tg', fake_tg):
            self.assertEqual(messengers.poll_telegram(s, c2, s.list_sources(), llm=None), 0)
        self.assertEqual(calls['getUpdates']['offset'], 102)

    def test_only_switched_on_chats_ingest(self):
        s, c = self._store()
        s.save_source({'Channel': 'telegram', 'Address': '999', 'ConnectorId': c['ConnectorId'], 'Active': 1}, 'o')
        off = next(x for x in s.list_sources(active_only=False) if x['Address'] == '777')
        s.save_source({'SourceId': off['SourceId'], 'Active': 0}, 'o')     # known but OFF: stays out
        ups = [_tg_update(1, cid=777), _tg_update(2, cid=999, mid=9, text='mine')]
        srcs = [x for x in s.list_sources() if x['Channel'] == 'telegram']
        with mock.patch.object(messengers, 'tg', lambda t, m, **p: ups if m == 'getUpdates' else None):
            n = messengers.poll_telegram(s, c, srcs, llm=None)
        self.assertEqual(n, 1)
        self.assertEqual(s._rows("SELECT * FROM message WHERE Channel='telegram'")[0]['BodyText'], 'mine')

    def test_a_photo_rideses_the_attachment_pipeline_and_reaches_vision(self):
        s, c = self._store()
        def fake_tg(tok, method, **p):
            if method == 'getUpdates': return [_tg_update(5, text='', photo=True)]
            if method == 'getFile': return {'file_path': 'photos/file_1.jpg'}
        fake_get = mock.Mock(return_value=mock.Mock(content=base64.b64decode(PNG)))
        with mock.patch.object(messengers, 'tg', fake_tg), \
             mock.patch.object(messengers.requests, 'get', fake_get):
            n = messengers.poll_telegram(s, c, s.list_sources(), llm=None)
        self.assertEqual(n, 1)
        m = s._rows("SELECT * FROM message WHERE Channel='telegram'")[0]
        atts = s.list_attachments(m['MessageId'])
        self.assertEqual(len(atts), 1)
        self.assertEqual(atts[0]['ContentType'], 'image/jpeg')
        self.assertTrue(atts[0]['Path'])                       # the bytes are on disk

    def test_replies_go_back_into_the_same_chat(self):
        s, _ = self._store()
        sent = {}
        with mock.patch.object(messengers, 'tg', lambda t, m, **p: sent.update(p)):
            out = outbound.reply_to_message(s, {'Channel': 'telegram', 'ConversationId': 'telegram:777'}, 'Fixed.')
        self.assertEqual(out, {'channel': 'telegram', 'chat': '777'})
        self.assertEqual((sent['chat_id'], sent['text']), (777, 'Fixed.'))


class WhatsAppTests(unittest.TestCase):
    def _store(self):
        s = MemoryStore()
        cid = s.get_connector_by_type('whatsapp')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1}, 'o')
        # WhatsApp has no catch-all - a paired account sees every chat its owner is in - so the
        # chat this test feeds is named, the way a real install names one (2026-09-17)
        s.save_source({'Channel': 'whatsapp', 'Address': '155@s.whatsapp.net', 'ConnectorId': cid, 'Active': 1}, 'o')
        return s, s.get_connector_by_type('whatsapp', with_secret=True)

    def test_poll_keeps_own_messages_as_context_and_keeps_the_sequence(self):
        s, c = self._store()
        feed = {'seq': 7, 'messages': [
            {'seq': 6, 'id': 'a', 'jid': '155@s.whatsapp.net', 'name': 'Marcus', 'text': 'export is broken', 'ts': 1755700000},
            {'seq': 7, 'id': 'b', 'jid': '155@s.whatsapp.net', 'name': 'me', 'text': 'on it', 'ts': 1755700001, 'fromMe': True}]}
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: feed):
            n = messengers.poll_whatsapp(s, c, s.list_sources(), llm=None)
        self.assertEqual(n, 1)                                 # my own message is not inbound work
        rows = s._rows("SELECT * FROM message WHERE Channel='whatsapp' ORDER BY MessageId")
        self.assertEqual(rows[0]['ConversationId'], 'whatsapp:155@s.whatsapp.net')
        # ...but it IS kept, as the owner's half of the thread: the row now knows it was answered
        self.assertEqual((rows[1]['Status'], rows[1]['FromName'], rows[1]['BodyText']), ('context', 'You', 'on it'))
        self.assertIsNotNone(s.feed()[0]['AnsweredAt'])
        c2 = s.get_connector_by_type('whatsapp')
        self.assertEqual(json.loads(c2['ConfigJson'])['wa_seq'], 7)

    def test_an_idle_check_in_leaves_the_sequence_unwritten(self):
        # the bridge answers ~2/s with nothing new: rewriting the same seq every time moved the rail and emptied the pile
        s, c = self._store()
        s.set_connector_config(c['ConnectorId'], {**json.loads(c['ConfigJson'] or '{}'), 'wa_seq': 7})
        c = s.get_connector_by_type('whatsapp', with_secret=True)
        with mock.patch.object(s, 'set_connector_config') as wrote, \
             mock.patch.object(messengers, '_wa', lambda c_, p, body=None: {'seq': 7, 'messages': []}):
            messengers.poll_whatsapp(s, c, s.list_sources(), llm=None)
        wrote.assert_not_called()

    def test_only_the_chats_you_named_come_in_and_there_is_no_catch_all(self):
        """A paired account is the owner's OWN WhatsApp: it sees every group they are in and every
        DM they get. '*' used to admit all the direct ones, which on a real phone is far too much
        (the owner, 2026-09-17: "we should not allow * all as incoming ... specific channels only").
        So a chat is listed or it does not come in - and a leftover '*' row does not bring it back.
        """
        s, c = self._store()
        s.save_source({'Channel': 'whatsapp', 'Address': '4242@g.us', 'ConnectorId': c['ConnectorId'], 'Active': 1}, 'o')
        s.save_source({'Channel': 'whatsapp', 'Address': '*', 'ConnectorId': c['ConnectorId'], 'Active': 1}, 'o')
        feed = {'seq': 5, 'messages': [
            {'seq': 1, 'id': 'a', 'jid': '155@s.whatsapp.net', 'name': 'Marcus', 'text': 'listed dm comes in', 'ts': 1755700000},
            {'seq': 2, 'id': 'b', 'jid': '4242@g.us', 'group': True, 'name': 'Rita', 'text': 'picked group comes in', 'ts': 1755700001},
            {'seq': 3, 'id': 'c', 'jid': '9999@g.us', 'group': True, 'name': 'Rick', 'text': 'unpicked group stays out', 'ts': 1755700002},
            {'seq': 4, 'id': 'd', 'jid': '777@s.whatsapp.net', 'name': 'a stranger', 'text': 'unlisted dm stays out', 'ts': 1755700003}]}
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: feed):
            n = messengers.poll_whatsapp(s, c, s.list_sources(), llm=None)
        got = {m['BodyText'] for m in s._rows("SELECT * FROM message WHERE Channel='whatsapp'")}
        self.assertEqual((n, got), (2, {'listed dm comes in', 'picked group comes in'}))

    def test_poll_sets_the_baileys_pre_decryption_filter_before_reading(self):
        s, c = self._store()
        s.save_source({'Channel': 'whatsapp', 'Address': '4242@g.us',
                       'ConnectorId': c['ConnectorId'], 'Active': 1}, 'o')
        cfg = json.loads(c.get('ConfigJson') or '{}')
        s.set_connector_config(c['ConnectorId'], {**cfg, 'notify_chat': 'alerts@s.whatsapp.net',
                                                   'assistant_chat': 'me@s.whatsapp.net'})
        c = s.get_connector_by_type('whatsapp', with_secret=True)
        calls = []
        def fake(_c, path, body=None):
            calls.append((path, body))
            return {'ok': True} if path == '/filter' else {'seq': 0, 'messages': []}
        with mock.patch.object(messengers, '_wa', fake):
            self.assertEqual(messengers.poll_whatsapp(s, c, s.list_sources(), llm=None), 0)
        # allDirect is False now and stays False: the bridge decrypts and downloads media for the
        # named chats and nothing else, which is the point of telling it before reading
        self.assertEqual(calls[0], ('/filter', {
            'allDirect': False, 'jids': ['155@s.whatsapp.net', '4242@g.us', 'alerts@s.whatsapp.net',
                                         'me@s.whatsapp.net']}))
        self.assertTrue(calls[1][0].startswith('/messages?after='))

    def test_the_filter_is_sent_when_it_changes_not_on_every_read(self):
        """The doorway reads once a second (P13): an unchanged list is not re-sent, an unchanged watermark is
        not re-written, and a new chat, a restarted bridge or an old send each state the filter again."""
        s, c = self._store()
        calls, seq = [], [3]
        def fake(_c, path, body=None):
            calls.append(path)
            return {'ok': True} if path == '/filter' else {'seq': seq[0], 'messages': []}
        def read():
            calls.clear()
            with mock.patch.object(messengers, '_wa', fake): messengers.poll_whatsapp(s, s.get_connector_by_type('whatsapp', with_secret=True), s.list_sources())
            return [p.split('?')[0] for p in calls]
        self.assertEqual(read(), ['/filter', '/messages'])
        with mock.patch.object(s, 'set_connector_config', wraps=s.set_connector_config) as wrote:
            self.assertEqual(read(), ['/messages'])                             # idle: one bridge request, no write
            wrote.assert_not_called()
        s.save_source({'Channel': 'whatsapp', 'Address': '4242@g.us', 'ConnectorId': c['ConnectorId'], 'Active': 1}, 'o')
        self.assertEqual(read(), ['/filter', '/messages'])                      # a chat added: told at once
        seq[0] = 0; read()                                                      # the bridge restarted (seq went back)...
        self.assertEqual(read(), ['/filter', '/messages'])                      # ...so it is told again
        with mock.patch.object(messengers.time, 'monotonic', return_value=messengers.time.monotonic() + messengers.WA_FILTER_EVERY + 1):
            self.assertEqual(read(), ['/filter', '/messages'])                  # and re-stated after a while regardless

    def test_the_pairing_qr_is_drawn_for_the_card_and_a_down_bridge_is_a_state(self):
        s, c = self._store()
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: {'connected': False, 'me': '', 'qr': '2@abc,def,ghi', 'pairingCode': ''}):
            st = messengers.wa_status(c)
        self.assertFalse(st['connected']); self.assertTrue(st['qr_svg'].startswith('data:image/svg+xml'))
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: {'connected': True, 'me': 'Alex', 'qr': '', 'pairingCode': ''}):
            st = messengers.wa_status(c)
        self.assertEqual((st['connected'], st['me'], st['qr_svg']), (True, 'Alex', ''))
        with mock.patch.object(server.store, 'get_connector', return_value={**c, 'Type': 'whatsapp'}), \
             mock.patch.object(messengers.requests, 'get', side_effect=messengers.requests.ConnectionError('refused')):
            r = c_api.get(f"/api/connectors/{c['ConnectorId']}/wa/status")
        self.assertEqual(r.status_code, 200); self.assertEqual((r.json()['connected'], r.json()['bridge']), (False, False))

    def test_the_status_says_chats_turned_away_last_message_and_the_fix(self):
        """THE CARD TELLS THE TRUTH (2026-10-23): "connected" came from an open socket while chats were turned away and the
        contact sync failed every ten minutes. The bridge's new fields pass through, and one short line is made of them."""
        s, c = self._store()
        now = messengers.time.time()
        bridge = {'connected': True, 'me': 'Alex', 'jid': '15550100100:1@s.whatsapp.net', 'qr': '', 'pairingCode': '',
                  'admitted': 2, 'turnedAway': 12, 'lastInboundAt': now - 40 * 60, 'loggedOut': False,
                  'lastFailure': {'kind': 'decrypt', 'at': now - 60, 'detail': 'Bad MAC'},
                  'contactSync': {'failures': 1, 'at': now - 60, 'ok': 0, 'why': 'missing key'}}
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: bridge):
            st = messengers.wa_status(c)
        self.assertEqual((st['admitted'], st['turned_away'], st['last_failure']['kind'], st['contact_sync']['why']), (2, 12, 'decrypt', 'missing key'))
        self.assertEqual(st['line'], 'Connected · 2 chats · last message 40m ago · 12 turned away')
        self.assertEqual((st['parts'], st['fix']), (['Connected', '2 chats', 'last message 40m ago'], ''))
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: {**bridge, 'contactSync': {'failures': 3, 'why': 'missing key'}}):
            st = messengers.wa_status(c)
        self.assertEqual((st['line'], st['fix']), ('Connected · 2 chats · last message 40m ago · contact names not syncing · 12 turned away', 'pair'))
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: {**bridge, 'connected': False, 'loggedOut': True}):
            st = messengers.wa_status(c)
        self.assertEqual((st['line'], st['fix']), ('Logged out', 'pair'))
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: {**bridge, 'connected': False}):
            self.assertEqual((messengers.wa_status(c)['line'], messengers.wa_status(c)['fix']), ('Not connected', 'restart'))
        # an older bridge says none of it: no counts are made up
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: {'connected': True, 'me': 'Alex', 'qr': '', 'pairingCode': ''}):
            st = messengers.wa_status(c)
        self.assertEqual((st['line'], st['turned_away'], st['admitted']), ('Connected', None, None))
        self.assertEqual(messengers.wa_status_line({'connected': True, 'admitted': 1})['line'], 'Connected · 1 chat · no message yet')

    def test_every_chat_poll_that_reads_lines_is_logged_and_a_slow_empty_one_says_nothing_new(self):
        """Only slow polls were logged, so "read 0 line(s)" was all the log said about WhatsApp - as if nothing ever came."""
        self.assertEqual(server.chat_read_line(['whatsapp'], 3, 0.4), 'chat poll whatsapp read 3 lines in 0.4s')
        self.assertEqual(server.chat_read_line(['whatsapp', 'telegram'], 1, 0.2), 'chat poll whatsapp, telegram read 1 line in 0.2s')
        self.assertEqual(server.chat_read_line(['whatsapp'], 0, server.SLOW_CHAT_READ + 1.5), 'chat poll whatsapp slow (4.5s), nothing new')
        self.assertEqual(server.chat_read_line(['whatsapp'], 0, 0.3), '', "the doorway's once-a-second empty read stays quiet")

    def test_the_phone_reads_the_same_line_and_names_the_fix(self):
        from taskuary import doorway_browse
        s, c = self._store()
        s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1}, 'o')
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: {'connected': True, 'qr': '', 'pairingCode': '', 'admitted': 2,
                                                                          'turnedAway': 3, 'lastInboundAt': messengers.time.time() - 5}):
            self.assertEqual(doorway_browse._live(s, 'whatsapp'), 'Connected · 2 chats · last message just now · 3 turned away')
        with mock.patch.object(messengers, '_wa', side_effect=RuntimeError('the WhatsApp bridge is not running')):
            self.assertEqual(doorway_browse._live(s, 'whatsapp'), 'Not connected - Restart bridge on its desktop card')
        self.assertEqual(doorway_browse._live(s, 'telegram'), '')

    def test_the_chats_the_bridge_has_seen_are_offered_as_sources(self):
        """"Only this group" needs the group's JID, and there is no directory to browse: the JID
        appears the moment someone writes there. One row per chat, newest first, the other side's
        name (never ours), broadcast lists dropped."""
        s, c = self._store()
        feed = {'seq': 4, 'messages': [
            {'seq': 1, 'id': 'a', 'jid': '155@s.whatsapp.net', 'name': 'Marcus', 'text': 'export is broken', 'ts': 1755700000},
            {'seq': 2, 'id': 'b', 'jid': '120363@g.us', 'group': True, 'name': 'Rita', 'text': 'standup moved to 10', 'ts': 1755700100},
            {'seq': 3, 'id': 'c', 'jid': '120363@g.us', 'group': True, 'name': 'Alex', 'text': 'ok', 'ts': 1755700200, 'fromMe': True},
            {'seq': 4, 'id': 'd', 'jid': 'status@broadcast', 'name': 'x', 'text': 'story', 'ts': 1755700300}]}
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: feed):
            rows = messengers.wa_chats(c)
        self.assertEqual([r['jid'] for r in rows], ['120363@g.us', '155@s.whatsapp.net'])
        g = rows[0]
        self.assertEqual((g['group'], g['name'], g['n'], g['snippet']), (True, 'Rita', 2, 'ok'))
        self.assertTrue(g['last'].startswith('2025-'))
        with mock.patch.object(server.store, 'get_connector', return_value={**c, 'Type': 'whatsapp'}), \
             mock.patch.object(messengers, '_wa', lambda c_, p, body=None: feed):
            self.assertEqual(len(c_api.get(f"/api/connectors/{c['ConnectorId']}/wa/chats").json()['data']), 2)

    def test_the_bridge_account_roster_is_preferred_over_the_legacy_message_rollup(self):
        s, c = self._store()
        calls = []
        roster = {'chats': [
            {'jid': '120363@g.us', 'group': True, 'name': 'Operations', 'n': 0,
             'last': 1755700300, 'snippet': ''},
            {'jid': '155@s.whatsapp.net', 'group': False, 'name': 'Marcus', 'n': 4,
             'last': 1755700200, 'snippet': ''}]}
        with mock.patch.object(messengers, '_wa', side_effect=lambda c_, p, body=None: (calls.append(p), roster)[1]):
            rows = messengers.wa_chats(c)
        self.assertEqual(calls, ['/chats'])
        self.assertEqual([(r['jid'], r['name']) for r in rows],
                         [('120363@g.us', 'Operations'), ('155@s.whatsapp.net', 'Marcus')])
        self.assertTrue(rows[0]['last'].startswith('2025-'))

    def test_blocked_chat_is_discoverable_without_its_content(self):
        s, c = self._store()
        feed = {'seq': 0, 'messages': [], 'blockedChats': [
            {'jid': 'new-group@g.us', 'group': True, 'last': 1755700300}]}
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: feed):
            rows = messengers.wa_chats(c)
        self.assertEqual(rows[0]['jid'], 'new-group@g.us')
        self.assertEqual((rows[0]['name'], rows[0]['n']), ('', 0))
        # ...and it carries NOTHING about what was said, not even the bridge's reason for not
        # looking. That sentence was printed against most rows on a real account (2026-09-17).
        self.assertEqual(rows[0]['snippet'], '')

    def test_the_bridge_being_down_reads_as_instructions_not_a_stack_trace(self):
        s, c = self._store()
        # the bridge is a real localhost service: when a developer HAS one running, this test must still see it down
        with mock.patch.object(messengers.requests, 'get', side_effect=messengers.requests.ConnectionError('refused')), \
             self.assertRaises(RuntimeError) as e:
            messengers.wa_test(s, c)
        # ...and the instruction is the button, not a shell line (the owner, 2026-10-15: "where is the button to restart it")
        self.assertIn('Restart bridge', str(e.exception))
        self.assertNotIn('npm install', str(e.exception))

    def test_replies_post_to_the_bridge(self):
        s, _ = self._store()
        seen = {}
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: seen.update({'path': p, 'body': body})):
            out = outbound.reply_to_message(s, {'Channel': 'whatsapp',
                                                'ConversationId': 'whatsapp:155@s.whatsapp.net'}, 'Fixed.')
        self.assertEqual(out['chat'], '155@s.whatsapp.net')
        self.assertEqual(seen['body'], {'jid': '155@s.whatsapp.net', 'text': 'Fixed.'})


class OwnerTests(unittest.TestCase):
    def test_the_name_lives_in_one_setting_and_reaches_every_tokened_doc(self):
        s = MemoryStore()
        s.set_setting('owner_name', 'Dana Reyes', 'o')
        s.set_setting('owner_email', 'dana@northwind.example', 'o')
        s.save_doc('soul', 'You work for **{{owner}}** ({{owner_email}}). {{owner_first}} decides.', 'o')
        self.assertIn('Dana Reyes', s.doc('soul'))
        self.assertIn('Dana decides', s.doc('soul'))
        self.assertNotIn('{{owner', s.doc('soul'))

    def test_the_shipped_example_is_not_an_identity(self):
        """The open-source docs say John Smith on purpose - readable, not token soup. He must
        never become the fallback owner, or replies sign as the example."""
        s = MemoryStore()                                      # fresh install: template docs
        self.assertEqual(s.owner()['owner'], 'the owner')      # not 'John Smith'
        self.assertEqual(s.owner()['owner_email'], '')

    def test_retoken_sweeps_a_drifted_doc_without_touching_prose(self):
        drifted = ('You work for **Dana Reyes** (dana@x.net). Protect Dana\'s time.\n'
                   'Sign as John Smith. Johnson Controls is a vendor. the owner decides.')
        t = retoken_doc(drifted, 'Dana Reyes', 'dana@x.net')
        t = retoken_doc(t, 'John Smith', 'john.smith@example.com')
        self.assertIn('**{{owner}}** ({{owner_email}})', t)
        self.assertIn("{{owner_first}}'s time", t)
        self.assertIn('Sign as {{owner}}', t)
        self.assertIn('Johnson Controls', t)                   # substrings survive
        self.assertIn('the owner decides', t)                  # the placeholder phrase survives


if __name__ == '__main__':
    unittest.main()


class TheCatchAllIsRefusedAtTheDoorTests(unittest.TestCase):
    """Stopping the poller honouring '*' is not enough if the card can still create one - it would
    sit there looking switched on and doing nothing, which is worse than refusing it."""

    def test_a_whatsapp_catch_all_cannot_be_saved(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        r = TestClient(server.app).post('/api/sources', json={'Channel': 'whatsapp', 'Address': '*', 'Active': True})
        self.assertEqual(r.status_code, 422)
        self.assertIn('named chats only', r.json()['detail'])

    def test_telegram_keeps_its_own(self):
        """A Telegram bot only ever hears the chats it was added to, so there the catch-all is the
        whole roster rather than the world - and poll_telegram creates it on its own."""
        from fastapi.testclient import TestClient
        from taskuary import server
        r = TestClient(server.app).post('/api/sources', json={'Channel': 'telegram', 'Address': '*', 'Active': False})
        self.assertEqual(r.status_code, 200)


class TheDeadCatchAllRowTests(unittest.TestCase):
    """Making the poller ignore '*' was not enough: the row stayed on the card with a switch beside
    it, and the toggle sends {SourceId, Active} and nothing else - so the guard never saw a channel
    and the owner could turn a dead source back on (2026-09-17: "still see the * option? why?")."""

    def test_an_existing_row_cannot_be_switched_back_on(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        c = TestClient(server.app)
        cid = server.store.get_connector_by_type('whatsapp')['ConnectorId']
        sid = server.store.save_source({'Channel': 'whatsapp', 'Address': '*', 'ConnectorId': cid,
                                        'Active': 0, 'Owner': 'test'}, 'test')
        r = c.post('/api/sources', json={'SourceId': sid, 'Active': True})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(server.store.get_source(sid)['Active'], 0)

    def test_a_named_chat_is_still_perfectly_editable(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        c = TestClient(server.app)
        cid = server.store.get_connector_by_type('whatsapp')['ConnectorId']
        sid = server.store.save_source({'Channel': 'whatsapp', 'Address': '4242@g.us', 'ConnectorId': cid,
                                        'Active': 0, 'Owner': 'test'}, 'test')
        self.assertEqual(c.post('/api/sources', json={'SourceId': sid, 'Active': True}).status_code, 200)
        self.assertEqual(server.store.get_source(sid)['Active'], 1)

    def test_the_row_is_dropped_once_on_the_way_in(self):
        """A database that predates this opens without it - and Telegram's keeps its own."""
        import tempfile, os
        from taskuary.store import SQLiteStore
        path = os.path.join(tempfile.mkdtemp(), 'star.db')
        first = SQLiteStore(path)
        first.cx.execute("DELETE FROM setting WHERE Name='whatsapp_star_dropped'")
        first.cx.execute("INSERT INTO source (Channel, Address, Owner, Active) VALUES ('whatsapp','*','o',0)")
        first.cx.execute("INSERT INTO source (Channel, Address, Owner, Active) VALUES ('telegram','*','o',1)")
        first.cx.commit(); first.cx.close()

        reopened = SQLiteStore(path)                      # the migration runs on the way in
        left = {(r['Channel'], r['Address']) for r in
                reopened.cx.execute("SELECT Channel, Address FROM source WHERE Address='*'")}
        self.assertNotIn(('whatsapp', '*'), left)
        self.assertIn(('telegram', '*'), left, 'a bot only hears the chats it was added to')


class UnheardVoiceNoteTests(unittest.TestCase):
    """F22: a voice note with no voice connector named the place twice, got no thumb, and its answer had nothing to tap."""
    def test_one_place_named_a_thumb_and_the_choices_kept(self):
        from taskuary import remote_assistant, voice, words
        s = MemoryStore()
        c = s.get_connector_by_type('whatsapp', with_secret=True)
        chat = '15550001234@s.whatsapp.net'
        remote_assistant._offer([('Mark done', {'t': 'stay'}), ('Next', {'t': 'next'})])
        remote_assistant.remember_offered(s, 'whatsapp', chat, 'Reply with one of:\n1 · Mark done\n2 · Next')
        got = []
        with mock.patch.object(messengers, 'react', return_value=True) as thumb, \
             mock.patch.object(messengers, 'wa_send', side_effect=lambda st, ch, body, connector_id=None, poll=None: got.append((body, poll))):
            messengers._unheard(s, 'whatsapp', chat, c, RuntimeError(voice.NO_CONNECTOR), 'WAMID.1')
        thumb.assert_called_once()
        self.assertEqual(thumb.call_args.args[3], 'WAMID.1')
        body, poll = got[-1]
        self.assertEqual(body.count(words.name('voice')), 1, body)
        self.assertEqual(poll, ['Mark done', 'Next'])
