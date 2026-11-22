"""The agent's browser beside its terminal: agent-browser's state files say a browser is open,
the relay pipes its screencast to the page (and the owner's input back), Snapshot files the
frame on the task. A fake screencast server stands in for agent-browser - no Chrome in CI."""
import pytest
import asyncio, base64, json, os, socket, sys, threading, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import browserview as bv, server, terminal
from taskuary.store import MemoryStore

c = TestClient(server.app)
JPEG = base64.b64encode(b'\xff\xd8\xff\xe0 not really a jpeg \xff\xd9').decode()


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0)); return s.getsockname()[1]


class FakeScreencast:
    """agent-browser's stream socket, minus the browser: greets a client with a frame and a url,
    remembers everything the client sends, and notes the query string it was asked with."""
    def __init__(self, greet=None):
        self.port, self.got, self.paths, self.origins, self.greet = _free_port(), [], [], [], greet
        self.loop = asyncio.new_event_loop(); self.ready = threading.Event()
        threading.Thread(target=self._run, daemon=True).start(); self.ready.wait(5)
    def _run(self):
        import websockets
        async def handle(ws):
            self.paths.append(ws.request.path); self.origins.append(ws.request.headers.get('Origin'))
            await ws.send(json.dumps({'type': 'status', 'connected': True}))
            if self.greet is not None:
                for m in self.greet: await ws.send(json.dumps(m))
                async for m in ws: self.got.append(json.loads(m))
                return
            # data FIRST, type last: the order agent-browser 0.38.2 actually sends (2026-10-02)
            await ws.send(json.dumps({'data': JPEG, 'metadata': {'deviceWidth': 1280, 'deviceHeight': 720}, 'seq': 7, 'type': 'frame'}))
            await ws.send(json.dumps({'type': 'url', 'url': 'https://example.test/login'}))
            async for m in ws: self.got.append(json.loads(m))
        async def main():
            async with websockets.serve(handle, '127.0.0.1', self.port):
                self.ready.set(); await asyncio.Event().wait()
        asyncio.set_event_loop(self.loop)
        try: self.loop.run_until_complete(main())
        except Exception: pass
    def stop(self): self.loop.call_soon_threadsafe(self.loop.stop)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(os.environ['TASKUARY_HOME']) / f'ab-{time.time_ns()}'; self.tmp.mkdir()
        self.env = mock.patch.dict(os.environ, {'AGENT_BROWSER_HOME': str(self.tmp)}); self.env.start()
        bv._CACHE.clear(); bv.LAST.clear()
    def tearDown(self): self.env.stop()

    def test_no_files_means_no_browser(self):
        self.assertEqual(bv.state('nobody'), {'open': False, 'url': '', 'port': 0})

    def test_a_stale_stream_file_is_not_an_open_browser(self):
        """The daemon idles out after an hour and leaves its files behind - `open` means the port answers."""
        (self.tmp / 'tq-s1.stream').write_text(str(_free_port()))
        (self.tmp / 'tq-s1.target').write_text(json.dumps({'url': 'https://x.test/'}))
        st = bv.state('s1')
        self.assertEqual((st['open'], st['url']), (False, 'https://x.test/'))

    def test_a_listening_port_is_an_open_browser_and_the_answer_is_cached(self):
        srv = socket.socket(); srv.bind(('127.0.0.1', 0)); srv.listen(1)
        try:
            (self.tmp / 'tq-s2.stream').write_text(str(srv.getsockname()[1]))
            self.assertTrue(bv.state('s2')['open'])
            srv.close()
            self.assertTrue(bv.state('s2')['open'])                # within the TTL: the listing poll does not re-probe
            self.assertFalse(bv.state('s2', fresh=True)['open'])   # the relay asks for the truth
        finally: srv.close()

    def test_a_cold_chrome_is_waited_for_rather_than_declared_absent(self):
        """A launch slower than the old ten seconds still counts as a launch.

        It came up seconds after start() had already returned False - and a False here is not a
        missing browser, it is an agent never handed the session name, driving a browser the owner's
        pane is not watching (2026-09-14)."""
        slept, opens = [], iter([False] * 60 + [True])
        with mock.patch.object(bv.shutil, 'which', return_value='agent-browser'), mock.patch.object(bv.spawn, 'popen'):
            with mock.patch.object(bv.time, 'sleep', slept.append), \
                 mock.patch.object(bv, 'state', side_effect=lambda sid, fresh=False: {'open': next(opens), 'url': '', 'port': 0}):
                self.assertTrue(bv.start('slow'))
        self.assertGreater(sum(slept), 10, 'it waited past the warm budget rather than giving up on it')

    @pytest.mark.real_chrome
    def test_the_session_s_chrome_is_a_real_one_taskuary_starts_and_agent_browser_attaches_to(self):
        """Cloudflare looped on agent-browser's own headless launch, whose navigator.webdriver is TRUE (the owner, 2026-11-16): the
        session's Chrome is an ordinary headed one Taskuary starts on the session's own port and profile, with no automation flag and
        never headless, and every agent-browser command of the session attaches to it (AGENT_BROWSER_CDP) - no `--args`, no UA of ours."""
        import tempfile
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {'AGENT_BROWSER_HOME': d}):
            (Path(d) / 'browsers' / 'chrome-152.0.7977.64').mkdir(parents=True); exe = Path(d) / 'browsers' / 'chrome-152.0.7977.64' / 'chrome.exe'
            exe.write_text('')
            # ...on a computer with no Chrome installed: the installed one comes first (chrome_exe), so it is out of the way for the whole launch
            no_chrome = mock.patch.object(bv, 'installed_chrome', return_value=''); no_chrome.start(); self.addCleanup(no_chrome.stop)
            self.assertEqual(bv.chrome_exe(), str(exe))
            e = bv.env('rc1'); port = bv.cdp_port('rc1')
            self.assertEqual(e['AGENT_BROWSER_CDP'], str(port)); self.assertNotIn('AGENT_BROWSER_USER_AGENT', e)
            self.assertEqual(bv.env('rc1')['AGENT_BROWSER_CDP'], str(port), 'one port per session, whoever asks')
            started, up = [], iter([False, False, True])
            with mock.patch.object(bv, '_spawn_chrome', side_effect=lambda argv, hidden=True: started.append(argv) or 4242),                  mock.patch.object(bv, '_listening', side_effect=lambda p, timeout=.25: next(up, True)), mock.patch.object(bv.time, 'sleep'):
                self.assertEqual(bv.real_chrome('rc1'), 4242)
            argv = started[0]
            self.assertEqual(argv[0], str(exe)); self.assertIn(f'--remote-debugging-port={port}', argv)
            self.assertIn('--disable-blink-features=AutomationControlled', argv)
            self.assertFalse([a for a in argv if 'headless' in a or 'enable-automation' in a])
            self.assertTrue(any(a.startswith('--user-data-dir=') and a.endswith('tq-rc1') for a in argv))
            # ...AND WHAT IT DOWNLOADS LANDS WHERE ITS AGENT MAY READ IT: a click on a download link saved into the owner's own Downloads
            # (recorded with agent-browser 0.41.2 on a real Chrome: AGENT_BROWSER_DOWNLOAD_PATH is not applied to a browser it attaches to),
            # and reading it back was a read outside the task, held. Chrome takes the folder from its profile's preferences at launch
            prof = Path(next(a for a in argv if a.startswith('--user-data-dir=')).split('=', 1)[1])
            prefs = json.loads((prof / 'Default' / 'Preferences').read_text(encoding='utf-8'))
            self.assertEqual(Path(prefs['download']['default_directory']).resolve(), bv.downloads('rc1').resolve())     # ...the session's own, however spelled (/var is /private/var on macOS)
            self.assertFalse(prefs['download']['prompt_for_download'])
            self.assertTrue(bv.downloads().is_dir()); self.assertIn(str(bv.downloads()), bv.brief())
            from taskuary import readgate
            self.assertTrue(any(readgate._in(readgate._n(bv.downloads() / 'invoice.pdf'), r) for r in readgate.own(None, None)))

    @pytest.mark.real_chrome
    def test_a_helper_left_by_a_command_before_the_launch_is_no_open_browser_and_start_launches_the_chrome(self):
        """0.4.0.15: any agent-browser command of a session before Taskuary started its Chrome left a helper pointed at a port nobody
        listened on. Its stream answered, so the browser read "open", start() launched nothing, and every command timed out with no Chrome
        running. Open means the Chrome answers too; start closes that helper and launches the Chrome, and the page is opened after."""
        stream = socket.socket(); stream.bind(('127.0.0.1', 0)); stream.listen(64)
        try:
            (self.tmp / 'tq-early.stream').write_text(str(stream.getsockname()[1])); (self.tmp / 'tq-early.pid').write_text('5150')
            self.assertFalse(bv.state('early', fresh=True)['open'], 'a helper with no Chrome under it is no open browser')
            done, chrome = [], {'up': False}
            def run(argv, **kw): done.append(('run', argv[-1])); return mock.Mock(returncode=0)
            def launched(sid): chrome['up'] = True; done.append(('chrome', sid)); return 4242
            with mock.patch.object(bv, 'program', return_value='ab'), mock.patch.object(bv.spawn, 'run', side_effect=run),                  mock.patch.object(bv, '_end_daemon', side_effect=lambda sid, pids=None: done.append(('end', pids))),                  mock.patch.object(bv, 'real_chrome', side_effect=launched), mock.patch.object(bv, 'chrome_up', side_effect=lambda sid: chrome['up']),                  mock.patch.object(bv.spawn, 'popen', side_effect=lambda cmd, **kw: done.append(('open', cmd[-1]))), mock.patch.object(bv, 'clock'):
                self.assertTrue(bv.start('early', 'https://portal.example'))
            self.assertEqual([d[0] for d in done], ['run', 'end', 'chrome', 'open'])      # the helper closed, then the Chrome, then the page
            self.assertEqual(done[1][1], [5150])
        finally: stream.close()

    def test_with_no_chrome_of_agent_browser_s_own_an_installed_one_is_run(self):
        """A computer whose agent-browser never fetched a Chrome (Taskuary's own runtime, a fresh install): the session's Chrome is the one
        installed on the computer - agent-browser's own launch fell back to it, and with none found here nothing would start at all."""
        import tempfile
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {'AGENT_BROWSER_HOME': d, 'LOCALAPPDATA': d}):
            os.environ.pop('AGENT_BROWSER_EXECUTABLE_PATH', None)
            mine = Path(d) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe'; mine.parent.mkdir(parents=True); mine.write_text('')
            with mock.patch.dict(os.environ, {'PROGRAMFILES': d + 'x', 'PROGRAMFILES(X86)': d + 'y'}), mock.patch.object(bv.shutil, 'which', return_value=None):
                self.assertEqual(bv.chrome_exe(), str(mine))

    @pytest.mark.real_chrome
    def test_a_chrome_that_cannot_start_on_its_own_desktop_starts_off_the_screen(self):
        if os.name != 'nt': self.skipTest('its own desktop is a Windows road')
        tried = []
        def spawn_chrome(argv, hidden=True):
            tried.append(hidden)
            if hidden: raise OSError('no desktop')
            return 77
        with mock.patch.object(bv, 'chrome_exe', return_value='chrome.exe'), mock.patch.object(bv, '_spawn_chrome', side_effect=spawn_chrome),              mock.patch.object(bv, '_listening', side_effect=lambda p, timeout=.25: bool(tried) and tried[-1] is False), mock.patch.object(bv.time, 'sleep'):
            self.assertEqual(bv.real_chrome('fallback'), 77)
        self.assertEqual(tried, [True, False])

    def test_the_session_name_rides_in_the_pty_environment(self):
        """Every pty gets AGENT_BROWSER_SESSION=tq-<sid>: whatever agent-browser command the agent
        runs lands in a session Taskuary can find - no cooperation from the agent needed."""
        self.assertEqual(bv.env('abc')['AGENT_BROWSER_SESSION'], 'tq-abc')
        self.assertEqual(terminal.clean_env({'AGENT_BROWSER_SESSION': 'tq-abc'})['AGENT_BROWSER_SESSION'], 'tq-abc')
        with mock.patch.dict(os.environ, {'AGENT_BROWSER_SESSION': 'inherited'}):
            self.assertEqual(terminal.clean_env(bv.env('x'))['AGENT_BROWSER_SESSION'], 'tq-x')   # ours wins over a parent's
        t = terminal.Term([sys.executable, '-c', "import os;print('SESS='+os.environ.get('AGENT_BROWSER_SESSION',''))"],
                          os.getcwd(), 'shell')
        try:
            end = time.time() + 20
            while time.time() < end and 'SESS=' not in t.scrollback(): time.sleep(.05)
            self.assertIn(f'SESS=tq-{t.sid}', t.scrollback())
        finally: t.close(); terminal.SESSIONS.pop(t.sid, None)

    def test_the_seed_names_the_browser_only_when_it_is_installed(self):
        with mock.patch('shutil.which', return_value=None): self.assertEqual(bv.hint(), '')
        with mock.patch('shutil.which', return_value='/usr/bin/agent-browser'):
            h = bv.hint()
            self.assertIn('agent-browser is installed', h)
            self.assertIn('Never type passwords', h)               # the owner types them, in the pane
            self.assertLess(len(h), 220)                           # the seed rides a capped tty line (test_terminal guards 1000)

    def test_close_is_a_no_op_without_the_tool_or_a_session(self):
        with mock.patch('shutil.which', return_value=None), mock.patch('subprocess.run') as run:
            bv.close('s9'); run.assert_not_called()
        with mock.patch('shutil.which', return_value='/x/agent-browser'), mock.patch('subprocess.run') as run:
            bv.close('s9'); run.assert_not_called()                # no .stream file: nothing to close
            (self.tmp / 'tq-s9.stream').write_text('1234')
            bv.close('s9')
            self.assertEqual(run.call_args.args[0], ['/x/agent-browser', '--session', 'tq-s9', 'close'])


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(os.environ['TASKUARY_HOME']) / f'ab-{time.time_ns()}'; self.tmp.mkdir()
        self.env = mock.patch.dict(os.environ, {'AGENT_BROWSER_HOME': str(self.tmp)}); self.env.start()
        bv._CACHE.clear(); bv.LAST.clear()
        self.fake = FakeScreencast()
        (self.tmp / 'tq-r1.stream').write_text(str(self.fake.port))
        (self.tmp / 'tq-r1.target').write_text(json.dumps({'url': 'https://example.test/'}))
    def tearDown(self): self.fake.stop(); self.env.stop()

    def test_state_endpoint_reads_the_files(self):
        j = c.get('/api/terminals/r1/browser').json()
        self.assertEqual((j['open'], j['url'], j['port']), (True, 'https://example.test/', self.fake.port))
        self.assertEqual(c.get('/api/terminals/none/browser').json()['open'], False)

    def test_frames_flow_to_the_page_and_acks_flow_back(self):
        """Ack pacing is asked of agent-browser on the URL and the RENDERER's acks are forwarded -
        a proxy acking on receipt would leave frames queued upstream."""
        with c.websocket_connect('/api/terminals/r1/browser/ws') as ws:
            kinds = [ws.receive_json()['type'] for _ in range(3)]
            self.assertEqual(kinds, ['status', 'frame', 'url'])
            ws.send_json({'type': 'ack', 'seq': 7})
            ws.send_json({'type': 'input_keyboard', 'eventType': 'keyDown', 'key': 'a', 'text': 'a'})
            end = time.time() + 5
            while time.time() < end and len(self.fake.got) < 2: time.sleep(.05)
        self.assertEqual([m['type'] for m in self.fake.got], ['ack', 'input_keyboard'])
        self.assertIn('pacing=ack', self.fake.paths[0]); self.assertIn(f'maxFps={bv.MAX_FPS}', self.fake.paths[0])
        self.assertEqual(self.fake.origins[0], 'http://localhost')     # agent-browser admits localhost origins only
        # the newest frame and the page it showed are kept for Snapshot and the listing
        self.assertEqual((bv._frame(bv.LAST['r1']['frame']), bv.LAST['r1']['url']), (JPEG, 'https://example.test/login'))
        self.assertEqual(bv.state('r1', fresh=True)['url'], 'https://example.test/login')

    def test_a_press_on_a_tab_switches_the_browser_to_it_and_is_never_sent_to_the_page(self):
        """The owner, 2026-11-15: several sites in one task are tabs of its one browser, and the view lists them. A press on one reaches
        agent-browser as `tab <id>` - an argv list, its own id form only - and never the stream, which has no such message; while a sign-in
        is typed it does nothing. The agent is told, in the one place it is told how its browser works, to work each site in a tab."""
        with mock.patch.object(bv, 'switch_tab', return_value=True) as sw, c.websocket_connect('/api/terminals/r1/browser/ws') as ws:
            for _ in range(3): ws.receive_json()
            ws.send_json({'type': 'tab', 'tab': 't2'}); ws.send_json({'type': 'tab', 'tab': 't2 & del x'}); ws.send_json({'type': 'ack', 'seq': 7})
            end = time.time() + 5
            while time.time() < end and not self.fake.got: time.sleep(.05)
        self.assertEqual([x.args for x in sw.call_args_list], [('r1', 't2')])
        self.assertEqual(self.fake.got, [{'type': 'ack', 'seq': 7}])
        with mock.patch.object(bv, 'program', return_value='agent-browser'), mock.patch.object(bv.spawn, 'popen') as po:
            po.return_value.wait.return_value = 0
            self.assertTrue(bv.switch_tab('r1', 't3'))
            self.assertEqual(po.call_args.args[0], ['agent-browser', '--session', 'tq-r1', 'tab', 't3'])
            self.assertFalse(bv.switch_tab('r1', 't3; rm'))
        self.assertIn('agent-browser tab new <url>', bv.brief()); self.assertIn('agent-browser tab new <url>', bv.guide())

    def test_a_page_the_agent_went_to_after_the_view_closed_is_the_page_named(self):
        """The view was shown for a sign-in and closed; the agent then went to ANOTHER site, with no relay to hear it. The address the view
        last heard outlived it: handed a human check there, the owner read "Your turn in the browser on <the first site>" over the second
        site's page, its address bar naming the first (the browser round, 2026-11-14). agent-browser's own word, written since, is the page."""
        with c.websocket_connect('/api/terminals/r1/browser/ws') as ws:
            for _ in range(3): ws.receive_json()
        self.assertEqual(bv.state('r1', fresh=True)['url'], 'https://example.test/login')      # the owner's own click moved it: the view's word stands
        t = self.tmp / 'tq-r1.target'
        t.write_text(json.dumps({'url': 'https://other.example/check'})); os.utime(t, (time.time() + 5, time.time() + 5))
        self.assertEqual(bv.state('r1', fresh=True)['url'], 'https://other.example/check')
        # ...the same page with its query cut off is no other page: the view's fuller word for it is kept (page_url)
        bv.remember('r1', json.dumps({'type': 'url', 'url': 'https://other.example/check?app=1'}))
        os.utime(t, (time.time() + 9, time.time() + 9))
        self.assertEqual(bv.state('r1', fresh=True)['url'], 'https://other.example/check?app=1')

    def test_the_view_opens_on_the_page_as_it_is_now_not_on_the_last_picture_it_showed(self):
        """agent-browser greets a new viewer with the frame it last sent anyone - a minute old, of the page before - and only then the page
        as it is. Handed a human check, the owner saw the account page of the site before under "Your turn ... on <this site>" for a beat
        (recorded, the browser round 2026-11-14). The old picture is dropped, and acked so the stream goes on; and the tabs it greets with
        say where the page is, query and all, before anything moves."""
        self.fake.stop()
        old, new = int((time.time() - 60) * 1000), int(time.time() * 1000)
        self.fake = FakeScreencast(greet=[
            {'type': 'status', 'connected': True, 'screencasting': False},
            {'type': 'tabs', 'tabs': [{'active': False, 'url': 'https://example.test/other'}, {'active': True, 'url': 'https://example.test/check?app=1'}]},
            {'data': 'T0xE', 'metadata': {'deviceWidth': 980, 'timestamp': old}, 'seq': 39, 'type': 'frame'},
            {'data': JPEG, 'metadata': {'deviceWidth': 980, 'timestamp': new}, 'seq': 40, 'type': 'frame'}])
        (self.tmp / 'tq-r1.stream').write_text(str(self.fake.port)); bv._CACHE.clear()
        with c.websocket_connect('/api/terminals/r1/browser/ws') as ws:
            got = [ws.receive_json() for _ in range(3)]
            end = time.time() + 5
            while time.time() < end and not self.fake.got: time.sleep(.05)
            got = got + [ws.receive_json()]
        self.assertEqual([(m['type'], m.get('seq')) for m in got], [('status', None), ('status', None), ('tabs', None), ('frame', 40)])
        self.assertEqual(self.fake.got[0], {'type': 'ack', 'seq': 39})
        self.assertEqual((bv._frame(bv.LAST['r1']['frame']), bv.state('r1', fresh=True)['url']), (JPEG, 'https://example.test/check?app=1'))
        # ...a still page someone else is already watching sends no newer picture: the one it greets with is the page, and is shown
        self.fake.stop(); self.fake = FakeScreencast(greet=[{'type': 'status', 'connected': True, 'screencasting': True},
                                                            {'data': JPEG, 'metadata': {'timestamp': old}, 'seq': 39, 'type': 'frame'}])
        (self.tmp / 'tq-r1.stream').write_text(str(self.fake.port)); bv._CACHE.clear()
        with c.websocket_connect('/api/terminals/r1/browser/ws') as ws:
            self.assertEqual([ws.receive_json().get('seq') for _ in range(3)][-1], 39)

    def test_a_frame_held_back_for_a_sign_in_is_acked_by_the_relay_so_the_view_comes_back(self):
        """While Taskuary types a sign-in no frame reaches the page - and under ack pacing a frame nobody acks is the last one sent: the
        view stood frozen on the sign-in form for good after the fill. The relay acks what it drops; the page's own ack still goes
        through mid-fill, and its keys and clicks do not."""
        bv.FILLING.add('r1'); self.addCleanup(bv.FILLING.discard, 'r1')
        with c.websocket_connect('/api/terminals/r1/browser/ws') as ws:
            self.assertEqual([ws.receive_json()['type'] for _ in range(2)], ['status', 'url'])     # the frame was held back
            ws.send_json({'type': 'ack', 'seq': 6})
            ws.send_json({'type': 'input_keyboard', 'eventType': 'keyDown', 'key': 'a', 'text': 'a'})
            ws.send_json({'type': 'ack', 'seq': 8})
            end = time.time() + 5
            while time.time() < end and len(self.fake.got) < 3: time.sleep(.05)
        self.assertEqual(self.fake.got, [{'type': 'ack', 'seq': 7}, {'type': 'ack', 'seq': 6}, {'type': 'ack', 'seq': 8}])

    def test_no_browser_refuses_the_socket_like_a_missing_terminal(self):
        from starlette.websockets import WebSocketDisconnect
        with self.assertRaises(WebSocketDisconnect) as cm:
            with c.websocket_connect('/api/terminals/nothing/browser/ws') as ws: ws.receive_json()
        self.assertEqual(cm.exception.code, 4404)

    def test_snapshot_files_the_frame_on_the_task(self):
        s = server.store
        tid = s.create_task({'Title': 'browser work', 'Kind': 'coding'}, 'o')
        s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'log in please', 'BodyText': 'x', 'Status': 'new'})
        self.assertEqual(c.post('/api/terminals/r1/browser/snapshot', json={'task_id': tid}).status_code, 422)   # no frame yet
        with c.websocket_connect('/api/terminals/r1/browser/ws') as ws:
            for _ in range(3): ws.receive_json()
        j = c.post('/api/terminals/r1/browser/snapshot', json={'task_id': tid}).json()
        self.assertEqual(j['page'], 'https://example.test/login'); self.assertTrue(j['name'].endswith('.jpg'))
        atts = c.get(f"/api/messages/{s.list_messages(tid)[0]['MessageId']}/attachments").json()['data']
        self.assertEqual([(a['name'], a['content_type'], a['is_image']) for a in atts], [(j['name'], 'image/jpeg', True)])
        r = c.get(j['url'])
        self.assertEqual((r.status_code, r.content), (200, base64.b64decode(JPEG)))
        self.assertIn('Browser snapshot of https://example.test/login', s.list_comments(tid)[-1]['Body'])
        # a session on no task, with no task named, is refused - not attached to a guess
        self.assertEqual(c.post('/api/terminals/r1/browser/snapshot', json={}).status_code, 422)

    def test_a_snapshot_names_a_page_the_relay_never_heard_a_url_for(self):
        """A pane opened on a page already loaded gets frames and no url message - the page still has a name."""
        s = server.store
        tid = s.create_task({'Title': 'portal', 'Kind': 'general'}, 'o')
        s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'x', 'BodyText': 'x', 'Status': 'new'})
        bv.remember('r1', json.dumps({'data': JPEG, 'type': 'frame'}))
        self.assertEqual(c.post('/api/terminals/r1/browser/snapshot', json={'task_id': tid}).json()['page'], 'https://example.test/')


