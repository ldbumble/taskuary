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

    def test_wrapping_up_reads_the_screen_then_closes_everything(self):
        """"Done - wrap it up" asks the agent NOTHING. It takes the transcript that is already on
        screen, ends the session, has the main AI write the report from it, and leaves the reply
        drafted for approval. Nothing typed at the agent, nothing left running."""
        tid = c.post('/api/tasks', json={'Title': 'lookJobCode 325', 'Kind': 'coding'}).json()['taskId']
        server.store.add_message({'TaskId': tid, 'ExternalId': 'graph:CCC', 'Channel': 'email',
                                  'SourceName': 'me@corp.com', 'FromEmail': 'john@corp.com',
                                  'BodyText': 'all CNA should be restricted', 'Status': 'routed'})
        t = terminal.Term(ECHO, os.getcwd(), 'test')
        t.task_id, t.agent = tid, 'coder'
        terminal.SESSIONS[t.sid] = t
        self.assertTrue(_wait(lambda: 'hello-from-pty' in t.scrollback()))     # something on screen to harvest
        self.assertTrue(_wait(lambda: not t.alive))     # the CLI exited by itself - wrap-up must still work
        typed = []
        t.write = typed.append
        report = '{"determination": "325 was Y/Y", "actions": "flipped it to N/N", "summary": "no mailbox now"}'
        try:
            with mock.patch('taskuary.llm.build_llm', side_effect=[lambda s, u, **kw: report,
                                                                   lambda s, u, **kw: 'Done - 325 no longer gets a mailbox.']):
                out = c.post(f'/api/terminals/{t.sid}/wrap', json={'task_id': tid}).json()
            self.assertEqual(out['wrap'], 'done')
            self.assertIn('flipped it to N/N', out['report'])
            self.assertEqual(typed, [])                                        # the agent was never asked
            self.assertNotIn(t.sid, [x['sid'] for x in terminal.listing()])     # session gone
            pend = [r for r in server.store.list_reviews('pending') if r['TaskId'] == tid]
            self.assertEqual((len(pend), pend[0]['Kind']), (1, 'draft_reply'))
            self.assertIn('no longer gets a mailbox', pend[0]['DraftText'])
            self.assertEqual(server.store.get_task(tid)['Status'], 'waiting')  # waiting on you to send it
            self.assertTrue(any('flipped it to N/N' in cm['Body'] for cm in server.store.list_comments(tid)))
        finally:
            terminal.close(t.sid)

    def test_pausing_keeps_what_it_found_and_hands_it_to_the_next_session(self):
        """Killing a session threw away everything it had worked out. Pausing writes the handover
        note first, leaves the task OPEN (no report, no reply draft), and the next session on that
        task gets the note typed into it so it carries on instead of starting over."""
        tid = c.post('/api/tasks', json={'Title': 'importer is down', 'Kind': 'coding'}).json()['taskId']
        t = terminal.Term(ECHO, os.getcwd(), 'test')
        t.task_id, t.agent = tid, 'coder'
        terminal.SESSIONS[t.sid] = t
        self.assertTrue(_wait(lambda: 'hello-from-pty' in t.scrollback()))
        self.assertTrue(_wait(lambda: not t.alive))     # same for pausing an exited session
        note = '{"found": "a malformed date kills the batch", "did": "nothing yet", "next": "patch the date parse"}'
        try:
            with mock.patch('taskuary.llm.build_llm', return_value=lambda s, u, **kw: note):
                out = c.post(f'/api/terminals/{t.sid}/pause', json={'task_id': tid}).json()
            self.assertEqual(out['pause'], 'done')
            self.assertIn('malformed date', out['note'])
            self.assertNotIn(t.sid, [x['sid'] for x in terminal.listing()])      # session ended
            self.assertEqual(server.store.get_task(tid)['Status'], 'open')       # paused is not finished
            self.assertEqual([r for r in server.store.list_reviews('pending') if r['TaskId'] == tid], [])
            self.assertTrue(any('HANDOVER NOTE' in cm['Body'] for cm in server.store.list_comments(tid)))
            # ...and the note rides into the next session
            seed = terminal.seed_text(server.store, tid)
            self.assertIn('malformed date', seed)
            self.assertIn('do not start over', seed)
        finally:
            terminal.close(t.sid)

    def test_agent_argv_drops_the_headless_flags(self):
        # -p / --output-format stream-json make the CLI a one-shot pipe; a TUI needs neither
        with mock.patch('taskuary.agents._resolve_cmd', return_value=['claude']):
            self.assertEqual(terminal.agent_argv({'cmd': 'claude', 'args': ['-p', '--output-format', 'stream-json']}), ['claude'])
            self.assertEqual(terminal.agent_argv({'cmd': 'codex', 'interactive_args': ['tui']}), ['claude', 'tui'])


if __name__ == '__main__':
    unittest.main()
