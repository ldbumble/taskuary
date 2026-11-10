"""A browser of Taskuary's own, for the agents: agent-browser's official program and the Chrome it drives, fetched on first need into
the data folder. No Node, no npm, no terminal, no administrator - the way an app brings its runtime along (noderuntime.py is its twin).

An agent on an API card answered a task that needed a website with "the agent browser is not set up on this computer - set it up under
Connections" and, told yes, sent the owner to a tools card that prints `npm install -g agent-browser` (the owner, 2026-11-09: "it asks
for cli tool why?? we have an AI connected to run it"). The AI was never the problem: the browser is a program on this computer, and
nothing but a person at a terminal ever put it there. Now Taskuary does - the owner's own agent-browser on PATH is used before this one.

The program is one native file per platform: the GitHub release asset, byte for byte the file inside the npm package (which is only a
launcher around it). Both sources are tried - a company firewall often lets one through and not the other - and either is kept only when
its sha256 is the one pinned here. Chrome is agent-browser's own `install` (Chrome for Testing, into its own folder).
"""
import hashlib, io, os, platform, subprocess, tarfile, threading, time
from pathlib import Path
from loguru import logger

VERSION = '0.41.2'                          # sha256 of each release asset (github.com/vercel-labs/agent-browser/releases/tag/v<VERSION>)
SHA256 = {'win32-x64.exe': 'c2eadee7b67e326dfff02d5dd51a16ce7673eb165699d134b3ea5f05b4a7a9d0',
          'linux-x64': 'c4351f3802ffa5254d8c69f20a52e2fcf56925c6016fcf4203db25a07d811379',
          'linux-arm64': '00d291f45e1c4d527b3aa08c70c54c7c3030fde0794f8d4575aaa3ca1680f728',
          'linux-musl-x64': '5d452d57772330fe4cef9b7aeb5e7137890dde20bbb65e82b990e0bc0b35d9cd',       # the musl pair ships in the npm package only
          'linux-musl-arm64': '730a5168153e27ad1243ebe960157e69de0f24531fbbac9a040856a491bf491f',
          'darwin-arm64': '19680f06cf87d0095c318a2e80bea6b71523d95d3b651cd18d81885cd182477a',
          'darwin-x64': 'fc55608c2222650e6e0d0154f9edebd203b63bf853b85d22240bfbddbb006ea1'}
GITHUB = 'https://github.com/vercel-labs/agent-browser/releases/download'
NPM = 'https://registry.npmjs.org/agent-browser/-'
CHROME_WAIT = 900                           # Chrome is ~170 MB; a slow line still gets there
RETRY = 60                                  # a background try that failed is not made again within this: one a turn, not one a keystroke
BLOCKED = 'check the internet connection, a VPN, or a company firewall'


def home() -> Path:
    from . import config
    return config.home() / 'browser'


def asset(system: str = None, machine: str = None, libc: str = None) -> str:
    "This computer's build, e.g. 'win32-x64.exe'; '' where agent-browser ships none."
    s, m = (system or platform.system()).lower(), (machine or platform.machine()).lower()
    arch = 'arm64' if m in ('arm64', 'aarch64') else 'x64' if m in ('amd64', 'x86_64', 'x64') else ''
    if not arch: return ''
    if s == 'windows': return 'win32-x64.exe'            # no arm64 build: Windows on ARM runs the x64 one
    if s == 'darwin': return f'darwin-{arch}'
    if s != 'linux': return ''
    musl = (libc if libc is not None else platform.libc_ver()[0]) != 'glibc'
    return f"linux-{'musl-' if musl else ''}{arch}"


def _dir() -> Path: return home() / VERSION               # a pin bump is a new folder, so the old program is never mistaken for the new
def _exe() -> Path: return _dir() / ('agent-browser.exe' if os.name == 'nt' else 'agent-browser')
def find() -> str:
    "Our agent-browser, when it has been fetched; else ''."
    return str(_exe()) if _exe().is_file() else ''
def mine(p) -> bool:
    "Is this program path the one Taskuary fetched (and not the owner's own install)?"
    try: return Path(p).resolve().is_relative_to(home().resolve())
    except (OSError, ValueError): return False
def chrome() -> bool:
    "Is there a Chrome for it to drive: the owner's own (AGENT_BROWSER_EXECUTABLE_PATH), one agent-browser installed, or one we just did?"
    from . import browserview
    own = os.environ.get('AGENT_BROWSER_EXECUTABLE_PATH') or ''
    return bool(own and os.path.isfile(own)) or any((browserview.home() / 'browsers').glob('chrome-*')) or (_dir() / '.chrome').is_file()
def whole() -> bool: return bool(find()) and chrome()
def can() -> bool:
    "Can Taskuary set the browser up itself here? A test never downloads one."
    from . import config
    return bool(asset()) and not config._under_test()


def on_path() -> None:
    """Our folder on this process's PATH (last, so the owner's own install wins; never the durable PATH): a CLI agent runs `agent-browser`
    by name in its own shell. Put there before the program exists, so a session started during the download finds it when it lands."""
    from . import cliinstall
    cliinstall.ensure_on_path(_dir(), persist=False)


