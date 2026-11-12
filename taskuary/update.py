"""Update in place, from Settings: check what the latest release is, fetch it, swap it in, come back.

Everything the owner has - connections, tokens, the database, the operator documents, the
playbooks - lives under ~/.taskuary (config.home()), never beside the program. So an update is
only ever a program swap: nothing in the data folder is touched, and the new build opens the same
database the old one closed. That is what makes "keep the connection and all the settings" free.

Four ways Taskuary can be installed, four roads:
  setup   installed by TaskuarySetup.exe (the website's download since 2026-11-02): one folder under Programs, Start menu,
          an uninstall entry. The new installer is downloaded and run quietly after we exit; it replaces the folder and
          asks Windows for admin rights only when the app was installed for all users. Then the app is started again.
  exe     a one-file Taskuary.exe (the download before 2026-11-02, when the owner made the website's download only the
          installer). It moves into the installed app: the same TaskuarySetup.exe runs quietly for this user after we exit,
          into the install already there or the default one, the app starts from there, and the one-file exe is removed.
  pip     a wheel in a venv: `pip install -U taskuary`, then relaunch the same command line.
  source  a checkout (`pip install -e .`, the developer's machine): updating means `git pull`,
          which is not ours to run in somebody's repository - say so instead.

The latest version is the GitHub release the publish workflow cuts on every tag, and every road that downloads takes the
installer it attaches at a fixed URL (releases/latest/download/TaskuarySetup.exe). No token, no extra service, and the
same file a person would download by hand. Taskuary.exe is still attached for a while: builds up to 0.3.10.20 download
it by name, and that one-file build is what brings them onto this road.
"""
import os, re, subprocess, sys, threading, time
from pathlib import Path

import requests
from loguru import logger

from . import __version__

REPO = 'ldbumble/taskuary'
LATEST_API = f'https://api.github.com/repos/{REPO}/releases/latest'
SETUP = 'TaskuarySetup.exe'
SETUP_URL = f'https://github.com/{REPO}/releases/latest/download/{SETUP}'
APP_ID = '{6306b40a-3228-4273-8f53-a5c04956d201}'      # installer/taskuary.iss's AppId: where Inno Setup records the install
TIMEOUT = 20
# How long the helper waits for the old program to go before deciding it never will. Unbounded
# was the bug (2026-09-15): Update left a console spinning on a PID that stayed, and no app.
WAIT_S = 120
_cache = {'at': 0.0, 'result': None}
CACHE_S = 600                   # GitHub allows 60 anonymous calls an hour; the header pill asks often


def how() -> str:
    """'setup' | 'exe' | 'pip' | 'source' - which road an update takes on this install."""
    from . import spawn
    if getattr(sys, 'frozen', False): return 'setup' if spawn.onedir() else 'exe'
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
    out = {'current': __version__, 'how': how(), 'latest': None, 'newer': False, 'url': None, 'notes': None, 'error': None, 'failed': ''}
    try:
        r = requests.get(LATEST_API, timeout=TIMEOUT, headers={'Accept': 'application/vnd.github+json'})
        r.raise_for_status()
        j = r.json()
        tag = str(j.get('tag_name') or '').lstrip('v')
        out.update({'latest': tag or None, 'newer': newer(tag, __version__), 'notes': j.get('html_url'),
                    'url': next((a.get('browser_download_url') for a in j.get('assets') or []
                                 if str(a.get('name') or '').lower() == SETUP.lower()), SETUP_URL)})
        # a failed install reopens the old version with the same button lit: the card says why it failed (TQ-1397)
        if out['newer'] and out['how'] in ('setup', 'exe'): out['failed'] = last_failure()
    except Exception as e:
        # the reason is for the log; the card says what it means and what to do about it
        logger.warning(f'update check failed: {e}')
        out['error'] = ("Couldn't reach the release page to check for a newer version. "
                        'This computer may be offline, or a network filter blocks GitHub - try Check now in a minute.')
    _cache.update({'at': time.time(), 'result': out})
    return out


# ── downloading ─────────────────────────────────────────────────────────────────────────
def _download(url: str, dest: Path, progress=None) -> int:
    """Stream the new installer into staging. Size-checked against Content-Length and sniffed
    for the PE header: a half-downloaded or HTML-error-page 'exe' must never be run."""
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


