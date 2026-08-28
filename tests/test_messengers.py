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

    def test_the_chats_the_bridge_has_seen_are_offered_as_sources(self):
        """"Only this group" needs the group's JID, and there is no directory to browse: the JID
        appears the moment someone writes there. One row per chat, newest first, the other side's
        name (never ours), broadcast lists dropped."""
        s, c = self._store()
        feed = {'seq': 4, 'messages': [
            {'seq': 1, 'id': 'a', 'jid': '155@s.whatsapp.net', 'name': 'Marcus', 'text': 'export is broken', 'ts': 1755700000},
            {'seq': 2, 'id': 'b', 'jid': '120363@g.us', 'group': True, 'name': 'Rita', 'text': 'standup moved to 10', 'ts': 1755700100},
            {'seq': 3, 'id': 'c', 'jid': '120363@g.us', 'group': True, 'name': 'Uri', 'text': 'ok', 'ts': 1755700200, 'fromMe': True},
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


class NotifyTests(unittest.TestCase):
    """A channel as an OUTPUT: timeline events pushed into a chat instead of you polling the
    tab. The notify role names the connector, notify_chat names the chat, notify_level gates
    what qualifies - and nothing ever echoes back into the chat it happened in."""
    TASK_LLM = lambda self, s, u, **k: '{"intent": "task", "why": "asks for work"}'
    REPLY_LLM = lambda self, s, u, **k: '{"intent": "reply_only", "why": "just a question"}'

    def _store(self, level='needs_me'):
        s = MemoryStore()
        s.set_setting('notify_level', level, 'o')
        s.set_setting('coder_auto_enabled', '0', 'o')          # tests must not spawn a real CLI
        cid = s.get_connector_by_type('telegram')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'TOKEN', 'Active': 1,
                          'Roles': 'trigger,notify', 'ConfigJson': json.dumps({'notify_chat': '777'})}, 'o')
        return s

    def _msg(self, **kw):
        return {'external_id': kw.pop('ext', 'n1'), 'channel': 'email', 'subject': 'fix the export',
                'body': 'the nightly export writes empty files', 'from_email': 'marcus@corp.com',
                'from_name': 'Marcus', **kw}

    def test_a_new_task_pings_the_chat_with_the_ref_and_the_ask(self):
        from taskuary.ingest import ingest_message
        s, sent = self._store(), []
        with mock.patch.object(messengers, 'tg', lambda t, m, **p: sent.append(p)):
            out = ingest_message(s, self._msg(), llm=self.TASK_LLM)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]['chat_id'], 777)
        self.assertIn('TQ-0001', sent[0]['text'])
        self.assertIn('fix the export', sent[0]['text'])
        self.assertIn('Marcus', sent[0]['text'])
        self.assertIsNotNone(out['task_id'])

    def test_needs_me_stays_quiet_when_an_agent_was_dispatched(self):
        from taskuary.ingest import ingest_message
        s, sent = self._store(), []
        s.set_setting('coder_auto_enabled', '1', 'o')
        s.set_setting('owner_email', 'me@corp.com', 'o')       # marcus is a colleague, not a first-time stranger (senders.py)
        with mock.patch.object(messengers, 'tg', lambda t, m, **p: sent.append(p)), \
             mock.patch('taskuary.terminal.start_on_task'):
            ingest_message(s, self._msg(), llm=self.TASK_LLM)
        self.assertEqual(sent, [])                              # an agent has it - not waiting on you
        # ...but a QUESTION pings even with auto-dispatch on: no agent answers questions
        with mock.patch.object(messengers, 'tg', lambda t, m, **p: sent.append(p)), \
             mock.patch('taskuary.terminal.start_on_task'):
            ingest_message(s, self._msg(ext='n2', subject='lunch order for the retreat?',
                                        body='which caterer did we use last year?',
                                        from_email='rita@corp.com'), llm=self.REPLY_LLM)
        self.assertEqual(len(sent), 1)
        self.assertIn('question for you', sent[0]['text'])

    def test_off_is_off_and_a_failed_ping_never_breaks_the_ingest(self):
        from taskuary.ingest import ingest_message
        s, sent = self._store('off'), []
        with mock.patch.object(messengers, 'tg', lambda t, m, **p: sent.append(p)):
            self.assertIsNotNone(ingest_message(s, self._msg(), llm=self.TASK_LLM)['task_id'])
        self.assertEqual(sent, [])
        s2 = self._store()
        def boom(t, m, **p): raise RuntimeError('telegram down')
        with mock.patch.object(messengers, 'tg', boom):
            out = ingest_message(s2, self._msg(ext='n3'), llm=self.TASK_LLM)
        self.assertIsNotNone(out['task_id'])                    # the work landed anyway

    def test_an_event_in_the_notify_chat_never_echoes_back_into_it(self):
        from taskuary.outbound import notify
        s, sent = self._store(), []
        with mock.patch.object(messengers, 'tg', lambda t, m, **p: sent.append(p)):
            n = notify(s, 'ping', about={'Channel': 'telegram', 'ConversationId': 'telegram:777'})
        self.assertEqual((n, sent), (0, []))
        with mock.patch.object(messengers, 'tg', lambda t, m, **p: sent.append(p)):
            self.assertEqual(notify(s, 'ping', about={'Channel': 'email', 'ConversationId': 'x'}), 1)

    def test_the_wrap_up_pings_that_the_reply_is_waiting(self):
        from taskuary.coder import raise_reply
        s, sent = self._store(), []
        tid = s.create_task({'Title': 'export writes empty files', 'Kind': 'coding'}, 'o')
        mid = s.add_message({'TaskId': tid, 'Channel': 'email', 'FromEmail': 'marcus@corp.com',
                             'BodyText': 'broken again', 'Status': 'routed'})
        with mock.patch.object(messengers, 'tg', lambda t, m, **p: sent.append(p)), \
             mock.patch('taskuary.responder.write_draft', return_value='Fixed.'):
            raise_reply(s, tid, mid, None, {'summary': 'fixed'})
        self.assertEqual(len(sent), 1)
        self.assertIn('waiting on', sent[0]['text'])
        self.assertIn('export writes empty files', sent[0]['text'])
