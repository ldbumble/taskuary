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
import os, posixpath, re, sys, tempfile
from pathlib import Path
from urllib.parse import unquote

from .gate import TABLE
WHY, NEVER = TABLE['reads'].why, TABLE['never'].why          # said as the one table says them (gate.TABLE)
NEVER_WRITE = TABLE['unwritable'].why
UNKNOWN = 'where that path leads is not known until it runs'      # a path built as the line runs: nothing says it is outside (judge)
ALLOWED = 'Allowed - this task may read that folder'      # a read's Approve, said as what it did: nothing "ran" (heldCard says the same)
GRANT = 'read:'                                         # a folder the owner let this task read (store.set_perm_rule)
READ_TOOLS = ('Read', 'Glob', 'Grep', 'LS', 'NotebookRead')
_KEYS = ('file_path', 'notebook_path', 'path', 'pattern', 'dir', 'directory')
# ...a `${NAME}` is one word, never a block's braces: cut there, `cat ${HOME}/.ssh/x` named only `/.ssh/x`, which exists nowhere
_SPLIT = re.compile(r'(\$\{[^}\s]*\})|\r?\n|;|&&|\|\||\||\{|\}|\(|\)')
# ...a name that starts with a letter or `_`: `$5.46` in a script's text is a price, never a folder (the HIPAA walk, 2026-11-22: a PDF written
# to the task's own outputs held as "a path it builds from a variable" - the copper price in its words)
_VAR = re.compile(r'\$\{?(?:env:)?([A-Za-z_]\w*)\}?|%([A-Za-z_]\w*)%', re.I)
_WILD = re.compile(r'[*?\[]')
# a variable read by name in a script's text: Python's os.environ[...] / .get / getenv, Node's process.env, Ruby's ENV[...], Perl's $ENV{...}
_ENV_REF = re.compile(r'''(?:os\.environ(?:\.get)?|os\.getenv|process\.env|Deno\.env\.get|\bENV|\$ENV)\s*[\[({.]?\s*["']?([A-Za-z_]\w*)["']?\s*[\])}]?''')


def _n(p) -> str: return os.path.normcase(os.path.realpath(os.path.expanduser(str(p))))
def _in(p: str, root: str) -> bool: return bool(root) and (p == root or p.startswith(root.rstrip('\\/') + os.sep))


# WHAT THE AGENT WROTE IS ITS OWN WORK (the goal walk on Claude CLI, 2026-11-22: it drew a picture in a scratch folder of its own, and its read
# of the script and SVG it had just written stood as an Approve card - "outside this task's own folders" - the picture waiting on him). The
# folder of every file a task's agent writes is its own for the rest of the task; the never-places stay shut whatever it wrote there
WRITE_TOOLS = ('Write', 'Edit', 'MultiEdit', 'NotebookEdit')
# A PATH THAT IS ONLY LISTED - its names, never what is in its files: a folder holding a never-place may be listed on his press (`ls ~`,
# `find ~ -name x`, the LS tool), and is never read through (`grep -r ~`, `find ~ -exec cat`, `tar c ~`). judge reads the mark
class Listed(str): pass
LIST_TOOLS = ('LS', 'Glob')
def listed(paths): return [Listed(p) if isinstance(p, str) else p for p in paths]
# ...the programs that list names, and those that only filter the names piped to them: a line of these alone reads no file's contents
_LISTS = {'ls', 'dir', 'tree', 'du', 'stat', 'find', 'get-childitem', 'gci', 'get-item', 'gi', 'test-path', 'resolve-path', 'realpath', 'pwd'}
_NAMES = {'', '=', 'head', 'tail', 'sort', 'uniq', 'wc', 'grep', 'egrep', 'fgrep', 'findstr', 'where-object', 'where',
          '?', 'select-object', 'select', 'sort-object', 'measure-object', 'measure', 'format-table', 'ft', 'format-list', 'fl', 'out-string',
          'more', 'less', 'cut', 'tr', 'echo', 'write-output', 'write-host', 'cd', 'chdir', 'set-location', 'sl', 'pushd', 'popd', 'true'}
_RUNS_ON = ('-exec', '-execdir', '-ok', '-okdir')            # find's own way of reading what it found
WROTE: dict = {}
def wrote(tid, paths) -> None:
    "Note the folders task `tid`'s agent wrote files in (its file tools' own paths)."
    if not str(tid or '').isdigit(): return
    WROTE.setdefault(int(tid), set()).update(_n(os.path.dirname(p) if not os.path.isdir(p) else p) for p in paths or [] if p)