# THE NEW INSTALLER IS SIGNED BY WHOEVER SIGNED THIS ONE (M5, 2026-11-08): TLS and the first two bytes were the whole check, so a
# replaced release asset ran on every machine's next Update. A signed build only runs a download that Windows calls validly signed by
# the same signer as itself; an unsigned build (releases before signing was set up, a local build) has no signer to hold it to.
def signer(path) -> tuple:
    "(status, subject) of a Windows program's Authenticode signature; ('', '') where it cannot be read."
    from . import spawn
    q = str(path).replace("'", "''")
    try: out = spawn.run(['powershell', '-NoProfile', '-NonInteractive', '-Command',
                          f"$s = Get-AuthenticodeSignature -LiteralPath '{q}'; \"$($s.Status)|$($s.SignerCertificate.Subject)\""],
                         capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError) as e: logger.warning(f'update: signature unread - {e}'); return '', ''
    st, _, sub = str(out or '').strip().partition('|')
    return st.strip(), sub.strip()

def check_signed(new: Path, exe: Path):
    "Raises, and deletes the download, unless it is validly signed by this program's own signer (a signed build only)."
    if os.name != 'nt' or not getattr(sys, 'frozen', False): return
    st, mine = signer(exe)
    if st != 'Valid' or not mine: logger.warning(f'update: this build is not signed ({st or "unread"}), so the download is not held to a signer'); return
    got = signer(new)
    if got != ('Valid', mine):
        new.unlink(missing_ok=True)
        raise RuntimeError(f"the downloaded installer is not signed by {mine.split(',')[0]} ({got[0] or 'no signature'}"
                           f"{', signed by ' + got[1].split(',')[0] if got[1] and got[1] != mine else ''}), so it was not run")


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


# ── the setup road ──────────────────────────────────────────────────────────────────────
def for_all_users(exe) -> bool:
    """Installed for everyone (Program Files) - that install, and so its update, needs Windows' admin yes; a per-user one never does."""
    from . import spawn
    return any(r and spawn.inside(str(exe), r) for r in (os.environ.get(k) for k in ('ProgramFiles', 'ProgramFiles(x86)', 'ProgramW6432')))


