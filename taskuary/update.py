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
        out['error'] = f'could not reach GitHub to check: {str(e)[:160]}'
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


def swap_script(exe: Path, new: Path, pid: int, args: list) -> str:
    """The batch that finishes the job after this process has gone. Waits for the PID (the exe
    is locked while it runs), moves the new file over the old (retrying - antivirus likes to hold
    a fresh download for a second), starts the new build with the SAME arguments, removes itself."""
    q = lambda s: '"' + str(s).replace('"', '""') + '"'
    argstr = ' '.join(q(a) for a in args)
    log = exe.with_name('taskuary-update.log')
    return '\r\n'.join([
        '@echo off',
        'setlocal',
        f'set "update_log={log}"',
        '> "%update_log%" echo update helper started %date% %time%',
        ':wait',
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul',
        'if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait)',
        '>> "%update_log%" echo old process exited %date% %time%',
        'set /a tries=0',
        ':swap',
        f'move /Y {q(new)} {q(exe)} >nul 2>&1',
        'if errorlevel 1 (',
        '  set /a tries+=1',
        '  if %tries% geq 30 goto giveup',
        '  timeout /t 1 /nobreak >nul',
        '  goto swap',
        ')',
        '>> "%update_log%" echo program swapped; launching new build %date% %time%',
        f'start "" /D {q(exe.parent)} {q(exe)} {argstr}'.rstrip(),
        'if errorlevel 1 goto launchfail',
        '>> "%update_log%" echo launch requested successfully %date% %time%',
        'del "%~f0"',
        'exit /b 0',
        ':giveup',
        '>> "%update_log%" echo ERROR: could not replace the old program after 30 tries %date% %time%',
        f'start "" /D {q(exe.parent)} {q(exe)} {argstr}'.rstrip(),
        'del "%~f0"',
        'exit /b 1',
        ':launchfail',
        '>> "%update_log%" echo ERROR: Windows refused to launch the new program %date% %time%',
        'exit /b 2',
    ]) + '\r\n'


def _launch_swap(script: Path, cwd: Path):
    """Start the updater outside the desktop app's lifetime.

    Corporate launchers commonly put desktop programs in a Windows Job with "kill every child
    when the parent exits" enabled. DETACHED_PROCESS removes the console, but it does *not* leave
    that Job; the old app therefore disappeared and took its updater with it. Ask Windows to break
    the helper out of the Job. Some locked-down Jobs refuse that flag, so retry without it rather
    than refusing the update before it has begun.
    """
    cmd = os.environ.get('COMSPEC') or 'cmd.exe'
    argv = [cmd, '/d', '/c', 'call', str(script)]
    base = (getattr(subprocess, 'DETACHED_PROCESS', 0)
            | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
            | getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    kw = dict(cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
              stderr=subprocess.DEVNULL, close_fds=True)
    breakaway = getattr(subprocess, 'CREATE_BREAKAWAY_FROM_JOB', 0x01000000)
    try:
        return subprocess.Popen(argv, creationflags=base | breakaway, **kw)
    except OSError as e:
        if getattr(e, 'winerror', None) not in (5, 87):
            raise
        logger.warning(f'update: Windows refused job breakaway ({e}); retrying detached')
        return subprocess.Popen(argv, creationflags=base, **kw)


def _apply_exe(url: str, progress=None) -> dict:
    exe = Path(sys.executable).resolve()
    new = exe.with_name('Taskuary.new.exe')
    size = _download(url, new, progress)
    script = exe.with_name('taskuary-update.cmd')
    script.write_text(swap_script(exe, new, os.getpid(), sys.argv[1:]), encoding='utf-8')
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


def apply(progress=None) -> dict:
    """Do it. Returns what happened; the caller ends the process (exit_soon) when 'restarting'."""
    road = how()
    if road == 'source':
        raise RuntimeError('this is a source checkout - update it with `git pull` in the repository, then restart')
    info = check(force=True)
    if info.get('error'): raise RuntimeError(info['error'])
    if not info.get('newer'): raise RuntimeError(f'already on the latest release ({__version__})')
    return _apply_exe(info.get('url') or EXE_URL, progress) if road == 'exe' else _apply_pip(progress)


def exit_soon(delay: float = 1.5):
    """Leave AFTER the HTTP answer has gone out. os._exit, not sys.exit: uvicorn runs in a
    thread and pywebview owns the main one; a polite exit from a request handler goes nowhere."""
    def _go():
        time.sleep(delay)
        logger.info('update: exiting so the new build can start')
        os._exit(0)
    threading.Thread(target=_go, daemon=True).start()
