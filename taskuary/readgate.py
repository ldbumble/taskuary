"""AN AGENT ASKS BEFORE IT READS OUTSIDE ITS WORK (the owner, 2026-11-15: "for all agents they should ask before acting like all other actions
that ask for permissions").

Every agent - general or coding, on every brain - reads freely in its own work area: the folder it works in (a coding agent's checkout, a
general agent's scratch folder), the task's outputs folder, the files that came on the task's own mail, and the temp folder where a CLI
keeps its scratchpad. A read or a listing anywhere else is held as any other gated step is (shellgate.check: the task's Approve card, or the
owner's Allow once / Reject where those are drawn) - never a new kind of prompt. Approved, the folder is the task's for the rest of it
(a `read:` rule on the task, permissions' own table). Taskuary's own home and the places sign-ins are kept (floor.kept_secret - the same
rule a web report runs under) are never read by an agent, not even on a yes.

What is read is found by structure, never by words: a file tool's own path argument (Read, Glob, Grep, LS, an ACP call's locations, the
API road's file tools), and in a shell line every argument that is a path - drive-rooted, ~ or a home variable, or climbing out with `..`.
A path built from a variable this cannot read is held, as an unreadable delete is. Programs' own folders (Program Files, the system's,
Python's) are no one's files and pass.
"""
import os, re, sys, tempfile
from pathlib import Path

WHY = "it is outside this task's own folders"
NEVER = ("Taskuary's own data and the places sign-ins are kept are never read by an agent - not even with the owner's yes. Go on without "
         'it, and say what you needed if it matters')
ALLOWED = 'Allowed - this task may read that folder'      # a read's Approve, said as what it did: nothing "ran" (heldCard says the same)
GRANT = 'read:'                                         # a folder the owner let this task read (store.set_perm_rule)
READ_TOOLS = ('Read', 'Glob', 'Grep', 'LS', 'NotebookRead')
_KEYS = ('file_path', 'notebook_path', 'path', 'pattern', 'dir', 'directory')
# ...a `${NAME}` is one word, never a block's braces: cut there, `cat ${HOME}/.ssh/x` named only `/.ssh/x`, which exists nowhere
_SPLIT = re.compile(r'(\$\{[^}\s]*\})|\r?\n|;|&&|\|\||\||\{|\}|\(|\)')
_VAR = re.compile(r'\$\{?(?:env:)?(\w+)\}?|%(\w+)%', re.I)
_WILD = re.compile(r'[*?\[]')


def _n(p) -> str: return os.path.normcase(os.path.realpath(os.path.expanduser(str(p))))
def _in(p: str, root: str) -> bool: return bool(root) and (p == root or p.startswith(root.rstrip('\\/') + os.sep))


def own(store, tid, cwd: str = '') -> list:
    """The task's own work area, as normalised roots: where it works, its outputs, Taskuary's scratch, its mail's files - and the context
    files Taskuary writes for it and tells it to read (context.files; recorded on the real CLI, 2026-11-16: its Read was refused as Taskuary's
    own data, and the agent told the owner "the task's context file was blocked from reading")."""
    from . import config, context, outputs
    rs = [cwd, config.home() / 'scratch'] + ([outputs.folder(int(tid)), *context.files(int(tid))] if str(tid or '').isdigit() else [])
    if store is not None and str(tid or '').isdigit():
        # ...and each of its messages' own folders whole (artifacts.attachment_dir's: one per message - named, never made), so a search across what came on the task
        # is its own work - timed on a long task, 2026-11-16: a grep over its mail's files was refused as Taskuary's data, and it worked around
        ms = store.list_messages(int(tid))
        rs += [a['Path'] for m in ms for a in store.list_attachments(m['MessageId']) if a.get('Path')] + [config.home() / 'attachments' / str(int(m['MessageId'])) for m in ms]
    return [_n(r) for r in dict.fromkeys(map(str, rs + checkouts(store) + named(store, tid))) if r]


