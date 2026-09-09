"""The Install button for the coding CLIs: get claude / codex / gemini / copilot / cursor onto
this machine, and onto PATH, without sending the owner to a terminal first.

Every road into Taskuary's coding side started with "install the CLI yourself, then come back".
On the one install most people download - a double-clicked Taskuary.exe on a Windows box with no
Node - that is not a small ask, and the wizard's answer to it was a sentence: "No AI CLI found on
your PATH." A dead end at the exact step the product exists to get past.

WHAT IT RUNS is a closed table, for the same reason deps.OPTIONAL is closed: this executes an
installer, and an open field would be "run anything on this machine" wearing a button's clothes.
POST /api/cli/install is on guard.DENIED beside it - an agent reads untrusted mail, and an agent
that can install software can be talked into installing anything.

THREE WAYS IN, best first, because the machine that needs this most has no npm:
  script   the vendor's own installer (claude, cursor). Downloads their binary and runs their
           setup - claude's `claude install` does the launcher and PATH itself.
  npm      `npm install -g <pkg>`. Its global bin is already on PATH from Node's own installer.
  binary   the release archive, extracted into ~/.taskuary/bin (codex, where npm is the only
           other road). Nothing puts that on PATH but us.

AND PATH IS THREE THINGS, not one. A user-PATH write reaches no process that is already running
- not this server, not a terminal the owner already has open - so on its own it looks broken for
the rest of the day:
  1. os.environ here, so the agent runner can spawn what was just installed, now, no restart;
  2. the absolute path saved as the agent profile's `cmd` (server side), so nothing the app does
     depends on PATH at all;
  3. the registry (Windows) or the shell rc file (posix), so a terminal opened tomorrow has it.
Only (3) is what people mean by "on PATH", and it is the one that helps least today.
"""
import os, platform, shutil, threading, time
from pathlib import Path

from loguru import logger

from . import spawn

WINDOWS = os.name == 'nt'
MARK = '# added by Taskuary'                       # the rc line's fingerprint, so we append once

# name -> the ways in, best first. `os` narrows a recipe to a platform; absent means anywhere.
# npm package names and their bins verified against the registry, 2026-09-09.
RECIPES = {
    'claude': [
        {'how': 'script', 'os': 'nt', 'cmd': ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                              '-Command', 'irm https://claude.ai/install.ps1 | iex']},
        {'how': 'script', 'os': 'posix', 'cmd': ['bash', '-lc', 'curl -fsSL https://claude.ai/install.sh | bash']},
        {'how': 'npm', 'pkg': '@anthropic-ai/claude-code'},
    ],
    'codex': [
        {'how': 'npm', 'pkg': '@openai/codex'},
        # no vendor script anywhere, so the Node-less machine gets the release archive
        {'how': 'binary', 'repo': 'openai/codex', 'stem': 'codex'},
    ],
    'gemini': [{'how': 'npm', 'pkg': '@google/gemini-cli'}],
    'copilot': [{'how': 'npm', 'pkg': '@github/copilot'}],
    # cursor-agent IS on npm but ships no bin, so npm is not a road; its installer is bash-only
    'cursor': [{'how': 'script', 'os': 'posix', 'cmd': ['bash', '-lc', 'curl https://cursor.com/install -fsS | bash']}],
}

# what to look for once an installer says it is done - the bin name, not the profile's nickname
BINARY = {'claude': 'claude', 'codex': 'codex', 'gemini': 'gemini', 'copilot': 'copilot', 'cursor': 'cursor-agent'}
CMD2NAME = {v: k for k, v in BINARY.items()}       # cursor-agent -> cursor: the bin is not the recipe


def recipe_for(cmd: str) -> str:
    """Which recipe a profile's `cmd` is an install OF, or ''.

    A profile is named for its job - every install ships one called `coder` - so the name to
    install is read off the command it runs, never off the row's own name. Asking to install
    'coder' is a 422, and `coder` is the first row an owner sees."""
    base = str(cmd or '').replace('\\', '/').rsplit('/', 1)[-1].lower()   # both separators, on either OS
    for ext in ('.exe', '.cmd', '.bat', '.ps1'):
        if base.endswith(ext): base = base[:-len(ext)]
    return base if base in RECIPES else CMD2NAME.get(base, '')


_STATE = {'phase': 'idle', 'name': '', 'detail': '', 'path': '', 'at': 0.0}   # idle|installing|done|failed
_LOCK = threading.Lock()


