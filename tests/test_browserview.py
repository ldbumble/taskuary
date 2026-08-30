"""The agent's browser beside its terminal: agent-browser's state files say a browser is open,
the relay pipes its screencast to the page (and the owner's input back), Snapshot files the
frame on the task. A fake screencast server stands in for agent-browser - no Chrome in CI."""
import asyncio, base64, json, os, socket, sys, threading, time, unittest
from pathlib import Path
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import browserview as bv, server, terminal

c = TestClient(server.app)
JPEG = base64.b64encode(b'\xff\xd8\xff\xe0 not really a jpeg \xff\xd9').decode()


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0)); return s.getsockname()[1]


class FakeScreencast:
    """agent-browser's stream socket, minus the browser: greets a client with a frame and a url,
    remembers everything the client sends, and notes the query string it was asked with."""
    def __init__(self):
        self.port, self.got, self.paths, self.origins = _free_port(), [], [], []
        self.loop = asyncio.new_event_loop(); self.ready = threading.Event()
        threading.Thread(target=self._run, daemon=True).start(); self.ready.wait(5)
    def _run(self):
        import websockets
        async def handle(ws):
            self.paths.append(ws.request.path); self.origins.append(ws.request.headers.get('Origin'))
            await ws.send(json.dumps({'type': 'status', 'connected': True}))
            await ws.send(json.dumps({'type': 'frame', 'seq': 7, 'data': JPEG, 'metadata': {'deviceWidth': 1280, 'deviceHeight': 720}}))
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
        self.assertEqual((bv.LAST['r1']['seq'], bv.LAST['r1']['url']), (7, 'https://example.test/login'))
        self.assertEqual(bv.state('r1', fresh=True)['url'], 'https://example.test/login')

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


if __name__ == '__main__': unittest.main()
