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
import os, platform, shutil, subprocess, threading, time
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
    # muse is a static binary behind a shell installer - no npm package, and no release archive
    # named by platform triple, so `binary` is not a road either. The installer itself exits
    # `unsupported platform` on Windows (WSL2 is Meta's answer), which is why this is posix-only:
    # plan() then returns [] on Windows and the row draws no Install button over a road that
    # hard-fails. A Windows owner reaches Muse Spark through the `meta` connector instead.
    'muse': [{'how': 'script', 'os': 'posix', 'cmd': ['bash', '-lc', 'curl -fsSL https://dev.meta.ai/install.sh | bash']}],
    # devin publishes a script per OS and nothing else - no npm package, and its releases are
    # laid out by the installer's own versioned scheme rather than as triple-named archives, so
    # `binary` is not a road. Both scripts END BY RUNNING `devin setup`, the CLI's interactive
    # wizard, which has no terminal to run in when it is spawned from here: the short timeout is
    # how long we wait for a wizard that may never return, and install() treats a timeout with a
    # binary on disk as the success it is.
    'devin': [
        {'how': 'script', 'os': 'nt', 'timeout': 300,
         'cmd': ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                 '-Command', 'irm https://static.devin.ai/cli/setup.ps1 | iex']},
        {'how': 'script', 'os': 'posix', 'timeout': 300,
         'cmd': ['bash', '-lc', 'curl -fsSL https://cli.devin.ai/install.sh | bash']},
    ],
}

# what to look for once an installer says it is done - the bin name, not the profile's nickname
BINARY = {'claude': 'claude', 'codex': 'codex', 'gemini': 'gemini', 'copilot': 'copilot', 'cursor': 'cursor-agent',
          'muse': 'muse', 'devin': 'devin'}
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


# UPDATING IS NOT INSTALLING AGAIN. A CLI that ships its own updater is the one thing that knows
# where it put itself - codex keeps its releases under ~/.codex/packages/standalone/<version>
# behind a junction, and an `npm -g` over that leaves a second copy with the old one still first
# on PATH. So the vendor's updater first, the package manager only as the fallback.
#
# The button exists because a CLI too old for its own configured model fails every single run and
# says so only in the JSON it writes to stdout: codex 0.148.0 answering "The 'gpt-6-astra' model
# requires a newer version of Codex" to everything Taskuary asked it (the owner, 2026-09-11).
# A closed table, for the same reason RECIPES is one: this runs a program on the owner's machine.
UPDATES = {
    'claude': [{'how': 'self', 'args': ['update']}, {'how': 'npm', 'pkg': '@anthropic-ai/claude-code@latest'}],
    'codex': [{'how': 'self', 'args': ['update']}, {'how': 'npm', 'pkg': '@openai/codex@latest'}],
    'gemini': [{'how': 'npm', 'pkg': '@google/gemini-cli@latest'}],
    'copilot': [{'how': 'npm', 'pkg': '@github/copilot@latest'}],
}

_STATE = {'phase': 'idle', 'name': '', 'verb': 'install', 'detail': '', 'path': '', 'at': 0.0}   # idle|installing|done|failed
_LOCK = threading.Lock()


def state() -> dict: return dict(_STATE)
def reset() -> None: _STATE.update(phase='idle', name='', verb='install', detail='', path='', at=0.0)
def _set(phase, name='', detail='', path='', verb='install'):
    _STATE.update(phase=phase, name=name, verb=verb, detail=str(detail)[-400:], path=path, at=time.time())


def update_plan(name: str, has_npm: bool = None) -> list:
    """The update roads that could run here, best first. Pure, like `plan` - `updatable` in the UI
    is `bool(update_plan(...))`, so a button is never drawn over a road that does not exist."""
    have_npm = bool(npm()) if has_npm is None else has_npm
    return [r for r in UPDATES.get(name, ()) if r['how'] != 'npm' or have_npm]