def own(store, tid, cwd: str = '') -> list:
    """The task's own work area, as normalised roots: where it works, its outputs, Taskuary's scratch, its mail's files - and the context
    files Taskuary writes for it and tells it to read (context.files; recorded on the real CLI, 2026-11-16: its Read was refused as Taskuary's
    own data, and the agent told the owner "the task's context file was blocked from reading")."""
    from . import config, context, outputs
    # ...ITS OWN SCRATCH, never every task's (walk 9, 2026-11-23): its work folder, its kept turns and the browser's downloads - and the tasks'
    # outputs, where one task's deliverable is another's to use by its path (sharedfiles) - never another task's own scratch work
    from .browserview import downloads
    rs = [cwd] + ([outputs.work_folder(int(tid)), config.home() / 'scratch' / 'outputs', outputs.turns_folder(int(tid)), downloads(),
                   *context.files(int(tid))] if str(tid or '').isdigit() else [config.home() / 'scratch'])
    if store is not None and str(tid or '').isdigit():
        # ...and each of its messages' own folders whole (artifacts.attachment_dir's: one per message - named, never made), so a search across what came on the task
        # is its own work - timed on a long task, 2026-11-16: a grep over its mail's files was refused as Taskuary's data, and it worked around
        ms = store.list_messages(int(tid))
        rs += [a['Path'] for m in ms for a in store.list_attachments(m['MessageId']) if a.get('Path')] + [config.home() / 'attachments' / str(int(m['MessageId'])) for m in ms]
    rs += sorted(WROTE.get(int(tid), ())) if str(tid or '').isdigit() else []
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
            rest = p[len(base):].lstrip('\\/').split(os.sep)
            if len(rest) >= 3 and rest[1] == 'tool-results' and rest[0]: return True
    codex = _n(Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'generated_images')
    return any(_in(p, _n(Path(codex) / str(sid))) for sid in sids if sid)


def _sids(store, tid) -> list:
    """The ids of the CLI sessions this task's agents ran (their transcripts) and its chat's kept conversation (session_resume - his live app,
    2026-11-25: a chat on Codex keeps no transcript, so the picture its own image tool drew for the task was nobody's work): the threads
    whose own downloads are its work."""
    if store is None or not str(tid or '').isdigit(): return []
    try: kept = (store.saved_session(int(tid)) or {}).get('NativeId')
    except Exception: kept = None
    try: return [*(r['Sid'] for r in store._rows('SELECT DISTINCT Sid FROM transcript WHERE TaskId=?', (int(tid),)) if r.get('Sid')), *([kept] if kept else [])]
    except Exception: return [kept] if kept else []


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


# ...AND WHERE PROGRAMS INSTALLED FOR THE WHOLE MACHINE KEEP THEIR OWN FILES (%ProgramData%: a package manager's bin, a tool's shims), ITS NAMES
# ARE LISTED (the real-CLI check, 2026-11-26: an agent looking for a converter ran `ls C:/ProgramData/chocolatey/bin` - held as a card asking
# him to let it read "bin", and it stopped there). Names only (Listed): what a file there holds - a service's keys, a program's data - waits as before
def _listable() -> list: return [_n(os.environ['ProgramData'])] if os.name == 'nt' and os.environ.get('ProgramData') else []


def opened(store, tid, p: dict) -> bool:
    """A held step that was only reads the gate lets through now (`p` a shell_act payload): never his to answer, so never drawn (the owner,
    2026-11-17: "Read craft-floor.md in reference · Dismissed" stood after the CLI's own skills were opened - "it told you to get rid of it").
    His own Approve is no opening here: a folder he let in stays his press, on its card."""
    from . import floor, shellgate
    if p.get('action') != 'shell_act' or not p.get('reads'): return False
    cwd = p.get('cwd') or ''
    if p.get('command') and shellgate.acts(p['command'], cwd) or TABLE['settings'].why in str(p.get('why') or ''): return False
    ok, nev = own(store, tid, cwd) + _open(), [_n(x) for x in floor.kept_secret()]
    return all(not any(_in(_n(f), r) for r in nev) and any(_in(_n(f), r) for r in ok) for f in p['reads'])


def granted(store, tid) -> list:
    if store is None or not str(tid or '').isdigit(): return []
    return [r['Pattern'][len(GRANT):] for r in store.perm_rules(int(tid)) if str(r.get('Pattern') or '').startswith(GRANT) and r.get('Answer') == 'allow']


def grant(store, tid, folders) -> None:
    for f in folders or []: store.set_perm_rule(int(tid), GRANT + _n(f), 'allow')


