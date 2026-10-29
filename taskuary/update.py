"""Update in place, from Settings: check what the latest release is, fetch it, swap it in, come back.

Everything the owner has - connections, tokens, the database, the operator documents, the
playbooks - lives under ~/.taskuary (config.home()), never beside the program. So an update is
only ever a program swap: nothing in the data folder is touched, and the new build opens the same
database the old one closed. That is what makes "keep the connection and all the settings" free.

Three ways Taskuary can be installed, three roads:
  exe     Taskuary.exe (PyInstaller, taskuary.spec). A running exe cannot overwrite itself on
          Windows, so the new one is downloaded beside it as Taskuary.new.exe and a tiny batch
          script does the rest after we exit: wait for our PID to go, move the new file over
          the old, start it with the same arguments, delete itself.
  pip     a wheel in a venv: `pip install -U taskuary`, then relaunch the same command line.
  source  a checkout (`pip install -e .`, the developer's machine): updating means `git pull`,
          which is not ours to run in somebody's repository - say so instead.

The latest version is the GitHub release the publish workflow cuts on every tag, and the exe is
the asset it attaches at a fixed URL (releases/latest/download/Taskuary.exe). No token, no extra
service, and the same file a person would download by hand.
"""
import os, re, subprocess, sys, threading, time
from pathlib import Path

import requests
from loguru import logger

from . import __version__

REPO = 'ldbumble/taskuary'
LATEST_API = f'https://api.github.com/repos/{REPO}/releases/latest'
EXE_URL = f'https://github.com/{REPO}/releases/latest/download/Taskuary.exe'
TIMEOUT = 20
# How long the helper waits for the old program to go before deciding it never will. Unbounded
# was the bug (2026-09-15): Update left a console spinning on a PID that stayed, and no app.
WAIT_S = 120
_cache = {'at': 0.0, 'result': None}
CACHE_S = 600                   # GitHub allows 60 anonymous calls an hour; the header pill asks often


def how() -> str:
    """'exe' | 'pip' | 'source' - which road an update takes on this install."""
    if getattr(sys, 'frozen', False): return 'exe'
    if (Path(__file__).parent.parent / 'pyproject.toml').is_file(): return 'source'
    return 'pip'


def _parts(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r'\d+', str(v or '')))


def newer(latest: str, current: str) -> bool:
    """Is `latest` a later release than `current`? Dotted integers, any depth; a bad string is
    never newer - an update button must not fire on a parse error."""
    a, b = _parts(latest), _parts(current)
    if not a or not b: return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def check(force: bool = False) -> dict:
    """What is out there vs what is running. Cached ten minutes; a failure to reach GitHub is a
    fact in the answer, not an exception - the card says 'could not check' and stays useful."""
    if not force and _cache['result'] and time.time() - _cache['at'] < CACHE_S: return _cache['result']
    out = {'current': __version__, 'how': how(), 'latest': None, 'newer': False, 'url': None, 'notes': None, 'error': None}
    try:
        r = requests.get(LATEST_API, timeout=TIMEOUT, headers={'Accept': 'application/vnd.github+json'})
        r.raise_for_status()
        j = r.json()
        tag = str(j.get('tag_name') or '').lstrip('v')
        out.update({'latest': tag or None, 'newer': newer(tag, __version__), 'notes': j.get('html_url'),
                    'url': next((a.get('browser_download_url') for a in j.get('assets') or []
                                 if str(a.get('name') or '').lower() == 'taskuary.exe'), EXE_URL)})
    except Exception as e:
        # the reason is for the log; the card says what it means and what to do about it
        logger.warning(f'update check failed: {e}')
        out['error'] = ("Couldn't reach the release page to check for a newer version. "
                        'This computer may be offline, or a network filter blocks GitHub - try Check now in a minute.')
    _cache.update({'at': time.time(), 'result': out})
    return out