class RememberTests(unittest.TestCase):
    """What Snapshot files. The kind was read off the message's HEAD, and agent-browser 0.38.2 puts `data`
    first - so no frame was ever kept and Snapshot answered "no frame yet" over a painting page (2026-10-02)."""
    def setUp(self): bv.LAST.clear()

    def test_a_frame_is_kept_whatever_order_its_keys_come_in(self):
        for i, m in enumerate([{'type': 'frame', 'seq': 1, 'data': 'QUFB'}, {'data': 'QkJC', 'seq': 2, 'type': 'frame'},
                               {'seq': 3, 'data': 'Q0ND', 'metadata': {'deviceWidth': 9}, 'type' : 'frame'}]):
            bv.remember('k', json.dumps(m, separators=(',', ':') if i else (', ', ': ')))
            self.assertEqual(bv._frame(bv.LAST['k']['frame']), m['data'])

    def test_the_page_is_kept_and_nothing_else_is(self):
        bv.remember('k', json.dumps({'url': 'https://a.example/', 'type': 'url'}))
        for m in [{'type': 'status', 'connected': False}, {'type': 'tabs', 'tabs': []},
                  {'type': 'console', 'text': '"type":"frame"'}, {'type': 'url', 'url': 'https://b.example/?q="type":"frame"'}]:
            bv.remember('k', json.dumps(m))
        self.assertEqual((bv.LAST['k']['frame'], bv.LAST['k']['url']), ('', 'https://b.example/?q="type":"frame"'))
        bv.remember('k', 'not json "type":"url"'); bv.remember('k', '{"type":"url"}')   # junk and an empty url change nothing
        self.assertEqual(bv.LAST['k']['url'], 'https://b.example/?q="type":"frame"')


