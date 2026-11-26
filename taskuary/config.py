"""Config: ~/.taskuary/config.toml (or TASKUARY_HOME) - zero assumptions, all defaults sane.

[server] port/host/token; [agents.<name>] cmd/args/resume_args/timeout/cwd/cwd_map;
[github] token/default_repo. Everything is optional: `taskuary` runs with no config at all
(SQLite store, stub agent, localhost server). TASKUARY_HOST / TASKUARY_PORT / TASKUARY_TOKEN
are runtime overlays on [server] (a container binds 0.0.0.0 this way) and are never written
back — save() keeps the on-disk [server] block. Empty env is unset, so compose cannot wipe
a token stored on the volume.
"""
import json, os, re
from loguru import logger
try: import tomllib
except ImportError: import tomli as tomllib  # py3.10
from pathlib import Path

_TEST_MARKS = ('pytest', 'unittest', 'fastapi.testclient', 'starlette.testclient')


def _under_test() -> bool:
    """Are we inside a test run? sys.modules is the honest signal: pytest and unittest are both
    imported by the time anything of ours is."""
    import sys
    # fastapi's TestClient is the other one, and it is the one that got past this guard the very
    # day it was written: a throwaway `python -c` driving the API to check a fix imports neither
    # pytest nor unittest, and wrote a message, a task, two routes and a memory note into the
    # owner's database. TestClient exists for nothing but testing, so its presence is proof.
    return any(m in sys.modules for m in _TEST_MARKS) and not os.getenv('TASKUARY_ALLOW_TEST_HOME')


def home() -> Path:
    """Where the owner's data lives - unless a test is asking, in which case it never is.

    tests/conftest.py points TASKUARY_HOME at a temp dir before anything of ours is imported, and
    that works for `pytest`. It does NOT work for `python tests/test_terminal.py`, because every
    test file here ends in unittest.main() and running one directly loads no conftest at all. That
    door was open, and something went through it: two copies of test_terminal's fixture task, and
    its graph:E2E message, in the owner's live database (2026-09-01; and the same class of
    accident on 2026-08-27, which cost SOUL.md and left 140 fixture tasks on the board).

    So the guard moves to where the decision is actually made. A test that has not been given a
    home gets a temp one and is told so - loudly, once - instead of quietly opening the real
    database. Set TASKUARY_ALLOW_TEST_HOME=1 for the rare test that means it."""
    env = os.getenv('TASKUARY_HOME')
    if not env and _under_test():
        from .spawn import own_temp           # ...gone again when the run ends (spawn.own_temp)
        env = os.environ['TASKUARY_HOME'] = own_temp('taskuary_test_')
        print(f'taskuary: test run with no TASKUARY_HOME - using {env}, not your real data',
              file=__import__('sys').stderr)
    p = Path(env or Path.home() / '.taskuary')
    old = Path.home() / '.taskhub'
    # one-time migration from the pre-rename data dir
    if not env and not p.exists() and old.exists(): old.rename(p)
    p.mkdir(parents=True, exist_ok=True)
    # credentials live here in plaintext; the directory itself should not be group/world readable
    # (audit 2026-09-16). mkdir inherits umask, so an existing 755 home stays 755 until this.
    # Windows chmod only toggles the read-only flag, and st_mode never reads back as 0700, so
    # without this skip every home() call would SetFileAttributes on the live data dir — including
    # while sqlite has taskuary.db open. The matching test is already skipped on nt.
    if os.name != 'nt':
        try:
            if (p.stat().st_mode & 0o777) != 0o700: p.chmod(0o700)
        except OSError:
            pass
    return p

def _read() -> dict:
    f = home() / 'config.toml'
    return tomllib.loads(f.read_text(encoding='utf-8')) if f.exists() else {}

def _put(text: str):
    """config.toml in one step: a write in place truncates it first, and a load() in that moment read no tokens, minted new ones and wrote
    them over the owner's - every open page and agent then refused as out of date (CI: the floor door answered 401 to its own token)."""
    import time, uuid
    p = home() / 'config.toml'; tmp = p.with_name(f'.config.{uuid.uuid4().hex}.tmp'); tmp.write_text(text, encoding='utf-8')
    if os.name != 'nt': tmp.chmod(0o600)      # ...the owner's alone from its first byte (red team #2, T3): every save, not only a token's write
    for i in range(50):                       # ...Windows refuses a replace while a reader holds the file open: a moment later it goes
        try: return os.replace(tmp, p)
        except PermissionError:
            if i == 49: tmp.unlink(missing_ok=True); raise
            time.sleep(.02)

def _write(d: dict): _put(dumps_toml(d) + '\n')

_CRED = re.compile(r'(token|secret|password|passwd|api_?key)$', re.I)
def backup(name: str) -> None:
    """A copy of config.toml to go back to before a migration, once - WITHOUT its tokens and keys (red team #2, T3: the copy held the owner
    token in clear beside the sealed original). Restored, the server mints fresh ones (guard.ensure_tokens); the owner's alone on disk."""
    p, b = home() / 'config.toml', home() / name
    if not p.exists() or b.exists(): return
    bare = lambda d: {k: bare(v) if isinstance(v, dict) else v for k, v in d.items() if not (_CRED.search(k) and isinstance(v, str))}
    b.write_text(dumps_toml(bare(_read())) + '\n', encoding='utf-8')
    if os.name != 'nt': b.chmod(0o600)

def port_number(value) -> int:
    """A TCP port accepted by sockets and server runners."""
    try: port = int(value)
    except (TypeError, ValueError): raise ValueError('port must be a number from 1 to 65535') from None
    if not 1 <= port <= 65535: raise ValueError('port must be a number from 1 to 65535')
    return port

