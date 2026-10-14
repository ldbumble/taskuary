"""What no stranger's session may touch, whatever its reviewer decides (spec 2026-10-14, section 3).

A fixed list checked in code - nobody approves anything here, and a call it does not name passes straight on to the
CLI's auto mode. It exists because auto mode does not review reads: in auto mode alone, a stranger's agent could read
config.toml, take the owner token, and act as the owner through Taskuary's API."""
import os, re
from .config import home

_CREDS = ('.ssh', '.aws', '.azure', '.config/gh', 'AppData/Roaming/GitHub CLI', '.docker/config.json', '.git-credentials',
          '.netrc', '.claude/.credentials.json', '.claude.json', '.codex/auth.json', '.gemini', '.qwen', '.kube')
_FILE_KEYS = ('file_path', 'notebook_path', 'path')
_HOME_FORMS = r'(~|\$home|\$env:userprofile|%userprofile%)'

def _norm(p, cwd: str = '', real: bool = True) -> str:
    "One spelling per file: expanded, absolute (a relative path is the SESSION's, not the server's), case-folded on Windows, forward slashes."
    p = os.path.expandvars(os.path.expanduser(str(p or '').strip().strip('"\'')))
    if cwd and not os.path.isabs(p): p = os.path.join(cwd, p)
    return os.path.normcase((os.path.realpath if real else os.path.abspath)(p)).replace('\\', '/')

def protected() -> list:
    "Taskuary's own folder plus the places credentials live, as normalised prefixes (symlink-resolved and as written)."
    rs = [home()] + [os.path.join('~', c) for c in _CREDS]
    return list(dict.fromkeys(_norm(r, real=rl) for r in rs for rl in (True, False)))

def _own(tid: int, store=None) -> list:
    "This task's own files: its stranger file, its scratch folder, and the attachments of ITS messages - not another task's."
    from .store import task_ref
    ref = task_ref(tid)
    atts = [a['Path'] for m in (store.list_messages(tid) if store else []) for a in store.list_attachments(m['MessageId']) if a.get('Path')]
    fs = [home() / 'context' / f'{ref}.stranger.md', home() / 'scratch' / ref, *atts]
    return list(dict.fromkeys(_norm(f, real=rl) for f in fs for rl in (True, False)))

def _under(p, roots): return any(p == r or p.startswith(r.rstrip('/') + '/') for r in roots)

def _deny(why: str) -> dict:
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                   'permissionDecisionReason': f"{why} - a stranger's task may not touch it"}}

def _addresses() -> list:
    from . import config
    port = str(config.load()['server'].get('port') or 7787)
    return [f'{h}:{port}' for h in ('127.0.0.1', 'localhost', '[::1]', '0.0.0.0')]

def check(payload: dict, tid: int, store=None) -> dict:
    "{} when the floor has nothing against this call, else a PreToolUse deny."
    inp, cwd = payload.get('tool_input') or {}, str(payload.get('cwd') or '')
    own, prot = _own(tid, store), protected()
    for k in _FILE_KEYS:
        if inp.get(k):
            p = _norm(inp[k], cwd)
            if _under(p, prot) and not _under(p, own): return _deny(f'{inp[k]} is a protected file')
    text = ' '.join(str(inp.get(k) or '') for k in ('command', 'url', 'pattern'))
    if not text.strip(): return {}
    low = text.replace('\\', '/').lower()
    if any(a in low for a in _addresses()): return _deny("that is Taskuary's own address")
    for o in sorted(own, key=len, reverse=True): low = low.replace(o.lower(), ' ')   # its own files pass - but only those, not a neighbour in the same line
    low = os.path.expandvars(low).replace('\\', '/').lower()
    h = _norm('~', real=False)
    for root in prot:
        try: rel = os.path.relpath(root, h).replace('\\', '/').lower()
        except ValueError: rel = ''                                    # another drive: no home-relative form exists
        if root.lower() in low or (rel and not rel.startswith('..') and re.search(_HOME_FORMS + '/' + re.escape(rel), low)):
            return _deny(f'it names {rel or root}')
    return {}
