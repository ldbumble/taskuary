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
import base64, json, os, re, shutil, socket, subprocess, tempfile, threading, time
from datetime import datetime
from pathlib import Path
from loguru import logger
from . import spawn

MAX_FPS = 12                    # a watched page, not a game: 12 frames/s at ~50KB each is plenty and easy on a LAN tab
MAX_FRAME = 8 * 1024 * 1024     # a 1280x720 jpeg is ~54KB; this is the ceiling for a huge viewport, not a target
_TTL = 2.0                      # state() is on the terminal-listing poll path: one socket probe per pane per 2s, not per render
# How long a launch is given before the caller is told it did not come up. Ten seconds was a warm
# Chrome's budget - a measured cold start on Windows (first launch of the day, profile restore) took
# longer than that and came up seconds later, with the caller already told there was no browser. That
# is the worst outcome of the three: the agent is never handed the session name, so the browser it
# opens for itself is one the owner's pane is not watching (2026-09-14). Waiting costs nothing when
# the browser is quick - this returns the moment it answers.
LAUNCH_WAIT = 25.0
LAUNCH_POLL = 0.25
NAV_WAIT = 45.0                 # one page load on a browser that is already up, not a launch: a slow sign-in page, not a cold Chrome
# Chrome's own launch flags. agent-browser leaves `navigator.webdriver` TRUE by default (measured
# here 2026-09-14: true without this flag, false with it) - the cheapest tell a login page has, and
# one it reads before any of the interesting signals. The other half of the 2026 detection advice is
# to run HEADED, and that half is deliberately not taken: Windows has no virtual display, so a headed
# browser is a Chrome window sitting across the owner's own work - which is exactly what happened
# when it was tried (the owner, 2026-09-14: "I closed it by mistake. It should not show up in random.
# but in the browser."). The pane IS where this browser shows.
LAUNCH_ARGS = '--disable-blink-features=AutomationControlled'
LAST = {}                       # sid -> the newest frame seen by any relay: what Snapshot files
_CACHE = {}                     # sid -> (when, state)
_START_LOCKS = {}               # sid -> one launch at a time; session mount + first prompt race otherwise opens two Chromes
_START_LOCKS_GUARD = threading.Lock()
_KEPT = re.compile(r'^\{\s*"type"\s*:\s*"(frame|url)"')   # the head of the message, before paying for a 50KB parse


def installed() -> bool: return bool(shutil.which('agent-browser'))
def session_name(sid: str) -> str: return f'tq-{sid}'
# WHAT EVERY agent-browser COMMAND FOR A SESSION MUST AGREE ON. agent-browser fingerprints a
# command's launch options into <session>.config, and when a command's fingerprint differs from
# the running daemon's it SHUTS THAT DAEMON DOWN and starts a default one on about:blank. The idle
# timeout is in the fingerprint (--restore and --args are not; measured 2026-09-18 with 0, 720h and
# raw ms alike). So it rides here, in the environment the pty, the pane and the server all share -
# a `--idle-timeout` flag on the launch alone was a mismatch with the agent's very first flagless
# `agent-browser open`: the browser the owner was watching died, a fresh blank one took its port,
# the restored login went with it, and the pane was white (the new blank page) or black (still on
# the dying daemon's socket). "It either appears but is plain white, or freezes and is just black"
# (the owner, 2026-09-18). 0 = never idle out: this browser is closed by close(), not by a clock.
IDLE_MS = '0'
# ...AND NO PERIODIC AUTOSAVE. With --restore, agent-browser 0.37.1 saves cookies and storage on a
# 30-second clock as well as after every command - and the clocked save, once the tab has been to a
# SECOND site, closes the browser: measured 2026-09-18 outside Taskuary (launch, wikipedia, a login
# page, dead at +34s; example.com then example.org, dead at +40s; one site alone, or no --restore, or
# this set to 0: alive for minutes). The pane went white, and the next command opened a fresh browser
# without the restored login. The per-command save keeps what the owner typed; the clock only broke it.
AUTOSAVE_MS = '0'
def env(sid: str) -> dict:
    return {'AGENT_BROWSER_SESSION': session_name(sid), 'AGENT_BROWSER_IDLE_TIMEOUT_MS': IDLE_MS,
            'AGENT_BROWSER_AUTOSAVE_INTERVAL_MS': AUTOSAVE_MS}