class NavigateTests(unittest.TestCase):
    """The owner's own address bar. The agent is told to hand the keyboard over for a password or
    a 2FA code, and until this there was nowhere to hand it to: Take over forwards clicks, and
    about:blank has nothing to click."""
    def setUp(self):
        self.calls = []
        self.open = mock.patch.object(bv, 'state', side_effect=lambda sid, fresh=False: {'open': sid != 'dead', 'url': '', 'port': 1})
        self.which = mock.patch.object(bv.shutil, 'which', return_value='agent-browser')
        self.open.start(); self.which.start()
        def popen(argv, **kw):
            self.calls.append((argv, kw))
            return mock.Mock(wait=mock.Mock(return_value=0), kill=mock.Mock())
        self.popen = mock.patch.object(bv.spawn, 'popen', side_effect=popen); self.popen.start()
        # ...and the session's own Chrome, which a command first asks over its DevTools port whether a load is stuck (browserview.unstick):
        # none answers here - left real, it reached for a port on this machine, and macOS CI's guard refused it (2026-11-18)
        self.cdp = mock.patch.object(bv, '_devtools', return_value=None); self.cdp.start()
    def tearDown(self):
        for p in (self.open, self.which, self.popen, self.cdp): p.stop()

    def test_a_bare_host_is_https_and_the_argv_is_a_list(self):
        self.assertEqual(bv.navigate('s', ' adp.com/login '), 'https://adp.com/login')
        argv, _ = self.calls[0]
        self.assertEqual(argv[:4], ['agent-browser', '--session', 'tq-s', 'open'])
        self.assertEqual(argv[4], 'https://adp.com/login')

    @unittest.skipUnless(sys.platform == 'win32', "builds Windows paths - pathlib cannot make them elsewhere")
    def test_on_windows_the_npm_shim_is_skipped_so_an_ampersand_stays_in_the_address(self):
        """npm's agent-browser.cmd runs through cmd.exe, which cut https://portal.example/?app=1&return=... at the & and ran the rest
        as a command - the page sat on a white spinner. The shim only starts the .exe beside it, so the .exe is what runs."""
        d = Path(os.environ['TASKUARY_HOME']) / f'npm-{time.time_ns()}'
        native = d / 'node_modules' / 'agent-browser' / 'bin' / 'agent-browser-win32-x64.exe'
        native.parent.mkdir(parents=True); native.write_bytes(b''); (d / 'agent-browser.cmd').write_text('@ECHO off')
        url = 'https://portal.example/signin/?app=1&return=https://portal.example/home&target=%23/home'
        with mock.patch.object(bv.shutil, 'which', return_value=str(d / 'agent-browser.cmd')), mock.patch.object(bv.os, 'name', 'nt'), \
             mock.patch('platform.machine', return_value='AMD64'):
            self.assertEqual(bv.program(), str(native))
            bv.navigate('s', url)
        self.assertEqual(self.calls[0][0], [str(native), '--session', 'tq-s', 'open', url])
        # ...and elsewhere, or with no .exe beside the shim, it is what PATH says
        with mock.patch.object(bv.shutil, 'which', return_value='/usr/bin/agent-browser'): self.assertEqual(bv.program(), '/usr/bin/agent-browser')
        native.unlink()
        with mock.patch.object(bv.shutil, 'which', return_value=str(d / 'agent-browser.cmd')), mock.patch.object(bv.os, 'name', 'nt'):
            self.assertEqual(bv.program(), str(d / 'agent-browser.cmd'))

    def test_only_http_addresses_are_opened(self):
        """A pane that runs whatever is typed at it is a hole; http(s) is the whole job here."""
        for bad in ('file:///c:/secrets.txt', 'javascript:alert(1)', 'data:text/html,<b>x', 'chrome://net-internals'):
            with self.assertRaises(ValueError): bv.navigate('s', bad)
        self.assertEqual(self.calls, [])

    def test_nothing_typed_and_no_browser_are_both_refused(self):
        with self.assertRaises(ValueError): bv.navigate('s', '   ')
        with self.assertRaises(ValueError): bv.navigate('dead', 'example.com')
        self.assertEqual(self.calls, [])

    def test_the_output_never_goes_to_a_pipe(self):
        """THE REGRESSION THIS GUARDS. `open` leaves a daemon running and the daemon INHERITS the
        pipe, so a captured call waits for a process built to outlive it - and `timeout` does not
        save you: TimeoutExpired kills the CLI, then blocks again draining the same pipe. Measured
        on Windows: a piped open asked to give up after 45s returned after 156.9s, when the browser
        was closed by hand. A request thread would hang there, and the owner would never be told
        whether his page opened."""
        bv.navigate('s', 'example.com')
        _, kw = self.calls[0]
        self.assertNotIn(bv.subprocess.PIPE, (kw.get('stdout'), kw.get('stderr')))
        self.assertEqual(kw.get('stdin'), bv.subprocess.DEVNULL)

    def test_a_refusal_says_what_agent_browser_said(self):
        log = Path(bv.tempfile.gettempdir()) / 'tq-s-open.log'
        def popen(argv, **kw):
            log.write_bytes(b'noise\nError: net::ERR_NAME_NOT_RESOLVED\n')
            return mock.Mock(wait=mock.Mock(return_value=1), kill=mock.Mock())
        with mock.patch.object(bv.spawn, 'popen', side_effect=popen):
            with self.assertRaises(ValueError) as e: bv.navigate('s', 'nope.test')
        self.assertIn('ERR_NAME_NOT_RESOLVED', str(e.exception))

    def test_a_page_that_never_loads_kills_the_cli_and_says_so(self):
        killed = mock.Mock()
        def popen(argv, **kw):
            return mock.Mock(wait=mock.Mock(side_effect=bv.subprocess.TimeoutExpired(argv, 1)), kill=killed)
        with mock.patch.object(bv.spawn, 'popen', side_effect=popen):
            with self.assertRaises(ValueError) as e: bv.navigate('s', 'slow.test')
        self.assertTrue(killed.called)
        self.assertIn('watch the pane', str(e.exception))

    def test_the_endpoint_answers_with_the_address_it_opened(self):
        r = c.post('/api/terminals/s/browser/open', json={'url': 'adp.com'})
        self.assertEqual((r.status_code, r.json()), (200, {'url': 'https://adp.com'}))
        self.assertEqual(c.post('/api/terminals/s/browser/open', json={'url': 'file:///etc/passwd'}).status_code, 422)


