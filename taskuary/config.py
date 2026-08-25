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

def home() -> Path:
    p = Path(os.getenv('TASKUARY_HOME') or Path.home() / '.taskuary')
    old = Path.home() / '.taskhub'
    # one-time migration from the pre-rename data dir
    if not os.getenv('TASKUARY_HOME') and not p.exists() and old.exists(): old.rename(p)
    p.mkdir(parents=True, exist_ok=True)
    return p

def _read() -> dict:
    f = home() / 'config.toml'
    return tomllib.loads(f.read_text(encoding='utf-8')) if f.exists() else {}

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