def _cli_env(sid: str) -> dict: return {**os.environ, **env(sid)}    # the server's own calls match the pty's
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


def navigate(sid: str, url: str) -> str:
    """Point this session's browser at a URL, on the owner's say-so.

    The pane had no way to open anything. `start()` opens the browser on about:blank so there is
    something to watch, the agent drives it from then on - and when the agent asks the OWNER to
    take it from here ("open ADP in the browser pane and sign in yourself", 2026-09-16) there was
    no address bar, nothing to click on a blank page, and Take over only forwards clicks. The task
    could not be finished from the screen it was being watched on.

    Run with an explicit --session and an argv LIST: no shell, so none of the PowerShell
    stderr-is-an-error trouble that made the agent give up in the first place. The exit code is
    what decides, never the stream.

    AND NEVER capture_output HERE. The daemon this command leaves running inherits the pipe, so
    the pipe never reaches EOF and we would be waiting on a process built to outlive us - and
    `timeout` does not save you: TimeoutExpired kills the CLI and then blocks again draining that
    same inherited pipe. Measured on this box, a piped `open` asked to give up after 45s came
    back at 156.9s, when the browser was closed by hand. set_viewport meets this by never waiting
    at all; here the owner is owed an answer, so the output goes to a FILE - inheritable, read
    after the CLI exits, and never a reason to wait.
    """
    u = (url or '').strip()
    if not u: raise ValueError('no address given')
    if not re.match(r'^https?://', u, re.I):
        if re.match(r'^[a-z][a-z0-9+.-]*:', u, re.I):
            raise ValueError('only http:// and https:// addresses can be opened here')
        u = 'https://' + u
    exe = shutil.which('agent-browser')
    if not exe: raise ValueError('agent-browser is not installed')
    if not state(sid, fresh=True)['open']: raise ValueError('this session has no browser open')
    # one log per session, overwritten each time: on Windows the daemon may still hold the handle,
    # so this is never unlinked - a file per session is a bounded mess, a file per click is not
    log = Path(tempfile.gettempdir()) / f'{session_name(sid)}-open.log'
    try:
        with open(log, 'wb') as f:
            p = spawn.popen([exe, '--session', session_name(sid), 'open', u], env=_cli_env(sid),
                            stdout=f, stderr=f, stdin=subprocess.DEVNULL)
            try: rc = p.wait(timeout=NAV_WAIT)
            except subprocess.TimeoutExpired:
                p.kill()
                raise ValueError('the page did not finish loading in time - the browser still has it, so watch the pane')
    except OSError as e:
        raise ValueError(f'could not open that page: {e}')
    if rc != 0:
        try: said = log.read_text(encoding='utf-8', errors='replace').strip()
        except OSError: said = ''
        raise ValueError(said[-300:].strip() or 'agent-browser could not open that page')
    _CACHE.pop(sid, None)
    return u


def close(sid: str):
    """The pty ended: close its browser too. Best effort, and only when there is one - otherwise a
    headless Chrome per finished task sits idle for an hour each."""
    exe = shutil.which('agent-browser')
    with _START_LOCKS_GUARD:
        lock = _START_LOCKS.setdefault(sid, threading.Lock())
    # If the workspace closes while Chrome is still coming up, wait for that exact launch and
    # close it. Reading the stream file before the launch settled leaked the late browser.
    with lock:
        if exe and _read(session_name(sid), 'stream'):
            try: spawn.run([exe, '--session', session_name(sid), 'close'], env=_cli_env(sid), timeout=20, capture_output=True)
            except (OSError, subprocess.SubprocessError) as e: logger.debug(f'could not close the browser of {sid}: {e}')
        _CACHE.pop(sid, None); LAST.pop(sid, None)
    with _START_LOCKS_GUARD:
        if _START_LOCKS.get(sid) is lock: _START_LOCKS.pop(sid, None)


