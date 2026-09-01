"""Interactive terminals: a real pty around a process, its bytes fanned out to sockets.
Spawns python itself (no CLI agent required), so it runs the same on every OS in CI.
"""
import json, os, sys, tempfile, threading, time, unittest
from pathlib import Path
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import server, terminal

c = TestClient(server.app)
ECHO = [sys.executable, '-c', "print('hello-from-pty')"]


# ConPTY holds the pipe open for ~8s after the child exits, so "the CLI has finished" is not a
# fast condition on Windows - 8s was right on the line and made every wait here a coin flip.
def _wait(fn, secs=20):
    end = time.time() + secs
    while time.time() < end:
        if fn(): return True
        time.sleep(0.05)
    return False


class SeedArgvTests(unittest.TestCase):
    def test_prompt_rides_the_command_line_when_the_cli_takes_one(self):
        """The fastest way to type a prompt is not to type it: claude/codex take it as an
        argument, gemini behind -i - the session starts WITH it, no echo dance, no boot
        dialog eating keystrokes. Unknown CLIs keep the verified typed path."""
        self.assertEqual(terminal.seed_argv({'cmd': 'C:/x/claude.CMD'}, 'do it'), ['do it'])
        self.assertEqual(terminal.seed_argv({'cmd': 'codex'}, 'do it'), ['do it'])
        self.assertEqual(terminal.seed_argv({'cmd': 'gemini'}, 'do it'), ['-i', 'do it'])
        self.assertIsNone(terminal.seed_argv({'cmd': 'mystery-tui'}, 'do it'))

    def test_a_cmd_shim_never_gets_the_seed_on_its_command_line(self):
        """cmd.exe parses & | and stray quotes as its OWN syntax: through an npm .CMD shim the
        seed's `subject "T&E System"` was cut AT THE AMPERSAND and half a prompt arrived as if
        whole. Shims take the verified typed road; only direct executables embed."""
        server.store.upsert_agent('shimseed', 'coding', 'cli', json.dumps({'cmd': 'claude', 'cwd': os.getcwd()}))
        seed = 'TASK TQ-0001 - subject "T&E System": fix & report'
        with mock.patch.object(terminal, 'Term') as T, \
             mock.patch('taskuary.agents._resolve_cmd',
                        return_value=['cmd', '/c', r'C:\npm\claude.CMD']):
            T.return_value = mock.Mock(sid='sh1', cwd=os.getcwd(), info=lambda: {})
            try:
                terminal.open_session(server.store, 'shimseed', seed_fn=lambda cwd: seed)
                self.assertNotIn(seed, T.call_args.args[0])              # never through cmd.exe
                T.return_value.seed.assert_called_once_with(seed)        # typed instead, whole
            finally:
                terminal.SESSIONS.pop('sh1', None)

    def test_open_session_embeds_the_seed_or_falls_back_to_typing(self):
        for cmd, embedded in (('claude', True), ('mystery-tui', False)):
            server.store.upsert_agent('argvseed', 'coding', 'cli', json.dumps({'cmd': cmd, 'cwd': os.getcwd()}))
            with mock.patch.object(terminal, 'Term') as T, \
                 mock.patch('taskuary.agents._resolve_cmd', return_value=[cmd]):
                T.return_value = mock.Mock(sid='e1', cwd=os.getcwd(), info=lambda: {})
                try:
                    terminal.open_session(server.store, 'argvseed', seed_fn=lambda cwd: 'TASK TQ-0001 - go')
                    if embedded:
                        self.assertEqual(T.call_args.args[0][-1], 'TASK TQ-0001 - go')   # starts WITH it
                        T.return_value.seed.assert_not_called()
                        self.assertEqual(T.return_value.seeded, 'TASK TQ-0001 - go')     # harvest drops the echo
                    else:
                        self.assertNotIn('TASK TQ-0001 - go', T.call_args.args[0])
                        T.return_value.seed.assert_called_once_with('TASK TQ-0001 - go')
                finally:
                    terminal.SESSIONS.pop('e1', None)

    def test_codex_auto_degrades_when_the_windows_sandbox_helper_is_missing(self):
        """Without codex-windows-sandbox-setup.exe next to codex, workspace-write kills every
        command before it runs - full-auto degrades to codex's bypass flag, the same trust the
        claude preset ships. With the helper present the sandbox stays."""
        import tempfile
        auto = ['--sandbox', 'workspace-write', '--ask-for-approval', 'never']
        d = tempfile.mkdtemp()
        exe = os.path.join(d, 'codex.EXE'); open(exe, 'w').close()
        if os.name == 'nt':
            self.assertEqual(terminal._codex_windows_auto([exe] + auto),
                             [exe, '--dangerously-bypass-approvals-and-sandbox'])
            open(os.path.join(d, 'codex-windows-sandbox-setup.exe'), 'w').close()
            self.assertEqual(terminal._codex_windows_auto([exe] + auto), [exe] + auto)
        else:
            self.assertEqual(terminal._codex_windows_auto([exe] + auto), [exe] + auto)   # posix sandboxes fine
        self.assertEqual(terminal._codex_windows_auto(['claude'] + auto), ['claude'] + auto)


class InteractiveArgsTests(unittest.TestCase):
    def test_codex_full_auto_translates_to_interactive_auto(self):
        """--full-auto belongs to `codex exec`; the live TUI gets the same INTENT spelled its
        way - workspace-write sandbox, never ask (failures return to the model). NOT on-failure:
        current codex builds dropped that value and died on boot with 'invalid value'."""
        self.assertEqual(terminal.interactive_args(['exec', '--full-auto', '--json']),
                         ['--sandbox', 'workspace-write', '--ask-for-approval', 'never', '--json'])
        # claude keeps its own auto flag; only the pipe flags are stripped
        self.assertEqual(terminal.interactive_args(['-p', '--output-format', 'stream-json',
                                                    '--dangerously-skip-permissions']),
                         ['--dangerously-skip-permissions'])


