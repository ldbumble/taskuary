"""A14 (approved 2026-10-22): the files an agent made for a task reach the phone. A card on a task with files in its outputs folder
names them and offers 📎 Send; the tap sends the file itself into the chat it came from - Telegram's sendDocument, the bridge's
/send-document. Only a file inside that task's own folder, only to the owner's Assistant chat, never on the model's say, and never
silently: too big says so with the desktop's address, a failed send says why with Try again. Invented people and files only."""
import json, shutil, unittest
from unittest import mock

from taskuary import config, outputs, remote_assistant as ra
from tests.phone_transcript import GAIL, JID, TG_CHAT, Phone, text_of

CSV = b'Plate,Visitor,Day\nNW-1042,Ray Colton,Mon\nNW-2210,Paula Vance,Tue\n'
BOOK = b'PK\x03\x04 invented workbook bytes \x00\x01\x02'


class PhoneFiles(unittest.TestCase):
    channel, brain = 'telegram', None

    def setUp(self):
        self.ph = Phone(self.channel, brain=self.brain)
        self.addCleanup(self.ph.close)
        self.addCleanup(shutil.rmtree, config.home() / 'scratch' / 'outputs', True)
        self.s, self.f = self.ph.s, self.ph.f
        self.chat = TG_CHAT if self.channel == 'telegram' else JID

    def task(self, files: dict):
        tid, _ = self.f._work('Reconcile the March ledger', subject='Reconcile the March ledger', from_name=GAIL[0], from_email=GAIL[1],
                              body='Alex, can you get the March GL reconciled before the close?', sent_at=self.f.ago(hours=2))
        d = outputs.folder(tid)
        for name, data in files.items():
            (d / name).parent.mkdir(parents=True, exist_ok=True); (d / name).write_bytes(data)
        self.ph.ready()
        return tid

    def card(self):
        (text, picks), *_ = [b for b in self.ph.walk() if b[1]] or [('', [])]
        return text, picks