# One profile's worth of cookies, keyed here and not on the session id: a session is born and
# dies per task, and a login the owner typed by hand in the pane last week should still be
# there this week. --restore is agent-browser's own auto-save/restore of cookies and storage.
RESTORE_KEY = 'taskuary'
WANTS = 'needs:browser'


def wanted(task: dict | None) -> bool:
    """Did the owner say this task needs a browser? (the tag the New task dialog writes)"""
    import re as _re
    return bool(_re.search(rf'(^|[\s,]){_re.escape(WANTS)}([\s,]|$)', str((task or {}).get('Tags') or '')))


def start(sid: str, url: str = 'about:blank') -> bool:
    """Open the browser FOR this session, before the agent asks for one.

    Until now a browser existed only if the agent thought to run agent-browser, which meant a
    task that plainly needs one - a portal with no API, a page behind a login - started with
    nothing on screen and the owner watching text. A task marked "needs a browser" gets one
    with the session: bound to it by name, restored from the owner's own saved cookies, and
    closed with it (Term._pump -> close).
    """
    exe = shutil.which('agent-browser')
    if not exe: return False
    # General work starts the browser as soon as the workspace mounts, then its first prompt
    # verifies that it is ready before handing the CLI browser instructions. Those two roads can
    # arrive together. agent-browser's on-disk session files are not a launch mutex: without one,
    # both processes may decide the name is absent and leave two Chromes and two stream ports.
    with _START_LOCKS_GUARD:
        lock = _START_LOCKS.setdefault(sid, threading.Lock())
    with lock:
        if state(sid, fresh=True)['open']: return True             # the agent or mount got there first
        # ...AND IT STAYS UP WHILE THE TASK IS OPEN. agent-browser shuts its daemon down after an hour
        # of inactivity by default, which is fine for a tool and wrong for a page someone is watching:
        # a walk left overnight at a half-finished ADP sign-in came back to a white pane, because the
        # browser had gone at 23:06 and the next command got a fresh empty one (the owner, 2026-09-15:
        # "it showed the browser, then turned white"). This browser belongs to the session and dies
        # with it - close() on the pty's end is what closes it, not a clock nobody set. The "never"
        # is AGENT_BROWSER_IDLE_TIMEOUT_MS in env(), NOT an --idle-timeout flag here: a flag only the
        # launch carries is a launch-option mismatch with every later command, and a mismatch is
        # exactly what makes agent-browser replace this daemon with a blank default one (see IDLE_MS).
        cmd = [exe, '--session', session_name(sid), '--restore', RESTORE_KEY,
               '--args', LAUNCH_ARGS, 'open', url or 'about:blank']
        try:
            # detached and HEADLESS: the live pane is the visible browser. --headed opens a second
            # desktop window outside Taskuary and defeats the side-by-side surface.
            spawn.popen(cmd, env=_cli_env(sid), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, close_fds=True)
        except (OSError, subprocess.SubprocessError) as e:
            logger.warning(f'could not start the browser for {sid}: {e}')
            return False
        for _ in range(int(LAUNCH_WAIT / LAUNCH_POLL)):            # it has a Chrome to launch
            time.sleep(LAUNCH_POLL)
            if state(sid, fresh=True)['open']: return True
        logger.warning(f'the browser for {sid} did not come up within {LAUNCH_WAIT:.0f}s')
        return False


def set_viewport(sid: str, w: int, h: int) -> bool:
    """Render the page at the SHAPE OF THE PANE the owner is watching it in.

    Chrome renders at a viewport nobody chose - a wide desktop default - and the pane is taller than
    it is wide, so fitFrame letterboxes it: measured 2026-09-14, 55% of the pane was black and the
    page drew at 38% of its size. The width stays desktop (browserSplit.MIN_VIEWPORT_W) so sites
    serve the layout a desktop gets; only the shape follows the pane.

    Fire and forget: the page still draws, letterboxed, if this never lands. Nothing is waited on -
    a piped agent-browser call blocks until the DAEMON exits, not until the command does."""
    exe = shutil.which('agent-browser')
    w, h = int(w), int(h)
    if not exe or not (200 <= w <= 4000 and 200 <= h <= 4000): return False
    try:
        spawn.popen([exe, '--session', session_name(sid), 'set', 'viewport', str(w), str(h)], env=_cli_env(sid),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, close_fds=True)
        return True
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug(f'could not resize the browser of {sid}: {e}')
        return False


