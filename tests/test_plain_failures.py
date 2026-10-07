"""A failed connection Test says what went wrong and what to do next, in words - never a socket's errno or a server's bytes."""
import imaplib, json, socket, unittest
from unittest import mock
import requests
from taskuary import channels, imapmail
from taskuary.channels import plain_failure


def http_error(code):
    r = requests.Response(); r.status_code = code; r.url = 'https://api.vendor.example/me'
    return requests.HTTPError(f'{code} Client Error: for url: {r.url}', response=r)


class PlainFailureTests(unittest.TestCase):
    def test_common_failures_get_a_sentence(self):
        self.assertIn('key or password', plain_failure(http_error(401)))
        self.assertIn('would not let it in', plain_failure(http_error(403)))
        self.assertIn('key or password', plain_failure(RuntimeError('401 Client Error: Unauthorized for url: https://x.example')))
        self.assertIn('address could not be found', plain_failure(socket.gaierror(11001, 'getaddrinfo failed')))
        self.assertIn('did not answer in time', plain_failure(TimeoutError('timed out')))
        self.assertIn('did not answer in time', plain_failure(requests.ConnectTimeout('ConnectTimeout: read timed out')))
        self.assertIn('turned the connection away', plain_failure(ConnectionRefusedError(10061, 'No connection could be made because the target machine actively refused it')))

    def test_our_own_words_pass_through(self):
        self.assertEqual(plain_failure(RuntimeError('no mailbox address set')), 'no mailbox address set')
        from taskuary.msauth import LAPSED
        self.assertIn(LAPSED, plain_failure(RuntimeError(f'{LAPSED} - sign in again (401)')))

    def test_imap_password_refusal_names_the_app_password(self):
        c = {'Type': 'imap', 'Secret': 'pw', 'ConfigJson': json.dumps({'address': 'alex@northwind.example', 'imap_host': 'imap.northwind.example'})}
        M = mock.MagicMock(); M.login.side_effect = imaplib.IMAP4.error(b'[AUTHENTICATIONFAILED] Invalid credentials (Failure)')
        with mock.patch('imaplib.IMAP4_SSL', return_value=M), mock.patch.object(imapmail, 'verify_pin'):
            with self.assertRaises(RuntimeError) as e: imapmail._login(c)
        self.assertIn('app password', str(e.exception)); self.assertNotIn('AUTHENTICATIONFAILED', str(e.exception))

    def test_imap_trouble_that_is_not_the_password_keeps_its_own_words(self):
        # a dropped connection or "too many connections" is not the owner's password, and must not send them for an app password
        c = {'Type': 'imap', 'Secret': 'pw', 'ConfigJson': json.dumps({'address': 'alex@northwind.example', 'imap_host': 'imap.northwind.example'})}
        for err in (imaplib.IMAP4.abort('socket error: EOF'), imaplib.IMAP4.error(b'[UNAVAILABLE] Too many simultaneous connections')):
            M = mock.MagicMock(); M.login.side_effect = err
            with mock.patch('imaplib.IMAP4_SSL', return_value=M), mock.patch.object(imapmail, 'verify_pin'):
                with self.assertRaises(imaplib.IMAP4.error) as e: imapmail._login(c)
            self.assertNotIn('app password', str(e.exception))

    def test_the_test_button_reports_the_sentence_and_keeps_the_raw_error_on_the_row(self):
        from taskuary.store import MemoryStore
        s = MemoryStore(); cid = s.get_connector_by_type('teams')['ConnectorId']
        with mock.patch.object(channels, 'graph_creds', side_effect=socket.gaierror(11001, 'getaddrinfo failed')):
            out = channels.test_connector(s, cid)
        self.assertFalse(out['ok']); self.assertIn('address could not be found', out['detail'])
        self.assertIn('getaddrinfo', s.get_connector(cid)['LastError'])


if __name__ == '__main__': unittest.main()


class StopAndCancelTests(unittest.TestCase):
    def test_stop_sets_every_answer_being_written(self):
        # the Stop beside the typing dots: an answer that hung had no way out (New chat is refused while one is written)
        import threading
        from taskuary import server
        a, b = threading.Event(), threading.Event()
        server._ANSWERING.update({a, b})
        try: self.assertEqual(server.concierge_stop(), {'stopped': 2})
        finally: server._ANSWERING.difference_update({a, b})
        self.assertTrue(a.is_set() and b.is_set())
        self.assertEqual(server.concierge_stop(), {'stopped': 0})

    def test_cancel_takes_the_chatgpt_listener_down_now(self):
        from taskuary import chatgptauth
        srv = mock.MagicMock(); chatgptauth._FLOWS['f1'] = {'srv': srv, 'at': 0}
        chatgptauth.cancel('f1')
        self.assertNotIn('f1', chatgptauth._FLOWS); srv.shutdown.assert_called_once()
        chatgptauth.cancel('gone')                    # a flow already over is no error