# ── the exe road ────────────────────────────────────────────────────────────────────────
def _download(url: str, dest: Path, progress=None) -> int:
    """Stream the new exe beside the old one. Size-checked against Content-Length and sniffed
    for the PE header: a half-downloaded or HTML-error-page 'exe' must never be swapped in."""
    with requests.get(url, stream=True, timeout=TIMEOUT, allow_redirects=True) as r:
        r.raise_for_status()
        total = int(r.headers.get('Content-Length') or 0)
        got = 0
        with open(dest, 'wb') as f:
            for chunk in r.iter_content(1 << 20):
                if not chunk: continue
                f.write(chunk); got += len(chunk)
                if progress: progress(got, total)
    if total and got != total:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f'download stopped short: {got:,} of {total:,} bytes')
    with open(dest, 'rb') as f: head = f.read(2)
    if head != b'MZ':
        dest.unlink(missing_ok=True)
        raise RuntimeError('what came down is not a Windows program - the release asset may be missing')
    return got


def staging() -> Path:
    """Where the new build is assembled before it is put in place.

    It used to be assembled beside the running program, which is wherever the owner happened to
    launch it from - and for a single-file download that is the Downloads folder, the most watched
    directory on a Windows box. Writing a brand-new .exe there is exactly what Controlled Folder
    Access and every antivirus is built to stop, so the update failed before it began with
    "[Errno 13] Permission denied" and nothing to act on (an owner's machine, 2026-09-02).

    The data folder is the one directory this program is PROVEN able to write to: the database it
    is serving from is open in it right now. So the download, the helper script and its log all
    go here, and the only thing that ever touches the program's own folder is a single move.
    """
    from . import config
    d = config.home() / 'update'
    d.mkdir(parents=True, exist_ok=True)
    return d


def wait_lines(pids, stuck: str) -> list:
    """Batch lines that wait for each PID to go, WAIT_S seconds between them all, then `goto <stuck>`.
    `find " <pid> "` with the spaces: a bare `find "12"` also matched PID 1234 and waited on a stranger."""
    out = []
    for i, p in enumerate(pids):
        lbl = 'wait' if i == 0 else f'wait{i}'
        out += [f':{lbl}', f'tasklist /FI "PID eq {p}" 2>nul | find " {p} " >nul', 'if not errorlevel 1 (',
                '  set /a waited+=1', f'  if %waited% geq {WAIT_S} goto {stuck}', '  ping -n 2 127.0.0.1 >nul', f'  goto {lbl}', ')']
    return out


