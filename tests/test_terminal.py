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

    def test_wrapping_up_a_session_ends_it_like_a_headless_run(self):
        """"Done - wrap it up" used to file a comment, mark the task done and leave you with a
        live shell and no answer to the person who wrote in. It has to end the way a headless
        run ends: report filed, reply drafted for approval, session gone."""
        tid = c.post('/api/tasks', json={'Title': 'lookJobCode 325', 'Kind': 'coding'}).json()['taskId']
        server.store.add_message({'TaskId': tid, 'ExternalId': 'graph:CCC', 'Channel': 'email',
                                  'SourceName': 'me@corp.com', 'FromEmail': 'john@corp.com',
                                  'BodyText': 'all CNA should be restricted', 'Status': 'routed'})
        t = terminal.Term(ECHO, os.getcwd(), 'test')
        t.task_id, t.agent = tid, 'coder'
        terminal.SESSIONS[t.sid] = t
        try:
            # wrap_up runs on a thread and types into the pty; drive `filed` directly instead
            with mock.patch.object(terminal, 'wrap_up', lambda term, on_done, **kw: on_done('Flipped 325 to N/N.')), \
                 mock.patch('taskuary.llm.build_llm', return_value=lambda s, u, **kw: 'Done - 325 no longer gets a mailbox.'):
                self.assertEqual(c.post(f'/api/terminals/{t.sid}/wrap', json={'task_id': tid}).json()['taskId'], tid)
            pend = [r for r in server.store.list_reviews('pending') if r['TaskId'] == tid]
            self.assertEqual((len(pend), pend[0]['Kind']), (1, 'draft_reply'))
            self.assertIn('no longer gets a mailbox', pend[0]['DraftText'])
            self.assertEqual(server.store.get_task(tid)['Status'], 'waiting')   # waiting on you to send it
            self.assertTrue(any('Flipped 325' in cm['Body'] for cm in server.store.list_comments(tid)))
            self.assertNotIn(t.sid, [x['sid'] for x in terminal.listing()])     # and the session is gone
        finally:
            terminal.close(t.sid)

    def test_agent_argv_drops_the_headless_flags(self):
        # -p / --output-format stream-json make the CLI a one-shot pipe; a TUI needs neither
        with mock.patch('taskuary.agents._resolve_cmd', return_value=['claude']):
            self.assertEqual(terminal.agent_argv({'cmd': 'claude', 'args': ['-p', '--output-format', 'stream-json']}), ['claude'])
            self.assertEqual(terminal.agent_argv({'cmd': 'codex', 'interactive_args': ['tui']}), ['claude', 'tui'])


if __name__ == '__main__':
    unittest.main()
