"""The agent's browser, watched live beside its terminal.

A coding session drives a headless Chrome through agent-browser (clis.TOOLS) from its own
terminal, and until now that was all you saw of it - text scrolling past. This is the other
half: the owner watches the page the agent is on, in the task page and on the Wall, and can
take the keyboard when a page asks for something an agent must never type (a password, a
2FA code).

How the two are tied together, with NO cooperation from the agent: every pty gets
AGENT_BROWSER_SESSION=tq-<sid> in its environment (terminal.clean_env), so whatever
`agent-browser` command the agent runs lands in a session named after the terminal it ran
in. agent-browser keeps that session's state in ~/.agent-browser/<name>.* - `.stream` is the
port of its screencast WebSocket (always on, frames start when a client attaches), `.target`
the page it is on. Reading those files is how Taskuary knows a browser is open; connecting to
that port is how it shows it. No CLI call on the poll path, no daemon of our own.

The relay is a plain pipe: agent-browser's messages (frame / url / status / tabs / console,
JSON text) go to the page, the page's messages (input_mouse / input_keyboard / ack) go back.
Ack pacing is requested on the upstream URL and the RENDERER's acks are forwarded, which is
what keeps a slow tab looking at the current page instead of ten seconds of history - the
proxy generating acks itself would leave frames queued on the far side (agent-browser's
streaming notes say exactly this).
"""
import base64, json, os, re, shutil, socket, subprocess, time
from datetime import datetime
from pathlib import Path
from loguru import logger

MAX_FPS = 12                    # a watched page, not a game: 12 frames/s at ~50KB each is plenty and easy on a LAN tab
MAX_FRAME = 8 * 1024 * 1024     # a 1280x720 jpeg is ~54KB; this is the ceiling for a huge viewport, not a target
_TTL = 2.0                      # state() is on the terminal-listing poll path: one socket probe per pane per 2s, not per render
LAST = {}                       # sid -> the newest frame seen by any relay: what Snapshot files
_CACHE = {}                     # sid -> (when, state)
_KEPT = re.compile(r'^\{\s*"type"\s*:\s*"(frame|url)"')   # the head of the message, before paying for a 50KB parse


def session_name(sid: str) -> str: return f'tq-{sid}'
def env(sid: str) -> dict: return {'AGENT_BROWSER_SESSION': session_name(sid)}
def home() -> Path: return Path(os.environ.get('AGENT_BROWSER_HOME') or Path.home() / '.agent-browser')


def _read(name: str, ext: str) -> str:
    try: return (home() / f'{name}.{ext}').read_text(encoding='utf-8', errors='replace').strip()
    except OSError: return ''

def _listening(port: int, timeout: float = .25) -> bool:
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=timeout): return True
    except OSError: return False


def state(sid: str, fresh: bool = False) -> dict:
    """{'open', 'url', 'port'} for the browser of pty session `sid`, from agent-browser's own
    state files. `open` means the screencast port answers - a stale file from a daemon that
    idled out an hour ago is not an open browser."""
    now = time.time()
    hit = _CACHE.get(sid)
    if hit and not fresh and now - hit[0] < _TTL: return hit[1]
    name = session_name(sid)
    port = int(_read(name, 'stream') or 0) if _read(name, 'stream').isdigit() else 0
    url = ''
    try: url = (json.loads(_read(name, 'target') or '{}') or {}).get('url') or ''
    except ValueError: pass
    st = {'open': bool(port) and _listening(port), 'url': (LAST.get(sid) or {}).get('url') or url, 'port': port}
    _CACHE[sid] = (now, st)
    return st


def remember(sid: str, raw: str):
    """Keep the newest frame and the current page per session - what Snapshot files, and what the
    listing shows as the URL between polls. Cheap check first: a frame is ~50KB of base64 and
    only frames and url messages matter here."""
    if not _KEPT.match(raw): return
    try: m = json.loads(raw)
    except ValueError: return
    cur = LAST.setdefault(sid, {'data': '', 'seq': 0, 'url': '', 'at': 0})
    if m.get('type') == 'frame' and m.get('data'):
        cur.update(data=m['data'], seq=m.get('seq') or 0, at=time.time())
    elif m.get('type') == 'url' and m.get('url'):
        cur['url'] = m['url']


