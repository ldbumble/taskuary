"""What no stranger's session may touch, whatever its reviewer decides (spec 2026-10-14, section 3).

A fixed list checked in code - nobody approves anything here, and a call it does not name passes straight on to the
CLI's auto mode. It exists because auto mode does not review reads: in auto mode alone, a stranger's agent could read
config.toml, take the owner token, and act as the owner through Taskuary's API.

It is a floor, not a sandbox: globbing, encoding or assembling a path from pieces in a shell are auto mode's to catch."""
import os, re, posixpath
from .config import home

_CREDS = ('.ssh', '.aws', '.azure', '.config/gh', '.config/gcloud', '.config/hub', 'AppData/Roaming/GitHub CLI', 'AppData/Roaming/gcloud',
          '.docker/config.json', '.git-credentials', '.netrc', '.npmrc', '.pypirc', '.claude/.credentials.json', '.claude.json',
          '.codex/auth.json', '.gemini', '.qwen', '.kube')
_FILE_KEYS = ('file_path', 'notebook_path', 'path')
_TEXT_KEYS = ('command', 'url', 'pattern', 'glob')
_HOME_VAR = re.compile(r'\$\{?(?:env:)?(?:home|userprofile)\}?|%userprofile%|(?<![\w~])~(?=/|$|\s)', re.I)
_CD = ('cd', 'chdir', 'pushd', 'set-location', 'sl')
_SPLIT = re.compile(r'[\s;&|()<>,=`]+')

def _cf(s) -> str: return str(s).replace('\\', '/').casefold()   # always fold: APFS and NTFS are case-insensitive, and on Linux folding only refuses more

def _strip(p: str) -> str:
    "\\\\?\\C:\\x and \\\\.\\C:\\x are C:\\x; \\\\?\\UNC\\h\\s is \\\\h\\s. Windows also ignores trailing dots and spaces on a name."
    p = str(p or '').strip().strip('"\'').replace('\\', '/')
    if p[:4] in ('//?/', '//./'): p = p[4:]; p = '/' + p[3:] if p[:4].lower() == 'unc/' else p
    return '/'.join(s if s in ('.', '..') else s.rstrip('. ') or s for s in p.split('/'))

def _forms(p, cwd: str = '') -> set:
    "Every way something might open `p`: as written, with ~ and variables expanded, resolved or not - refuse if ANY is protected."
    out = set()
    for q in {_strip(p), _strip(os.path.expandvars(os.path.expanduser(str(p or ''))))}:
        if cwd and not os.path.isabs(q): q = os.path.join(cwd, q)
        out |= {_cf(os.path.normcase(f(q))) for f in (os.path.abspath, os.path.realpath)}
    return out

def _norm(p, cwd: str = '', real: bool = True) -> str:
    p = os.path.expandvars(os.path.expanduser(_strip(p)))
    if cwd and not os.path.isabs(p): p = os.path.join(cwd, p)
    return _cf(os.path.normcase((os.path.realpath if real else os.path.abspath)(p)))

def protected() -> list:
    "Taskuary's own folder plus the places credentials live, as normalised prefixes (symlink-resolved and as written)."
    rs = [home()] + [os.path.join('~', c) for c in _CREDS]
    return list(dict.fromkeys(_norm(r, real=rl) for r in rs for rl in (True, False)))

def _names() -> list:
    "Protected folders by their home-relative name, so `cd ~ && cat .ssh/x` and `../../.ssh/x` are seen without any root in sight."
    ns = [_cf(c) for c in _CREDS]
    return ns + ([_cf(home().name)] if home().name.startswith('.') else [])

def _own(tid: int, store=None) -> list:
    "This task's own files: its stranger file, its scratch folder, and the attachments of ITS messages - not another task's."
    from .store import task_ref
    ref = task_ref(tid)
    atts = [a['Path'] for m in (store.list_messages(tid) if store else []) for a in store.list_attachments(m['MessageId']) if a.get('Path')]
    fs = [home() / 'context' / f'{ref}.stranger.md', home() / 'scratch' / ref, *atts]
    return list(dict.fromkeys(_norm(f, real=rl) for f in fs for rl in (True, False)))

def _under(p, roots): return any(p == r or p.startswith(r.rstrip('/') + '/') for r in roots)
def _above(p, roots): return any(r == p or r.startswith(p.rstrip('/') + '/') for r in roots)   # a protected root lies inside p

def _deny(why: str) -> dict:
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                   'permissionDecisionReason': f"{why} - a stranger's task may not touch it"}}

def _port() -> str:
    from . import config
    return str(config.load()['server'].get('port') or 7787)

def _text_hit(text: str, own: list, prot: list, cwd: str = ''):
    "Why a command/url/glob is refused, or ''. Checked token by token so an own file's name cannot launder a neighbour's."
    h = _norm('~', real=False)
    t = _HOME_VAR.sub(h, text); t = _cf(os.path.expandvars(t)).replace('"', '').replace("'", '')   # expand BEFORE folding, quotes are not part of a path
    if re.search(':' + _port() + r'(?!\d)', t):   # any host that reaches it - 127.1, a LAN name, [::ffff:127.0.0.1] - is still this port
        return "that is Taskuary's own address"
    cur, prev, nxt = _norm(cwd) if cwd else '', '', ''     # where a relative token points: the session's folder, moved by the last `cd` before it
    for tok in filter(None, _SPLIT.split(t)):
        cur, nxt = nxt or cur, ''                # a cd takes effect AFTER its own argument is checked against the old folder
        if prev in _CD and not tok.startswith('-'):
            d = posixpath.normpath(tok); d = d if re.match(r'([a-z]:)?/', d) or not cur else posixpath.normpath(posixpath.join(cur, d))
            nxt = d if re.match(r'([a-z]:)?/', d) else ''
        prev = tok
        rel = cur and '://' not in tok and not re.match(r'(/|[a-z]:/)', tok) and ('/' in tok or tok.startswith('..'))
        n = posixpath.normpath(posixpath.join(cur, tok) if rel else tok); a = re.sub(r'^/(?=[a-z]:/)', '', n)   # "/c:/x" as bash on Windows writes it
        if _under(a, own): continue
        if _under(a, prot) or _above(a, prot) and re.match(r'([a-z]:)?/', a) or any(re.search(r'(^|/)' + re.escape(s) + r'(/|$)', n) for s in _names()):
            return f'it names {tok}'
    return ''

def check(payload: dict, tid: int, store=None) -> dict:
    "{} when the floor has nothing against this call, else a PreToolUse deny."
    inp, cwd, tool = payload.get('tool_input') or {}, str(payload.get('cwd') or ''), str(payload.get('tool_name') or '')
    own, prot = _own(tid, store), protected()
    for k in _FILE_KEYS:
        if not inp.get(k): continue
        raw = _strip(inp[k])
        if raw.startswith('//'): return _deny(f'{inp[k]} is a network path')
        for p in _forms(inp[k], cwd):
            if _under(p, prot) and not _under(p, own): return _deny(f'{inp[k]} is a protected file')
    if tool in ('Grep', 'Glob'):    # these walk a tree: a root ABOVE a protected folder reaches it just as well
        sr = {_cf(os.path.normcase(os.path.abspath(o))) for o in ((inp.get('path') and _forms(inp['path'], cwd)) or ([cwd] if cwd else []))}
        for s in sr:
            if _above(s, prot): return _deny(f'searching from {inp.get("path") or cwd} would reach a protected folder')
    if why := _text_hit(' '.join(str(inp.get(k) or '') for k in _TEXT_KEYS), own, prot, cwd): return _deny(why)
    return {}