def judge(store, tid, paths, cwd: str = '', write: bool = False, unread=()) -> tuple:
    """(held, never) for the paths a call reads: `held` one step per folder outside the work area ({'tool', 'what', 'why', 'where',
    'folder'} - shellgate's own shape), `never` the reason when one is Taskuary's own or a sign-in place ('' else). None in `paths` is a
    path that could not be read, held as a step of its own. `write`: the paths it writes - the same work area and never-places, and of
    the open places only the temp folder: a program's own folder (Taskuary's package among them) is read freely, never written.
    `unread`: the words those unreadable paths were written as - named on their step, which says what is so: where it leads is not known."""
    if not paths: return [], ''
    from . import floor
    mine, nev, sids = own(store, tid, cwd), [_n(p) for p in floor.kept_secret()], () if write else _sids(store, tid)
    ok = granted(store, tid) + ([_n(tempfile.gettempdir())] if write else _open())
    verb, why = ('write', TABLE['writes'].why) if write else ('read', WHY)
    held, blind, out = {}, False, []
    for raw in paths or []:
        if raw is None: blind = True; continue
        # ...WHAT A LATER SESSION RUNS IS NEVER JUST WORK (red team #2, T2): a git hook, git's config, a CLI's settings or hooks - the floor's
        # one list (floor._is_conf), on every road - waits for his press even in the agent's own checkout; his yes lets that one file be written
        if write and floor._is_conf(c := floor._norm(raw)) and not any(_in(_n(raw), _n(g)) for g in granted(store, tid)):
            out.append(settings(f'write {os.path.basename(c)}', _n(raw))); continue
        p, pat = _n(_cut(raw)), _n(raw)
        # ...a never-place is never the work's: only a work folder INSIDE it (the task's scratch, outputs, mail in Taskuary's home) lets a
        # read there through - a checkout at the home folder does not open the sign-ins in it. A glob that can reach one is that one, and so
        # is a folder that holds one (red team #3: `grep -r token /`, `tar c ~`, `find / -exec cat` read config.toml past the never-list)
        sec = [r for r in nev if _in(p, r) or (_reaches(pat, r) if pat != p else _in(r, p) and not isinstance(raw, Listed))]
        if any(_in(p, r) and (not sec or any(_in(r, n) for n in sec)) for r in mine) or (not sec and fetched(p, cwd, sids)): continue
        if sec: return [], NEVER_WRITE if write else NEVER
        if any(_in(p, r) for r in ok) or (not write and isinstance(raw, Listed) and any(_in(p, r) for r in _listable())): continue
        p = os.path.realpath(os.path.expanduser(_cut(str(raw))))     # ...said as the owner's own spelling of it, never case-folded
        folder = p if os.path.isdir(p) else os.path.dirname(p)
        held.setdefault(folder, []).append('' if folder == p else os.path.basename(p))
    out += [{'tool': verb, 'kind': 'reads', 'what': _said(f, ns, verb), 'why': why, 'where': f, 'folder': f} for f, ns in held.items()]
    # ...A PATH NOBODY COULD READ IS SAID AS THAT, WITH THE WORD IT IS (walk 25: its card said "it is outside this task's own folders" of a line
    # that never left them - a reason nobody had checked): which word, and that where it leads is not known until the line runs
    named = ', '.join(dict.fromkeys(' '.join(str(u).split())[:60] for u in unread or () if str(u).strip()))
    if blind: out.append({'tool': verb, 'kind': 'reads', 'what': f'{verb} files at a path it builds from a variable' + (f' ({named})' if named else ''),
                          'why': UNKNOWN, 'where': '', 'folder': ''})
    return out, ''


def settings(what: str, path: str = '') -> dict:
    "One held step that changes what a later session or git command runs (TABLE 'settings'): `path` the file his yes lets it write."
    return {'tool': 'write', 'kind': 'settings', 'what': what, 'why': TABLE['settings'].why, 'where': path, 'folder': path}


def _cut(p: str) -> str:
    "A glob's path up to the folder it lists - the part that names a real place."
    return re.split(r'[\\/](?=[^\\/]*' + _WILD.pattern + ')', str(p), maxsplit=1)[0]


def _reaches(pat: str, root: str) -> bool:
    """Can glob `pat` (normalised) match `root` or reach inside it? Matched name by name as a shell does: `*` takes no leading dot, so
    `~/*` is not `~/.ssh`, while `~/.s*` is."""
    import fnmatch
    ps, rs = pat.split(os.sep), root.split(os.sep)
    return len(ps) > 1 and all(fnmatch.fnmatchcase(r, q) and (q == r or not r.startswith('.') or q.startswith('.')) for r, q in zip(rs, ps))


def _said(folder: str, names: list, verb: str = 'read') -> str:
    fs, place = [n for n in dict.fromkeys(names) if n], os.path.basename(folder.rstrip('\\/')) or folder
    return f"{verb} {', '.join(fs[:3])}{' and more' if len(fs) > 3 else ''} in {place}" if fs else f'{verb} the folder {place}' if verb == 'read' else f'{verb} in the folder {place}'


