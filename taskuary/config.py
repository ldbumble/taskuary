"""Config: ~/.taskuary/config.toml (or TASKUARY_HOME) - zero assumptions, all defaults sane.

[server] port/host/token; [agents.<name>] cmd/args/resume_args/timeout/cwd/cwd_map;
[github] token/default_repo. Everything is optional: `taskuary` runs with no config at all
(SQLite store, stub agent, localhost server). TASKUARY_HOST / TASKUARY_PORT / TASKUARY_TOKEN
are runtime overlays on [server] (a container binds 0.0.0.0 this way) and are never written
back — save() keeps the on-disk [server] block. Empty env is unset, so compose cannot wipe
a token stored on the volume.
"""
import json, os
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
        import tempfile
        env = os.environ['TASKUARY_HOME'] = tempfile.mkdtemp(prefix='taskuary_test_')
        print(f'taskuary: test run with no TASKUARY_HOME - using {env}, not your real data',
              file=__import__('sys').stderr)
    p = Path(env or Path.home() / '.taskuary')
    old = Path.home() / '.taskhub'
    # one-time migration from the pre-rename data dir
    if not env and not p.exists() and old.exists(): old.rename(p)
    p.mkdir(parents=True, exist_ok=True)
    return p

def _read() -> dict:
    f = home() / 'config.toml'
    return tomllib.loads(f.read_text(encoding='utf-8')) if f.exists() else {}

def _write(d: dict):
    (home() / 'config.toml').write_text(dumps_toml(d) + '\n', encoding='utf-8')

def _env_server() -> dict:
    """Non-empty TASKUARY_* overlays. Empty is unset — an injected '' must not disable a stored token."""
    out = {}
    h, p, t = os.getenv('TASKUARY_HOST'), os.getenv('TASKUARY_PORT'), os.getenv('TASKUARY_TOKEN')
    if h: out['host'] = h
    if p: out['port'] = int(p)
    if t: out['token'] = t
    return out

def load() -> dict:
    cfg = _read()
    cfg.setdefault('server', {})
    cfg['server'].setdefault('host', '127.0.0.1')
    cfg['server'].setdefault('port', 7787)
    # every install gets an AGENT token, whether or not the owner set an owner token: without one
    # there is no way to tell a session's request from a person's, and guard.DENIED has nothing
    # to act on. It is written back to config.toml so it survives a restart.
    from . import guard
    guard.ensure_tokens(_read, _write, cfg['server'])
    # --dangerously-skip-permissions matters: without it a headless claude waits forever
    # for permission approvals nobody can click. stream-json (+ required --verbose) makes
    # claude emit events AS IT WORKS so the Board can stream the run live.
    cfg.setdefault('agents', {'coder': {'cmd': 'claude',
                                        'args': ['-p', '--dangerously-skip-permissions',
                                                 '--output-format', 'stream-json', '--verbose'],
                                        'resume_args': ['--resume'], 'timeout': 1500}})
    cfg.setdefault('github', {})
    cfg['server'].update(_env_server())
    return cfg

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
    (home() / 'config.toml').write_text(dumps_toml(out) + '\n', encoding='utf-8')