class TelegramFileTests(PhoneFiles):
    def test_the_card_names_the_file_and_a_tap_sends_its_bytes_as_a_document(self):
        tid = self.task({'visitor-parking.csv': CSV})
        text, picks = self.card()
        self.assertIn('📎 visitor-parking.csv', text)
        self.assertIn('📎 Send visitor-parking.csv', picks)
        got = self.ph.tap('📎 Send visitor-parking.csv')
        self.assertEqual(self.ph.docs, [(self.chat, 'visitor-parking.csv', CSV, 'text/csv', f'TQ-{tid:04d} · visitor-parking.csv')])
        said = text_of(got)
        self.assertIn('Sent visitor-parking.csv', said)
        self.assertTrue(got[-1][1], 'the receipt carries a way on')

    def test_several_files_are_one_pick_that_sends_each(self):
        self.task({'gl-recon.xlsx': BOOK, 'visitor-parking.csv': CSV})
        text, picks = self.card()
        self.assertIn('gl-recon.xlsx', text); self.assertIn('visitor-parking.csv', text)
        self.assertIn('📎 Send the 2 files', picks)
        self.ph.tap('📎 Send the 2 files')
        self.assertEqual(sorted((n, d) for _c, n, d, _m, _cap in self.ph.docs), [('gl-recon.xlsx', BOOK), ('visitor-parking.csv', CSV)])
        self.assertEqual({m for *_x, m, _cap in self.ph.docs},
                         {'text/csv', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})

    def test_a_card_with_no_files_offers_none(self):
        self.task({})
        _text, picks = self.card()
        self.assertFalse([p for p in picks if p.startswith('📎')], picks)

    def test_a_path_outside_the_folder_is_refused_and_nothing_is_sent(self):
        tid = self.task({'visitor-parking.csv': CSV})
        (config.home() / 'scratch' / 'outputs' / 'secret.txt').write_bytes(b'not this task')
        self.card()
        pick = '📎 Send visitor-parking.csv'
        for bad in ('../secret.txt', str(config.home() / 'config.toml'), 'C:/Windows/win.ini', '..\\secret.txt', 'sub/../../secret.txt'):
            acts = ra.acts_for(self.s, 'telegram', self.chat)
            acts[pick] = {'t': 'files', 'tid': tid, 'paths': [bad]}
            self.s.set_setting(f'{ra.ACTS_KEY}:telegram:{self.chat}', json.dumps(acts), 't')
            said = text_of(self.ph.tap(pick))
            self.assertEqual(self.ph.docs, [], bad)
            self.assertIn('was not sent', said, bad)
            self.ph.tap('Back to')                                            # the card again, its own pick under it

    def test_a_file_too_big_is_said_plainly_with_the_desktop_instead(self):
        tid = self.task({'gl-recon.xlsx': BOOK})
        self.card()
        with mock.patch.dict('taskuary.messengers.FILE_MAX', {'telegram': 10}):
            got = self.ph.tap('📎 Send gl-recon.xlsx')
        said = text_of(got)
        self.assertEqual(self.ph.docs, [])
        self.assertIn('gl-recon.xlsx is', said)
        self.assertIn('Telegram takes files up to', said)
        self.assertIn('not sent', said)
        self.assertIn(f"Open TQ-{tid:04d} on the desktop - it's under the task's files.", said)
        self.assertNotIn('http', said)                                        # a localhost address opens nothing on a phone
        self.assertEqual(got[-1][1], [f'Back to TQ-{tid:04d}', ra.WALK, ra.MENU])

    def test_a_failed_send_says_why_and_try_again_sends_it(self):
        self.task({'visitor-parking.csv': CSV})
        self.card()
        self.ph.doc_fails = 'Bad Request: chat not found'
        got = self.ph.tap('📎 Send visitor-parking.csv')
        said = text_of(got)
        self.assertIn('Could not send visitor-parking.csv', said)
        self.assertIn('chat not found', said)
        self.assertIn('Try again', got[-1][1])
        self.ph.doc_fails = None
        self.ph.tap('Try again')
        self.assertEqual([n for _c, n, *_r in self.ph.docs], ['visitor-parking.csv'])

    def test_a_strangers_chat_gets_nothing(self):
        self.task({'visitor-parking.csv': CSV})
        self.card()
        stranger = '777000111'
        self.ph.queue.append({'update_id': 9001, 'callback_query': {'id': 'q9001', 'data': 'p0', 'from': {'id': 99, 'is_bot': False, 'first_name': 'Someone'},
                              'message': {'message_id': max(self.ph.msgs), 'chat': {'id': int(stranger), 'type': 'private'}}}})
        self.ph.queue.append({'update_id': 9002, 'message': {'message_id': 9002, 'text': '1', 'date': 2_000_000_000,
                              'chat': {'id': int(stranger), 'type': 'private'}, 'from': {'id': 99, 'is_bot': False, 'first_name': 'Someone'}}})
        self.ph._poll()
        self.assertEqual(self.ph.docs, [])
        # ...and the pick run on any road but the owner's own chat sends nothing and says nothing
        n = len(self.ph.bubbles)
        acts = ra.acts_for(self.s, 'telegram', self.chat)
        act = next(a for w, a in acts.items() if w.startswith('📎'))
        for asking in (None, {'channel': 'telegram', 'chat': stranger, 'connector_id': self.ph.cid}):
            ra._ASKING.chat = asking
            try: self.assertEqual(ra.send_files(self.s, act), '')
            finally: ra._ASKING.chat = None
        self.assertEqual((self.ph.docs, len(self.ph.bubbles)), ([], n))


class ModelCannotSendTests(PhoneFiles):
    """The model reads words; it never sends a file. Its answer may name the file and even print the pick's words - nothing goes."""
    brain = staticmethod(lambda said: 'Here it is: 📎 Send visitor-parking.csv\n1 · 📎 Send visitor-parking.csv')

    def test_typed_words_to_the_model_send_no_file(self):
        self.task({'visitor-parking.csv': CSV})
        self.card()
        self.ph.type('send me the parking file')
        self.ph.type('📎 Send visitor-parking.csv')
        self.assertEqual(self.ph.docs, [])