def _env_server() -> dict:
    """Non-empty TASKUARY_* overlays. Empty is unset — an injected '' must not disable a stored token."""
    out = {}
    h, p, t = os.getenv('TASKUARY_HOST'), os.getenv('TASKUARY_PORT'), os.getenv('TASKUARY_TOKEN')
    if h: out['host'] = h
    if p:
        try: out['port'] = port_number(p)
        except ValueError as e: logger.warning(f'ignoring TASKUARY_PORT={p!r}: {e}')
    if t: out['token'] = t
    return out

_ONCE = __import__('contextvars').ContextVar('config_once', default=None)


class once:
    """`with config.once():` - one read of config.toml for everything inside. Opening a task asked the router for "Run again on the
    strong model" and its resolvers parsed config.toml ten times per open, 2.7x the 0.3.9.34 cost (2026-10-26). Read-only work only:
    a save inside would be shadowed by the copy read at the start."""
    def __enter__(self): self.tok = _ONCE.set({}); return self
    def __exit__(self, *a): _ONCE.reset(self.tok)


def load() -> dict:
    memo = _ONCE.get()
    if memo is not None:
        if 'cfg' not in memo: memo['cfg'] = _load()
        return memo['cfg']
    return _load()


def _load() -> dict:
    cfg = _read()
    cfg.setdefault('server', {})
    cfg['server'].setdefault('host', '127.0.0.1')
    cfg['server'].setdefault('port', 7787)
    # every install gets an AGENT token, whether or not the owner set an owner token: without one
    # there is no way to tell a session's request from a person's, and guard.DENIED has nothing
    # to act on. It is written back to config.toml so it survives a restart.
    from . import guard
    k = f'agent_token:{home()}'
    guard.ensure_tokens(_read, _write, cfg['server'], _LIVE.get(k, ''))
    _LIVE[k] = cfg['server']['agent_token']
    _owner_token(cfg['server'])
    # A FRESH INSTALL NAMES NO AI (the owner, 2026-10-20: "the advisor says claude is installed, set it up?? ... it was not, and
    # stop assuming that"): this default carried `cmd = "claude"`, cli_connections.migrate split it into a `claude` connection on
    # the first start, and setup drew Claude as "Connected" and lit it on a machine with no Claude Code. The coding profile is
    # instructions on whichever brain the owner picks (clis.KNOWN carries each CLI's headless flags for when they do).
    cfg.setdefault('agents', {'coding': {'kind': 'coding'}})
    cfg.setdefault('github', {})
    cfg['server'].update(_env_server())
    return cfg

def _owner_token(srv: dict):
    """THE OWNER TOKEN LIVES IN THE RUNNING SERVER'S MEMORY ALONE (the owner, 2026-11-25): sealed in config.toml it was still a file a session
    could read and the OS would open for it (red team F2). Minted when this process first reads its config, and never written anywhere: a
    restart mints another, and an open tab or the phone opens again from the app. A window, the launch key and the phone link are handed it
    by the server that holds it (launchkey.remote_link). A process carrying a session's marks (launchkey.in_session) holds a random one of its
    own. One an older build left on disk, sealed or plain, is deleted - and refused, as any token not this run's."""
    import secrets
    from . import launchkey
    if launchkey.in_session(): srv['token'] = secrets.token_urlsafe(24); return
    if 'token' in srv:                     # ...read off config.toml just now: an older build's
        try:
            if 'token' in (cur := _read()).get('server', {}): cur['server'].pop('token'); _write(cur)
        except Exception as e: logger.warning(f'the old owner token was not taken off config.toml ({e}) - it is refused all the same')
    srv['token'] = _LIVE.setdefault('token', secrets.token_urlsafe(24))
_LIVE: dict = {}


def db_path() -> str:
    return str(home() / 'taskuary.db')


def _tval(v):
    if isinstance(v, bool): return 'true' if v else 'false'
    if isinstance(v, (int, float)): return str(v)
    if isinstance(v, list): return '[' + ', '.join(_tval(o) for o in v) + ']'
    return json.dumps(str(v))  # json string escaping == toml basic string escaping

def dumps_toml(d: dict, prefix='') -> str:
    """Minimal TOML writer for our config shapes (scalars, string lists, nested tables).
    tomllib is stdlib-read-only; this keeps the UI able to persist config with no new deps.
    None is omitted: json.dumps(str(None)) would persist the literal string "None"."""
    lines, tables = [], []
    for k, v in d.items():
        key = k if k.replace('_', '').replace('-', '').isalnum() else json.dumps(k)
        if isinstance(v, dict): tables.append((key, v))
        elif v is None: continue
        else: lines.append(f'{key} = {_tval(v)}')
    out = (f'[{prefix}]\n' if prefix and lines else '') + '\n'.join(lines)
    for key, v in tables:
        sub = dumps_toml(v, f'{prefix}.{key}' if prefix else key)
        if sub: out += ('\n\n' if out else '') + sub
    return out

def save(cfg: dict):
    """Persist cfg to ~/.taskuary/config.toml. [server] on disk is the source of truth —
    env overlays (and None) stay runtime-only, so an agent/cwd_map save cannot leak
    0.0.0.0 or a container token into the volume. Does not mutate cfg."""
    disk, env = _read(), _env_server()
    out = {k: v for k, v in cfg.items() if k != 'server'}
    if 'server' in disk:
        out['server'] = disk['server']
    else:
        srv = {k: v for k, v in (cfg.get('server') or {}).items() if v is not None and k not in env}
        if srv: out['server'] = srv
    _put(dumps_toml(out) + '\n')