def swap_script(exe: Path, new: Path, pid: int, args: list, also=()) -> str:
    """The batch that finishes the job after this process has gone. Waits for the PID (the exe
    is locked while it runs), moves the new file over the old (retrying - antivirus likes to hold
    a fresh download for a second), starts the new build with the SAME arguments, removes itself.
    `also`: more PIDs that hold the exe - the one-file bootloader that started us runs the same
    Taskuary.exe and holds it locked while it cleans up after us (unpack.bootloader)."""
    q = lambda s: '"' + str(s).replace('"', '""') + '"'
    argstr = ' '.join(q(a) for a in args)
    # beside the DOWNLOAD, not beside the program: the whole point of staging is that the
    # program's own folder is written to exactly once, by the move below
    log = Path(new).with_name('taskuary-update.log')
    return '\r\n'.join([
        '@echo off',
        'setlocal',
        # This batch carries the OLD exe's environment, and the new build lands at the same path.
        # PyInstaller >= 6.9 reads that pair as "I am my own onefile child", skips unpacking, and
        # looks for python312.dll in the old _MEI folder - deleted when the old process exited.
        # The first run after Update died on "Failed to load Python DLL" (an owner's machine,
        # 2026-09-24). This variable is PyInstaller's own switch for "start as a new program".
        'set "PYINSTALLER_RESET_ENVIRONMENT=1"',
        f'set "update_log={log}"',
        '> "%update_log%" echo update helper started %date% %time%',
        'set /a waited=0',
        # `ping`, not `timeout`: this helper runs with its stdin on DEVNULL, and timeout answers
        # redirected stdin with "ERROR: Input redirection is not supported" - so the poll never
        # slept, it spun. ping -n 2 is one second and needs neither a console nor stdin.
        *wait_lines([pid, *also], 'stuck'),
        '>> "%update_log%" echo old process exited %date% %time%',
        'set /a tries=0',
        ':swap',
        f'move /Y {q(new)} {q(exe)} >nul 2>&1',
        'if errorlevel 1 (',
        '  set /a tries+=1',
        '  if %tries% geq 30 goto giveup',
        # same reason as the wait loop: timeout cannot run with stdin on DEVNULL, so "retry for
        # 30 seconds while the scanner lets go of the download" was really 30 tries in a few
        # milliseconds - and then it gave up on a file that would have been free a second later.
        '  ping -n 2 127.0.0.1 >nul',
        '  goto swap',
        ')',
        '>> "%update_log%" echo program swapped; launching new build %date% %time%',
        f'start "" /D {q(exe.parent)} {q(exe)} {argstr}'.rstrip(),
        'if errorlevel 1 goto launchfail',
        '>> "%update_log%" echo launch requested successfully %date% %time%',
        'del "%~f0"',
        'exit /b 0',
        ':stuck',
        # The old program never exited. Leaving the owner with no app at all is the worst
        # outcome available, so put the KNOWN GOOD one back in front of them and say why in the
        # log; the new build stays staged and the next Update tries again.
        '>> "%update_log%" echo ERROR: the old process never exited; starting it again unchanged %date% %time%',
        f'start "" /D {q(exe.parent)} {q(exe)} {argstr}'.rstrip(),
        'del "%~f0"',
        'exit /b 3',
        ':giveup',
        '>> "%update_log%" echo ERROR: could not replace the old program after 30 tries %date% %time%',
        f'start "" /D {q(exe.parent)} {q(exe)} {argstr}'.rstrip(),
        'del "%~f0"',
        'exit /b 1',
        ':launchfail',
        '>> "%update_log%" echo ERROR: Windows refused to launch the new program %date% %time%',
        'exit /b 2',
    ]) + '\r\n'