class SeedEchoTests(unittest.TestCase):
    def test_chips_wraps_and_tails_all_count_as_echo(self):
        """Claude Code folds burst-typed text into '[Pasted text #N]' chips (the words never
        render), the input box wraps mid-phrase, and a long seed scrolls so only its tail stays
        visible - every one of those is a landed prompt, and an empty screen is not."""
        class T:
            cols, rows, seeded = 110, 32, 'TASK TQ-0001 - fix the import. WHAT TO DO: work it.'
            _sees = terminal.Term._sees
            def scrollback(self): return '> [Pasted text #1][Pasted text #2]'
        self.assertTrue(terminal.Term._echoed(T()))
        class Wrapped(T):                                        # a chip broken by the input box's own wrap
            def scrollback(self): return '> [Pasted te' + chr(10) + 'xt #1]'
        self.assertTrue(terminal.Term._echoed(Wrapped()))
        class Empty(T):
            def scrollback(self): return '> '
        self.assertFalse(terminal.Term._echoed(Empty()))         # nothing echoed: still a dialog risk
        self.assertFalse(Empty()._sees('TASK TQ-0001 - fix t')) # the toe check says not-listening too
        class TailOnly(T):                                       # a long seed scrolls the box: only its
            seeded = ('TASK TQ-0002 - a long ask that scrolls the input box entirely out of view. '
                      'WHAT TO DO: work it from this message alone.')
            def scrollback(self):                                # ...tail stays visible - that is enough
                return '> box entirely out of view. WHAT TO DO: work it from this message alone.'
        self.assertTrue(terminal.Term._echoed(TailOnly()))

    def test_seed_types_a_toe_then_the_payload_and_submits(self):
        """The whole seed() loop against a scripted chip-drawing TUI: a 20-char toe proves the
        box is listening, the payload follows, Enter submits - and what lands is ONE complete
        copy of the prompt, never a beheaded or doubled one (the Image-#2 and #4 regressions)."""
        SEED = 'TASK TQ-0001 - fix the import. WHAT TO DO: work it from this message alone.'
        class FakeTerm:
            alive, n, cols, rows, sid, seeded = True, 1, 110, 32, 'probe', ''
            _sees, _echoed = terminal.Term._sees, terminal.Term._echoed
            def __init__(self): self.landed, self.keys, self.screen = '', [], '> '
            def settle(self, budget=None): return True
            def scrollback(self): return self.screen
            def write(self, s):
                if s in ('\r', '\n'):
                    self.keys.append(s)
                    if self.landed: self.screen += ' * Working on it'; self.n += 5   # Enter submits
                    return
                self.landed += s
                self.screen += '[Pasted text #1]'                # chips, never the words
        f = FakeTerm()
        terminal.Term.seed(f, SEED)
        self.assertTrue(_wait(lambda: f.keys), f.landed)
        self.assertEqual(f.landed, SEED)                         # complete, single copy
        self.assertIn('Working on it', f.screen)                 # ...and it actually started

    def test_seed_survives_a_boot_dialog_eating_the_toe(self):
        """A TUI still booting eats the earliest bytes. Only the 20-char toe is ever exposed to
        that: it is retyped once the screen moves, and the payload still lands exactly once and
        whole - the old one-shot write submitted whatever half survived the eating."""
        SEED = 'TASK TQ-0002 - restart the importer. WHAT TO DO: work it from this message alone.'
        class Hungry:
            alive, cols, rows, sid, seeded = True, 110, 32, 'probe2', ''
            _sees, _echoed = terminal.Term._sees, terminal.Term._echoed
            def __init__(self): self.landed, self.keys, self.screen, self.ate = '', [], '> ', False; self._n = 1
            @property
            def n(self):
                if self.ate: self._n += 1     # after the eat every look shows movement: the dialog repainting
                return self._n
            def settle(self, budget=None): return True
            def scrollback(self): return self.screen
            def write(self, s):
                if s in ('\r', '\n'): self.keys.append(s); return
                if not self.ate: self.ate = True; return         # the boot dialog swallows the first bytes
                self.landed += s
                self.screen += s
        h = Hungry()
        terminal.Term.seed(h, SEED)
        self.assertTrue(_wait(lambda: h.keys), h.landed)
        self.assertEqual(h.landed, SEED)                         # eaten toe retyped; payload whole, once


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

    def test_repaint_after_resize_does_not_reset_idle(self):
        """The reattach wiggle forces a full repaint - output that says NOTHING about the agent.
        Counting it reset idle(), so a session parked at its prompt flipped back to 'Agent
        working' on every tab switch and the board flapped between lanes."""
        t = terminal.Term([sys.executable, '-c', 'import time; time.sleep(6)'], os.getcwd(), 'test')
        terminal.SESSIONS[t.sid] = t
        try:
            t.last = time.time() - 100                    # long parked at its prompt
            t.resize(32, 109)                             # the reattach wiggle
            t._saw_output()                               # ...and the repaint it triggers
            self.assertGreater(t.idle(), 90)              # still parked: waiting on you
            t.calm_until = 0
            t._saw_output()                               # real output later
            self.assertLess(t.idle(), 5)                  # genuinely active again
        finally:
            terminal.close(t.sid)

    def test_first_resize_wiggles_the_pty_so_a_tui_repaints(self):
        """Reattaching to a full-screen TUI (codex) replayed raw scrollback and showed smeared
        blank bars - nothing told the CHILD to repaint. The first resize of every socket now
        wiggles one column so ConPTY signals a window change and the TUI redraws whole."""
        t = terminal.Term([sys.executable, '-c', 'import time; time.sleep(8)'], os.getcwd(), 'test')
        terminal.SESSIONS[t.sid] = t
        sizes = []
        try:
            with mock.patch.object(t, 'resize', side_effect=lambda r, c_: sizes.append((r, c_))):
                with c.websocket_connect(f'/api/terminals/{t.sid}/ws') as ws:
                    ws.send_json({'type': 'resize', 'rows': 30, 'cols': 100})
                    ws.send_json({'type': 'resize', 'rows': 30, 'cols': 100})
                    ws.send_json({'type': 'in', 'data': ''})     # ordering fence: resizes processed
                    self.assertTrue(_wait(lambda: len(sizes) >= 3))
            self.assertEqual(sizes[:3], [(30, 99), (30, 100), (30, 100)])   # wiggle once, then honest sizes
        finally:
            terminal.close(t.sid)

    def test_fast_keystrokes_are_coalesced_while_conpty_is_busy(self):
        """A synchronous pywinpty write can stall while Codex repaints. The socket must keep
        receiving so the rest of a quickly typed sentence crosses in one later PTY write, rather
        than paying that stall once per character."""
        t = terminal.Term([sys.executable, '-c', 'import time; time.sleep(8)'], os.getcwd(), 'test')
        terminal.SESSIONS[t.sid] = t
        calls, first_started, release = [], threading.Event(), threading.Event()
        def slow_write(data):
            calls.append(data)
            if len(calls) == 1:
                first_started.set(); release.wait(2)
        try:
            with mock.patch.object(t, 'write', side_effect=slow_write):
                with c.websocket_connect(f'/api/terminals/{t.sid}/ws') as ws:
                    ws.send_json({'type': 'in', 'data': 'a'})
                    self.assertTrue(first_started.wait(1))
                    for ch in 'bcdef': ws.send_json({'type': 'in', 'data': ch})
                    time.sleep(.1)                         # socket drains while the first PTY call waits
                    release.set()
                    self.assertTrue(_wait(lambda: ''.join(calls) == 'abcdef'))
            self.assertEqual(calls, ['a', 'bcdef'])
        finally:
            release.set(); terminal.close(t.sid)

    def test_ready_follows_the_resize_repaint_on_the_wire(self):
        """resize() only requests a Codex redraw. The curtain barrier belongs after the PTY
        output caused by that request, or the owner sees the redraw flash line by line."""
        t = terminal.Term([sys.executable, '-c', 'import time; time.sleep(8)'], os.getcwd(), 'test')
        terminal.SESSIONS[t.sid] = t
        sizes = []
        try:
            def repaint(rows, cols):
                sizes.append((rows, cols))
                # the redraw answers THE resize the client sent - found by its size, not by its
                # position in the list: whether the handshake resizes first depends on the pty
                # backend, and on the Windows runner it did not, so "the second call" never came
                if (rows, cols) == (30, 100) and sizes.count((30, 100)) == 1:
                    t._append('\x1b[Hlive codex screen')
                    t._emit('\x1b[Hlive codex screen')
            with mock.patch.object(t, 'resize', side_effect=repaint):
                with c.websocket_connect(f'/api/terminals/{t.sid}/ws') as ws:
                    ws.send_json({'type': 'resize', 'rows': 30, 'cols': 100})
                    frames = []
                    for _ in range(20):
                        frames.append(ws.receive_json())
                        if frames[-1]['type'] == 'ready': break
            kinds = [m['type'] for m in frames]
            self.assertIn('ready', kinds)
            live_at = next(i for i, m in enumerate(frames) if 'live codex screen' in m.get('data', ''))
            self.assertLess(live_at, kinds.index('ready'))
        finally:
            terminal.close(t.sid)

    def test_replay_never_asks_the_terminal_questions(self):
        """The scrollback replay carried the TUI's own terminal queries (ESC[c, ESC[6n...), and
        xterm answered each one AGAIN on every reattach - '[?1;2c' typed into codex's input box.
        The replay is scrubbed; content and colors survive; the live stream is untouched."""
        raw = ('boot \x1b[32mgreen\x1b[0m text \x1b[c mid \x1b[6n more \x1b[>c '
               '\x1b]11;?\x07 tail \x1b[?2004$p end')
        scrubbed = terminal.scrub_queries(raw)
        for q in ('\x1b[c', '\x1b[6n', '\x1b[>c', '\x1b]11;?\x07', '\x1b[?2004$p'):
            self.assertNotIn(q, scrubbed)
        self.assertIn('\x1b[32mgreen\x1b[0m', scrubbed)          # ordinary paint survives
        self.assertIn('boot', scrubbed); self.assertIn('end', scrubbed)
        t = terminal.Term([sys.executable, '-c', 'import time; time.sleep(4)'], os.getcwd(), 'test')
        terminal.SESSIONS[t.sid] = t
        try:
            t._append('hello \x1b[6n world')
            with c.websocket_connect(f'/api/terminals/{t.sid}/ws') as ws:
                first = ws.receive_json()
            self.assertEqual(first['type'], 'out')
            self.assertNotIn('\x1b[6n', first['data'])           # the replay asks nothing
            self.assertIn('hello', first['data'])
        finally:
            terminal.close(t.sid)

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

    def test_screen_preview_renders_without_resizing_or_typing(self):
        """The Timeline may watch the real screen, but it must not alter the PTY that owns it."""
        fake = mock.Mock(sid='preview1', alive=True, rows=40, cols=120)
        fake.scrollback.return_value = 'raw terminal bytes'
        with mock.patch.object(terminal, 'get', return_value=fake), \
             mock.patch.object(terminal, 'render', return_value='old\nline one\nline two\nline three'):
            r = c.get('/api/terminals/preview1/screen?lines=2')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['lines'], ['line two', 'line three'])
        fake.resize.assert_not_called()
        fake.write.assert_not_called()

    def test_starting_a_session_reopens_a_done_task(self):
        tid = c.post('/api/tasks', json={'Title': 'finished but needs another pass', 'Kind': 'coding'}).json()['taskId']
        server.store.update_task(tid, {'Status': 'done'}, 'test')
        class Fake:
            cwd, sid, label = os.getcwd(), 'reopened-session', 'coder'
            def info(self): return {'sid': self.sid, 'cwd': self.cwd, 'alive': True}
        # Exercise the exact door used by TasksView's Start session button, not dispatch's
        # start_on_task wrapper; both must promote a closed task independently.
        with mock.patch.object(server.hub_term, 'open_session', return_value=Fake()):
            self.assertEqual(c.post('/api/terminals', json={'agent': 'coder', 'task_id': tid}).status_code, 200)
        self.assertEqual(server.store.get_task(tid)['Status'], 'in_progress')

    def test_continue_reopens_the_same_coder_checkout_with_the_saved_result(self):
        tid = c.post('/api/tasks', json={'Title': 'investigate then implement', 'Kind': 'coding'}).json()['taskId']
        server.store.upsert_agent('codex-continuation', 'coding', 'cli', '{"cmd": "codex"}')
        server.store.add_transcript(tid, 'old-session', 'the old terminal', 'codex-continuation', os.getcwd())
        server.store.add_comment(tid, 'codex-continuation', 'agent',
                                 'CODER REPORT\nSummary: found the missing mapper\nActions: documented the approach')
        server.store.update_task(tid, {'Status': 'waiting'}, 'test')
        opened = {'sid': 'continued-session', 'alive': True, 'agent': 'codex-continuation'}
        with mock.patch.object(terminal, 'start_on_task', return_value=opened) as start:
            out = c.post(f'/api/tasks/{tid}/continue', json={'instruction': 'implement the mapper and tests'}).json()
        self.assertEqual((out['agent'], out['fromSession'], out['session']['sid']),
                         ('codex-continuation', 'old-session', 'continued-session'))
        self.assertEqual(start.call_args.args[:5],
                         (server.store, tid, 'codex-continuation', None, 'implement the mapper and tests'))
        self.assertEqual(start.call_args.kwargs['cwd'], os.getcwd())
        seed = terminal.seed_text(server.store, tid, 'implement the mapper and tests')
        self.assertIn('PREVIOUS SESSION RESULT', seed)
        self.assertIn('found the missing mapper', seed)
        self.assertIn('implement the mapper and tests', seed)

    def test_continue_can_switch_to_an_explicitly_selected_harness(self):
        tid = c.post('/api/tasks', json={'Title': 'try another coder', 'Kind': 'coding'}).json()['taskId']
        server.store.upsert_agent('old-coder', 'coding', 'cli', '{"cmd": "old"}')
        server.store.upsert_agent('backup-coder', 'coding', 'cli', '{"cmd": "backup"}')
        server.store.add_transcript(tid, 'old-session', 'rate limited', 'old-coder', os.getcwd())
        opened = {'sid': 'backup-session', 'alive': True, 'agent': 'backup-coder'}
        with mock.patch.object(terminal, 'start_on_task', return_value=opened) as start:
            out = c.post(f'/api/tasks/{tid}/continue',
                         json={'agent': 'backup-coder', 'instruction': 'pick up from the failed run'}).json()
        self.assertEqual(out['agent'], 'backup-coder')
        self.assertEqual(start.call_args.args[2], 'backup-coder')

    def test_start_session_seeds_the_new_prompt(self):
        tid = c.post('/api/tasks', json={'Title': 'repair imports', 'Kind': 'coding'}).json()['taskId']
        captured = {}
        class Fake:
            cwd, sid, label = os.getcwd(), 'prompted-session', 'coder'
            def info(self): return {'sid': self.sid, 'cwd': self.cwd, 'alive': True}
        def opened(*args, **kwargs):
            captured['seed'] = kwargs['seed_fn'](os.getcwd())
            return Fake()
        with mock.patch.object(server.hub_term, 'open_session', side_effect=opened):
            r = c.post('/api/terminals', json={'agent': 'coder', 'task_id': tid, 'seed': True,
                                                'instruction': 'Only repair the CSV retry path.'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('Only repair the CSV retry path.', captured['seed'])

    def test_stop_agent_leaves_task_status_unchanged(self):
        tid = c.post('/api/tasks', json={'Title': 'keep this task', 'Kind': 'coding'}).json()['taskId']
        server.store.update_task(tid, {'Status': 'waiting'}, 'test')
        live = mock.Mock(sid='only-the-session', alive=True, label='Codex', agent='coder')
        with mock.patch.object(server.hub_term, 'session_for', return_value=live), \
             mock.patch.object(server.hub_term, 'close', return_value=True) as close:
            out = c.post(f'/api/tasks/{tid}/agent/stop').json()
        self.assertEqual(out, {'stopped': True, 'taskStatus': 'waiting'})
        self.assertEqual(server.store.get_task(tid)['Status'], 'waiting')
        close.assert_called_once_with('only-the-session')

    def test_continue_does_not_silently_replace_a_removed_coder(self):
        tid = c.post('/api/tasks', json={'Title': 'continue it', 'Kind': 'coding'}).json()['taskId']
        server.store.add_transcript(tid, 'gone-session', 'work', 'removed-coder', os.getcwd())
        r = c.post(f'/api/tasks/{tid}/continue', json={'instruction': 'make the changes'})
        self.assertEqual(r.status_code, 422)
        self.assertIn('removed-coder', r.json()['detail'])

    def test_an_image_pasted_into_a_task_terminal_is_saved_for_its_prompt(self):
        tid = c.post('/api/tasks', json={'Title': 'inspect this screenshot', 'Kind': 'coding'}).json()['taskId']
        t = terminal.Term([sys.executable, '-c', 'import time; time.sleep(5)'], os.getcwd(), 'test', tid)
        terminal.SESSIONS[t.sid] = t
        try:
            with tempfile.TemporaryDirectory() as tmp, mock.patch.object(server.config, 'home', return_value=Path(tmp)):
                r = c.post(f'/api/terminals/{t.sid}/image', content=b'not-a-real-png-but-the-browser-sent-it',
                           headers={'Content-Type': 'image/png'})
                self.assertEqual(r.status_code, 200)
                p = Path(r.json()['path'])
                self.assertTrue(p.is_file())
                self.assertEqual(p.read_bytes(), b'not-a-real-png-but-the-browser-sent-it')
                self.assertEqual(c.post(f'/api/terminals/{t.sid}/image', content=b'x',
                                        headers={'Content-Type': 'text/plain'}).status_code, 415)
        finally:
            terminal.close(t.sid)

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
            # the handbook is OFF for this one. It is on by default now and asks the transcript
            # its own question during wrap (coder.wrap -> handbook.learn_from_session), which
            # would eat one of the two brains below and leave the reply undrafted. What wrap does
            # with the handbook is tests/test_handbook.py's subject, not this test's.
            with mock.patch('taskuary.handbook.enabled', return_value=False),                  mock.patch('taskuary.llm.build_llm', side_effect=[lambda s, u, **kw: report,
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

    def test_the_prompt_carries_everything_so_the_agent_never_calls_back(self):
        """An agent that goes back to Taskuary for the message spends a minute of tool calls
        re-fetching what it was handed. The prompt says the message IS the context - and carries
        the mail, the repo and CODER.md (which claimed to be sent every run, and never was)."""
        tid = c.post('/api/tasks', json={'Title': 'payroll import month is wrong', 'Kind': 'coding'}).json()['taskId']
        server.store.add_message({'TaskId': tid, 'ExternalId': 'graph:PAY1', 'Channel': 'email',
                                  'FromName': 'Dana Reyes', 'FromEmail': 'dreyes@northwind.example',
                                  'Subject': 'Payroll File Imports', 'SentAt': '2026-08-19 15:03',
                                  'BodyText': 'files with adjustments import in the wrong month'})
        seed = terminal.seed_text(server.store, tid, 'use the payroll date', 'northwind/Census', 'C:/src/Census')
        for s in ['payroll import month is wrong', 'Dana Reyes', 'wrong month', 'use the payroll date',
                  'REPO: northwind/Census', 'Do NOT call the Taskuary API', 'fix it if it is fixable',
                  'Do NOT create GitHub issues']:
            self.assertIn(s, seed)
        self.assertIn('RULES:', seed)                                   # CODER.md rides along
        self.assertIn('Work ONLY in the repository', seed)
        self.assertNotIn('\\n', seed)                                   # one line - a newline submits

    def test_repo_is_guessed_from_the_soul_map_when_the_task_has_no_tag(self):
        prof = {'cwd_map': {'northwind/Census': 'C:/src/Census', 'northwind/Reports': 'C:/src/Reports'}}
        server.store.save_doc('soul', '## Repository map\n'
                              '- **northwind/Census**: employee portal - PTO, payroll imports, timesheets\n'
                              '- **northwind/Reports**: nightly financial reporting pipeline\n', 'test')
        pto = c.post('/api/tasks', json={'Title': 'PTO import maps the wrong month',
                                         'Summary': 'the payroll timesheet import is off'}).json()['taskId']
        self.assertEqual(terminal.guess_repo(server.store, pto, prof)[0], 'northwind/Census')
        named = c.post('/api/tasks', json={'Title': 'Reports is failing at 2am'}).json()['taskId']
        self.assertEqual(terminal.guess_repo(server.store, named, prof), ('northwind/Reports', 'named in the ask'))
        tagged = c.post('/api/tasks', json={'Title': 'anything', 'Tags': 'repo:northwind/Reports'}).json()['taskId']
        self.assertEqual(terminal.guess_repo(server.store, tagged, prof), ('northwind/Reports', 'tagged on the task'))
        # nothing to match against, or nothing that matches: the agent's own folder, not a wrong repo
        self.assertEqual(terminal.guess_repo(server.store, pto, {}), (None, None))
        blank = c.post('/api/tasks', json={'Title': 'zzz qqq'}).json()['taskId']
        self.assertIsNone(terminal.guess_repo(server.store, blank, prof)[0])

    def test_start_session_seeds_the_same_full_prompt_as_dispatch(self):
        """"Start session" in the Tasks header used to build its OWN thin prompt - title plus
        summary, no message, no rules - which is precisely why an agent started that way went
        back to the API for the mail. One prompt builder, both doors."""
        server.store.upsert_agent('coder', 'coding', 'cli', '{"cmd": "claude"}')
        tid = c.post('/api/tasks', json={'Title': 'payroll month', 'Kind': 'coding'}).json()['taskId']
        server.store.add_message({'TaskId': tid, 'ExternalId': 'graph:PAY2', 'Channel': 'email',
                                  'FromEmail': 'dreyes@northwind.example', 'Subject': 'Payroll File Imports',
                                  'SentAt': '2026-08-19 15:03', 'BodyText': 'imports in the wrong month'})

        class Fake:
            sid, cwd, label, agent, task_id = 'fake-sid', os.getcwd(), 'coder', 'coder', tid
            seeded = None
            def info(self): return {'sid': self.sid, 'cwd': self.cwd, 'alive': True}
        def fake_open(*a, seed_fn=None, **k):
            Fake.seeded = seed_fn(os.getcwd()) if seed_fn else None    # the prompt now travels as seed_fn
            return Fake()
        with mock.patch.object(terminal, 'open_session', side_effect=fake_open):
            self.assertEqual(c.post('/api/terminals', json={'agent': 'coder', 'task_id': tid, 'seed': True}).status_code, 200)
        for s in ('imports in the wrong month', 'dreyes@northwind.example', 'Do NOT call the Taskuary API', 'fix it if it is fixable'):
            self.assertIn(s, Fake.seeded)

    def test_the_prompt_is_sent_not_just_typed(self):
        """Killer detail: a long paste and a carriage return in the same breath read as ONE edit
        to a TUI, so the prompt sat there typed but never submitted. Enter goes in on its own."""
        t = terminal.Term([sys.executable, '-c', 'import time; time.sleep(3)'], os.getcwd(), 'test')
        terminal.SESSIONS[t.sid] = t
        wrote = []
        # a pty ECHOES what is typed - the seed verifies that before any Enter goes in, so the
        # fake write feeds the buffer the way a real echo would
        def fake_write(x): wrote.append(x); t._append(x)
        try:
            with mock.patch.object(t, 'write', side_effect=fake_write):
                with mock.patch.object(terminal, 'SEED_QUIET', 0), mock.patch.object(terminal, 'SEED_ENTER', .05):
                    t.n = 1                                  # the TUI has printed: it is 'ready'
                    t.seed('do the thing and then do the other thing')
                    self.assertTrue(_wait(lambda: '\r' in wrote))
            self.assertEqual(wrote[0], 'do the thing and the')    # the 20-char toe goes first, alone
            self.assertEqual(''.join(wrote[:wrote.index(chr(13))]),
                             'do the thing and then do the other thing')   # whole prompt, exactly once
            self.assertEqual(wrote[wrote.index(chr(13))], '\r')   # then Enter, on its own
        finally:
            terminal.close(t.sid)

    def test_an_unechoed_prompt_is_never_submitted_blind(self):
        """codex boots into "do you trust this directory?" - a dialog that eats typed text and
        treats Enter as its ANSWER. If the text never echoes, no Enter may be pressed: trusting
        a directory is the owner's security decision, not the seeder's."""
        t = terminal.Term([sys.executable, '-c', 'import time; time.sleep(3)'], os.getcwd(), 'test')
        terminal.SESSIONS[t.sid] = t
        wrote = []
        try:
            with mock.patch.object(t, 'write', side_effect=wrote.append):   # NO echo: a dialog ate it
                with mock.patch.object(terminal, 'SEED_QUIET', 0), mock.patch.object(terminal, 'SEED_ENTER', .05), \
                     mock.patch.object(terminal, 'SEED_BUDGET', 1.5):
                    t.n = 1
                    t.seed('do the thing and then do the other thing')
                    time.sleep(2.5)
            self.assertNotIn('\r', wrote)                     # nothing answered the dialog for them
            self.assertNotIn('\n', wrote)
        finally:
            terminal.close(t.sid)

    def test_the_wrap_up_reads_the_WHOLE_session_not_the_last_48k_of_escape_codes(self):
        """TQ-0013: 27 minutes of real work, and the report said "the content is heavily
        corrupted". The tail was taken off the RAW stream - and in a busy TUI the last 48k chars
        are spinner frames and cursor moves, not words. Render first, then take the tail."""
        work = ('Root-caused and fixed (Census master b4275ce9). ACH rows in bankFeed carry nothing in '
                'Cust. Ref, so the doc-number rules can never fire for an EFT and only amount+date is '
                'left. CFG settled Shady Grove over two deposits, which is why they show uncleared.\r\n')
        spam = ''.join(f'\r\x1b[2K\x1b[36m✻\x1b[0m Levitating… ({i}s · esc to interrupt · {i * 431} tokens)'
                       for i in range(1, 1200))          # what a TUI paints while it thinks
        t = terminal.Term(ECHO, os.getcwd(), 'test')
        terminal.SESSIONS[t.sid] = t
        try:
            t.buf.clear(); t.n = 0
            t._append(work); t._append(spam)
            self.assertGreater(len(t.scrollback()), 48000)        # the old window would see spam only
            self.assertLess(len(t.scrollback()), terminal.SCROLLBACK)
            got = terminal.harvest(t)
            self.assertIn('Root-caused and fixed', got)
            self.assertIn('Shady Grove', got)
            self.assertNotIn('Levitating', got)                   # and the chrome still goes
            self.assertGreater(terminal.letters(got), 160)
            # a session that printed nothing but chrome hands back the rendered text, not silence:
            # noise an AI can discount, emptiness it cannot
            t.buf.clear(); t.n = 0; t._append(spam)
            self.assertTrue(terminal.harvest(t).strip())
        finally:
            terminal.close(t.sid)

    def test_end_to_end_a_real_tui_gets_the_prompt_submitted_and_the_report_is_real(self):
        """The whole lifecycle against a REAL pty running a TUI that only works on a full line:
        seed it, and the work only happens if Enter actually went in. Then the wrap-up has to
        write the report from what the TUI said - not from its spinner."""
        fake = str(Path(__file__).parent / 'fake_tui.py')
        server.store.upsert_agent('faketui', 'coding', 'cli', json.dumps({'cmd': sys.executable, 'args': [fake]}))
        # fake_tui reads stdin in CANONICAL mode: macOS caps a line at 1024 bytes and drops the
        # overflow at the tty layer. Real TUIs are raw-mode (no cap) - so trim what only bloats
        # this test's prompt, and assert it fits, or the failure mode is invisible.
        saved = {n: server.store.get_doc(n) for n in ('coder', 'soul')}
        for n in saved: server.store.save_doc(n, '', 'test')
        # ...and the wall, the owner's standing notes, the semantic layer, and the CONTEXT FILE
        # line below. Every one of them is real prompt content that grows with whatever other
        # tests left in the shared store, and this test measures the SEED - so it owns every
        # input to it.
        server.store._exec('DELETE FROM boardnote')
        server.store._exec('DELETE FROM memory')
        server.store._exec('DELETE FROM metric')
        self.addCleanup(lambda: [server.store.save_doc(n, v or '', 'test') for n, v in saved.items()])
        tid = c.post('/api/tasks', json={'Title': 'payroll adjustments post to the wrong month',
                                         'Kind': 'coding'}).json()['taskId']
        server.store.add_message({'TaskId': tid, 'ExternalId': 'graph:E2E', 'Channel': 'email',
                                  'FromName': 'Dana Reyes', 'FromEmail': 'dreyes@northwind.example',
                                  'Subject': 'Payroll File Imports', 'SentAt': '2026-08-19 15:03',
                                  'BodyText': 'files with adjustments import in the wrong month'})
        # the context file is the last variable input, and the one that bit: it is written only
        # when there IS a sender history or a past task to write about, so this measured 921
        # characters alone and 1111 in a full run, where forty other tests have filled the store
        # and its temp-dir path joins the prompt. Its LENGTH is a property of the machine's temp
        # directory, not of the prompt, so it is not what this budget is about.
        with mock.patch('taskuary.context.write', return_value=None):
            seed = terminal.seed_text(server.store, tid)
        # Back to 1000. Switching the handbook on briefly pushed this to 1100 by adding a line
        # about how to write an entry - and a longer seed takes longer to type into a real TUI,
        # which is what turned this end-to-end test red on CI while passing locally. The rule
        # moved to CODER.md instead of the ceiling moving: "belongs in a document" was already
        # the right answer, written in this comment, one line above where it was ignored.
        self.assertLess(len(seed), 1000, seed)
        ses = c.post('/api/terminals', json={'agent': 'faketui', 'task_id': tid, 'seed': True,
                                             'cwd': os.getcwd()}).json()
        t = terminal.get(ses['sid'])
        try:
            # the TUI echoes the ask only when a whole line arrives, so this passing IS the proof
            # that the prompt was submitted and not just typed into the box
            # A loaded macOS runner can spend most of the first 40 seconds proving the canonical
            # PTY accepted the prompt (the failure transcript had already reached "Working…" at
            # the cutoff). The seed path deliberately owns a longer retry window, so this test
            # must allow the work line to arrive instead of racing that recovery machinery.
            self.assertTrue(_wait(lambda: 'run_pto_intacct.py' in terminal.plain(t.scrollback()), 75),
                            terminal.plain(t.scrollback())[-400:])
            self.assertIn('Payroll File Imports', terminal.plain(t.scrollback()))   # the mail rode in
            got = terminal.harvest(t)
            self.assertIn('wrong month', got)
            self.assertIn('run_pto_intacct.py', got)
            self.assertNotIn('Levitating', got)                       # spinner frames stay out
            self.assertNotIn('esc to interrupt', got)
            seen = []                       # the wrap calls the AI twice: report, then reply draft
            def fake_llm(system, user, **kw):
                seen.append(user)
                return '{"determination": "adjustment rows took the first line date", "actions": "fixed the batch date", "summary": "posts to the right month now"}'
            with mock.patch('taskuary.llm.build_llm', return_value=fake_llm):
                out = c.post(f'/api/terminals/{t.sid}/wrap', json={'task_id': tid, 'close': True}).json()
            self.assertIn('fixed the batch date', out['report'])
            self.assertIn('run_pto_intacct.py', seen[0])               # the AI read the real transcript
            self.assertNotIn('Levitating', seen[0])
            self.assertNotIn('esc to interrupt', seen[0])
            # ...and not the prompt WE typed in, echoed back by the pty as if the agent said it
            self.assertNotIn('Do NOT call the Taskuary API', seen[0])
        finally:
            terminal.close(ses['sid'])


    def test_the_seed_carries_the_message_not_the_signature(self):
        """Corporate mail is half signature and legal footer, and all of it rode into every
        session prompt - context spent on a confidentiality NOTICE instead of the ask."""
        tid = c.post('/api/tasks', json={'Title': 'reimbursement error', 'Kind': 'coding'}).json()['taskId']
        server.store.add_message({'TaskId': tid, 'ExternalId': 'graph:SIG1', 'Channel': 'email',
                                  'FromName': 'Dana Reyes', 'Subject': 'Reimbursement App',
                                  'BodyText': chr(10).join([
                                      'I am seeing ????? at the end of each transaction.', '',
                                      'Thank you,', '', 'Dana Reyes', 'Director of Payroll',
                                      'Phone: 555-0100', '',
                                      'NOTICE: This confidential message contains information intended '
                                      'for a specific individual and purpose.'])})
        seed = terminal.seed_text(server.store, tid)
        self.assertIn('????? at the end of each transaction', seed)
        self.assertNotIn('NOTICE', seed)
        self.assertNotIn('Phone: 555-0100', seed)
        self.assertNotIn('Director of Payroll', seed)

    def test_agents_open_issues_only_when_the_setting_says_so(self):
        """Off (the default): the seed forbids tracker items and the SOUL.md tool blurb scopes
        writes to the ask. On: both sides grant the licence. One switch, both documents."""
        from taskuary import docsync
        tid = c.post('/api/tasks', json={'Title': 'issue policy probe', 'Kind': 'coding'}).json()['taskId']
        server.store.set_setting('agent_issues_enabled', '0', 'test')
        self.assertIn('Do NOT create GitHub issues', terminal.seed_text(server.store, tid))
        self.assertIn('Do NOT push, deploy', terminal.seed_text(server.store, tid))
        server.store.set_setting('agent_push_enabled', '1', 'test')
        self.assertIn('may push and deploy', terminal.seed_text(server.store, tid))
        server.store.set_setting('agent_push_enabled', '0', 'test')
        self.assertIn('never issues or tracker items', docsync.role_text(server.store, 'tool'))
        server.store.set_setting('agent_issues_enabled', '1', 'test')
        try:
            seed = terminal.seed_text(server.store, tid)
            self.assertNotIn('Do NOT create GitHub issues', seed)
            self.assertIn('GitHub is the issue tracker', seed)
            self.assertIn('as the work needs', docsync.role_text(server.store, 'tool'))
            # ...and the GitHub CONNECTOR's own config outranks the legacy setting: the decision
            # about GitHub lives on the GitHub card
            server.store.set_connector_config(server.store.get_connector_by_type('github')['ConnectorId'],
                                              {'use_as_tracker': False, 'agents_push': True})
            self.assertIn('Do NOT create GitHub issues', terminal.seed_text(server.store, tid))
            self.assertIn('may push and deploy', terminal.seed_text(server.store, tid))
            server.store.set_connector_config(server.store.get_connector_by_type('github')['ConnectorId'], {})
        finally:
            server.store.set_setting('agent_issues_enabled', '0', 'test')

    def test_agent_argv_drops_the_headless_flags(self):
        # -p / --output-format stream-json make the CLI a one-shot pipe; a TUI needs neither
        with mock.patch('taskuary.agents._resolve_cmd', return_value=['claude']):
            self.assertEqual(terminal.agent_argv({'cmd': 'claude', 'args': ['-p', '--output-format', 'stream-json']}), ['claude'])
            self.assertEqual(terminal.agent_argv({'cmd': 'codex', 'interactive_args': ['tui']}), ['claude', 'tui'])

    def test_codex_uses_the_low_repaint_tui_inside_the_browser_terminal(self):
        with mock.patch('taskuary.agents._resolve_cmd', return_value=['C:/npm/codex.exe']):
            argv = terminal.agent_argv({'cmd': 'codex', 'args': ['exec']})
        self.assertIn('--no-alt-screen', argv)
        self.assertIn('tui.animations=false', argv)

    def test_codex_profile_can_explicitly_override_the_tui_defaults(self):
        configured = ['--no-alt-screen', '--config', 'tui.animations=true']
        with mock.patch('taskuary.agents._resolve_cmd', return_value=['C:/npm/codex.exe']):
            argv = terminal.agent_argv({'cmd': 'codex', 'interactive_args': configured})
        self.assertEqual(argv.count('--no-alt-screen'), 1)
        self.assertIn('tui.animations=true', argv)
        self.assertNotIn('tui.animations=false', argv)


class ShimResolutionTests(unittest.TestCase):
    """An npm .CMD shim is four lines of batch around one real program. Reaching THROUGH it
    instead of running it under cmd /c is what decides whether the first prompt can be passed
    as an argument at all - and a prompt passed as argv arrives whole or not at all, where a
    typed one arrives in 160-char bites that a busy TUI input loop drops."""
    B = chr(92)

    def _shim(self, tail):
        import tempfile
        d = tempfile.mkdtemp()
        binp = os.path.join(d, 'node_modules', 'pkg', 'bin')
        os.makedirs(binp)
        for f in ('tool.exe', 'cli.js'):
            open(os.path.join(binp, f), 'w').write('x')
        cmd = os.path.join(d, 'tool.cmd')
        open(cmd, 'w').write('@ECHO off' + chr(10) + 'SET dp0=%~dp0' + chr(10) + tail + chr(10))
        return cmd, os.path.join(binp, 'tool.exe'), os.path.join(binp, 'cli.js')

    def _q(self, name):
        return '"%dp0%' + self.B + 'node_modules' + self.B + 'pkg' + self.B + 'bin' + self.B + name + '"'

    def test_a_shim_wrapping_an_exe_resolves_to_the_exe(self):
        from taskuary.agents import _shim_target
        cmd, exe, _ = self._shim(self._q('tool.exe') + '   %*')
        self.assertEqual(_shim_target(cmd), [exe])

    def test_a_shim_wrapping_node_plus_a_script_resolves_to_both(self):
        from taskuary.agents import _shim_target
        cmd, exe, js = self._shim(self._q('tool.exe') + ' ' + self._q('cli.js') + ' %*')
        self.assertEqual(_shim_target(cmd), [exe, js])

    def test_a_shim_it_cannot_read_falls_back_rather_than_failing(self):
        """cmd /c still works - it just costs the argv prompt. Guessing wrong must not stop a
        session from starting at all."""
        from taskuary.agents import _shim_target
        cmd, _, _ = self._shim('something::unparseable %*')
        self.assertEqual(_shim_target(cmd), [])

    def test_resolving_past_the_shim_is_what_lets_the_prompt_ride_argv(self):
        """open_session strips the argv prompt the moment cmd.exe is in the command - which on
        Windows was ALWAYS, so every prompt was typed, in bites, unverified."""
        blocked = lambda argv: any(str(a).lower().endswith(('.cmd', '.bat')) or
                                   os.path.basename(str(a)).lower() in ('cmd', 'cmd.exe') for a in argv)
        self.assertTrue(blocked(['cmd', '/c', 'C:' + self.B + 'npm' + self.B + 'claude.CMD']))
        self.assertFalse(blocked(['C:' + self.B + 'npm' + self.B + 'bin' + self.B + 'claude.exe']))
        self.assertEqual(terminal.seed_argv({'cmd': 'claude'}, 'the ask'), ['the ask'])


class ReplaySeedTests(unittest.TestCase):
    """What a reopened pane is seeded with. The raw scrollback of a full-screen TUI is a stream of
    ABSOLUTE cursor moves; replayed into a fresh xterm that has none of that history it smears into
    debris, and the live repaint then lands on top of the debris instead of replacing it - the
    screenshot the owner sent on 2026-09-02, and the scrolling that came with it."""

    ESC = chr(27)

    class Fake:
        cols, rows = 80, 12
        def __init__(self, raw): self.raw = raw
        def scrollback(self): return self.raw

    def _seed(self, raw, **kw):
        return terminal.replay_text(self.Fake(raw), **kw)

    def test_the_seed_is_what_the_terminal_would_show_not_the_bytes(self):
        E = self.ESC
        raw = (E + '[?1049h' + E + '[2J' + E + '[3;5Hhello there'
               + E + '[1;1Hcodex is working' + E + '[6n')
        out = self._seed(raw)
        self.assertTrue(out.startswith(terminal.REPLAY_RESET))
        body = out[len(terminal.REPLAY_RESET):]
        self.assertNotIn(E, body)                       # nothing left for xterm to mis-position
        self.assertIn('codex is working', body)
        self.assertIn('hello there', body)              # the absolute move was OBEYED, not deleted
        self.assertIn(terminal.CRLF, body)              # xterm needs CR before LF

    def test_a_cursor_query_cannot_survive_it(self):
        """A replayed query makes xterm answer it AGAIN and the answer lands in the CLI as typed
        junk. A render cannot emit one, which retires that whole class of bug."""
        self.assertNotIn('[6n', self._seed(self.ESC + '[6nhello'))

    def test_an_empty_session_seeds_nothing(self):
        self.assertEqual(self._seed('   ' + chr(10) + '  '), '')
        self.assertEqual(self._seed(''), '')

    def test_the_seed_is_capped_to_the_tail(self):
        raw = chr(10).join('line %d' % n for n in range(1200))
        out = self._seed(raw, lines=50)
        self.assertEqual(out.count(terminal.CRLF), 49)
        self.assertIn('line 1199', out)
        self.assertNotIn('line 900', out)


if __name__ == '__main__':
    unittest.main()


class DurableWrapTests(unittest.TestCase):
    """Wrapping up must not depend on a pty still being around. A CLI that exits on its own is
    reaped after ten minutes, and with it went the only handle the Done/Pause buttons had - so a
    task whose agent had finished could never be closed out at all."""

    def _task(self, title='reaped session task'):
        return c.post('/api/tasks', json={'Title': title, 'Kind': 'coding'}).json()['taskId']

    def test_the_transcript_outlives_the_pty_and_the_task_can_still_be_wrapped(self):
        tid = self._task()
        t = terminal.Term(ECHO, os.getcwd(), 'coder', tid, 'coder', store=server.store)
        terminal.SESSIONS[t.sid] = t
        self.assertTrue(_wait(lambda: not t.alive))                     # it exited by itself
        self.assertTrue(_wait(lambda: server.store.last_transcript(tid) is not None))
        self.assertIn('hello-from-pty', server.store.last_transcript(tid)['Text'])
        # now the session is gone entirely, as the reaper would leave it
        terminal.SESSIONS.pop(t.sid, None)
        self.assertIsNone(terminal.session_for(tid))
        text, agent, sid = terminal.transcript_for(server.store, tid)
        self.assertIn('hello-from-pty', text)
        self.assertEqual((agent, sid), ('coder', t.sid))
        # ...and the buttons still have somewhere to point
        self.assertTrue(c.get(f'/api/tasks/{tid}').json()['transcript'])
        with mock.patch('taskuary.llm.build_llm', return_value=None):   # no AI: files the tail verbatim
            out = c.post(f'/api/tasks/{tid}/wrap', json={'close': True})
        self.assertEqual(out.status_code, 200)
        self.assertIn('hello-from-pty', out.json()['report'])

    def test_pause_works_off_a_dead_session_too(self):
        tid = self._task('paused after exit')
        t = terminal.Term(ECHO, os.getcwd(), 'coder', tid, 'coder', store=server.store)
        terminal.SESSIONS[t.sid] = t
        self.assertTrue(_wait(lambda: server.store.last_transcript(tid) is not None))
        terminal.SESSIONS.pop(t.sid, None)
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            out = c.post(f'/api/tasks/{tid}/pause', json={})
        self.assertEqual(out.status_code, 200)
        self.assertIn('hello-from-pty', out.json()['note'])
        # pausing is not finishing: the task stays open and nothing is drafted
        self.assertEqual(c.get(f'/api/tasks/{tid}').json()['task']['Status'], 'open')

    def test_a_task_that_never_had_a_session_says_so_instead_of_500ing(self):
        tid = self._task('no session ever')
        self.assertIsNone(c.get(f'/api/tasks/{tid}').json()['transcript'])
        self.assertEqual(c.post(f'/api/tasks/{tid}/wrap', json={'close': True}).status_code, 422)
        self.assertEqual(c.post('/api/tasks/999999/wrap', json={'close': True}).status_code, 422)

    def test_a_reply_drafted_from_the_mail_is_held_while_the_agent_works_and_rewritten_after(self):
        """Triage answers a question from the mail alone. Send that same task to a coding agent and
        the draft was still sitting in Review looking ready to send - promising a fix nobody had
        looked at yet. It waits, then comes back written from what the session found."""
        tid = self._task('held reply task')
        mid = server.store.add_message({'TaskId': tid, 'ExternalId': 'graph:HELD1', 'Channel': 'email',
                                        'FromEmail': 'asker@corp.com', 'SourceName': 'me@corp.com',
                                        'BodyText': 'is the import fixed?', 'Status': 'routed'})
        rid = server.store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                                       'DraftText': 'We will look into it.', 'Reason': 'needs a reply'})
        pending = lambda: [r['ReviewId'] for r in c.get('/api/reviews', params={'status': 'pending'}).json()['data']]
        self.assertIn(rid, pending())
        t = terminal.Term(ECHO, os.getcwd(), 'coder', tid, 'coder', store=server.store)
        terminal.SESSIONS[t.sid] = t
        server.store.hold_reviews(tid, 'held while an agent works the task')   # what open_session does
        self.assertNotIn(rid, pending())                                        # out of the queue
        held = [r['ReviewId'] for r in c.get('/api/reviews', params={'status': 'held'}).json()['data']]
        self.assertIn(rid, held)                                                # but visible, not vanished
        self.assertTrue(_wait(lambda: server.store.last_transcript(tid) is not None))
        terminal.SESSIONS.pop(t.sid, None)
        with mock.patch('taskuary.responder.write_draft', return_value='The import is fixed.') as wd:
            with mock.patch('taskuary.llm.build_llm', return_value=None):
                out = c.post(f'/api/tasks/{tid}/wrap', json={'close': True}).json()
        self.assertTrue(out['drafting'])
        self.assertEqual(wd.call_args.args[2], rid)          # the SAME review, not a second one
        self.assertIn(rid, pending())                        # back in the queue, rewritten
        self.assertIn('what it found', server.store.get_review(rid)['Reason'])

    def test_a_held_reply_can_be_released_without_waiting(self):
        tid = self._task('released reply task')
        mid = server.store.add_message({'TaskId': tid, 'Channel': 'email', 'ExternalId': 'graph:HELD2',
                                        'FromEmail': 'asker@corp.com', 'BodyText': 'any news?', 'Status': 'routed'})
        rid = server.store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                                       'DraftText': 'Looking now.', 'Reason': 'needs a reply'})
        server.store.hold_reviews(tid)
        self.assertEqual(c.post(f'/api/reviews/{rid}/release').status_code, 200)
        self.assertEqual(server.store.get_review(rid)['Status'], 'pending')
        self.assertEqual(c.post(f'/api/reviews/{rid}/release').status_code, 422)   # not held any more