if __name__ == '__main__': unittest.main()


class StuckLoadTests(unittest.TestCase):
    """A page whose server takes the connection and never answers: agent-browser's `open` gave up after ~30 s with the load still pending,
    and every command of the session after it - `get url`, `snapshot`, the next `open`, the sign-in's `get cdp-url` - hung behind it
    (measured on 0.41.2). The load is stopped over the session's own DevTools port before the next command, and after one of Taskuary's own."""

    def setUp(self):
        from taskuary import signin
        self.stopped, self.pages = [], [{'type': 'page', 'id': 'A', 'url': 'https://slow.example/report'},     # pending: history is elsewhere
                                         {'type': 'page', 'id': 'B', 'url': 'https://portal.example/runs#top'}]  # settled
        on = {'A': 'https://portal.example/', 'B': 'https://portal.example/runs'}
        test = self
        class Cdp:
            def __init__(self, ws, target): self.t = target
            def call(self, method, params=None, top=False, timeout=10.0):
                if method == 'Page.stopLoading': test.stopped.append(self.t)
                return {'currentIndex': 0, 'entries': [{'url': on[self.t]}]} if method == 'Page.getNavigationHistory' else {}
            def close(self): pass
        answers = lambda sid, path: {'webSocketDebuggerUrl': 'ws://127.0.0.1:9/devtools/browser/x'} if path == '/json/version' else self.pages
        for p in (mock.patch.object(signin, 'Cdp', Cdp), mock.patch.object(bv, '_devtools', side_effect=answers)):
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(bv._BEGAN.pop, 'st', None)

    def test_a_load_left_pending_past_its_wait_is_stopped_before_the_next_command(self):
        bv._BEGAN['st'] = time.time() - bv.STUCK - 5
        self.assertTrue(bv.began('st'))
        self.assertEqual(self.stopped, ['A'])

    def test_a_load_still_inside_its_wait_is_left_alone(self):
        bv._BEGAN['st'] = time.time() - 3                   # a click that is navigating now, and a look right after it
        self.assertFalse(bv.began('st'))
        self.assertEqual(self.stopped, [])

    def test_an_open_of_taskuarys_own_that_failed_on_it_says_it_was_stopped_and_the_next_look_runs(self):
        from taskuary import browsergate
        def popen(argv, **kw):
            kw['stdout'].write(b'Failed to read: Resource temporarily unavailable (os error 11)\n')
            return mock.Mock(wait=mock.Mock(return_value=1), kill=mock.Mock())
        with mock.patch.object(bv, 'program', return_value='agent-browser'), mock.patch.object(bv.spawn, 'popen', side_effect=popen), \
             mock.patch.object(bv, 'STUCK', 0):
            rc, said = browsergate._run('st', ['open', 'https://slow.example/report'], 45, 'api')
        self.assertEqual(rc, 1); self.assertIn(bv.STOPPED, said); self.assertEqual(self.stopped, ['A'])

    def test_the_owners_address_bar_says_it_in_one_plain_line(self):
        def popen(argv, **kw):
            kw['stdout'].write(b'Failed to read: Resource temporarily unavailable (os error 11)\n')
            return mock.Mock(wait=mock.Mock(return_value=1), kill=mock.Mock())
        with mock.patch.object(bv, 'program', return_value='agent-browser'), mock.patch.object(bv.spawn, 'popen', side_effect=popen), \
             mock.patch.object(bv, 'state', return_value={'open': True}), mock.patch.object(bv, 'STUCK', 0):
            with self.assertRaises(ValueError) as e: bv.navigate('st', 'https://slow.example/report')
        self.assertTrue(str(e.exception).startswith('It had not finished loading')); self.assertIn('Taskuary stopped it', str(e.exception))

    def test_the_agents_next_browser_line_stops_it_first(self):
        from taskuary import browsergate, gatecmd
        bv._BEGAN['st'] = time.time() - bv.STUCK - 5
        with mock.patch.object(bv, 'on_demand'), mock.patch.object(browsergate, 'check', return_value={}):
            gatecmd.judge(MemoryStore(), 1, 'st', 'agent-browser get url')
        self.assertEqual(self.stopped, ['A'])

    def test_the_sign_in_reaches_chrome_on_its_own_port_not_through_agent_browser(self):
        from taskuary import signin
        with mock.patch.object(bv.spawn, 'popen') as asked:
            self.assertEqual(signin._cdp_url('st'), 'ws://127.0.0.1:9/devtools/browser/x')
        asked.assert_not_called()


