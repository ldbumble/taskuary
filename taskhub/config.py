"""Config: ~/.taskhub/config.toml (or TASKHUB_HOME) - zero assumptions, all defaults sane.

[server] port/host/token; [agents.<name>] cmd/args/resume_args/timeout/cwd/cwd_map;
[github] token/default_repo. Everything is optional: `taskhub` runs with no config at all
(SQLite store, stub agent, localhost server).
"""
import os, sys, tomllib
from pathlib import Path

def home() -> Path:
    p = Path(os.getenv('TASKHUB_HOME') or Path.home() / '.taskhub')
    p.mkdir(parents=True, exist_ok=True)
    return p

def load() -> dict:
    f = home() / 'config.toml'
    cfg = tomllib.loads(f.read_text(encoding='utf-8')) if f.exists() else {}
    cfg.setdefault('server', {})
    cfg['server'].setdefault('host', '127.0.0.1')
    cfg['server'].setdefault('port', 7787)
    cfg.setdefault('agents', {'coder': {'cmd': 'claude', 'args': ['-p', '--output-format', 'json'],
                                        'resume_args': ['--resume'], 'timeout': 1200}})
    cfg.setdefault('github', {})
    return cfg

def db_path() -> str:
    return str(home() / 'taskhub.db')
