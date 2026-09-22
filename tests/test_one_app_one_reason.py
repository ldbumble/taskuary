"""One app per machine, and a failure that says what it was.

A fresh install on a second machine: the Timeline sat on "Loading timeline" for ever, the assistant
said "Request failed with status code 500" and nothing else, pressing Set it up on a CLI that had
just passed its Test answered 500 too - and the desktop had been opening twice every launch (the
owner, 2026-09-22). Three faults, and the last one explains how two pollers, two schedulers and two
writers end up on one SQLite file.
"""
import socket
import unittest
from unittest import mock

from fastapi import HTTPException
from fastapi.testclient import TestClient

from taskuary import clisetup, desktop, server


class ACrashSaysWhatItWasTests(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(server.app, raise_server_exceptions=False)

    def test_a_crashed_api_call_carries_its_reason_and_where_the_trace_is(self):
        with mock.patch.object(server.store, 'feed', side_effect=RuntimeError('the disk went away')):
            r = self.c.get('/api/feed')
        self.assertEqual(r.status_code, 500)
        body = r.json()
        self.assertIn('RuntimeError', body['detail'])
        self.assertIn('the disk went away', body['detail'])
        self.assertIn('/api/feed', body['where'])
        self.assertTrue(body['log'].endswith('taskuary.log'), body['log'])

    def test_a_pane_that_cannot_open_is_a_refusal_with_its_reason(self):
        """Test passes by running the CLI once; Set it up needs a PTY, and everything that can stop
        one - no pywinpty on this Windows, a shim ConPTY will not spawn - used to be a bare 500."""
        for boom in (RuntimeError('the interactive terminal needs pywinpty on Windows'),
                     OSError('the checkout is gone'),
                     ValueError('codex is not on this machine yet - install it first')):
            with mock.patch.object(clisetup, 'start', side_effect=boom):
                r = self.c.post('/api/cli/setup', json={'name': 'codex'})
            self.assertEqual(r.status_code, 422, r.text)
            self.assertIn(str(boom), r.json()['detail'])


class OneAppPerMachineTests(unittest.TestCase):
    def test_the_desktop_serves_the_configured_port_not_a_random_one(self):
        """A random port is why a running app could never be found by the port it was configured on."""
        with mock.patch.object(desktop, 'free_port', side_effect=AssertionError('a free port was taken instead')), \
             mock.patch('uvicorn.Server') as srv, mock.patch('threading.Thread'), \
             mock.patch.object(socket.socket, 'connect_ex', return_value=1):
            srv.return_value.started = True
            _server, url = desktop.start_server()
        self.assertTrue(url.endswith(':7787'), url)

    def test_a_second_launch_finds_the_first_instead_of_booting_beside_it(self):
        with mock.patch.object(socket.socket, 'connect_ex', return_value=0), \
             mock.patch.object(desktop, 'serving', return_value=True):
            self.assertEqual(desktop.already_serving(), 'http://127.0.0.1:7787')

    def test_something_else_on_that_port_is_not_ours_to_open(self):
        with mock.patch.object(socket.socket, 'connect_ex', return_value=0), \
             mock.patch.object(desktop, 'serving', return_value=False):
            self.assertEqual(desktop.already_serving(), '')

    def test_a_free_port_means_nothing_is_running(self):
        with mock.patch.object(socket.socket, 'connect_ex', return_value=1):
            self.assertEqual(desktop.already_serving(), '')


if __name__ == '__main__':
    unittest.main()
