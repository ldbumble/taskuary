"""A WhatsApp chat saved as a phone number is that person's chat: sent as it was, the bridge answered "Cannot destructure property
'user' of 'jidDecode(...)'" to every walk handed to the phone (TQ-1251)."""
import unittest
from unittest import mock

from taskuary import messengers


class WhatsAppAddresses(unittest.TestCase):
    def test_a_number_is_that_persons_chat(self):
        for raw in ('15550100200', '+1 555-010-0200', '(555) 010.0200 '):
            self.assertRegex(messengers.wa_jid(raw), r'^\d+@s\.whatsapp\.net$', raw)

    def test_a_real_address_is_left_alone(self):
        for j in ('15550100200@s.whatsapp.net', '7000@lid', '120363000000000009@g.us'):
            self.assertEqual(messengers.wa_jid(j), j)

    def test_a_name_is_refused_in_words(self):
        with self.assertRaisesRegex(RuntimeError, 'pick the Assistant chat again'): messengers.wa_jid('Alex Doyle')

    def test_the_send_carries_the_address(self):
        store = mock.Mock(); store.get_connector_by_type.return_value = {'Type': 'whatsapp', 'ConfigJson': '{}'}
        with mock.patch.object(messengers, '_wa') as wa:
            messengers.wa_send(store, '+1 555 010 0200', 'hello')
        self.assertEqual(wa.call_args.args[2]['jid'], '15550100200@s.whatsapp.net')