def _launch_swap(script: Path, cwd: Path, env: dict = None):
    """Start the updater outside the desktop app's lifetime.

    Corporate launchers commonly put desktop programs in a Windows Job with "kill every child
    when the parent exits" enabled. DETACHED_PROCESS removes the console, but it does *not* leave
    that Job; the old app therefore disappeared and took its updater with it. Ask Windows to break
    the helper out of the Job. Some locked-down Jobs refuse that flag, so retry without it rather
    than refusing the update before it has begun.
    """
    cmd = os.environ.get('COMSPEC') or 'cmd.exe'
    argv = [cmd, '/d', '/c', 'call', str(script)]
    # NOT DETACHED_PROCESS. Windows ignores CREATE_NO_WINDOW when DETACHED_PROCESS is set, and a
    # detached cmd.exe allocates a console of its OWN - which Windows 11 hands to Windows Terminal.
    # That is the black window the owner was left staring at, titled with whatever the batch was
    # running at the time (`find "10592"`). CREATE_NO_WINDOW alone gives the helper a console it
    # needs for tasklist/find/ping, and hides it. CREATE_NEW_PROCESS_GROUP still keeps our Ctrl
    # events off it, and the breakaway below is what actually outlives us.
    base = (getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
            | getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    kw = dict(cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
              stderr=subprocess.DEVNULL, close_fds=True, **({'env': env} if env else {}))
    breakaway = getattr(subprocess, 'CREATE_BREAKAWAY_FROM_JOB', 0x01000000)
    from . import spawn          # bare: it outlives us, so it must hold nothing of the exe's unpack folder
    try:
        return spawn.bare(argv, creationflags=base | breakaway, **kw)
    except OSError as e:
        if getattr(e, 'winerror', None) not in (5, 87):
            raise
        logger.warning(f'update: Windows refused job breakaway ({e}); retrying detached')
        return spawn.bare(argv, creationflags=base, **kw)


# WHY THE UPDATE COULD NOT BE WRITTEN. "[Errno 13] Permission denied" and a path tells the owner
# nothing they can act on, and it invites the two wrong answers - run it as administrator, install
# it as a service - neither of which touches any real cause. It is not about RIGHTS: everything
# here is inside the owner's own profile and they can already write to it. Something is refusing
# this particular write, and which one it is decides what to do.
def _why_refused(new: Path, exe: Path, err: OSError) -> str:
    if new.exists():
        return (f'{new.name} is already in {new.parent} from an earlier attempt and something still has '
                f'it open - usually a virus scanner. Delete {new} and press Update again.')
    probe = new.with_name(f'.taskuary-write-test-{os.getpid()}')
    try:
        probe.write_bytes(b'x'); probe.unlink(missing_ok=True)
        folder_ok = True
    except OSError:
        folder_ok = False
    if folder_ok:
        return (f'Windows allowed an ordinary file into {new.parent} but refused a new program there. '
                'That is Controlled Folder Access (Windows Security → Virus & threat protection → '
                'Ransomware protection) or your antivirus stopping a fresh .exe from appearing. Allow '
                'Taskuary through it and press Update again.')
    return (f'Nothing can be written into {new.parent} at all - and that is the Taskuary data folder, '
            'which it is otherwise using right now, so this is almost certainly antivirus or a security '
            'policy blocking it. Allow Taskuary through and press Update again. Running as administrator '
            'does not help: the block is on the program, not on your account.')


def _apply_exe(url: str, progress=None) -> dict:
    exe = Path(sys.executable).resolve()
    stage = staging()
    new = stage / 'Taskuary.new.exe'
    new.unlink(missing_ok=True)          # a leftover from a run that never finished is not our copy
    try:
        size = _download(url, new, progress)
        script = stage / 'taskuary-update.cmd'
        from . import unpack
        boot = unpack.bootloader()
        script.write_text(swap_script(exe, new, os.getpid(), sys.argv[1:], also=[boot] if boot else ()), encoding='utf-8')
    except OSError as e:
        if getattr(e, 'errno', None) != 13 and getattr(e, 'winerror', None) not in (5, 32):
            raise
        raise RuntimeError('the new build could not be saved. '
                           + _why_refused(new, exe, e)
                           + f' (Windows said: {e})') from e
    # detached and, where Windows permits it, outside any parent Job: it must outlive us.
    _launch_swap(script, exe.parent)
    logger.info(f'update: {size:,} bytes downloaded to {new.name}; {script.name} takes over when this process exits')
    return {'how': 'exe', 'downloaded': size, 'restarting': True}


# ── the pip road ────────────────────────────────────────────────────────────────────────
def _apply_pip(progress=None) -> dict:
    from . import spawn
    if progress: progress(0, 0)
    r = spawn.run([sys.executable, '-m', 'pip', 'install', '-U', '--no-input', 'taskuary'],
                  capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError('pip could not update: ' + (r.stderr or r.stdout or '').strip()[-400:])
    # relaunch the same command line, detached, once we are gone
    import subprocess
    kw = ({'creationflags': getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)}
          if os.name == 'nt' else {'start_new_session': True})
    spawn.popen([sys.executable, *sys.argv], close_fds=True, **kw)
    return {'how': 'pip', 'restarting': True, 'pip': (r.stdout or '').strip()[-300:]}


def ready() -> dict:
    """The release to install, or the reason there is none - asked BEFORE an update waits, so it never waits for an update it cannot do."""
    if how() == 'source':
        raise RuntimeError('this is a source checkout - update it with `git pull` in the repository, then restart')
    info = check(force=True)
    if info.get('error'): raise RuntimeError(info['error'])
    if not info.get('newer'): raise RuntimeError(f'already on the latest release ({__version__})')
    return info


def apply(progress=None, info: dict = None) -> dict:
    """Do it. Returns what happened; the caller ends the process (exit_soon) when 'restarting'."""
    info = info or ready()
    return _apply_exe(info.get('url') or EXE_URL, progress) if how() == 'exe' else _apply_pip(progress)


# AN UPDATE WAITS FOR RUNNING WORK (the owner, 2026-10-25): the swap ends this process, and with it every agent and workflow run it
# holds. So Update now with work live is kept, said ("Update waits for 1 running agent"), and done the moment the last one stops -
# never by itself otherwise: only the owner's press queues it, and quitting forgets it.
# What it waits for is work IN FLIGHT (awake.update_waits_for): an agent parked at its prompt is waiting on the owner and would hold
# the update for good, so the swap closes it the way Quit does and its task stays open (TQ-1237).
IDLE_POLL = 5.0
QUEUED = {'at': None, 'error': None}
_QLOCK = threading.Lock()


def waits_line(running: str) -> str: return f'Update waits for {running}' if running else ''


def status_line(running: str = '', lit: bool = True) -> str:
    """For the Assistant, beside Settings → Updates (concierge app.find): what is known now about a newer release, from the last check -
    the header's own, never a fresh call in a chat turn - and that the page's button is lit for the owner, never pressed by the chat."""
    r = _cache['result'] or {}
    if r.get('latest'):
        s = (f"v{r['latest']} is out (this is v{r['current']}) - " + (f"the page's Update to v{r['latest']} button is lit for the owner to press"
             if lit else f"Update to v{r['latest']} on that screen, at their desk, installs it") if r.get('newer') else f"v{r['current']} is the latest release - nothing to install")
    else: s = f"this is v{__version__}; whether a newer release is out shows on the page as it opens"
    if running and r.get('newer'): s += f'. {waits_line(running)} once pressed'
    return s + '. Nothing installs unless the owner presses it.'


def when_idle(running, go, poll: float = IDLE_POLL) -> dict:
    """Run `go()` once `running()` says '' - now, or on a thread that looks every `poll` seconds. One wait at a time: a second press
    while it waits is told the same thing. `go` returns apply()'s answer; its failure is kept for the card (QUEUED['error'])."""
    busy = running()
    if not busy: return go()
    with _QLOCK:
        if QUEUED['at'] is None:
            QUEUED.update(at=time.time(), error=None)
            def wait():
                try:
                    while running(): time.sleep(poll)
                    go()
                except Exception as e:
                    logger.warning(f'update: the waiting update did not go - {e}'); QUEUED['error'] = str(e)
                finally: QUEUED['at'] = None
            threading.Thread(target=wait, name='taskuary-update-wait', daemon=True).start()
            logger.info(f'update: {waits_line(busy)}')
    return {'waiting': True, 'waits': waits_line(busy), 'restarting': False}


STOP_WAIT = 20.0                # what the children get to stop in before we go regardless: the helper is waiting on us


def exit_soon(delay: float = 1.5):
    """Leave AFTER the HTTP answer has gone out. os._exit, not sys.exit: uvicorn runs in a
    thread and pywebview owns the main one; a polite exit from a request handler goes nowhere.

    os._exit skips the server's lifespan and every atexit, so what those would have stopped is
    stopped HERE first (unpack.stop_owned): agent terminals, their browsers, headless CLI runs. Left
    running they held the old exe's unpack folder, and its bootloader answered the Update with
    "Failed to remove temporary directory" (2026-10-22). Then the folder's removal is handed to a
    quiet sweeper (unpack.handoff), so nothing a child still holds can turn into a dialog either."""
    def _go():
        time.sleep(delay)
        from . import unpack
        t = threading.Thread(target=unpack.stop_owned, daemon=True); t.start(); t.join(STOP_WAIT)
        if t.is_alive(): logger.warning(f'update: children still stopping after {STOP_WAIT:.0f}s - exiting anyway')
        unpack.handoff()
        logger.info('update: exiting so the new build can start')
        os._exit(0)
    threading.Thread(target=_go, daemon=True).start()