def state() -> dict: return dict(_STATE)
def reset() -> None: _STATE.update(phase='idle', name='', detail='', path='', at=0.0)
def _set(phase, name='', detail='', path=''): _STATE.update(phase=phase, name=name, detail=str(detail)[-400:], path=path, at=time.time())


def npm() -> str:
    """The npm launcher, or ''. `npm` on Windows is npm.cmd, which which() finds only with the
    extension on some PATHs."""
    return shutil.which('npm') or (shutil.which('npm.cmd') if WINDOWS else '') or ''


def bin_dir() -> Path:
    """Where a downloaded binary lands: beside the owner's data, never inside a frozen exe's
    temp unpack directory, which lasts exactly one run."""
    from .config import home
    return home() / 'bin'


def plan(name: str, has_npm: bool = None, system: str = None) -> list:
    """The recipes that could actually run on this machine, best first. Pure - `installable` in
    the UI is just `bool(plan(name))`, so a button is never drawn over a road that does not exist."""
    nt = (system or platform.system()) == 'Windows' if system else WINDOWS
    have_npm = bool(npm()) if has_npm is None else has_npm
    out = []
    for r in RECIPES.get(name, ()):
        if r.get('os') == 'nt' and not nt: continue
        if r.get('os') == 'posix' and nt: continue
        if r['how'] == 'npm' and not have_npm: continue
        out.append(r)
    return out


def find(name: str) -> str:
    """Where the CLI is NOW - PATH first, then the places installers put things when the PATH
    this process inherited predates them (a GUI app keeps the environment it was launched with)."""
    cmd = BINARY.get(name, name)
    found = shutil.which(cmd)
    if found: return found
    home = Path.home()
    roots = [bin_dir(), home / '.local' / 'bin', home / 'bin']
    if WINDOWS: roots += [Path(os.getenv('APPDATA', '')) / 'npm', home / '.local' / 'bin']
    else: roots += [Path('/usr/local/bin'), Path('/opt/homebrew/bin')]
    for d in roots:
        for ext in ('.exe', '.cmd', '.bat', '') if WINDOWS else ('',):
            p = d / f'{cmd}{ext}'
            if p.exists(): return str(p)
    return ''


def _run(cmd: list, timeout: int = 900) -> tuple:
    """(returncode, output). One place, so a test can stand in front of every installer at once."""
    r = spawn.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
    return int(r.returncode or 0), ((r.stdout or '') + (r.stderr or '')).strip()


def _triple() -> str:
    """The release-asset platform tag. Rust triples, which is what these projects publish under."""
    m = (platform.machine() or '').lower()
    arch = 'aarch64' if m in ('arm64', 'aarch64') else 'x86_64'
    if WINDOWS: return f'{arch}-pc-windows-msvc'
    if platform.system() == 'Darwin': return f'{arch}-apple-darwin'
    return f'{arch}-unknown-linux-musl'


def _binary(name: str, recipe: dict) -> str:
    """Download the latest release archive and put the one binary in it into ~/.taskuary/bin.

    /releases/latest/download/<asset> is a permanent redirect to whatever the newest release is,
    so nothing here has to call the API or know a version number."""
    import io, tarfile, urllib.request, zipfile
    stem, dst = recipe['stem'], bin_dir()
    asset = f"{stem}-{_triple()}" + ('.exe.zip' if WINDOWS else '.tar.gz')
    url = f"https://github.com/{recipe['repo']}/releases/latest/download/{asset}"
    dst.mkdir(parents=True, exist_ok=True)
    logger.info(f'downloading {url}')
    with urllib.request.urlopen(url, timeout=300) as r: blob = r.read()      # noqa: S310 - a pinned vendor host
    out = dst / (f'{stem}.exe' if WINDOWS else stem)
    if asset.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            member = next(n for n in z.namelist() if n.lower().endswith('.exe'))
            out.write_bytes(z.read(member))
    else:
        with tarfile.open(fileobj=io.BytesIO(blob), mode='r:gz') as t:
            member = next(m for m in t.getmembers() if m.isfile())
            out.write_bytes(t.extractfile(member).read())
    if not WINDOWS: out.chmod(0o755)
    ensure_on_path(dst)
    return str(out)