class RepoRoutingTests(unittest.TestCase):
    """A wrong checkout means an agent editing the wrong tree in good faith. The real failure:
    SOUL.md knew about the reimbursement repo, the agent had a path for only ONE repo, and
    "the only repo this agent has a path for" won without the ask ever being read."""

    SOUL = ('## Repository map\n'
            '- **northwind/Census**: Python enterprise integration services, payroll imports, timesheets\n'
            '- **northwind/TopE**: a travel and expense reimbursement platform with AI receipt validation\n')

    def setUp(self):
        server.store.save_doc('soul', self.SOUL, 'test')
        server.store.upsert_agent('coder', 'coding', 'cli',
                                  json.dumps({'cmd': 'claude', 'cwd': os.getcwd(),
                                              'cwd_map': {'northwind/Census': os.getcwd()}}))

    def _task(self, title, summary=''):
        return c.post('/api/tasks', json={'Title': title, 'Summary': summary, 'Kind': 'coding'}).json()['taskId']

    def test_the_ask_beats_the_only_repo_that_happens_to_be_configured(self):
        prof = json.loads(server.store.get_agent('coder')['Config'])
        tid = self._task('Reimbursement app', 'approving reimbursements shows an error on each transaction')
        repo, why = terminal.guess_repo(server.store, tid, prof)
        self.assertEqual(repo, 'northwind/TopE')           # NOT the one with a path
        self.assertTrue(why)
        ranked = terminal.rank_repos(server.store, tid, prof)
        self.assertEqual(ranked[0][0], 'northwind/TopE')
        self.assertFalse(ranked[0][2])                   # ...and we know we have no path for it
        # a payroll task still goes to the integrations repo
        pay = self._task('payroll import posts to the wrong month', 'the timesheets import is off')
        self.assertEqual(terminal.guess_repo(server.store, pay, prof)[0], 'northwind/Census')

    def test_a_repo_with_no_path_refuses_instead_of_opening_the_wrong_folder(self):
        # find_checkout scans the REAL disk now, so the refusal only fires on a genuine miss -
        # pin that with a search that must come up empty. CI has no claude, so resolution is
        # mocked too: this test is about the repo guard, not the binary.
        with mock.patch.object(terminal, 'find_checkout', return_value=None),              mock.patch('taskuary.agents._resolve_cmd', return_value=[sys.executable]),              self.assertRaises(ValueError) as e:
            terminal.open_session(server.store, 'coder', self._task('x'), 'northwind/TopE')
        self.assertIn('no local path for northwind/TopE', str(e.exception))
        self.assertIn('search of your code folders', str(e.exception))
        self.assertIn('Pick the repository', str(e.exception))    # the fix is ON the task now
        self.assertIn('wrong tree', str(e.exception))

    def test_the_api_lists_every_repo_with_whether_it_can_be_opened(self):
        tid = self._task('Reimbursement app', 'approving reimbursements errors out')
        out = c.get(f'/api/tasks/{tid}/repos').json()
        self.assertEqual(out['picked'], 'northwind/TopE')
        by = {r['repo']: r for r in out['data']}
        self.assertFalse(by['northwind/TopE']['has_path'])
        self.assertTrue(by['northwind/Census']['has_path'])
        self.assertIn('reimbursement', by['northwind/TopE']['what'])

    def test_pinning_a_repo_overrides_the_guess_and_takes_the_path_with_it(self):
        tid = self._task('Reimbursement app', 'approving reimbursements errors out')
        here = os.getcwd()
        r = c.put(f'/api/tasks/{tid}/repo', json={'repo': 'northwind/TopE', 'path': here, 'agent': 'coder'})
        self.assertEqual(r.status_code, 200)
        prof = json.loads(server.store.get_agent('coder')['Config'])
        self.assertEqual(prof['cwd_map']['northwind/TopE'], here)          # the path stuck
        self.assertEqual(terminal.guess_repo(server.store, tid, prof), ('northwind/TopE', 'tagged on the task'))
        self.assertIn('repo:northwind/TopE', server.store.get_task(tid)['Tags'])
        # ...and the prompt now says so, which is the whole point
        self.assertIn('REPO: northwind/TopE', terminal.seed_text(server.store, tid, None, 'northwind/TopE', here))
        # a bad path is refused rather than silently stored
        self.assertEqual(c.put(f'/api/tasks/{tid}/repo',
                               json={'repo': 'northwind/TopE', 'path': os.path.join(here, 'nope')}).status_code, 422)
        # unpinning hands the choice back to the guess
        c.put(f'/api/tasks/{tid}/repo', json={'repo': None})
        self.assertNotIn('repo:', str(server.store.get_task(tid)['Tags'] or ''))