def _expand(t: str, cwd: str, env: dict) -> str | None:
    "A path token with its variables filled in - None when one names nothing this can read."
    def sub(m):
        n = (m.group(1) or m.group(2)).lower()
        v = env.get(n) or next((v for k, v in os.environ.items() if k.lower() == n), None)
        if v is None and n == 'home': v = os.path.expanduser('~')
        if v is None: raise KeyError(n)
        return v
    if re.search(r'\$\{(?:env:)?\w+[^\w}]', t) or _RUNS.match(t): return None    # `${HOME:-/x}`, `$(...)` and their kin pick it at run time: held
    try: t = _VAR.sub(sub, t)
    except KeyError: return None
    # ...`~name` is that user's home, beside his own on Windows (where Python leaves it be): one it cannot find is unknown
    if not (m := re.match(r'^~([\w.-]+)', t := os.path.expanduser(t))): return t
    return os.path.join(os.path.dirname(os.path.expanduser('~')), m[1]) + t[m.end():] if os.name == 'nt' else None


# ...a word whose value only a run can give: `$(...)`'s `$` (cut from its command), a backtick's command, a call on [Environment]
_RUNS = re.compile(r'^\$$|^`\w|^\[(?:System\.)?Environment\]::', re.I)
_PRINTS = {'=', 'echo', 'printf', 'write-output', 'write-host'}      # ...programs that show their words and open none


def _pathish(t: str) -> bool:
    """Drive-rooted, Git Bash's /c/, ~ or ~user, a variable with a path after it, a rooted POSIX path - or a relative one that climbs out
    with `..`. A bare variable is judged by its value (_filled)."""
    if re.match(r'^[A-Za-z]:[\\/]|^~[\w.-]*(?=[\\/]|$)|^[$%].*[\\/]', t) or '..' in re.split(r'[\\/]', t): return True
    return t.startswith('/') and (bool(re.match(r'^/[A-Za-z](?=/|$)', t)) if os.name == 'nt' else True)      # ...`/` itself, the root of all


def _filled(t: str, cwd: str, env: dict) -> bool:
    """Is a word the shell fills in a path? Walk 21: `grep -rl token $HOME` ran unasked, its bare variable read as no path at all. Judged by
    the value it will have - `$HOME`, `%USERPROFILE%`, `$env:HOMEDRIVE$env:HOMEPATH` - and one only a run can give, or an environment's
    variable that is not set, is unknown: held. A bare `$f` that is no environment's is a loop's word, not a place."""
    if _RUNS.match(t): return True
    if not _VAR.search(t): return False
    if (e := _expand(t, cwd, env)) is None: return bool(re.search(r'\$\{?env:|%\w+%', t, re.I))
    return _pathish(e) or os.path.isabs(e)


def _quoted(cmd: str) -> list:
    """The [start, end) spans of `cmd` inside quotes - '...' whole, "..." with its backslash escapes - where no command ends."""
    spans, q, at, i = [], '', 0, 0
    while i < len(cmd):
        c = cmd[i]
        if q == '"' and c == '\\': i += 2; continue
        # ...a `$(...)` in double quotes runs a command all the same: the quoting stops at it
        if q == '"' and cmd.startswith('$(', i): spans.append((at, i)); q = ''; i += 1; continue
        if c in '\'"' and (not q or c == q):
            if q: spans.append((at, i)); q = ''
            else: q, at = c, i
        i += 1
    if q: spans.append((at, len(cmd)))
    return spans


def _segments(cmd: str) -> list:
    """The line cut where one command ends and another begins - a `${NAME}` kept whole, and never inside quotes: a `python -c "..."` script's
    own lines and `;` are its text (the HIPAA walk, 2026-11-22: each line of a PDF's script was read as a command of its own)."""
    out, cur, qs = [''], 0, _quoted(cmd)
    for m in _SPLIT.finditer(cmd):
        if not m[1] and any(a < m.start() < b for a, b in qs): continue
        out[-1] += cmd[cur:m.start()] + (m[1] or ''); cur = m.end()
        if not m[1]: out.append('')
    out[-1] += cmd[cur:]
    return out


