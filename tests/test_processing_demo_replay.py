"""The rendered-browser fixture uses the real terminal websocket with a safe recording."""
from unittest import mock

from starlette.testclient import TestClient

from taskuary import demo, server, terminal
from taskuary.store import MemoryStore


def test_demo_terminal_reconnect_replays_and_reaches_ready_without_closing_recording():
    store = MemoryStore()
    with mock.patch.object(demo.Replay, '_play'):
        replay = demo.Replay(store, 1)
    replay._emit('persisted fixture output\r\n')
    replay.last -= 100
    client = TestClient(server.app)
    try:
        with mock.patch.dict(terminal.SESSIONS, {replay.sid: replay}):
            for _ in range(2):
                with client.websocket_connect(f'/api/terminals/{replay.sid}/ws') as ws:
                    frame = ws.receive_json()
                    assert frame['type'] == 'out' and frame['replay'] is True
                    assert 'persisted fixture output' in frame['data']
                    ws.send_json({'type': 'resize', 'rows': replay.rows, 'cols': replay.cols})
                    assert ws.receive_json() == {'type': 'ready'}
                assert replay.alive
                assert replay.idle() > 90
                assert not replay.subs
    finally:
        replay.close()
        client.close()


def test_demo_attach_does_not_turn_recording_into_an_interactive_worker():
    with mock.patch.object(demo.Replay, '_play'):
        replay = demo.Replay(MemoryStore(), 1)
    try:
        replay._emit('recorded output')
        before = replay.scrollback()
        replay.quiet_for(10)
        replay.resize(40, 120)
        replay.write('fixture input')
        assert replay.scrollback() == before
        assert (replay.rows, replay.cols) == (40, 120)
    finally:
        replay.close()
