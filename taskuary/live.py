"""Push the Timeline, Board and Studio instead of making them guess.

The UI used to ask every few seconds. A WebSocket the terminal already speaks carries
feed-changed / ingest-status / task-changed / run-tail, and the views refetch only when something
actually moved. emit() is safe from any thread (the poll, a click, a pty byte).
Many writes in one gulp coalesce: forty new mail rows are one feed-changed, not forty.
"""
import asyncio, contextvars, itertools, threading
from loguru import logger

FEED, INGEST, TASK, RUN = 'feed-changed', 'ingest-status', 'task-changed', 'run-tail'
# a phone turn in the Assistant's chat: the desktop read its conversation only on a 30 s tick, so a WhatsApp answer
# reached the tab up to half a minute after the phone had it (the owner, 2026-09-24: "it takes 20 seconds")
CHAT = 'chat-changed'
# the startup catch-up finished (or outlived its wait) with a greeting held for it: the page asks for the greeting again (welcome.py)
ARRIVE = 'arrive'
# the Advisor's line landed on an item (advisor.judge): the prompt box fills for that key, nothing on the rail moves
ADVICE = 'advice'
KINDS = (FEED, INGEST, TASK, RUN, CHAT, ARRIVE, ADVICE)

# WHICH WRITES A READ HAS SEEN (the load-once pass, 2026-10-27). Every wake-up about a durable write is stamped `seq` (stamp(), taken
# once the write committed) and a read is stamped with seq() as it begins: a read whose stamp is at least an event's began after that
# write committed, so it holds it and the page need not read again. `by`: the tab whose request made the write (X-Taskuary-Tab) - that
# page already drew what its own press answered, and only it waits for the burst; anyone else's write is read at once.
# A wake-up with no stamp (a direct emit, a write still inside a transaction) is never covered: the safe error is one read too many.
_seq = itertools.count(1)
_last = 0
TAB = contextvars.ContextVar('taskuary_tab', default=None)


def seq() -> int:
    """The newest stamp handed out: a read begun now has seen every write stamped up to it."""
    return _last


def stamp() -> int:
    global _last
    with _lock:
        _last = next(_seq)
        return _last


_loop = None
_clients = set()
_lock = threading.Lock()
_pending = {}          # kind -> payload (last writer wins for that kind)
_timers = {}           # kind -> Timer
# run-tail is a screen you watch, so it can wait a beat to fold pty bursts; the other two
# are "something landed" and should reach the tab before the next glance.
_DELAY = {RUN: 0.25, FEED: 0.08, INGEST: 0.08, TASK: 0.08, CHAT: 0.05, ARRIVE: 0.05, ADVICE: 0.05}


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


def _merged(prev: dict, payload: dict) -> dict:
    """Two writes in one window. The last writer's fields win, but not for WHICH TASKS moved: a mail splitting off its thread wrote
    the thread's task and a new one in the same 80 ms, the event named only the new one, and a tab holding the thread's task kept
    its old read (the intake walk, 2026-10-26). Every task the window touched is in `task_ids`; a write that named none is about
    all of them, so the merged event names none either."""
    msg = {**prev, **payload}
    # a window is covered only when every write in it was stamped, and is one tab's only when every write in it was that tab's
    if prev:
        if 'seq' in prev and 'seq' in payload: msg['seq'] = max(prev['seq'], payload['seq'])
        else: msg.pop('seq', None)
        if prev.get('by') != payload.get('by'): msg.pop('by', None)
    if not prev or 'task_id' not in msg: return msg
    a = prev.get('task_ids') or ([prev['task_id']] if prev.get('task_id') is not None else None)
    b = [payload['task_id']] if payload.get('task_id') is not None else None
    if a is None or b is None: msg.pop('task_id', None); msg.pop('task_ids', None)
    elif len(ids := sorted({*a, *b}, key=str)) > 1: msg['task_ids'] = ids
    return msg


def emit(kind, **payload):
    """Tell every attached tab. Unknown kinds are ignored so a typo cannot wedge the queue.
    No listeners means no timer: a poll writing forty rows must not spawn forty Timers
    when nobody has the UI open. The first write arms a fixed window; later writes only
    update the payload. Re-arming on every emit starved a stream faster than the delay
    (a pty printing, a 150-row catch-up) and the tab heard nothing until it paused."""
    if kind not in KINDS:
        return
    # a write's wake-up is stamped as it is sent - after the write, as every caller sends it - unless its sender said it cannot be
    # (seq=None: store._poke inside a transaction); and it names the tab whose request it is (TAB), where there is one
    if 'seq' in payload and payload['seq'] is None: payload.pop('seq')
    elif kind in (FEED, TASK) and 'seq' not in payload: payload['seq'] = stamp()
    if kind in (FEED, TASK) and 'by' not in payload and TAB.get(): payload['by'] = TAB.get()
    with _lock:
        if not _clients:
            return
        msg = {**_merged(_pending.get(kind) or {}, payload), 'type': kind}
        _pending[kind] = msg
        if kind in _timers:
            return                      # a window is already open; this write rides it
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
    if loop is None:
        return
    try:
        if not loop.is_running():
            return
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