# A `$(...)` THAT ONLY PRINTS ITS OWN WORDS IS THOSE WORDS (walk 24, 2026-11-25: a commit message handed over as `-m "$(cat <<'EOF' ...)"` - how
# Claude Code writes every commit - and a pull request's body the same way were held as "read files at a path it builds from a variable"): the
# shell's own grammar, read before the line is cut - echo's words, printf's one literal (or what its bare %s prints), a quoted heredoc fed to cat. Put
# in its place, each word is judged as any other word of the line: `cat "$(echo ~/.ssh/x)"` reads that path, and a message reads none. One
# that runs anything else, pipes or reads a file is a value only a run can give, as before (_RUNS)
_SUBST = re.compile(r'(")?\$\(([^()`|;&>]*)\)(?(1)")')
def _printed(m) -> str:
    from .browsergate import words
    w = words(m[2])
    tool, args = (w[0].lower() if w else ''), w[1:]
    # ...a heredoc under a QUOTED mark: its body is text as written - under a bare one the shell runs the `$(...)` in it, which no one read here
    if tool == 'cat' and len(args) >= 2 and args[0] in ('<<', '<<-') and len(set(args[1:])) == 1 and re.search(r'<<-?\s*[\'"]', m[2]): said = ''
    elif '<' in m[2]: return m[0]
    # ...and words the program DECODES are not the words written (red team round 5: `cat "$(printf '\056\056/\056\056/config\056toml')"` named no
    # path here and the owner's token to the shell): a backslash escape is a value only a run can give - but for printf's own closing `\n`
    elif '\\' in m[2].replace('%s\\n', '%s', 1): return m[0]
    elif tool == 'echo': said = ' '.join(x for x in args if not re.fullmatch(r'-[neE]+', x))
    elif tool == 'printf' and len(args) == 1 and '%' not in args[0].replace('%%', ''): said = args[0]
    elif tool == 'printf' and len(args) > 1 and args[0].replace('\\\\', '\\') in ('%s', '%s\\n'): said = ' '.join(args[1:])      # ...words doubles a `\` on Windows
    else: return m[0]
    return '"' + said.replace('"', '\\"') + '"' if m[1] else said
# ...AND `$'...'` IS THE SHELL'S OWN DECODING, done before any program runs: read as the words it will be (`cat $'\x2e\x2e/x'` is `cat ../x`),
# so a tab handed to sort or a message's line breaks stay plain words. One whose words cannot be written back as one quoted word is UNREAD
_ESC = re.compile(r'\\(?:(0?[0-7]{1,3})|x([0-9A-Fa-f]{1,2})|u([0-9A-Fa-f]{1,4})|U([0-9A-Fa-f]{1,6})|c(.)|(.))', re.S)
_ESC1 = dict(zip('abeEfnrtv\\\'"?', '\a\b\x1b\x1b\f\n\r\t\v\\\'"?'))
UNREAD = '${env:TASKUARY_UNREAD}'                # a word only a run can give, spelled as a variable no environment has: held wherever it is a path
def _ansi(cmd: str) -> str:
    def said(m): return (chr(int(m[1], 8) & 255) if m[1] else chr(min(int(m[2] or m[3] or m[4], 16), 0x10ffff)) if m[2] or m[3] or m[4]
                         else chr(ord(m[5].upper()) ^ 64) if m[5] else _ESC1.get(m[6], m[0]))
    out, q, i = [], '', 0
    while i < len(cmd):
        c = cmd[i]
        if not q and cmd.startswith("$'", i):
            j = i + 2
            while j < len(cmd) and cmd[j] != "'": j += 2 if cmd[j] == '\\' else 1
            t = _ESC.sub(said, cmd[i + 2:j])
            out.append(f"'{t}'" if not re.search(r"['\\]", t) else f'"{t}"' if not re.search(r'["\\$`]', t) else UNREAD); i = j + 1; continue
        if c == '\\' and q != "'" and i + 1 < len(cmd): out.append(cmd[i:i + 2]); i += 2; continue
        if q: q = '' if c == q else q
        elif c in '"\'': q = c
        out.append(c); i += 1
    return ''.join(out)


def _literal(cmd: str) -> str:
    "The line with each `$'...'` as its words (_ansi) and each `$(...)` that only prints its own words replaced by them (_printed) - innermost first."
    cmd = _ansi(cmd)
    for _ in range(8):
        if (new := _SUBST.sub(_printed, cmd)) == cmd: break
        cmd = new
    return cmd


# A VARIABLE THE LINE ITSELF SET, HOWEVER THE SHELL SPELLS READING IT: `${!b}` is the variable `b` names, `${a[0]}` and `${a[@]}` items of a
# list, `${a:-x}` the value it has - and a word that reads a list is each word it may be. A cut or a swap (`${f%.txt}`) is left as written
_ARRAY = re.compile(r'(?<![\w$.\-/])([A-Za-z_]\w*)=\(([^()]*)\)')
_FORM = re.compile(r'\$\{(!?)([A-Za-z_]\w*)((?:\[[^\]}]*\])?)([^}]*)\}')
_MULTI = re.compile(r'\$(?:\{([A-Za-z_]\w*)(?:\[\])?\}|([A-Za-z_]\w*))')
def _forms(x: str, env: dict, deep: int = 0) -> list:
    def one(m):
        n = m[2].lower()
        if n not in env and n + '[]' not in env: return m[0]
        if m[1]: return env.get(str(env.get(n)).lower(), UNREAD) if not (m[3] or m[4]) else UNREAD
        if m[4] and not re.match(r':?[-=]', m[4]): return m[0]
        return '${' + n + ('[]' if m[3] and n + '[]' in env else '') + '}'
    x = _FORM.sub(one, x)
    m = next((m for m in _MULTI.finditer(x) if (m[1] or m[2]).lower() + '[]' in env), None)
    if not m or deep > 2: return [x]
    its = env[(m[1] or m[2]).lower() + '[]'].split('\0')
    return [y for it in its[:12] + [UNREAD] * (len(its) > 12) for y in _forms(x[:m.start()] + it + x[m.end():], env, deep + 1)]