# A FOLDER THE OWNER NAMES IS HIS GO-AHEAD (design round 3, 2026-11-18: "fix the rounding bug - my checkout is at <path>" from New, and the
# agent's every read there would have stood as a card asking him to let it read the folder he had just pointed it at). The paths in his own
# words on the task - what he typed in New, his lines in its chat - found by their shape (drive-rooted, ~ or /), each the longest stretch of
# his words that is a folder or a file here (a file: its folder). Never a place the never-list keeps: his naming it does not open it
_PATHISH = re.compile(r'(?<![\w/\\])(?:[A-Za-z]:[\\/]|~[\\/]|/(?=\w))')
def named(store, tid) -> list:
    "The folders the owner named in his own words on task `tid` that exist here."
    if store is None or not str(tid or '').isdigit(): return []
    from . import floor, general
    t = store.get_task(int(tid)) or {}
    said = [str(t.get('Summary') or '')] if t.get('OriginBase') == 'owner' else []
    said += [str(c.get('Body') or '') for c in store.list_comments(int(tid), internal=True) if c.get('ActorType') == general.USER_TYPE and not general.is_brief(c)]
    nev, out = [_n(p) for p in floor.kept_secret()], []
    for text in said:
        for line in text.splitlines():
            for m in _PATHISH.finditer(line):
                words = line[m.start():].split(' ')
                for k in range(len(words), 0, -1):           # ...the longest stretch first: a folder's name may hold a space
                    p = Path(' '.join(words[:k]).rstrip('.,;:)"\'`').strip('"\'`')).expanduser()
                    try: d = p if p.is_dir() else p.parent if p.is_file() else None
                    except OSError: d = None
                    if d is None: continue
                    if not any(_in(_n(d), r) for r in nev): out.append(str(d))
                    break
    return list(dict.fromkeys(out))


def checkouts(store) -> list:
    """EVERY CHECKOUT OF A REPOSITORY TASKUARY HAS IS WORK, FOR EVERY AGENT (the owner, 2026-11-16, "we went through this 50 times": a general
    agent asked to "read the folder FanApp" - his own GitHub-connected repository, whose checkout coding tasks run in): the checkouts the agents'
    profiles map their repositories to (repochoice), and every checkout a coding task's session ran in (its transcripts) - as folders, never
    the folders above them."""
    if store is None: return []
    from . import repochoice
    out = [p for p in repochoice._paths(store).values() if p]
    try: out += [r['Cwd'] for r in store._rows("SELECT DISTINCT Cwd FROM transcript WHERE IFNULL(Cwd,'')<>''") if repochoice.is_checkout(r['Cwd'])]
    except Exception: pass
    return list(dict.fromkeys(map(str, out)))


# WHAT ITS OWN CLI FETCHED FOR IT IS ITS WORK TOO (the owner, 2026-11-16, of a research turn whose PDF read-back was held as a card under its
# finished answer: "files the agent's own CLI downloaded during the task count as its work area"). The exact folders, never their parents:
# Claude Code keeps what a WebFetch saved in <its home>/projects/<the session's folder, spelled>/<session>/tool-results - the project part
# names THIS task's folder, so another task's or the owner's own sessions are not in it; Codex keeps the pictures it made in
# <CODEX_HOME>/generated_images/<thread>, read here only for the threads this task's sessions ran. Everything else in those homes - their
# sign-ins, settings, other sessions - still asks, or is never read (floor.kept_secret).
def _slug(cwd: str) -> str: return re.sub(r'[^A-Za-z0-9]', '-', str(cwd or ''))
def fetched(p: str, cwd: str = '', sids=()) -> bool:
    """Is normalised path `p` inside a folder the task's own CLI downloaded into: Claude Code's tool-results for a session started in `cwd`,
    or Codex's pictures for one of `sids`?"""
    from .climodels import claude_home
    if cwd:
        base = _n(Path(claude_home()) / 'projects' / _slug(cwd))
        if _in(p, base):
            rest = p[len(base):].lstrip('\/').split(os.sep)
            if len(rest) >= 3 and rest[1] == 'tool-results' and rest[0]: return True
    codex = _n(Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'generated_images')
    return any(_in(p, _n(Path(codex) / str(sid))) for sid in sids if sid)


def _sids(store, tid) -> list:
    "The ids of the CLI sessions this task's agents ran (their transcripts): the threads whose own downloads are its work."
    if store is None or not str(tid or '').isdigit(): return []
    try: return [r['Sid'] for r in store._rows('SELECT DISTINCT Sid FROM transcript WHERE TaskId=?', (int(tid),)) if r.get('Sid')]
    except Exception: return []