def _pull(get, url: str, say, what: str) -> bytes:
    r = get(url); r.raise_for_status()
    total, buf, last = int(r.headers.get('content-length') or 0), io.BytesIO(), 0
    for chunk in r.iter_content(1 << 16):
        buf.write(chunk)
        mb = buf.tell() >> 20
        if mb >= last + 16: last = mb; say(f'Setting up the browser - downloading {what}, {mb} of {total >> 20} MB' if total else f'Setting up the browser - downloading {what}, {mb} MB')
    return buf.getvalue()


def _from_npm(blob: bytes, a: str) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(blob), mode='r:gz') as t: return t.extractfile(f'package/bin/agent-browser-{a}').read()


def fetch(say=lambda s: None, get=None) -> str:
    """Download and check our agent-browser; its path. Raises RuntimeError with what went wrong, in words.
    `say` hears the progress; `get` stands in for requests.get in a test."""
    if (have := find()): return have
    a = asset()
    if not a: raise RuntimeError(f'agent-browser has no build for this computer ({platform.system()} {platform.machine()})')
    from . import config
    if get is None and config._under_test(): raise RuntimeError('a test does not download the browser')
    import requests
    get = get or (lambda url: requests.get(url, stream=True, timeout=(10, 60)))
    roads = [('npm', f'{NPM}/agent-browser-{VERSION}.tgz', lambda b: _from_npm(b, a))]
    if 'musl' not in a: roads.insert(0, ('GitHub', f'{GITHUB}/v{VERSION}/agent-browser-{a}', lambda b: b))
    say('Setting up the browser - downloading agent-browser (one time)')
    said = []
    for name, url, pick in roads:
        try: blob = pick(_pull(get, url, say, 'agent-browser'))
        except (requests.RequestException, OSError, tarfile.TarError, KeyError, AttributeError) as e:
            said.append(f'{name}: {str(e)[:120]}'); continue
        if hashlib.sha256(blob).hexdigest() != SHA256[a]:
            said.append(f'{name}: the download did not match its published checksum, so it was thrown away'); continue
        try:
            _dir().mkdir(parents=True, exist_ok=True)
            tmp = _dir() / f'.fetch-{os.getpid()}'
            tmp.write_bytes(blob); tmp.chmod(0o755); os.replace(tmp, _exe())
        except OSError as e: raise RuntimeError(f'could not save agent-browser into {_dir()} ({e})')
        on_path()
        logger.info(f'browser: agent-browser {VERSION} set up at {_exe()} (from {name})')
        return str(_exe())
    raise RuntimeError(f"agent-browser could not be downloaded ({'; '.join(said)}) - {BLOCKED}")


def install_chrome(exe: str, say=lambda s: None, run=None) -> None:
    "The Chrome agent-browser drives, by its own `install`. Raises RuntimeError in words. `run` stands in for the subprocess in a test."
    if chrome(): return
    from . import config, spawn
    if run is None and config._under_test(): raise RuntimeError('a test does not download Chrome')
    run = run or (lambda cmd: spawn.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=CHROME_WAIT,
                                        stdin=subprocess.DEVNULL))
    say('Setting up the browser - downloading Chrome (one time, about 170 MB)')
    try: r = run([exe, 'install'])
    except subprocess.TimeoutExpired: raise RuntimeError(f'Chrome was still downloading after {CHROME_WAIT // 60} minutes and was stopped - {BLOCKED}')
    except OSError as e: raise RuntimeError(f'agent-browser could not be run to download Chrome ({e})')
    if r.returncode != 0:
        tail = ' '.join(((r.stderr or '') + ' ' + (r.stdout or '')).split())[-200:]
        raise RuntimeError(f"Chrome could not be downloaded ({tail or f'agent-browser install exited {r.returncode}'}) - {BLOCKED}")
    try: (_dir() / '.chrome').write_text(VERSION, encoding='utf-8')          # it said yes: believed, wherever a later version keeps its Chrome
    except OSError: pass


# ONE SET-UP AT A TIME, HEARD BY EVERYONE WAITING ON IT: a turn that needs the browser now joins the download a turn before it started
_LOCK, _HEAR, _STATE = threading.Lock(), [], {'line': '', 'failed': '', 'at': 0.0}


def _tell(s: str) -> None:
    _STATE['line'] = s
    for f in list(_HEAR):
        try: f(s)
        except Exception as e: logger.debug(f'browser: a listener did not take "{s}" - {e}')


def ensure(say=None, get=None, run=None) -> str:
    "The program's path once it AND its Chrome are here, fetching what is missing. Raises RuntimeError with the reason, in words."
    if say: _HEAR.append(say)
    try:
        if say and _LOCK.locked() and _STATE['line']: say(_STATE['line'])        # joined half way: where it is now
        with _LOCK:
            try:
                exe = fetch(_tell, get)
                install_chrome(exe, _tell, run)
            except RuntimeError as e: _STATE.update(failed=str(e), line=''); raise
            if _STATE['line']: _tell('The browser is set up')
            _STATE.update(failed='', line='')
            return exe
    finally:
        if say and say in _HEAR: _HEAR.remove(say)


def start() -> bool:
    "Set the browser up in the background - nothing if it is here, under way, or failed a moment ago. True when a try was started."
    if whole() or _LOCK.locked() or time.time() - _STATE['at'] < RETRY: return False
    _STATE['at'] = time.time()
    def go():
        try: ensure()
        except RuntimeError as e: logger.warning(f'browser: not set up - {e}')
    threading.Thread(target=go, daemon=True, name='browser-setup').start()
    return True