def install_dir() -> Path:
    """Where this user's TaskuarySetup.exe install lives: the folder Inno Setup recorded for it, else its default."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf'Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}_is1') as k:
            d = str(winreg.QueryValueEx(k, 'InstallLocation')[0] or '').rstrip('\\/')
        if d: return Path(d)
    except (ImportError, OSError): pass
    return Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local') / 'Programs' / 'Taskuary'


LEFT_S = 15                     # what the install folder's other processes get to close by themselves before they are ended


# NOTHING ELSE MAY HOLD THE INSTALL FOLDER WHEN THE INSTALLER RUNS (TQ-1397): a second window builds before it opened as its own
# Taskuary.exe (desktop.show_running ends that) closed only seconds after the server stopped answering. The installer ran the moment
# our PID went, found "Taskuary" still holding its files, could not close it, and in /SUPPRESSMSGBOXES aborted with code 5: the old
# version came back on every press. The update runs in the OLD build, so whatever still runs from the folder gets LEFT_S, then is ended.
def free_folder_line(folder) -> str:
    "One batch line: wait for every process whose program is inside `folder` to exit, then end what is left."
    d = str(folder).rstrip('\\/').replace("'", "''") + '\\'
    sel = f"Get-Process | ? {{ $_.Path -and $_.Path.StartsWith('{d}', [StringComparison]::OrdinalIgnoreCase) }}"
    return (f'powershell -NoProfile -NonInteractive -Command "$p = @({sel}); if ($p) {{ \'still running: \' + ($p.Name -join \', \'); '
            f'$p | Wait-Process -Timeout {LEFT_S} -ErrorAction SilentlyContinue; {sel} | Stop-Process -Force -PassThru -ErrorAction SilentlyContinue '
            f'| ForEach-Object {{ \'ended \' + $_.Name + \' \' + $_.Id }}; Start-Sleep -Milliseconds 500 }}" >> "%update_log%" 2>&1')


def last_failure() -> str:
    "Why the last update did not install, from the helper's own FAILED line in its log, with what to do - or ''."
    try: lines = (staging() / 'taskuary-update.log').read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError: return ''
    why = next((l.split('FAILED:', 1)[1].strip() for l in reversed(lines) if l.startswith('FAILED:')), '')
    return (f'The last update did not install - {why} - so this is still the old version. Close every Taskuary window and press Update '
            f'again; the installer\'s own log is {staging() / "taskuary-setup.log"}.') if why else ''


def setup_script(setup, exe, pid: int, args: list, all_users: bool = False, also=(), into=None) -> str:
    """The batch that runs the new installer once this process has gone, then starts the app again. Quiet (/VERYSILENT): the
    owner already pressed Update. /ALLUSERS keeps an all-users install where it is - Windows asks for the admin yes then, as for
    any installer; /CURRENTUSER never asks. The app is started by this batch, not by the installer, so it never runs elevated.
    `also`: more PIDs to wait for - the one-file bootloader that started us holds Taskuary.exe while it cleans up (unpack.bootloader).
    `into`: a one-file Taskuary.exe moving into the installed app - the installer is pointed at that folder (/DIR) and the app
    started from it; the one-file exe is removed only once the install is there. A failed install starts the old program unchanged."""
    q = lambda s: '"' + str(s).replace('"', '""') + '"'
    argstr = ' '.join(q(a) for a in args)
    go = lambda x: f'start "" /D {q(x.parent)} {q(x)} {argstr}'.rstrip()
    to = into / 'Taskuary.exe' if into is not None else exe
    log, slog = Path(setup).with_name('taskuary-update.log'), Path(setup).with_name('taskuary-setup.log')
    return '\r\n'.join([
        '@echo off', 'setlocal',
        # the helper carries the old exe's environment; PyInstaller >= 6.9 would read that as "I am my own onefile child"
        'set "PYINSTALLER_RESET_ENVIRONMENT=1"',
        f'set "update_log={log}"',
        '> "%update_log%" echo update helper (installer) started %date% %time%',
        'set /a waited=0',
        *wait_lines([pid, *also], 'stuck'),
        '>> "%update_log%" echo old process exited %date% %time%',
        free_folder_line(to.parent),
        '>> "%update_log%" echo running the installer %date% %time%',
        f'start "" /wait {q(setup)} /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS '
        f'{"/ALLUSERS" if all_users else "/CURRENTUSER"}{f" /DIR={q(into)}" if into is not None else ""} /LOG={q(slog)}',
        'set "code=%errorlevel%"',
        'if not "%code%"=="0" goto failed',
        *([f'if not exist {q(to)} goto failed'] if into is not None else []),
        '>> "%update_log%" echo starting the app %date% %time%',
        go(to),
        # the one-file exe was this program; left behind it would open the old version on the same data folder
        *([f'del /F /Q {q(exe)} >nul 2>&1'] if into is not None and str(exe).lower() != str(to).lower() else []),
        'del "%~f0"', 'exit /b 0',
        ':failed',
        '>> "%update_log%" echo ERROR: the install did not finish ^(installer code %code%^) - starting the app as it was %date% %time%',
        '>> "%update_log%" echo FAILED: the installer stopped with code %code%',
        go(exe),
        'del "%~f0"', 'exit /b 1',
        ':stuck',
        '>> "%update_log%" echo ERROR: the old process never exited; nothing installed %date% %time%',
        '>> "%update_log%" echo FAILED: the old Taskuary never closed',
        go(exe),
        'del "%~f0"', 'exit /b 3',
    ]) + '\r\n'


def _run_setup(url: str, road: str, progress=None, **kw) -> dict:
    exe, stage = Path(sys.executable).resolve(), staging()
    new = stage / SETUP
    new.unlink(missing_ok=True)          # a leftover from a run that never finished is not our copy
    try:
        size = _download(url, new, progress)
        check_signed(new, exe)
        script = stage / 'taskuary-update.cmd'
        script.write_text(setup_script(new, exe, os.getpid(), sys.argv[1:], **{'all_users': for_all_users(exe), **kw}), encoding='utf-8')
    except OSError as e:
        if getattr(e, 'errno', None) != 13 and getattr(e, 'winerror', None) not in (5, 32): raise
        raise RuntimeError('the new installer could not be saved. ' + _why_refused(new, exe, e) + f' (Windows said: {e})') from e
    # detached and, where Windows permits it, outside any parent Job: it must outlive us
    _launch_swap(script, stage)
    logger.info(f'update: {size:,} bytes downloaded to {new.name}; {script.name} runs it when this process exits')
    return {'how': road, 'downloaded': size, 'restarting': True}


def _apply_setup(url: str, progress=None) -> dict: return _run_setup(url, 'setup', progress)


def _apply_exe(url: str, progress=None) -> dict:
    """The one-file exe moves into the installed app, for this user, wherever that install already is."""
    from . import unpack
    boot = unpack.bootloader()
    return _run_setup(url, 'exe', progress, all_users=False, also=[boot] if boot else (), into=install_dir())


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
    h = how()
    if h in ('setup', 'exe'): return (_apply_setup if h == 'setup' else _apply_exe)(info.get('url') or SETUP_URL, progress)
    return _apply_pip(progress)


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