class TheAddressIsTheTabsOwnTests(unittest.TestCase):
    """agent-browser rewrites its .target only at its next command: after an open that errored ("This site can't be reached") or never
    finished, the file still named the page before it - the PAGE an API agent read, the page an act was judged on, and the site a sign-in
    ask was pinned to and the owner shown."""

    def setUp(self):
        files = {'target': json.dumps({'targetId': 'T1', 'url': 'https://portal.example/runs'}), 'stream': '4242'}
        self.tabs = [{'type': 'page', 'id': 'T0', 'url': 'about:blank'}, {'type': 'page', 'id': 'T1', 'url': 'https://login.vendor.example/signin?next=%2F'}]
        for p in (mock.patch.object(bv, '_read', side_effect=lambda name, ext: files.get(ext, '')), mock.patch.object(bv, '_listening', return_value=True),
                  mock.patch.object(bv, '_devtools', side_effect=lambda sid, path: self.tabs)):
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(bv._CACHE.pop, 't1', None)

    def test_the_tab_agent_browser_names_is_read_live_from_its_chrome(self):
        from taskuary import browsergate, signin
        self.assertEqual(bv.state('t1', fresh=True)['url'], 'https://login.vendor.example/signin?next=%2F')
        self.assertEqual(browsergate.address('t1'), 'https://login.vendor.example/signin?next=%2F')
        self.assertEqual(signin.site_of(bv.state('t1', fresh=True)['url']), 'vendor.example')

    def test_a_chrome_that_does_not_answer_leaves_the_file_as_before(self):
        self.tabs = None
        self.assertEqual(bv.state('t1', fresh=True)['url'], 'https://portal.example/runs')