# WHAT A LINE WRITES, BY ITS GRAMMAR (red team F2): a redirect's target, and the file a writing program is named on - its destination for a copy
# or a move. Judged as writes (judge, write=True), never as reads: a program's own folder is free to read and never free to write
_REDIRECT = re.compile(r'^\d?>>?&?$|^&>$')
_WRITERS = {'tee', 'out-file', 'set-content', 'add-content', 'new-item', 'ni', 'sc', 'ac', 'touch', 'mkdir', 'md'}
_COPIES = {'cp', 'mv', 'copy', 'move', 'copy-item', 'move-item', 'cpi', 'mi', 'xcopy', 'robocopy', 'rsync', 'install', 'ln'}
def command_paths(cmd: str, cwd: str = '', env: dict = None, made: list = None, writes: list = None, unread: list = None) -> list:
    """Every path a shell line names as an argument, through `cd`, `bash -c "..."` and `--opt=value` - None for one built from a variable
    it cannot read. The program itself, options, URLs and switches (`/s`) are not paths. `made` gets the files the line writes rather than
    reads: a browser screenshot's picture (walk 16: the agent's own screenshot in Temp stood as a card asking to read it). `writes`, where
    given, gets the paths it writes (_REDIRECT, _WRITERS, _COPIES) instead of the list it returns. `unread`, where given, gets each word a
    None stands for, as the line wrote it - what its card names."""
    from .browsergate import _head, _verb, types, words
    from .shellgate import _OWN, shell_text, unwrap
    # ...a line that is a shell started on a script (Codex's every call) is read as that script, whole: cut at the `;` inside its quotes first,
    # `$outDir = "<its outputs folder>"; New-Item $outDir` lost its assignment and the task's own folder was held as a variable it could not
    # read (the HIPAA walk, 2026-11-21)
    if (inner := unwrap(cmd))[0]: return command_paths(inner[1], cwd, env, made, writes, unread)
    out, here, env, reads = [], cwd, dict(env or {}), False
    line = _literal(shell_text(str(cmd or '')))                        # ...a heredoc's or a here-string's body is data, never a path read
    qs = _quoted(line)
    line = _ARRAY.sub(lambda m: m[0] if any(a < m.start() < b for a, b in qs) else f'{m[1]}[]={m[2]} ;', line)
    for seg in _segments(line):
        # ...a path kept in a variable is read where the variable is (`$p='C:/x.csv'; Get-Content $p` - the real-CLI walk, 2026-11-16)
        # ...AND KEPT AS WHAT IT IS BY THEN (red team round 5: `a=.ssh/id_ed25519; b=$a; cd ~; cat "$b"` - each hop was filled in once, so a
        # second hop was a word that named nothing): a value is filled in where it is set, a list's items (`a=(x y)`, `for f in x y`) are
        # each the word it may be, and `export`, `declare` and their kin set one as a bare `a=` does
        if (m := re.match(r'^\s*(?:(?:export|declare|local|readonly|typeset)\s+(?:-\w+\s+)*)?\$?([A-Za-z_]\w*)(\[\])?\s*=\s*([^=].*)$', seg)):
            v, n = m[3].strip() if m[2] else m[3].strip().strip('"\''), m[1].lower()
            if m[2]: env[n + '[]'] = '\0'.join(words(v))
            else: env[n] = v if (e := _expand(v, here, env)) is None else e; env.pop(n + '[]', None)
            seg = f'= {v}'
        elif (m := re.match(r'^\s*for\s+([A-Za-z_]\w*)\s+in\s+(.*)$', seg)): env[m[1].lower() + '[]'] = '\0'.join(words(m[2]))
        # ...a PowerShell array's items are its words, never one name with a comma on it (`@("$env:USERPROFILE\Desktop", ...)` held "Read \", in
        # Desktop"), and a segment that opens on a value is an expression - its first word a path like the rest, not a program
        w = [x for x in (y.rstrip(',') for y in words(seg)) if x]
        if seg.lstrip()[:1] in ('"', "'", '$', '@', '[') and w and not re.match(r'^\$?[A-Za-z_]\w*\s*=', seg.lstrip()): w = ['', *w]
        while w and (re.match(r'^[A-Za-z_]\w*=', w[0]) or w[0].lower() in ('&', 'sudo', 'time', 'nohup', 'command', 'exec', 'call', 'then', 'do', 'if', 'else')): w = w[1:]
        if not w: continue
        tool = re.sub(r'\.(exe|cmd|ps1|bat)$', '', os.path.basename(w[0].replace('\\', '/')).lower())
        if tool in ('bash', 'sh', 'zsh', 'dash', 'ksh', 'powershell', 'pwsh', 'cmd'):
            i = next((i for i, x in enumerate(w) if x.lower() in ('-c', '-command', '/c', '/k')), None)
            if i is not None: out += command_paths(' '.join(w[i + 1:]), here, env, made, writes, unread)
            continue
        # ...and a line handed to the shell to run again is that line (`eval "cat <path>"`, PowerShell's iex): one quoted word named no path
        if tool in ('eval', 'iex', 'invoke-expression'): out += command_paths(' '.join(w[1:]), here, env, made, writes, unread); continue
        cd, named = tool in ('cd', 'chdir', 'set-location', 'sl', 'pushd'), len(out)
        lists = tool in _LISTS and not any(x in _RUNS_ON for x in w)
        reads = reads or not (lists or tool in _NAMES)
        shot = (a := _head(w)) is not None and next((x.lower() for x in a if not x.startswith('-')), '') == 'screenshot'
        if a is not None and types(a): continue                 # ...words typed into a page's box are text, never a path (browsergate.types)
        # ...and the script a page is handed to run (agent-browser's eval, by its grammar) is text the same way: a `$(...)` that builds it names
        # no file of its own (walk 24: a look at what the post box held, its script piped through base64, was held as a read at a path built
        # from a variable, and stayed pending for good). What that `$(...)` itself runs is read as the commands it is, as ever
        script = a is not None and _verb(a)[0] == 'eval'
        if tool == 'join-path': w = [w[0], os.sep.join(x for x in w[1:] if not x.startswith('-'))]     # ...the one path it builds
        # ...a `$(...)` that is a word of its own, never one inside a string's text (`"rows: $((Import-Csv $p).Count)"`)
        sub = bool(re.search(r'(?:^|\s)' + '"' * (seg.count('"') % 2) + r'\$\s*$', seg))
        code = re.sub(r'[\d.]+$', '', tool) in ('python', 'py', 'node', 'ruby', 'perl', 'deno') and any(x in ('-c', '-e') for x in w[1:3])
        # ...an inline script's text is read word by word for the paths in it: its words are mostly data, so one is a path only where one is
        # there (below) - `open('~/.ssh/id_rsa')` in it is read as ever
        # ...and a variable it reads by name (`os.environ['TASKUARY_HOME'] + '/config.toml'`, process.env.HOME) is that variable's path, joined to
        # the text after it (red team #2, T3): the script names the file as surely as `cat $TASKUARY_HOME/config.toml` does
        if code: w = [w[0], *(t for x in w[1:] for t in re.split(r"[\s'\"(),;=+]+", _joined(x)) if t and t not in ('-c', '-e'))]
        else: w = [w[0], *(y for x in w[1:] for y in _forms(x, env))]
        dest = max((i for i, x in enumerate(w) if i and not x.startswith('-')), default=0) if tool in _COPIES else 0
        for i, x in enumerate(w[1:], 1):
            to = bool(_REDIRECT.match(w[i - 1])) or i == dest or tool in _WRITERS
            x = re.sub(r'^\d?[<>]+&?', '', x)
            # ...an option's value is read as its own word, and so is a `name=value` operand's (`dd if=<home>/config.toml`, red team #3)
            if x.startswith('-') or re.match(r'^[A-Za-z_][\w.-]*=', x): x = x.split('=', 1)[1] if '=' in x else ''
            if x == '$' and (script or not sub): continue
            # ...AND A PROGRAM FOUND AS THE LINE RUNS IS THE PROGRAM, NEVER A FILE IT READS (walk 25, 2026-11-26: `F=$(python -c "...get_ffmpeg_exe()");
            # "$F" -y -i "$O/clip.webm" "$O/clip.mp4"`, every file in the task's own folder, was held as "read files at a path it builds
            # from a variable ... outside this task's own folders"): a variable a command's output filled, standing first with words after it,
            # is run with them - each of those is read as ever. Alone on its segment (`$p | Get-Content`) it is a value handed on: held
            if i == 1 and not w[0] and len(w) > 2 and (v := _VAR.fullmatch(x)) and _RUNS.match(env.get((v[1] or v[2]).lower()) or ''): continue
            raw = x
            if (v := _VAR.fullmatch(x)) and (v[1] or v[2]).lower() in env: x = env[(v[1] or v[2]).lower()]
            # ...after a `cd` away, a plain name that is there is read there (`cd ~ && cat .ssh/x`)
            near = here != cwd and here and x and not x.startswith('-') and os.path.exists(os.path.join(here, x))
            # ...and a plain name that is a link somewhere else is read where it leads (`ln -s ../../.taskuary/config.toml c; cat c`)
            near = near or bool(x) and not x.startswith('-') and _linked(os.path.join(here or cwd or os.getcwd(), x))
            # ...a file:// address is the file it names (`curl file://$TASKUARY_HOME/config.toml`)
            if re.match(r'^file:', x, re.I): x = re.sub(r'^/(?=[A-Za-z]:)', '', unquote(re.sub(r'^file:(//(localhost)?)?', '', x, flags=re.I)))
            # ...a rooted path is the place it comes to: `/dev/../<home>/config.toml` is no device (red team round 5)
            if x.startswith('/') and '..' in x.split('/'): x = posixpath.normpath(x)
            # ...and Taskuary's own address as a session is handed it ($TASKUARY_URL/api/...) is a web address, never a file: a read-only curl
            # of its own API was held as "a path it builds from a variable", a card each time the agent looked (the roads audit, 2026-11-19)
            if not x or '://' in x or _OWN.match(x) or re.match(r'^/\w$', x) or re.match(r'^(/dev/|\d$)', x) or not (near or _pathish(x) or tool not in _PRINTS and _filled(x, here, env)): continue
            e = _expand(x, here, env)
            if e is None:
                if not code:                         # ...in a script's text a name it does not know is mostly not a path at all
                    out.append(None)
                    if unread is not None: unread.append('$(...)' if raw == '$' else raw)
                continue
            e = re.sub(r'^/([A-Za-z])(?=/|$)', r'\1:', e) if os.name == 'nt' else e
            if not os.path.isabs(e): e = os.path.join(here or os.getcwd(), e)
            # ...a rooted token whose first folder does not exist is a pattern or an API path, not a file (`grep /api/ x`). A glob stays
            # whole: judge reads the folder it lists, and whether it can reach a sign-in place
            parts = Path(_cut(e)).parts
            if len(parts) > 1 and not os.path.exists(os.path.join(parts[0], parts[1])): continue
            # ...and in an inline script's text (`python -c "..."`) a word is a path only where one is there: its words are mostly data (the HIPAA
            # walk, 2026-11-22: "~\$5.46", a price a PDF's script drew, held as a read in his home folder)
            if code and not _WILD.search(e) and not os.path.lexists(e): continue
            if cd: here = _cut(e); break
            if shot and made is not None: made.append(e)
            elif to and writes is not None: writes.append(e)
            else: out.append(Listed(e) if lists else e)
        else:
            if cd and len(w) == 1: here = os.path.expanduser('~')          # a bare `cd` goes home
        # ...a step that names no path reads where the line has moved to: `cd ~/Documents && ls`
        if not cd and len(out) == named and here != cwd: out.append(Listed(here) if lists else here)
    return [str(o) if reads and isinstance(o, Listed) else o for o in out]     # ...names piped on to a reader (`| xargs cat`) are read


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
    "The variables a session of this task has that the server may not: its outputs folder, the folder it is in, and Taskuary's home."
    from . import config, outputs
    return {'taskuary_outputs': str(outputs.folder(int(tid))) if str(tid or '').isdigit() else '', 'pwd': cwd, 'taskuary_home': str(config.home())}