class WhatsAppFileTests(PhoneFiles):
    channel = 'whatsapp'

    def test_the_poll_offers_the_file_and_a_vote_sends_it_through_the_bridge(self):
        tid = self.task({'gl-recon.xlsx': BOOK})
        text, picks = self.card()
        self.assertIn('📎 gl-recon.xlsx', text)
        self.assertIn('📎 Send gl-recon.xlsx', picks)
        got = self.ph.tap('📎 Send gl-recon.xlsx')
        self.assertEqual(self.ph.docs, [(JID, 'gl-recon.xlsx', BOOK, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                         f'TQ-{tid:04d} · gl-recon.xlsx')])
        self.assertIn('Sent gl-recon.xlsx', text_of(got))

    def test_a_typed_number_is_a_pick_too(self):
        self.task({'gl-recon.xlsx': BOOK})
        _text, picks = self.card()
        self.ph.type(str(picks.index('📎 Send gl-recon.xlsx') + 1))
        self.assertEqual([n for _c, n, *_r in self.ph.docs], ['gl-recon.xlsx'])

    def test_too_big_for_whatsapp_and_a_bridge_that_fails(self):
        self.task({'gl-recon.xlsx': BOOK})
        self.card()
        with mock.patch.dict('taskuary.messengers.FILE_MAX', {'whatsapp': 10}):
            said = text_of(self.ph.tap('📎 Send gl-recon.xlsx'))
        self.assertIn('WhatsApp takes files up to', said)
        self.assertIn("on the desktop - it's under the task's files.", said); self.assertNotIn('http', said)
        self.assertEqual(self.ph.docs, [])
        self.ph.tap('Back to')
        self.ph.doc_fails = 'not connected to WhatsApp'
        got = self.ph.tap('📎 Send gl-recon.xlsx')
        self.assertIn('not connected to WhatsApp', text_of(got))
        self.assertIn('Try again', got[-1][1])


class SendDocumentTests(unittest.TestCase):
    """messengers.send_document on the wire: Telegram's multipart sendDocument, the bridge's JSON with the bytes - each under its cap."""
    def setUp(self):
        from taskuary.store import MemoryStore
        self.s = MemoryStore()
        for ch in ('telegram', 'whatsapp'):
            cid = self.s.get_connector_by_type(ch)['ConnectorId']
            self.s.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': 'tok-123', 'ConfigJson': '{}'}, 't')

    def test_telegram_posts_the_file_as_multipart_and_never_logs_the_token(self):
        from taskuary import messengers
        ok = mock.Mock(json=lambda: {'ok': True, 'result': {'message_id': 7}})
        with mock.patch.object(messengers.requests, 'post', return_value=ok) as post:
            messengers.send_document(self.s, 'telegram', TG_CHAT, CSV, 'visitor-parking.csv', 'text/csv', 'TQ-0001 · visitor-parking.csv')
        url, kw = post.call_args[0][0], post.call_args[1]
        self.assertTrue(url.endswith('/bottok-123/sendDocument'))
        self.assertEqual(kw['files'], {'document': ('visitor-parking.csv', CSV, 'text/csv')})
        self.assertEqual(kw['data'], {'chat_id': TG_CHAT, 'caption': 'TQ-0001 · visitor-parking.csv'})
        with mock.patch.object(messengers.requests, 'post', side_effect=OSError('https://api.telegram.org/bottok-123/sendDocument refused')):
            with self.assertRaises(RuntimeError) as e: messengers.send_document(self.s, 'telegram', TG_CHAT, CSV, 'a.csv', 'text/csv')
        self.assertNotIn('tok-123', str(e.exception))

    def test_whatsapp_hands_the_bridge_the_bytes_and_each_cap_is_checked_first(self):
        import base64
        from taskuary import messengers
        with mock.patch.object(messengers, '_wa', return_value={'ok': True}) as wa:
            messengers.send_document(self.s, 'whatsapp', JID, BOOK, 'gl-recon.xlsx', 'application/octet-stream')
        path, body = wa.call_args[0][1:3]
        self.assertEqual((path, body['jid'], body['fileName'], base64.b64decode(body['data'])), ('/send-document', JID, 'gl-recon.xlsx', BOOK))
        self.assertGreater(wa.call_args[1]['timeout'], 20)
        self.assertEqual(messengers.FILE_MAX, {'telegram': 50 * 2**20, 'whatsapp': 64 * 2**20})
        with mock.patch.dict(messengers.FILE_MAX, {'whatsapp': 4}), mock.patch.object(messengers, '_wa') as wa:
            with self.assertRaises(messengers.TooBig): messengers.send_document(self.s, 'whatsapp', JID, BOOK, 'gl-recon.xlsx', 'x/y')
        wa.assert_not_called()


if __name__ == '__main__':
    unittest.main()