def _open() -> list:
    """The temp folder, where a CLI keeps its scratchpad, and installed programs' folders - nobody's files: reading a library or a tool
    there is not reading the owner's things. Judged after the never-list: Taskuary's home in a temp folder is still Taskuary's."""
    rs = [tempfile.gettempdir(), sys.base_prefix, sys.prefix, *(os.environ.get(v) for v in ('ProgramFiles', 'ProgramFiles(x86)', 'ProgramW6432', 'SystemRoot'))]
    # ...and a program installed for this user alone (%LOCALAPPDATA%\Programs - Python, VS Code, most per-user installers): the real-CLI walk,
    # 2026-11-16 - an agent looking for its python (`ls .../AppData/Local/Programs/Python`) was held as a card asking him to let it read "Python"
    if os.name == 'nt' and os.environ.get('LOCALAPPDATA'): rs.append(os.path.join(os.environ['LOCALAPPDATA'], 'Programs'))
    if os.name != 'nt': rs += ['/tmp', '/usr', '/bin', '/lib', '/opt', '/dev', '/proc', '/sys', '/System', '/Library', '/Applications']
    # ...and A CLI'S OWN INSTRUCTIONS - the skills, plugins, agents and commands it loads to work (the owner's live task, 2026-11-17: a coding
    # agent reading ~/.claude/skills/impeccable/reference/craft-floor.md stood as a card "Read craft-floor.md in reference"). Its sign-ins and
    # settings in the same home stay on the never-list (floor.kept_secret), judged before this
    from .climodels import claude_home, codex_home
    rs += [Path(h) / d for h in (claude_home(), codex_home(), Path.home() / '.agents') for d in ('skills', 'plugins', 'agents', 'commands')]
    return [_n(r) for r in rs if r]


def opened(store, tid, p: dict) -> bool:
    """A held step that was only reads the gate lets through now (`p` a shell_act payload): never his to answer, so never drawn (the owner,
    2026-11-17: "Read craft-floor.md in reference · Dismissed" stood after the CLI's own skills were opened - "it told you to get rid of it").
    His own Approve is no opening here: a folder he let in stays his press, on its card."""
    from . import floor, shellgate
    if p.get('action') != 'shell_act' or not p.get('reads'): return False
    cwd = p.get('cwd') or ''
    if p.get('command') and shellgate.acts(p['command'], cwd): return False
    ok, nev = own(store, tid, cwd) + _open(), [_n(x) for x in floor.kept_secret()]
    return all(not any(_in(_n(f), r) for r in nev) and any(_in(_n(f), r) for r in ok) for f in p['reads'])


def granted(store, tid) -> list:
    if store is None or not str(tid or '').isdigit(): return []
    return [r['Pattern'][len(GRANT):] for r in store.perm_rules(int(tid)) if str(r.get('Pattern') or '').startswith(GRANT) and r.get('Answer') == 'allow']


def grant(store, tid, folders) -> None:
    for f in folders or []: store.set_perm_rule(int(tid), GRANT + _n(f), 'allow')


def judge(store, tid, paths, cwd: str = '') -> tuple:
    """(held, never) for the paths a call reads: `held` one step per folder outside the work area ({'tool', 'what', 'why', 'where',
    'folder'} - shellgate's own shape), `never` the reason when one is Taskuary's own or a sign-in place ('' else). None in `paths` is a
    path that could not be read, held as a step of its own."""
    from . import floor
    mine, nev, ok, sids = own(store, tid, cwd), [_n(p) for p in floor.kept_secret()], granted(store, tid) + _open(), _sids(store, tid)
    held, blind = {}, False
    for raw in paths or []:
        if raw is None: blind = True; continue
        p, pat = _n(_cut(raw)), _n(raw)
        # ...a never-place is never the work's: only a work folder INSIDE it (the task's scratch, outputs, mail in Taskuary's home) lets a
        # read there through - a checkout at the home folder does not open the sign-ins in it. A glob that can reach one is that one
        sec = [r for r in nev if _in(p, r) or (pat != p and _reaches(pat, r))]
        if any(_in(p, r) and (not sec or any(_in(r, n) for n in sec)) for r in mine) or (not sec and fetched(p, cwd, sids)): continue
        if sec: return [], NEVER
        if any(_in(p, r) for r in ok): continue
        p = os.path.realpath(os.path.expanduser(_cut(str(raw))))     # ...said as the owner's own spelling of it, never case-folded
        folder = p if os.path.isdir(p) else os.path.dirname(p)
        held.setdefault(folder, []).append('' if folder == p else os.path.basename(p))
    out = [{'tool': 'read', 'what': _said(f, ns), 'why': WHY, 'where': f, 'folder': f} for f, ns in held.items()]
    if blind: out.append({'tool': 'read', 'what': 'read files at a path it builds from a variable', 'why': WHY, 'where': '', 'folder': ''})
    return out, ''