def update(name: str) -> dict:
    """Bring an already-installed CLI up to date. Synchronous - `start_update` is the API's."""
    roads = update_plan(name)
    if not roads:
        _set('failed', name, f'Taskuary has no updater for {name} - reinstall it the way you installed it', verb='update')
        return state()
    # An update is not an install: with nothing here there is nothing to bring up to date, and
    # running a package manager would quietly become an install the owner did not press.
    exe = find(name)
    if not exe:
        _set('failed', name, f'{name} is not on this machine - install it first', verb='update')
        return state()
    _set('installing', name, f'updating {name}…', verb='update')
    last = ''
    for r in roads:
        try:
            cmd = [exe] + list(r['args']) if r['how'] == 'self' else [npm() or 'npm', 'install', '-g', r['pkg']]
            rc, out = _run(cmd, timeout=r.get('timeout', 900))
        except Exception as e:
            last = str(e); logger.warning(f'{name}: {r["how"]} update raised - {e}'); continue
        if rc != 0:
            last = out or f'{r["how"]} exited {rc}'; logger.warning(f'{name}: {r["how"]} update failed - {last[-200:]}'); continue
        _set('done', name, out.strip()[-400:] or f'{name} is up to date', find(name) or exe, verb='update')
        logger.info(f'updated {name}')
        return state()
    _set('failed', name, f'could not update {name}: {last}', verb='update')
    return state()


def start_update(name: str, **kw) -> dict:
    """Update in the background, for the same reason `start` installs in one."""
    with _LOCK:
        if _STATE['phase'] == 'installing': return state()
        _set('installing', name, f'updating {name}…', verb='update')
    threading.Thread(target=update, args=(name,), kwargs=kw, daemon=True, name=f'update-{name}').start()
    return state()


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


def why_not(name: str, has_npm: bool = None, system: str = None) -> str:
    """Why `plan` came back empty, in the owner's words - or '' when there IS a road.

    A row that simply vanished was the worse answer: the CLI exists, Taskuary knows about it,
    and "it is not in the list" reads as "Taskuary does not support it" rather than "your
    operating system cannot run its installer". Said out loud, the owner knows what to do
    (turn on WSL2, install Node) instead of wondering whether the app is broken."""
    if name not in RECIPES: return ''
    if plan(name, has_npm=has_npm, system=system): return ''
    nt = (system or platform.system()) == 'Windows' if system else WINDOWS
    hows = {r['how'] for r in RECIPES[name]}
    if nt and not any(r.get('os') != 'posix' for r in RECIPES[name]):
        return ("its installer does not run on Windows - install it inside WSL2 "
                "(wsl --install), or use this vendor's API connector instead")
    if 'npm' in hows and not (bool(npm()) if has_npm is None else has_npm):
        return 'it installs through npm, and Node is not on this machine yet - install Node first (nodejs.org)'
    return 'its installer does not support this operating system'


def find(name: str) -> str:
    """Where the CLI is NOW - PATH first, then the places installers put things when the PATH
    this process inherited predates them (a GUI app keeps the environment it was launched with)."""
    cmd = BINARY.get(name, name)
    found = shutil.which(cmd)
    if found: return found
    home = Path.home()
    roots = [bin_dir(), home / '.local' / 'bin', home / 'bin']
    # devin's own scheme: %LOCALAPPDATA%\devin\cli\bin on Windows, which its installer puts on the
    # USER path - a path this long-running process will not see until it is restarted, so looking
    # there is the difference between "installed" and "the installer said yes and left nothing"
    if WINDOWS: roots += [Path(os.getenv('APPDATA', '')) / 'npm', home / '.local' / 'bin',
                          Path(os.getenv('LOCALAPPDATA', '')) / 'devin' / 'cli' / 'bin']
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
                rc, out = _run(cmd, timeout=r.get('timeout', 900))
                if rc != 0: last = out or f'{r["how"]} exited {rc}'; logger.warning(f'{name}: {r["how"]} failed - {last[-200:]}'); continue
                last = out
        except Exception as e:
            last = str(e); logger.warning(f'{name}: {r["how"]} raised - {e}')
            # A TIMEOUT IS NOT PROOF OF FAILURE. An installer that ends by starting the CLI's own
            # interactive wizard (devin's does) never returns when it is spawned with no terminal
            # - while the binary it wrote a second earlier is installed and runnable. Only a
            # timeout gets this second look: any other exception left the install where it fell.
            if not (isinstance(e, subprocess.TimeoutExpired) and find(name)): continue
            last = 'the installer finished but its setup wizard needed a terminal'
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