async def relay(ws, sid: str):
    """Pipe the session's screencast to one page and that page's input back. `ws` is the FastAPI
    socket, not yet accepted - a session with no browser is refused with 4404 the way a missing
    terminal is."""
    import asyncio, websockets
    st = state(sid, fresh=True)
    if not st['open']: return await ws.close(code=4404)
    await ws.accept()
    url = f"ws://127.0.0.1:{st['port']}/?pacing=ack&maxFps={MAX_FPS}"
    try:
        # agent-browser only admits browser Origins from localhost; a client with none is a tool
        async with websockets.connect(url, origin='http://localhost', max_size=MAX_FRAME) as up:
            async def down():
                async for m in up:
                    m = m if isinstance(m, str) else m.decode('utf-8', 'replace')
                    remember(sid, m)
                    await ws.send_text(m)
            async def back():
                while True: await up.send(await ws.receive_text())
            tasks = [asyncio.create_task(down()), asyncio.create_task(back())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending: t.cancel()
            for t in done:
                exc = t.exception()
                if exc and not isinstance(exc, (websockets.ConnectionClosed, RuntimeError)):
                    logger.debug(f'browser relay {sid} ended: {exc!r}')
    except (OSError, websockets.WebSocketException) as e:
        logger.debug(f'browser relay {sid} could not attach to {url}: {e}')
    try: await ws.close()
    except Exception: pass


def snapshot(store, sid: str, actor: str, tid: int = None) -> dict:
    """Keep what the owner is looking at ON THE TASK: the newest frame as a JPEG attachment of the
    task's message, plus a comment naming the page - so the record of the work shows the page,
    not just that a browser was open."""
    last = LAST.get(sid) or {}
    if not last.get('data'): raise ValueError('no frame yet - the browser has not painted for this session')
    if not tid:
        from . import terminal as hub_term
        t = hub_term.get(sid); tid = t.task_id if t else None
    if not tid: raise ValueError('this session is not on a task')
    msgs = store.list_messages(tid)
    if not msgs: raise ValueError('the task has no message to attach the snapshot to')
    from .artifacts import attachment_dir
    mid, raw = msgs[0]['MessageId'], base64.b64decode(last['data'])
    name = f"browser-{datetime.now():%Y%m%d-%H%M%S}.jpg"
    p = attachment_dir(mid) / name
    p.write_bytes(raw)
    aid = store.add_attachment({'MessageId': mid, 'Name': name, 'ContentType': 'image/jpeg', 'Size': len(raw),
                                'Inline': 0, 'Path': str(p)})
    store.add_comment(tid, actor, 'human', f"Browser snapshot of {last.get('url') or 'the page'} - {name}")
    return {'attachmentId': aid, 'name': name, 'url': f'/api/attachments/{aid}', 'page': last.get('url') or ''}


def close(sid: str):
    """The pty ended: close its browser too. Best effort, and only when there is one - otherwise a
    headless Chrome per finished task sits idle for an hour each."""
    exe = shutil.which('agent-browser')
    if not exe or not _read(session_name(sid), 'stream'): return
    try: subprocess.run([exe, '--session', session_name(sid), 'close'], timeout=20, capture_output=True)
    except (OSError, subprocess.SubprocessError) as e: logger.debug(f'could not close the browser of {sid}: {e}')
    _CACHE.pop(sid, None); LAST.pop(sid, None)


def hint() -> str:
    """One line for the seed, only when the tool is installed: an agent has to be TOLD the browser
    exists and that the owner is watching it - and told that credentials are typed by the owner,
    in the pane, never by the agent (the transcript becomes the report). Short on purpose: the
    seed rides a tty line with a hard cap, and the CLI documents its own commands
    (`agent-browser skills get core`)."""
    if not shutil.which('agent-browser'): return ''
    return ('BROWSER: agent-browser is installed and the owner watches it live beside this terminal. Never type passwords '
            'or login codes yourself - say so and wait for the owner to take over the page.')
