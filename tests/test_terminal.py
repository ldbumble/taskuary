"""Interactive terminals: a real pty around a process, its bytes fanned out to sockets.
Spawns python itself (no CLI agent required), so it runs the same on every OS in CI.
"""
import os, sys, time, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import server, terminal

c = TestClient(server.app)
ECHO = [sys.executable, '-c', "print('hello-from-pty')"]


def _wait(fn, secs=8):
    end = time.time() + secs
    while time.time() < end:
        if fn(): return True
        time.sleep(0.05)
    return False


class TerminalTests(unittest.TestCase):
    def test_pty_streams_into_scrollback_and_dies(self):
        t = terminal.Term(ECHO, os.getcwd(), 'test')
        terminal.SESSIONS[t.sid] = t
        try:
            self.assertTrue(_wait(lambda: 'hello-from-pty' in t.scrollback()), t.scrollback()[:200])
            self.assertTrue(_wait(lambda: not t.alive))
            self.assertIn(t.sid, [x['sid'] for x in terminal.listing()])   # kept until nobody is watching
        finally:
            terminal.close(t.sid)
        self.assertNotIn(t.sid, [x['sid'] for x in terminal.listing()])

    def test_websocket_carries_output_and_exit(self):
        t = terminal.Term(ECHO, os.getcwd(), 'test')
        terminal.SESSIONS[t.sid] = t
        try:
            with c.websocket_connect(f'/api/terminals/{t.sid}/ws') as ws:
                got, exited = '', False
                for _ in range(40):
                    m = ws.receive_json()
                    if m['type'] == 'out': got += m['data']
                    if m['type'] == 'exit': exited = True; break
                    if 'hello-from-pty' in got and exited: break
                self.assertIn('hello-from-pty', got)
        finally:
            terminal.close(t.sid)

    def test_api_validates_before_spawning_anything(self):
        self.assertEqual(c.post('/api/terminals', json={'agent': 'ghost-cli'}).status_code, 422)
        self.assertEqual(c.post('/api/terminals', json={'cwd': os.path.join(os.getcwd(), 'no-such-dir')}).status_code, 422)
        self.assertEqual(c.delete('/api/terminals/nope').status_code, 404)
        self.assertEqual(c.get('/api/terminals').json()['data'], [])

    def test_agent_argv_drops_the_headless_flags(self):
        # -p / --output-format stream-json make the CLI a one-shot pipe; a TUI needs neither
        with mock.patch('taskuary.agents._resolve_cmd', return_value=['claude']):
            self.assertEqual(terminal.agent_argv({'cmd': 'claude', 'args': ['-p', '--output-format', 'stream-json']}), ['claude'])
            self.assertEqual(terminal.agent_argv({'cmd': 'codex', 'interactive_args': ['tui']}), ['claude', 'tui'])


if __name__ == '__main__':
    unittest.main()
