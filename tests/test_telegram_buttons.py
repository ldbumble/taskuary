"""Telegram's choices are the bot's own buttons (the owner, 2026-09-29: "if buttons work in telegram no need for
polls"). A tap is a pick - the same road as a typed number or a WhatsApp poll vote - and only the newest message's
buttons answer: the ones before are taken off, and a tap on one anyway is answered, never run."""
import json, unittest
from unittest import mock

from taskuary import messengers, remote_assistant as ra
from tests.test_remote_assistant import TG_CHAT, armed_store


def tap(msg_id, data, chat=TG_CHAT, qid='q1'):
    return {'id': qid, 'data': data, 'from': {'id': 1, 'is_bot': False},
            'message': {'message_id': msg_id, 'chat': {'id': int(chat), 'type': 'private'}}}


class TelegramButtonsTests(unittest.TestCase):
    def setUp(self):
        self.s, self.c = armed_store('telegram', TG_CHAT)
        self.calls = []
        def tg(tok, method, **p):
            self.calls.append((method, p))
            return {'message_id': 50 + len([m for m, _ in self.calls if m == 'sendMessage'])} if method == 'sendMessage' else True
        self.patch = mock.patch.object(messengers, 'tg', side_effect=tg); self.patch.start()
    def tearDown(self): self.patch.stop()

    def sent(self): return [p for m, p in self.calls if m == 'sendMessage']

    def test_the_choices_go_as_buttons_under_the_message_and_are_not_printed_twice(self):
        ra.send(self.s, 'telegram', TG_CHAT, 'Close out the docs PR?\n\nReply with one of:\n1 · Close out\n2 · Next', self.c['ConnectorId'])
        (msg,) = self.sent()
        self.assertEqual([row[0]['text'] for row in msg['reply_markup']['inline_keyboard']], ['Close out', 'Next'])
        self.assertNotIn('Reply with one of', msg['text'])
        self.assertEqual(ra.resolve_index(self.s, 'telegram', TG_CHAT, '2'), ('Next', True))   # a typed number still answers

    def test_new_buttons_take_the_old_ones_off(self):
        ra.send(self.s, 'telegram', TG_CHAT, 'One?\n\nReply with one of:\n1 · Close out\n2 · Next', self.c['ConnectorId'])
        ra.send(self.s, 'telegram', TG_CHAT, 'Two?\n\nReply with one of:\n1 · Mark done\n2 · Next', self.c['ConnectorId'])
        cleared = [p for m, p in self.calls if m == 'editMessageReplyMarkup']
        self.assertEqual([(p['message_id'], p['reply_markup']) for p in cleared], [(51, {'inline_keyboard': []})])

    def test_a_tap_is_the_pick_its_label_names(self):
        ra.send(self.s, 'telegram', TG_CHAT, 'Close out the docs PR?\n\nReply with one of:\n1 · Close out\n2 · Next', self.c['ConnectorId'])
        with mock.patch.object(ra, 'intercept', return_value=True) as heard:
            messengers.tg_tap(self.s, self.c, tap(51, 'p1'))
        self.assertEqual(heard.call_args.args[:4], (self.s, 'telegram', TG_CHAT, 'Next'))
        self.assertTrue(heard.call_args.kwargs['poll'])
        self.assertIn(('answerCallbackQuery', {'callback_query_id': 'q1'}), self.calls)

    def test_a_tap_on_an_older_message_runs_nothing_and_is_answered(self):
        ra.send(self.s, 'telegram', TG_CHAT, 'One?\n\nReply with one of:\n1 · Close out\n2 · Next', self.c['ConnectorId'])
        ra.send(self.s, 'telegram', TG_CHAT, 'Two?\n\nReply with one of:\n1 · Mark done\n2 · Next', self.c['ConnectorId'])
        with mock.patch.object(ra, 'intercept') as heard:
            messengers.tg_tap(self.s, self.c, tap(51, 'p0'))
        heard.assert_not_called()
        self.assertIn('older list', self.sent()[-1]['text'])

    def test_a_tap_in_any_other_chat_is_nobodys_pick(self):
        ra.send(self.s, 'telegram', TG_CHAT, 'One?\n\nReply with one of:\n1 · Close out', self.c['ConnectorId'])
        with mock.patch.object(ra, 'intercept') as heard:
            self.assertFalse(messengers.tg_tap(self.s, self.c, tap(51, 'p0', chat='123456')))
        heard.assert_not_called()

    def test_the_update_loop_asks_for_taps_and_hands_them_over(self):
        ups = [{'update_id': 7, 'callback_query': tap(51, 'p0')}]
        self.patch.stop()
        seen = {}
        def tg(tok, method, **p):
            if method == 'getUpdates': seen.update(p); return ups
            return True
        with mock.patch.object(messengers, 'tg', side_effect=tg), mock.patch.object(messengers, 'tg_tap') as handed:
            messengers.poll_telegram(self.s, self.c, [])
        self.patch.start()
        self.assertIn('callback_query', seen['allowed_updates']); handed.assert_called_once()


if __name__ == '__main__':
    unittest.main()