class FindCheckoutTests(unittest.TestCase):
    """"Why can't it find the local repo? It's there?" - it is, in a folder that is not named
    after the repo, which is why matching on the GIT REMOTE is the whole point."""

    def _tree(self):
        import tempfile
        root = Path(tempfile.mkdtemp())
        # the checkout, under a name that does not match the repo
        co = root / 'work' / 'oddname'
        (co / '.git').mkdir(parents=True)
        (co / '.git' / 'config').write_text('[remote "origin"]\n\turl = https://github.com/acme/widget.git\n')
        # a decoy with the right folder name but the wrong remote
        decoy = root / 'work' / 'widget'
        (decoy / '.git').mkdir(parents=True)
        (decoy / '.git' / 'config').write_text('[remote "origin"]\n\turl = https://github.com/other/widget-fork.git\n')
        (root / 'work' / 'node_modules' / 'widget').mkdir(parents=True)   # never descended into
        return root, co

    def test_finds_by_remote_not_by_folder_name(self):
        root, co = self._tree()
        hint = {'cwd': str(root / 'work' / 'somewhere-known')}
        (root / 'work' / 'somewhere-known').mkdir()
        found = terminal.find_checkout('acme/widget', hint)
        self.assertEqual(found, str(co))                       # oddname, because its REMOTE matches
        self.assertIsNone(terminal.find_checkout('acme/nothere', hint, seconds=1.0))

    def test_an_unreadable_git_config_does_not_crash_the_search(self):
        """A folder we cannot read used to 500 the repo picker: Path.is_file() on
        .git/config raises PermissionError, and that used to escape the walk."""
        import tempfile
        root = Path(tempfile.mkdtemp())
        known = root / 'work' / 'known'
        known.mkdir(parents=True)
        locked = root / 'work' / 'secret'
        (locked / '.git').mkdir(parents=True)
        (locked / '.git' / 'config').write_text(
            '[remote "origin"]\n\turl = https://github.com/acme/locked.git\n')
        locked.chmod(0)
        try:
            found = terminal.find_checkout(
                'acme/widget', {'cwd_map': {'acme/other': str(known)}}, budget=200, seconds=2)
            self.assertIsNone(found)
        finally:
            locked.chmod(0o755)

    def test_open_session_adopts_the_found_path_and_remembers_it(self):
        root, co = self._tree()
        server.store.upsert_agent('finder', 'coding', 'cli',
                                  json.dumps({'cmd': 'claude', 'cwd': str(root / 'work'),
                                              'cwd_map': {'acme/other': str(root / 'work')}}))
        try:
            with mock.patch.object(terminal, 'Term') as T,              mock.patch('taskuary.agents._resolve_cmd', return_value=[sys.executable]):
                T.return_value = mock.Mock(sid='x', cwd=str(co), info=lambda: {})
                terminal.open_session(server.store, 'finder', None, 'acme/widget')
                self.assertEqual(T.call_args.args[1], str(co))      # the session opens IN the checkout
            prof = json.loads(server.store.get_agent('finder')['Config'])
            self.assertEqual(prof['cwd_map']['acme/widget'], str(co))   # ...and it is remembered
        finally:
            terminal.SESSIONS.pop('x', None)     # the mock must not haunt later live_sessions() calls