def ensure_on_path(d, persist: bool = True) -> bool:
    """Put `d` on PATH: this process first (the only one that helps today), then durably.

    Returns whether anything changed. Idempotent on both halves - a PATH with the same directory
    in it four times is how the 1024-char Windows PATH limit gets hit."""
    d = Path(d)
    here = os.environ.get('PATH', '').split(os.pathsep)
    changed = str(d) not in here
    if changed: os.environ['PATH'] = os.pathsep.join([*here, str(d)]) if here != [''] else str(d)
    if persist:
        try: (persist_windows(d) if WINDOWS else persist_posix(d, Path.home()))
        except Exception as e: logger.warning(f'could not put {d} on the durable PATH: {e}')
    return changed


def persist_posix(d, home) -> str:
    """Append the export to the shell's rc file - the only PATH a new terminal reads. Written
    once: an rc file with forty identical lines in it is the bug this guards."""
    d, home = str(Path(d)), Path(home)
    rc = next((home / n for n in ('.zshrc', '.bashrc', '.profile') if (home / n).exists()), home / '.profile')
    if d in rc.read_text(encoding='utf-8', errors='replace') if rc.exists() else False: return str(rc)
    with rc.open('a', encoding='utf-8') as f: f.write(f'\n{MARK}\nexport PATH="{d}:$PATH"\n')
    return str(rc)


def persist_windows(d) -> str:
    """The USER PATH in the registry, then a broadcast so new processes read it without a logout.

    Deliberately not `setx PATH "%PATH%;..."`: that truncates at 1024 characters and writes the
    expanded SYSTEM path into the user's, which is a well-known way to wreck an environment."""
    import winreg
    d = str(Path(d))
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment', 0, winreg.KEY_READ | winreg.KEY_WRITE) as k:
        try: cur, kind = winreg.QueryValueEx(k, 'Path')
        except FileNotFoundError: cur, kind = '', winreg.REG_EXPAND_SZ
        if d in [p for p in str(cur).split(os.pathsep) if p]: return cur
        new = (str(cur).rstrip(os.pathsep) + os.pathsep + d) if cur else d
        winreg.SetValueEx(k, 'Path', 0, kind or winreg.REG_EXPAND_SZ, new)
    try:                                                   # tell everyone else, or it waits for a logout
        import ctypes
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, 'Environment', 0x0002, 5000, None)
    except Exception as e: logger.warning(f'PATH written but not broadcast: {e}')
    return new


def install(name: str, has_npm: bool = None, system: str = None) -> dict:
    """Try each road in turn until the CLI actually answers to its name. Synchronous - `start`
    is the one the API calls."""
    if name not in RECIPES:
        _set('failed', name, f'{name} is not one of the CLIs Taskuary installs ({", ".join(sorted(RECIPES))})')
        return state()
    roads = plan(name, has_npm=has_npm, system=system)
    if not roads:
        _set('failed', name, f'there is no way to install {name} on this machine automatically - '
                             + ('it needs Node (npm) first' if any(r['how'] == 'npm' for r in RECIPES[name])
                                else 'its installer does not support this operating system'))
        return state()
    _set('installing', name, f'installing {name}…')
    last = ''
    for r in roads:
        try:
            if r['how'] == 'binary':
                _binary(name, r)
            else:
                cmd = list(r['cmd']) if r['how'] == 'script' else [npm() or 'npm', 'install', '-g', r['pkg']]
                rc, out = _run(cmd)
                if rc != 0: last = out or f'{r["how"]} exited {rc}'; logger.warning(f'{name}: {r["how"]} failed - {last[-200:]}'); continue
                last = out
        except Exception as e:
            last = str(e); logger.warning(f'{name}: {r["how"]} raised - {e}'); continue
        # rc 0 proves the installer ran, not that anything is runnable: only a binary does that
        found = find(name)
        if found:
            ensure_on_path(Path(found).parent)
            _set('done', name, f'{name} is installed', found)
            logger.info(f'installed {name} at {found}')
            return state()
        last = last or 'the installer reported success but left nothing to run'
    _set('failed', name, f'could not install {name}: {last}')
    return state()


def start(name: str, **kw) -> dict:
    """Install in the background. An npm -g of a whole CLI is a minute on a slow line, and no
    HTTP request should be holding the browser open for it (wabridge.start, same shape)."""
    with _LOCK:
        if _STATE['phase'] == 'installing': return state()
        _set('installing', name, f'installing {name}…')
    threading.Thread(target=install, args=(name,), kwargs=kw, daemon=True, name=f'install-{name}').start()
    return state()
