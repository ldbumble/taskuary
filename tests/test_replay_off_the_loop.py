"""A reopened pane is seeded with the session as a terminal would show it (terminal.replay_text) - a pyte draw of the
whole scrollback, 0.2-1 s a pane. It ran on the event loop, so opening the Wall froze every other socket, typing in a
live pane included, for seconds. It is drawn on one worker now, and these pin what must NOT change with it: the frames
a pane receives and their order, and the text of the seed."""
import ast, asyncio, os, sys, threading, time, unittest
from pathlib import Path
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import server, terminal

c = TestClient(server.app)
HERE = Path(__file__).resolve().parent.parent / 'taskuary'


def _wait(cond, secs=10.0):
    end = time.time() + secs
    while time.time() < end:
        if cond(): return True
        time.sleep(.02)
    return cond()


class ReplayOffTheLoopTests(unittest.TestCase):
    def _term(self, said=''):
        # the reviewed sleeper the geometry tests use (conftest allows only reviewed child programs); what it "printed" is
        # put in the scrollback directly, the way the pump would
        t = terminal.Term([sys.executable, '-c', 'import time; time.sleep(8)'], os.getcwd(), 'test', rows=24, cols=80)
        if said: t._append(said)
        terminal.SESSIONS[t.sid] = t
        self.addCleanup(terminal.close, t.sid)
        return t

    def test_output_that_lands_during_the_draw_follows_the_replay(self):
        """The order on the wire is the order it was when nothing else could run: geom, the replay, then live bytes."""
        t = self._term('earlier output\r\n')
        self.assertTrue(_wait(lambda: 'earlier output' in t.scrollback()))
        real = terminal.replay_text
        def slow(term, *a, **k):
            term._emit('LIVE-DURING-DRAW')            # a chunk arrives while the seed is still being drawn
            time.sleep(.3)
            return real(term, *a, **k)
        with mock.patch.object(terminal, 'replay_text', slow), c.websocket_connect(f'/api/terminals/{t.sid}/ws') as ws:
            frames = [ws.receive_json(), ws.receive_json()]
            while 'LIVE-DURING-DRAW' not in str(frames[-1].get('data')) and len(frames) < 8: frames.append(ws.receive_json())
        # ConPTY's own start-up bytes come when they come, in a frame of their own or beside ours; the replay leads either way
        self.assertEqual([f['type'] for f in frames[:2]], ['geom', 'out'])
        self.assertTrue(frames[1].get('replay'))
        self.assertIn('earlier output', frames[1]['data'])
        self.assertIn('LIVE-DURING-DRAW', frames[-1]['data'])
        self.assertFalse(any(f.get('replay') for f in frames[2:]))

    def test_the_draw_runs_on_the_replay_worker_not_the_loop(self):
        t, seen, real = self._term('a long session\r\n'), [], terminal.replay_text
        def where(term, *a, **k):
            try: asyncio.get_running_loop(); seen.append('event loop')
            except RuntimeError: seen.append(threading.current_thread().name)
            return real(term, *a, **k)
        with mock.patch.object(terminal, 'replay_text', where), c.websocket_connect(f'/api/terminals/{t.sid}/ws') as ws:
            self.assertEqual(ws.receive_json()['type'], 'geom')
            self.assertTrue(ws.receive_json().get('replay'))
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0].startswith('replay'), seen)

    def test_an_unchanged_screen_is_drawn_once_and_a_changed_one_again(self):
        class T:
            argv = ['claude']
            def __init__(s): s.buf, s.writes, s.n, s.rows, s.cols = ['hello\r\n'], 1, 7, 24, 80
            def scrollback(s): return ''.join(s.buf)
        t, calls, real = T(), [], terminal.render_at
        def counted(*a): calls.append(1); return real(*a)
        with mock.patch.object(terminal, 'render_at', counted):
            first = terminal.replay_snapshot(t)
            self.assertEqual(terminal.replay_snapshot(t), first)
            self.assertEqual(len(calls), 1)
            t.buf.append('world\r\n'); t.writes, t.n = 2, 14
            self.assertEqual(terminal.replay_snapshot(t), terminal.replay_text(t))
            t.rows = 10
            self.assertEqual(terminal.replay_snapshot(t), terminal.replay_text(t))
        self.assertEqual(first, terminal.replay_text(type('U', (), {'argv': ['claude'], 'rows': 24, 'cols': 80, 'scrollback': lambda s: 'hello\r\n'})()))

    def test_stand_ins_without_counters_draw_every_time(self):
        class R:
            argv, rows, cols = [], 32, 110
            def scrollback(s): return 'demo line\r\n'
        self.assertEqual(terminal.replay_snapshot(R()), terminal.replay_text(R()))


def test_no_scrollback_draw_runs_on_the_event_loop():
    """A pyte draw inside an `async def` holds every socket until it finishes. Through the replay worker only."""
    slow = {'replay_text', 'replay_snapshot', 'render', 'render_at', 'harvest'}
    for f in ('server.py', 'terminal.py'):
        tree = ast.parse((HERE / f).read_text(encoding='utf-8'))
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.AsyncFunctionDef): continue
            for n in ast.walk(fn):
                if isinstance(n, ast.Call):
                    name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, 'id', '')
                    assert name not in slow, f'{f}:{n.lineno} {fn.name} calls {name} on the event loop'