def _joined(code: str) -> str:
    "A script's text with each variable it reads by name as `${NAME}/`, and the string joined on after it (`+ '/x'`, `, 'x'`, `/ 'x'`) one path."
    return re.sub(r'''(\}/|~)["']?\)?\s*[+/,]\s*[fbru]?["']''', r'\1/', _ENV_REF.sub(r'${\1}/', code))


def _linked(p: str) -> bool:
    "Is `p` (there now) reached through a link - its real path not the one written?"
    try: return os.path.lexists(p) and os.path.normcase(os.path.realpath(p)) != os.path.normcase(os.path.abspath(p))
    except (OSError, ValueError): return False


def of_command(store, tid, cmd: str, cwd: str = '') -> tuple:
    "(held, never) for a shell line."
    from . import floor
    made, ws, un = [], [], []
    ps = command_paths(cmd, cwd, env_for(store, tid, cwd), made, ws, un)
    wrote(tid, made)                                  # ...the picture it takes is its own work, read back without asking (wrote)
    (held, never), (wheld, wnever) = judge(store, tid, ps, cwd, unread=un), judge(store, tid, ws, cwd, write=True)
    # ...and a line that writes one of them, or sets git's own config that runs a program - the floor's reading of a shell line (T2)
    conf = [settings(why.removeprefix('it ')) for why in [floor._write_hit(str(cmd or ''), cwd)] if why]
    return held + wheld + conf, never or wnever