# A WINDOW THE PAGE OPENS IS FOLLOWED (the owner, live 2026-11-19: "Continue with Google" on a site's sign-in did nothing he could see)


def test_google_s_own_refusal_page_is_said_with_the_way_past_it():
    told = []
    with mock.patch('taskuary.terminal.get', return_value=SimpleNamespace(task_id=7)),             mock.patch.object(bv, 'your_turn', side_effect=lambda st, tid, sid, what='': told.append(what)), mock.patch('taskuary.browsergate._tell'):
        assert bv.refused('fw2', 'https://accounts.google.com/v3/signin/rejected?continue=x')
        assert not bv.refused('fw2', 'https://accounts.google.com/v3/signin/rejected')          # once a session
        assert not bv.refused('fw3', 'https://accounts.google.com/v3/signin/identifier')
    assert told == [bv.REFUSED_WHAT] and 'email and password' in told[0]


# A HUMAN CHECK IS HIS, AT ONCE, and A DOWNLOAD IS TOLD BY ITS PATH (the owner, 2026-11-19: "the browser must work like a regular user's; no dead ends")
def test_a_human_check_that_stands_is_handed_to_him_once_and_one_that_clears_is_nobodys():
    tl = [{'type': 'page', 'id': 'P', 'url': 'https://portal.vendor.example/login'},
          {'type': 'iframe', 'id': 'F', 'url': 'https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile'}]
    handed, told, seen = [], [], {}
    with mock.patch.object(bv, '_devtools', return_value=tl), mock.patch.object(bv, 'active_tab', return_value='P'), \
            mock.patch.object(bv, 'HUMAN_AFTER', 0), mock.patch('taskuary.terminal.get', return_value=SimpleNamespace(task_id=7)), \
            mock.patch.object(bv, 'your_turn', side_effect=lambda st, tid, sid, what='': handed.append(what)), \
            mock.patch('taskuary.browsergate._tell', side_effect=lambda st, tid, text, **k: told.append(text)):
        assert bv.human('hc1', seen) and not bv.human('hc1', seen)                       # once a page
    assert handed == [bv.HUMAN_WHAT] and "I'm done" in handed[0] and 'wait' in told[0]
    with mock.patch.object(bv, '_devtools', return_value=tl[:1]), mock.patch.object(bv, 'active_tab', return_value='P'):
        assert not bv.human('hc2', {})                                                    # no check on the page: nothing


def test_a_finished_download_is_told_by_its_path(tmp_path):
    told = []
    with mock.patch.object(bv, 'downloads', return_value=tmp_path), mock.patch('taskuary.terminal.get', return_value=SimpleNamespace(task_id=7)), \
            mock.patch('taskuary.browsergate._tell', side_effect=lambda st, tid, text, **k: told.append(text)):
        had = bv.arrived('dl1', set())
        (tmp_path / 'statement.pdf.crdownload').write_text('x'); had = bv.arrived('dl1', had)
        assert told == []                                                                 # still coming
        (tmp_path / 'statement.pdf').write_text('x'); bv.arrived('dl1', had)
    assert len(told) == 1 and str(tmp_path / 'statement.pdf') in told[0] and 'outputs folder' in told[0]
