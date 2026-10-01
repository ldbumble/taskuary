"""One PTY, one geometry owner.

A session can be on screen in several places at once - the task page, a Wall cell, the Feed
preview, an assistant card - and every one of them mounts its own xterm, fits it to its OWN box
and sends that size to the same PTY. The server arbitrated nothing, so the last socket to speak
won: the Wall's grid cell (~70 cols) would resize the PTY out from under the full-width task
page (~140), or the other way round. A full-screen TUI then paints with absolute cursor moves
computed for a width the other emulator does not have, its partial updates land on rows it never
wrote, and the pane shows two frames at once - "something in front and something behind"
(the owner, 2026-09-16, photographed on the Wall while the task page held the same session).

`TerminalPane` has always taken a `readOnly` prop to suppress exactly this, and the comment above
it names the hazard - but no call site ever passed it, so the guard never ran anywhere.

The rule: the first socket to attach owns the geometry and keeps it until it disconnects; the
next attach claims it. Everyone else is told the PTY's real size and renders at that.
"""
import os
import sys
import time
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import terminal
from taskuary.server import app

c = TestClient(app)


def _until_ready(ws, cap=12):
    """Collect frames up to the server's curtain barrier. `ready` always arrives, so a missing
    `geom` fails the assertion instead of blocking the socket for ever."""
    out = []
    for _ in range(cap):
        out.append(ws.receive_json())
        if out[-1].get('type') == 'ready': break
    return out


def _wait(cond, secs=2.0):
    end = time.time() + secs
    while time.time() < end:
        if cond(): return True
        time.sleep(.02)
    return cond()