def brief() -> str:
    """What an agent with a browser of its own needs to know. Longer than hint() on purpose -
    this only rides when the owner asked for a browser, so it can afford to say how to drive
    it and where the line is."""
    return ('A BROWSER IS OPEN for this task and the owner is WATCHING it beside this session. '
            'Drive the existing tab with `agent-browser` - it is already bound and restored, so '
            'NEVER use --session, --headed, profile listing, or launch Chrome separately. Navigate '
            'with `agent-browser open <url>`. '
            # POWERSHELL CALLS A SUCCESS AN ERROR. agent-browser writes its progress to stderr
            # ("[agent-browser] launched browser"), and Windows PowerShell 5.1 wraps any native
            # command's stderr in a NativeCommandError and sets $? to false EVEN ON EXIT 0. A CLI
            # shelling out through powershell.exe therefore reads a working `open` as a failure:
            # on 2026-09-16 an agent gave up after three such "errors", told the owner "the browser
            # connection failed", and left a daemon running with no page in it - which is exactly
            # what the black pane was. Measured: exit code 0, "✓ Example Domain", $? false.
            'ON WINDOWS, judge `agent-browser` by its EXIT CODE and its output, never by '
            'PowerShell\'s error record: it writes progress to stderr, and PowerShell 5.1 reports '
            'that as a NativeCommandError with $? false even when the command returned 0 and '
            'worked. A line like "[agent-browser] launched browser" IS the success. If your shell '
            'insists it failed, run `agent-browser get url` and believe what the browser '
            'itself says over what the shell claims. '
            # LOOK, and look CHEAPLY. The accessibility tree is what the browser already knows about
            # its own page - every control's role, name and state, with a @ref to act on - and it is
            # an order of magnitude smaller than the same page as pixels. An agent that screenshots
            # its way through a login burns the context it needs for the job and still guesses at
            # which box is the user id.
            'LOOK BEFORE YOU CLICK: `agent-browser snapshot -i -c` prints the page as an '
            'accessibility tree - every interactive element with its role, its name and a @ref you '
            'can act on (`agent-browser click @ref3`, `agent-browser type @ref1 "..."`). Use it as '
            'your eyes. `agent-browser read` gives the page text, `agent-browser find role button '
            '"Sign in" click` finds a control by what it IS. Take a screenshot only when the '
            'question is genuinely visual - it costs far more and says less. '
            '`agent-browser skills get core --full` if you need a command you do not know. '
            'Taskuary itself is already running at $TASKUARY_URL: do not '
            'start Taskuary, Vite, or another local server. '
            'NEVER type a password, a 2FA code or a card number: navigate to the page that asks '
            'and tell the owner here - they type it in the pane themselves. '
            # THEN GET OUT OF THE WAY. Told to hand over the keyboard for an ADP sign-in, an agent
            # asked for the User ID and kept working the same tab anyway - snapshot, get url, read,
            # and `open` on the sign-in URL again (2026-09-15). What had actually blanked that page
            # was the daemon idling out overnight, fixed in start(); this rule is the other half, and
            # stands on its own: a page someone is signing into is not a page to poll or re-enter.
            'WHEN YOU HAND THEM THE KEYBOARD, STOP: end that turn with the ask marker and run no '
            'browser command at all until they answer. Do not re-open the page, reload it, navigate, '
            'snapshot or poll to "check whether they are done" - a sign-in in progress is theirs, and '
            'touching the tab throws away what they have typed. Their answer is what tells you to look.')


def hint() -> str:
    """One line for the seed, only when the tool is installed: an agent has to be TOLD the browser
    exists and that the owner is watching it - and told that credentials are typed by the owner,
    in the pane, never by the agent (the transcript becomes the report). Short on purpose: the
    seed rides a tty line with a hard cap, and the CLI documents its own commands
    (`agent-browser skills get core`)."""
    if not shutil.which('agent-browser'): return ''
    return 'BROWSER: agent-browser is installed; Never type passwords/codes.'
