"""A FAILED CHATGPT SIGN-IN IS OVER, AND SAID ON ITS CARD (the owner, 2026-10-20: the sign-in failed, the card and the Advisor still
said "finish signing in", and pressing ChatGPT again did nothing). Every way a poll can go wrong answers `error` - never a 500 the
page would keep polling through - and leaves the failure on the card (its LastError) until a sign-in works. No OpenAI call is made."""
import unittest
from unittest import mock

import requests
from fastapi.testclient import TestClient

from taskuary import server
from taskuary.store import MemoryStore

TOKENS = {'client_id': 'c', 'host_id': 'h', 'email': 'alex@northwind.example', 'name': 'Alex Doyle', 'sub': 's', 'scope': 'x',
          'refresh_token': 'r'}


class SignInEndsTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.cid = self.s.save_connector({'Type': 'chatgpt', 'Name': 'ChatGPT', 'Active': 0}, 't')
        for p in (mock.patch.object(server, 'store', self.s), mock.patch.object(server, 'brain_arrived')):
            p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)

    def poll(self, **kw):
        with mock.patch('taskuary.chatgptauth.poll', **kw):
            r = self.c.post(f'/api/connectors/{self.cid}/chatgpt/poll', json={'flow': 'f'})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_every_failure_ends_it_and_stays_on_the_card(self):
        for raised, said in ((RuntimeError('the sign-in came back for a different attempt - start it again'), 'different attempt'),
                             (requests.ConnectionError('refused'), 'could not reach auth.openai.com'),
                             (ValueError('Expecting value'), 'could not be read'),          # an answer that was not JSON: it was a 500
                             (KeyError('access_token'), 'could not be read')):
            out = self.poll(side_effect=raised)
            self.assertEqual(out['status'], 'error', raised); self.assertIn(said, out['detail'])
            err = self.s.get_connector(self.cid)['LastError'] or ''
            self.assertIn("The ChatGPT sign-in didn't finish", err); self.assertIn(said, err)

    def test_still_waiting_is_not_a_failure_and_a_sign_in_that_works_clears_it(self):
        self.poll(side_effect=RuntimeError('no such sign-in in progress - start it again'))
        self.assertEqual(self.poll(return_value={'pending': True})['status'], 'pending')
        self.assertTrue(self.s.get_connector(self.cid)['LastError'], 'waiting leaves the last failure where it was')
        self.assertEqual(self.poll(return_value=dict(TOKENS))['status'], 'ok')
        self.assertFalse(self.s.get_connector(self.cid)['LastError'], 'signed in: the failure is over')


if __name__ == '__main__':
    unittest.main()