def _cut(p: str) -> str:
    "A glob's path up to the folder it lists - the part that names a real place."
    return re.split(r'[\\/](?=[^\\/]*' + _WILD.pattern + ')', str(p), maxsplit=1)[0]


def _reaches(pat: str, root: str) -> bool:
    """Can glob `pat` (normalised) match `root` or reach inside it? Matched name by name as a shell does: `*` takes no leading dot, so
    `~/*` is not `~/.ssh`, while `~/.s*` is."""
    import fnmatch
    ps, rs = pat.split(os.sep), root.split(os.sep)
    return len(ps) > 1 and all(fnmatch.fnmatchcase(r, q) and (q == r or not r.startswith('.') or q.startswith('.')) for r, q in zip(rs, ps))


def _said(folder: str, names: list) -> str:
    fs, place = [n for n in dict.fromkeys(names) if n], os.path.basename(folder.rstrip('\\/')) or folder
    return f"read {', '.join(fs[:3])}{' and more' if len(fs) > 3 else ''} in {place}" if fs else f'read the folder {place}'


def _expand(t: str, cwd: str, env: dict) -> str | None:
    "A path token with its variables filled in - None when one names nothing this can read."
    def sub(m):
        n = (m.group(1) or m.group(2)).lower()
        v = env.get(n) or next((v for k, v in os.environ.items() if k.lower() == n), None)
        if v is None and n == 'home': v = os.path.expanduser('~')
        if v is None: raise KeyError(n)
        return v
    if re.search(r'\$\{(?:env:)?\w+[^\w}]', t): return None          # `${HOME:-/x}` and its kin pick their value at run time: unread, held
    try: t = _VAR.sub(sub, t)
    except KeyError: return None
    return os.path.expanduser(t)


def _pathish(t: str) -> bool:
    """Drive-rooted, Git Bash's /c/, ~, a variable with a path after it, a rooted POSIX path - or a relative one that climbs out with `..`.
    A bare `$f` is a loop's word, not a place."""
    if re.match(r'^[A-Za-z]:[\\/]|^~(?=[\\/]|$)|^[$%].*[\\/]', t) or '..' in re.split(r'[\\/]', t): return True
    return t.startswith('/') and (bool(re.match(r'^/[A-Za-z](?=/|$)', t)) if os.name == 'nt' else len(t) > 1)


def _segments(cmd: str) -> list:
    "The line cut where one command ends and another begins - a `${NAME}` kept whole."
    out, cur = [''], 0
    for m in _SPLIT.finditer(cmd):
        out[-1] += cmd[cur:m.start()] + (m[1] or ''); cur = m.end()
        if not m[1]: out.append('')
    out[-1] += cmd[cur:]
    return out