class SeedCompletenessTests(unittest.TestCase):
    """What actually reaches the agent. Three separate ways the ask used to arrive short, and
    the worst of them was silent: the prompt says "work it from THIS message alone" while
    handing over a quarter of it."""

    def _task(self, body, title='long ask'):
        from taskuary.store import MemoryStore
        s = MemoryStore()
        tid = s.create_task({'Title': title, 'Kind': 'coding'}, 'o')
        s.add_message({'TaskId': tid, 'Channel': 'email', 'ExternalId': 'b1', 'FromName': 'Dana',
                       'FromEmail': 'd@x.example', 'Subject': 'Importer',
                       'SentAt': '2026-08-24 16:00:00', 'BodyText': body})
        return s, tid

    def test_a_long_message_is_not_quietly_quartered(self):
        body = 'x' * 11000
        s, tid = self._task(body)
        seed = terminal.seed_text(s, tid)
        self.assertIn('x' * 10900, seed)              # 3000 used to be the whole allowance

    def test_when_it_does_cut_it_says_so_and_says_how_much(self):
        s, tid = self._task('y' * 40000)
        seed = terminal.seed_text(s, tid)
        self.assertIn('truncated here', seed)
        self.assertIn('40,000 characters', seed)
        self.assertIn('Ask the owner for the rest', seed)

    def test_the_whole_prompt_stays_inside_a_command_line(self):
        """It travels as one argv element now; Windows refuses past 32767 without a word."""
        s, tid = self._task('z' * 200000)
        self.assertLessEqual(len(terminal.seed_text(s, tid)), terminal.SEED_CEILING + 500)

    def test_the_rules_survive_the_trim_and_the_ask_is_what_gives(self):
        """An agent that loses "work only in this repository" is more dangerous than one that
        loses the tail of a paragraph."""
        s, tid = self._task('z' * 200000)
        seed = terminal.seed_text(s, tid)
        for must in ('WHAT TO DO', 'Do NOT push', 'RULES:'):
            self.assertIn(must, seed, must)

    def test_the_NEWEST_message_is_the_ask(self):
        """Ordering decided this, and a stale stamp format used to put a three-day-old line
        last - so that was the one handed over. See StampTests in test_core."""
        s, tid = self._task('the older one')                    # stored 2026-08-24 16:00 local
        # the NEXT day in UTC, so it is later once converted in every timezone CI might run in
        # - and in the raw Graph shape, two-digit fraction and all, which is the exact string
        # that used to defeat normalization and sort this message to the top instead
        s.add_message({'TaskId': tid, 'Channel': 'teams', 'ExternalId': 'b2', 'FromName': 'Rich',
                       'SentAt': '2026-08-25T21:30:11.94Z', 'BodyText': 'the actual ask'})
        rows = s.list_messages(tid)
        self.assertEqual(rows[-1]['BodyText'], 'the actual ask')   # ordering, not luck
        self.assertIn('the actual ask', terminal.seed_text(s, tid))

    def test_a_short_message_is_passed_through_untouched(self):
        s, tid = self._task('the importer fails on Tuesdays')
        seed = terminal.seed_text(s, tid)
        self.assertIn('the importer fails on Tuesdays', seed)
        self.assertNotIn('truncated here', seed)
        self.assertIn('Missing required detail? Change nothing', seed)
        self.assertIn('if the sender must answer', seed)
