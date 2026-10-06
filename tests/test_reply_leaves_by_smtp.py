"""Mail that came in another way (a forward, the push door) and is answered: it leaves through the IMAP/Gmail mailbox it was
addressed to, or the only one there is when no Outlook card is on. The Graph road alone said "the outlook connection is not
set up" with an IMAP mailbox connected and working (2026-10-06)."""
import json, unittest
from unittest import mock

from taskuary import imapmail, outbound
from taskuary.store import MemoryStore


def box(s, typ, addr, active=1):
    c = s.get_connector_by_type(typ)
    s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': active, 'Secret': 'x', 'ConfigJson': json.dumps({'address': addr})}, 't')
    return c['ConnectorId']


MSG = {'Channel': 'email', 'ExternalId': 'push:1', 'SourceName': 'alex@northwind.example', 'FromEmail': 'paula@northwind.example',
       'Subject': 'Office closed Monday', 'ConversationId': 'c:1'}


class ReplyLeavesBySmtpTests(unittest.TestCase):
    def send(self, s):
        with mock.patch.object(imapmail, 'send_smtp', return_value={'channel': 'email'}) as smtp, \
             mock.patch.object(outbound, 'send_email', return_value={'channel': 'email', 'via': 'graph'}) as graph:
            outbound.reply_to_message(s, MSG, 'Does it reopen Tuesday?')
        return smtp, graph

    def test_the_mailbox_it_was_addressed_to_sends_it(self):
        s = MemoryStore(); cid = box(s, 'imap', 'alex@northwind.example')
        smtp, graph = self.send(s)
        self.assertEqual(smtp.call_args[0][1]['ConnectorId'], cid); graph.assert_not_called()
        self.assertEqual(smtp.call_args[0][2], ['paula@northwind.example'])

    def test_with_outlook_on_and_no_matching_box_it_is_outlooks(self):
        s = MemoryStore(); box(s, 'imap', 'someone.else@northwind.example'); box(s, 'outlook', 'alex@northwind.example')
        smtp, graph = self.send(s)
        smtp.assert_not_called(); graph.assert_called_once()


if __name__ == '__main__':
    unittest.main()