def command_paths(cmd: str, cwd: str = '', env: dict = None) -> list:
    """Every path a shell line names as an argument, through `cd`, `bash -c "..."` and `--opt=value` - None for one built from a variable
    it cannot read. The program itself, options, URLs and switches (`/s`) are not paths."""
    from .browsergate import words
    from .shellgate import _OWN
    out, here, env = [], cwd, dict(env or {})
    for seg in _segments(str(cmd or '')):
        # ...a path kept in a variable is read where the variable is (`$p='C:/x.csv'; Get-Content $p` - the real-CLI walk, 2026-11-16)
        if (m := re.match(r'^\s*\$?([A-Za-z_]\w*)\s*=\s*([^=].*)$', seg)):
            v = m[2].strip().strip('"\'')
            env[m[1].lower()] = v
            seg = f'= {v}'
        w = words(seg)
        while w and (re.match(r'^[A-Za-z_]\w*=', w[0]) or w[0].lower() in ('&', 'sudo', 'time', 'nohup', 'command', 'exec', 'call', 'then', 'do', 'if', 'else')): w = w[1:]
        if not w: continue
        tool = re.sub(r'\.(exe|cmd|ps1|bat)$', '', os.path.basename(w[0].replace('\\', '/')).lower())
        if tool in ('bash', 'sh', 'powershell', 'pwsh', 'cmd'):
            i = next((i for i, x in enumerate(w) if x.lower() in ('-c', '-command', '/c', '/k')), None)
            if i is not None: out += command_paths(' '.join(w[i + 1:]), here, env)
            continue
        cd, named = tool in ('cd', 'chdir', 'set-location', 'sl', 'pushd'), len(out)
        for x in w[1:]:
            x = re.sub(r'^\d?[<>]+&?', '', x)
            if x.startswith('-'): x = x.split('=', 1)[1] if '=' in x else ''
            if (v := _VAR.fullmatch(x)) and (v[1] or v[2]).lower() in env: x = env[(v[1] or v[2]).lower()]
            # ...after a `cd` away, a plain name that is there is read there (`cd ~ && cat .ssh/x`)
            near = here != cwd and here and x and not x.startswith('-') and os.path.exists(os.path.join(here, x))
            # ...and Taskuary's own address as a session is handed it ($TASKUARY_URL/api/...) is a web address, never a file: a read-only curl
            # of its own API was held as "a path it builds from a variable", a card each time the agent looked (the roads audit, 2026-11-19)
            if not x or '://' in x or _OWN.match(x) or re.match(r'^/\w$', x) or re.match(r'^(/dev/|\d$)', x) or not (near or _pathish(x)): continue
            e = _expand(x, here, env)
            if e is None: out.append(None); continue
            e = re.sub(r'^/([A-Za-z])(?=/|$)', r'\1:', e) if os.name == 'nt' else e
            if not os.path.isabs(e): e = os.path.join(here or os.getcwd(), e)
            # ...a rooted token whose first folder does not exist is a pattern or an API path, not a file (`grep /api/ x`). A glob stays
            # whole: judge reads the folder it lists, and whether it can reach a sign-in place
            parts = Path(_cut(e)).parts
            if len(parts) > 1 and not os.path.exists(os.path.join(parts[0], parts[1])): continue
            if cd: here = _cut(e); break
            out.append(e)
        else:
            if cd and len(w) == 1: here = os.path.expanduser('~')          # a bare `cd` goes home
        # ...a step that names no path reads where the line has moved to: `cd ~/Documents && ls`
        if not cd and len(out) == named and here != cwd: out.append(here)
    return out


def tool_paths(inp: dict, locations=None, cwd: str = '') -> list:
    "The paths a file tool reads: its own path argument, else the folder it runs in; an ACP call's locations too."
    inp = inp if isinstance(inp, dict) else {}
    ps = [str(inp[k]) for k in _KEYS if isinstance(inp.get(k), str) and inp[k].strip() and (k != 'pattern' or _pathish(inp[k]))]
    ps += [str(l.get('path') if isinstance(l, dict) else l) for l in locations or [] if (l.get('path') if isinstance(l, dict) else l)]
    out = []
    for p in ps:
        p = os.path.expanduser(p)
        if not os.path.isabs(p): p = os.path.join(cwd or os.getcwd(), p)
        out.append(p)
    return out


def env_for(store, tid, cwd: str = '') -> dict:
    "The variables a session of this task has that the server does not: its outputs folder and the folder it is in."
    from . import outputs
    return {'taskuary_outputs': str(outputs.folder(int(tid))) if str(tid or '').isdigit() else '', 'pwd': cwd}


def of_command(store, tid, cmd: str, cwd: str = '') -> tuple:
    "(held, never) for a shell line."
    return judge(store, tid, command_paths(cmd, cwd, env_for(store, tid, cwd)), cwd)
