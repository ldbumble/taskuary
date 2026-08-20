"""Telegram and WhatsApp: both offline - the Telegram API and the Baileys bridge are mocked at
the HTTP seam, so what is tested is Taskuary's half: watermarks that never re-ingest, chat
replies that go back into the SAME chat, and the owner-name flow the docs hang off."""
import base64, json, unittest
from unittest import mock
from taskuary import messengers, outbound
from taskuary.store import MemoryStore, retoken_doc

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
        # the row is seeded at init (like every connector) - a test configures it, not creates it
        cid = s.get_connector_by_type('telegram')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'TOKEN', 'Active': 1}, 'o')
        s.save_source({'Channel': 'telegram', 'Address': '*', 'ConnectorId': cid, 'Active': 1}, 'o')
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

    def test_a_specific_chat_source_filters_and_star_takes_everything(self):
        s, c = self._store()
        s.save_source({'Channel': 'telegram', 'Address': '999', 'ConnectorId': c['ConnectorId'], 'Active': 1}, 'o')
        ups = [_tg_update(1, cid=777), _tg_update(2, cid=999, mid=9, text='mine')]
        # a real chat id present -> '*' stops being a catch-all and the id is the filter
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
        s.save_source({'Channel': 'whatsapp', 'Address': '*', 'ConnectorId': cid, 'Active': 1}, 'o')
        return s, s.get_connector_by_type('whatsapp', with_secret=True)

    def test_poll_skips_own_messages_and_keeps_the_sequence(self):
        s, c = self._store()
        feed = {'seq': 7, 'messages': [
            {'seq': 6, 'id': 'a', 'jid': '155@s.whatsapp.net', 'name': 'Marcus', 'text': 'export is broken', 'ts': 1755700000},
            {'seq': 7, 'id': 'b', 'jid': '155@s.whatsapp.net', 'name': 'me', 'text': 'on it', 'ts': 1755700001, 'fromMe': True}]}
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: feed):
            n = messengers.poll_whatsapp(s, c, s.list_sources(), llm=None)
        self.assertEqual(n, 1)                                 # my own message is not inbound work
        m = s._rows("SELECT * FROM message WHERE Channel='whatsapp'")[0]
        self.assertEqual(m['ConversationId'], 'whatsapp:155@s.whatsapp.net')
        c2 = s.get_connector_by_type('whatsapp')
        self.assertEqual(json.loads(c2['ConfigJson'])['wa_seq'], 7)

    def test_the_bridge_being_down_reads_as_instructions_not_a_stack_trace(self):
        s, c = self._store()
        with self.assertRaises(RuntimeError) as e:
            messengers.wa_test(s, c)
        self.assertIn('npm install', str(e.exception))
        self.assertIn('bridge.mjs', str(e.exception))

    def test_replies_post_to_the_bridge(self):
        s, _ = self._store()
        seen = {}
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: seen.update({'path': p, 'body': body})):
            out = outbound.reply_to_message(s, {'Channel': 'whatsapp',
                                                'ConversationId': 'whatsapp:155@s.whatsapp.net'}, 'Fixed.')
        self.assertEqual(out['chat'], '155@s.whatsapp.net')
        self.assertEqual(seen['body'], {'jid': '155@s.whatsapp.net', 'text': 'Fixed.'})


class OwnerTests(unittest.TestCase):
    def test_the_name_lives_in_one_setting_and_reaches_every_doc(self):
        s = MemoryStore()
        s.set_setting('owner_name', 'Dana Reyes', 'o')
        s.set_setting('owner_email', 'dana@northwind.example', 'o')
        self.assertIn('Dana Reyes', s.doc('soul'))
        self.assertNotIn('{{owner', s.doc('soul'))
        self.assertIn('Dana is', s.doc('coder'))

    def test_a_tokenized_doc_never_leaks_the_token_as_the_fallback_name(self):
        s = MemoryStore()                                      # no owner_name set at all
        self.assertEqual(s.owner()['owner'], 'the owner')      # not '{{owner}}'
        self.assertIn('You work for **the owner**', s.doc('soul'))

    def test_retoken_sweeps_a_drifted_doc_without_touching_prose(self):
        drifted = ('You work for **Uri Nussbaum** (uri@x.net). Protect Uri\'s time.\n'
                   'Sign as John Smith. Johnson Controls is a vendor. the owner decides.')
        t = retoken_doc(drifted, 'Uri Nussbaum', 'uri@x.net')
        t = retoken_doc(t, 'John Smith', 'john.smith@example.com')
        self.assertIn('**{{owner}}** ({{owner_email}})', t)
        self.assertIn("{{owner_first}}'s time", t)
        self.assertIn('Sign as {{owner}}', t)
        self.assertIn('Johnson Controls', t)                   # substrings survive
        self.assertIn('the owner decides', t)                  # the placeholder phrase survives


if __name__ == '__main__':
    unittest.main()
