"""Push the Timeline, Board and Studio instead of making them guess.

The UI used to ask every few seconds. A WebSocket the terminal already speaks carries
feed-changed / task-changed / run-tail, and the views refetch only when something
actually moved. emit() is safe from any thread (the poll, a click, a pty byte).
Many writes in one gulp coalesce: forty new mail rows are one feed-changed, not forty.
"""
import asyncio, threading
from loguru import logger

FEED, TASK, RUN = 'feed-changed', 'task-changed', 'run-tail'
KINDS = (FEED, TASK, RUN)

_loop = None
_clients = set()
_lock = threading.Lock()
_pending = {}          # kind -> payload (last writer wins for that kind)
_timers = {}           # kind -> Timer
# run-tail is a screen you watch, so it can wait a beat to fold pty bursts; the other two
# are "something landed" and should reach the tab before the next glance.
_DELAY = {RUN: 0.25, FEED: 0.08, TASK: 0.08}


def bind(loop):
    """The asyncio loop that owns the sockets. Called from lifespan and again on connect,
    so a TestClient that never ran lifespan still fans out."""
    global _loop
    _loop = loop


def attach(ws):
    with _lock:
        _clients.add(ws)


def detach(ws):
    with _lock:
        _clients.discard(ws)


def reset():
    """Drop sockets and the loop. Tests that opened a tab must not leave one for the next."""
    global _loop
    with _lock:
        _clients.clear()
        _pending.clear()
        for t in _timers.values():
            try: t.cancel()
            except Exception: pass
        _timers.clear()
        _loop = None


def emit(kind, **payload):
    """Tell every attached tab. Unknown kinds are ignored so a typo cannot wedge the queue.
    No listeners means no timer: a poll writing forty rows must not spawn forty Timers
    when nobody has the UI open."""
    if kind not in KINDS:
        return
    with _lock:
        if not _clients:
            return
        msg = {**(_pending.get(kind) or {}), **payload, 'type': kind}
        _pending[kind] = msg
        old = _timers.pop(kind, None)
        if old:
            try: old.cancel()
            except Exception: pass
        t = threading.Timer(_DELAY.get(kind, 0.08), lambda k=kind: _flush_kind(k))
        t.daemon = True
        _timers[kind] = t
        t.start()


def flush():
    """Send whatever is waiting, now. Tests use this instead of sleeping the debounce."""
    with _lock:
        kinds = list(_pending)
        for k in kinds:
            t = _timers.pop(k, None)
            if t:
                try: t.cancel()
                except Exception: pass
    for k in kinds:
        _flush_kind(k)


def _flush_kind(kind):
    with _lock:
        _timers.pop(kind, None)
        msg = _pending.pop(kind, None)
    if msg:
        _broadcast(msg)


def _broadcast(msg):
    loop = _loop
    if loop is None or not loop.is_running():
        return
    try:
        asyncio.run_coroutine_threadsafe(_fanout(msg), loop)
    except RuntimeError:
        pass


async def _fanout(msg):
    with _lock:
        peers = list(_clients)
    dead = []
    for ws in peers:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    if dead:
        with _lock:
            for ws in dead:
                _clients.discard(ws)
        logger.debug(f'live: dropped {len(dead)} stale socket(s)')


async def serve(ws):
    """One connection per tab. The client does not need to send; we push."""
    bind(asyncio.get_running_loop())
    attach(ws)
    try:
        await ws.send_json({'type': 'hello'})
        while True:
            await ws.receive_text()
    finally:
        detach(ws)