class GeometryOwnerTests(unittest.TestCase):
    def setUp(self):
        self.t = terminal.Term([sys.executable, '-c', 'import time; time.sleep(8)'], os.getcwd(), 'test',
                               rows=40, cols=140)
        terminal.SESSIONS[self.t.sid] = self.t
        self.addCleanup(terminal.close, self.t.sid)

    def test_a_second_pane_cannot_resize_the_pty_under_the_first(self):
        """The Wall cell is small and the task page is wide. Whoever attached first keeps the PTY."""
        sizes = []
        with mock.patch.object(self.t, 'resize', side_effect=lambda r, cl: sizes.append((r, cl))):
            with c.websocket_connect(f'/api/terminals/{self.t.sid}/ws') as first:
                first.send_json({'type': 'resize', 'rows': 40, 'cols': 140})
                self.assertTrue(_wait(lambda: sizes == [] or sizes[-1] == (40, 140)))
                with c.websocket_connect(f'/api/terminals/{self.t.sid}/ws') as second:
                    second.send_json({'type': 'resize', 'rows': 20, 'cols': 70})
                    second.send_json({'type': 'in', 'data': ''})      # ordering fence
                    time.sleep(.15)
        self.assertNotIn((20, 70), sizes,
                         'the second pane resized the PTY out from under the first')

    def test_the_second_pane_is_told_the_size_it_must_render_at(self):
        """Ignoring its resize is only half the fix: a pane rendering 140-column output in a
        70-column xterm wraps where the child did not, which is the same corruption. The server
        says what the geometry IS, so a non-owner can match it instead of fitting its box."""
        with c.websocket_connect(f'/api/terminals/{self.t.sid}/ws') as first:
            first.send_json({'type': 'resize', 'rows': 40, 'cols': 140})
            with c.websocket_connect(f'/api/terminals/{self.t.sid}/ws') as second:
                second.send_json({'type': 'resize', 'rows': 20, 'cols': 70})
                frames = _until_ready(second)
        geom = [f for f in frames if f.get('type') == 'geom']
        self.assertTrue(geom, f'no geom frame told the second pane the PTY size: {frames}')
        self.assertEqual((geom[-1]['rows'], geom[-1]['cols'], geom[-1]['owner']), (40, 140, False))

    def test_the_first_pane_is_told_it_owns_the_geometry(self):
        with c.websocket_connect(f'/api/terminals/{self.t.sid}/ws') as first:
            first.send_json({'type': 'resize', 'rows': 40, 'cols': 140})
            frames = _until_ready(first)
        geom = [f for f in frames if f.get('type') == 'geom']
        self.assertTrue(geom, f'the owner was never told it owns the geometry: {frames}')
        self.assertTrue(geom[0]['owner'])

    def test_ownership_is_released_when_the_owner_closes(self):
        """Close the task page and the Wall must be able to drive the PTY - otherwise a session
        you only ever look at on the Wall is stuck at whatever the first pane left behind."""
        sizes = []
        with mock.patch.object(self.t, 'resize', side_effect=lambda r, cl: sizes.append((r, cl))):
            with c.websocket_connect(f'/api/terminals/{self.t.sid}/ws') as first:
                first.send_json({'type': 'resize', 'rows': 40, 'cols': 140})
                time.sleep(.1)
            with c.websocket_connect(f'/api/terminals/{self.t.sid}/ws') as second:
                second.send_json({'type': 'resize', 'rows': 20, 'cols': 70})
                second.send_json({'type': 'in', 'data': ''})
                self.assertTrue(_wait(lambda: (20, 70) in sizes),
                                'the second pane never inherited the geometry')


    def test_a_pane_put_away_hands_the_geometry_back(self):
        """The page keeps the last few panes alive when you switch away, so switching back is instant. A pane kept that
        way stays connected - and while it held the geometry, the Wall could never size the pty to its own cells."""
        sizes = []
        with mock.patch.object(self.t, 'resize', side_effect=lambda r, cl: sizes.append((r, cl))):
            with c.websocket_connect(f'/api/terminals/{self.t.sid}/ws') as kept:
                kept.send_json({'type': 'resize', 'rows': 40, 'cols': 140})
                kept.send_json({'type': 'release'})
                kept.send_json({'type': 'in', 'data': ''})
                time.sleep(.15)
                with c.websocket_connect(f'/api/terminals/{self.t.sid}/ws') as wall:
                    wall.send_json({'type': 'resize', 'rows': 20, 'cols': 70})
                    wall.send_json({'type': 'in', 'data': ''})
                    self.assertTrue(_wait(lambda: (20, 70) in sizes), 'the kept pane still held the geometry')

    def test_every_pane_hears_the_pty_change_size(self):
        """A kept pane is out of sight while another surface resizes the pty. If it went on drawing at the old size, the
        CLI's repaint for the new one would land in it wrapped wrong, and showing it again at an unchanged size would
        bring that back with no repaint to fix it. So every socket is told, in order with the bytes."""
        tick = terminal.Term([sys.executable, os.path.join(os.path.dirname(__file__), 'fake_tui.py')], os.getcwd(), 'test',
                             rows=40, cols=140)          # it answers a line, so a missed frame fails rather than hangs
        terminal.SESSIONS[tick.sid] = tick
        self.addCleanup(terminal.close, tick.sid)
        with c.websocket_connect(f'/api/terminals/{tick.sid}/ws') as owner:
            owner.send_json({'type': 'resize', 'rows': 40, 'cols': 140})
            _until_ready(owner)
            with c.websocket_connect(f'/api/terminals/{tick.sid}/ws') as kept:
                kept.send_json({'type': 'release'})
                _until_ready(kept)                                     # the attach geom, then the curtain lifts
                owner.send_json({'type': 'resize', 'rows': 30, 'cols': 100})
                owner.send_json({'type': 'in', 'data': 'hello' + chr(13)})
                frames = [kept.receive_json() for _ in range(12)]
                geom = [f for f in frames if f.get('type') == 'geom']
        self.assertTrue(geom, f'the kept pane never heard the pty change size: {frames}')
        self.assertEqual((geom[0]['rows'], geom[0]['cols'], geom[0]['owner']), (30, 100, False))


    def test_a_pane_back_on_screen_asking_for_the_size_it_already_has_is_answered(self):
        """A kept pane coming back does not fit itself first - if another pane owns the geometry it would shrink to its
        box and grow back, and that moves its rows (2026-10-01, on the Wall). It asks, and waits for the answer. When the
        pty is already the size it asks for, silence would leave it believing it owns nothing."""
        with c.websocket_connect(f'/api/terminals/{self.t.sid}/ws') as kept:
            kept.send_json({'type': 'resize', 'rows': 40, 'cols': 140})
            _until_ready(kept)
            kept.send_json({'type': 'release'})
            kept.send_json({'type': 'resize', 'rows': 40, 'cols': 140})          # back on screen, same size
            geom = kept.receive_json()
        self.assertEqual((geom['type'], geom['rows'], geom['cols'], geom['owner']), ('geom', 40, 140, True))


if __name__ == '__main__':
    unittest.main()
