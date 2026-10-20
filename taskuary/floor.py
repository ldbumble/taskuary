"""What no stranger's session may touch, whatever its reviewer decides (spec 2026-10-14, section 3).

A fixed list checked in code - nobody approves anything here, and a call it does not name passes straight on to the
CLI's auto mode. It exists because auto mode does not review reads: in auto mode alone, a stranger's agent could read
config.toml, take the owner token, and act as the owner through Taskuary's API.

It is a floor, not a sandbox: globbing, encoding or assembling a path from pieces in a shell are auto mode's to catch."""
import os, re, posixpath
from collections import Counter
from .config import home

_CREDS = ('.ssh', '.aws', '.azure', '.config/gh', '.config/gcloud', '.config/hub', 'AppData/Roaming/GitHub CLI', 'AppData/Roaming/gcloud',
          '.docker/config.json', '.git-credentials', '.netrc', '.npmrc', '.pypirc', '.claude/.credentials.json', '.claude.json',
          '.codex/auth.json', '.gemini', '.qwen', '.kube',
          # where hooks.install_user writes the hooks every session runs: written, each is a command the owner's next session
          # runs (R28). The SHARED agent token they send now sits in Taskuary's home (hooks.header_file), refused above them
          '.claude/settings.json', '.codex/hooks.json', '.copilot/hooks', '.config/devin/config.json', 'AppData/Roaming/devin/config.json')
# the session's own variables, by NAME: expanding them here would read the SERVER's environment, not the session's.
# Fail-closed on purpose: `grep -r TASKUARY_TOKEN .` in a stranger's repository is refused too - a name match cannot tell
# reading a value from mentioning it, and a refused search costs less than a printed token
_SESSION_VARS = re.compile(r'taskuary_(task_)?token|taskuary_url', re.I)
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
    "Taskuary's own folder, every stranger task's folder, and the places credentials live, as normalised prefixes (symlink-resolved and as written)."
    import tempfile
    # the strangers' folders (origin.stranger_dir) sit outside Taskuary's home; each task is let into its OWN one by _own
    rs = [home(), os.path.join(tempfile.gettempdir(), 'taskuary-stranger')] + [os.path.join('~', c) for c in _CREDS]
    # ...and the hook files where the CLI is told to keep them instead (hooks.install_user follows the same variables)
    rs += [os.path.join(os.environ[v], *f) for v, f in (('COPILOT_HOME', ('hooks',)), ('APPDATA', ('devin', 'config.json'))) if os.environ.get(v)]
    return list(dict.fromkeys(_norm(r, real=rl) for r in rs for rl in (True, False)))

def _names() -> list:
    "Protected folders by their home-relative name, so `cd ~ && cat .ssh/x` and `../../.ssh/x` are seen without any root in sight."
    ns = [_cf(c) for c in _CREDS]
    return ns + ([_cf(home().name)] if home().name.startswith('.') else [])

def _own(tid: int, store=None) -> list:
    """This task's own files: its working folder (origin.stranger_dir) - its stranger file lives there (R25) - and the
    attachments of ITS messages - not another task's."""
    from .origin import stranger_path
    fs = [a['Path'] for m in (store.list_messages(tid) if store else []) for a in store.list_attachments(m['MessageId']) if a.get('Path')]
    # the working folder sits in the shared temp, where someone else could plant a link: only its own NAME is let in,
    # never what that name resolves to (origin.stranger_dir refuses a planted one at launch). The system temp folder itself
    # is resolved - TEMP is often a short 8.3 name and the CLI writes the long one - but nothing below it is.
    import tempfile
    sd = [_norm(stranger_path(tid), real=False), _cf(os.path.normcase(os.path.join(os.path.realpath(tempfile.gettempdir()), 'taskuary-stranger', stranger_path(tid).name)))]
    return list(dict.fromkeys([_norm(f, real=rl) for f in fs for rl in (True, False)] + sd))

def _under(p, roots): return any(p == r or p.startswith(r.rstrip('/') + '/') for r in roots)
def _above(p, roots): return any(r == p or r.startswith(p.rstrip('/') + '/') for r in roots)   # a protected root lies inside p

def _deny(why: str) -> dict:
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                   'permissionDecisionReason': f"{why} - a stranger's task may not touch it"}}

def _port() -> str:
    from . import config
    return str(config.load()['server'].get('port') or 7787)

def _pn(p: str) -> str:
    "posixpath.normpath, but a drive stays a ROOT: normpath('c:/') is 'c:', which no absolute-path test recognises (I5)."
    n = posixpath.normpath(p)
    return n + '/' if re.fullmatch(r'[a-z]:', n) else n

def _text_hit(text: str, own: list, prot: list, cwd: str = ''):
    "Why a command/url/glob is refused, or ''. Checked token by token so an own file's name cannot launder a neighbour's."
    if m := _SESSION_VARS.search(text): return f"it names the session's {m[0].upper()}"
    h = _norm('~', real=False)
    t = _HOME_VAR.sub(h, text); t = _cf(os.path.expandvars(t)).replace('"', '').replace("'", '')   # expand BEFORE folding, quotes are not part of a path
    if re.search(':' + _port() + r'(?!\d)', t):   # any host that reaches it - 127.1, a LAN name, [::ffff:127.0.0.1] - is still this port
        return "that is Taskuary's own address"
    cur, prev, nxt = _norm(cwd) if cwd else '', '', ''     # where a relative token points: the session's folder, moved by the last `cd` before it
    for tok in filter(None, _SPLIT.split(t)):
        cur, nxt = nxt or cur, ''                # a cd takes effect AFTER its own argument is checked against the old folder
        if prev in _CD and not tok.startswith('-'):
            d = _pn(tok); d = d if re.match(r'([a-z]:)?/', d) or not cur else _pn(posixpath.join(cur, d))
            nxt = d if re.match(r'([a-z]:)?/', d) else ''
        prev = tok
        rel = cur and '://' not in tok and not re.match(r'(/|[a-z]:/)', tok) and ('/' in tok or tok.startswith('..'))
        n = _pn(posixpath.join(cur, tok) if rel else tok); a = re.sub(r'^/(?=[a-z]:/)', '', n)   # "/c:/x" as bash on Windows writes it
        if _under(a, own): continue
        if _under(a, prot) or _above(a, prot) and re.match(r'([a-z]:)?/', a) or any(re.search(r'(^|/)' + re.escape(s) + r'(/|$)', n) for s in _names()):
            return f'it names {tok}'
    return ''

# ── TASKUARY'S OWN PACKAGE, IN-PROCESS (wave B, B1b) ─────────────────────────────────────────────────────────────────
# Imported or run as a module it reads the home with this process's rights - config.toml's owner token, the mail - and
# none of the paths above appears in the command. cli.py refuses the same in a session it recognises; this is for the one
# that unset every marker Taskuary gave it, which is why naming those markers (or emptying the environment) is refused too.
# A command is refused if the BROAD check or the precise one hits (R35): the broad `-m taskuary` anywhere in a segment
# (python -W x -m, uv run -m...) - but not in git's own -m, which is a commit message. Python's import keywords are
# lowercase, so "data from Taskuary" in prose is not one. The python-gated form is what written non-script text is held to.
_PKG = re.compile(r'(?i:(?:^|[\s;&|(/\\"\'])(?:python[\d.]*w?|py)(?:\.exe)?["\']?(?:\s+-[^\s-]\S*)*?\s+-m\s*["\']?taskuary\b)'
                  r'|\b(?:from|import)\s+(?:[\w.]+\s*,\s*)*taskuary\b|(?:__import__|import_module)\s*\(\s*[\'"]taskuary\b')
_PKG_ANY = re.compile(r'-m\s*["\']?taskuary\b', re.I)
# ...the environment emptied or rewritten, whatever names it does not say: a PowerShell Env: drive in any form (a quoted
# "Env:$n", Get-Item Env:*), compgen -e, SetEnvironmentVariable, Start-Process -UseNew* (env and exec: _env_wipe).
# $env:PATH, reading one variable, stays ordinary.
_WIPE = r'(?<![$\w])["\']?env:|\bcompgen\s+-\w*e|setenvironmentvariable|-usen\w*'
# A command line: any TASKUARY_ variable by name, glob or indirection (${!TASKUARY_*}, Env:TASKUARY_*) - a path segment
# like /taskuary_tmp is not one.
_MARKS = re.compile(r'(?<![\w/\\.~-])taskuary_|' + _WIPE, re.I)
# A script's text: code may READ a TASKUARY_ variable; what is refused is unsetting, removing or overwriting one.
_SCRIPT_MARKS = re.compile(r'\bunset\s[^\n;|&]*\btaskuary_|^\s*(?:export\s+|set\s+"?)?taskuary_\w*\s*=|\$env:taskuary_\w*\s*='
                           r'|environ\.pop\s*\(\s*[\'"]taskuary_|\bdel\s+os\.environ\s*\[\s*[\'"]taskuary_|environ\.update\s*\([^)]*taskuary_'
                           r'|\b(?:unsetenv|putenv)\s*\(\s*[\'"]taskuary_|environ\.clear\s*\('
                           r'|environ\s*\[\s*[\'"]taskuary_\w*[\'"]\s*\]\s*=(?!=)|\bcompgen\s+-\w*e|setenvironmentvariable'
                           # the Env: drive only where it reads as PowerShell - `{env:"prod"}`, `{ env: x }` and `# rm it, env: prod` do not
                           r'|(?<![$\w])env:[\\/]|(?<![$\w])(["\'])env:(?:\1|[*$])|(?<![$\w])env:\s*\|'
                           r'|\b(?:remove-item|ri|clear-item|cli|rm|del|get-childitem|gci|get-item|gi|set-item|si)(?:\s+-\w+)*\s+["\']?env:(?=[\w*])'
                           r'|\b(?:start-process|saps|start)\b[^\n]*\s-usen\w*', re.I | re.M)
# ...but a PowerShell file IS PowerShell (R37): there every Env: drive reference but `$env:NAME` counts, as in a command -
# `rd Env:*`, `Set-Item Env:$n $null`, `-Path:Env:*` - and the narrowed forms above are for everything else
_PS_MARKS = re.compile(_SCRIPT_MARKS.pattern + '|' + _WIPE, re.I | re.M)
# cli.STRANGER_ACTS and the options that go with them (test_floor_wave_b keeps the two in step)
TASKUARY_OK = frozenset({'--reply', '--reply-file', '--draft', '--draft-file', '--attach', '--item', '--done', '--note'})
_TASKUARY_WITH = frozenset({'--slot', '--to', '--subject', '--result', '--overlap', '--settled', '--propose', '--no-reply', '--kind', '--follow-up'})
_TASKUARY_ASK = frozenset({'--help', '-h', '--version'})
_SEG = re.compile(r'(?:&&|\|\||[;|&\n]|\$\(|`)+')
_WORD = re.compile(r'(?:"[^"]*"|\'[^\']*\'|[^\s"\']+)+|["\']')     # a quote inside a word stays in it: --opt="a b"

def _words(seg: str) -> list:
    "A segment's words, unquoted, with leading VAR=value assignments and `sudo` dropped."
    ws = [w[1:-1] if w[:1] in '"\'' and w[-1:] == w[:1] and len(w) > 1 else w for w in _WORD.findall(seg)]
    while ws and (re.fullmatch(r'[A-Za-z_]\w*=.*', ws[0]) or ws[0].lower() in ('sudo', 'command', 'exec', 'nohup')): ws.pop(0)
    return ws

from functools import lru_cache
@lru_cache(maxsize=8192)
def _prog(w: str) -> str: return re.sub(r'(\.exe|\.cmd|\.bat|\.ps1|-script\.pyw?)$', '', _cf(w).rsplit('/', 1)[-1])

_ENV_VAL = ('-C', '-S', '-u', '-P', '--chdir', '--split-string', '--unset')    # env's options that take a value

def _uq(w: str) -> str: return w[1:-1] if len(w) > 1 and w[:1] in '"\'' and w[-1:] == w[:1] else w   # -S"-i x" is -S with "-i x"
def _long(o: str, full: str) -> bool: return len(o) >= 3 and full.startswith(o)    # GNU takes any prefix of a long option

def _env_wipe(ws: list) -> str:
    """`env` - at ANY word, so `nice env -i`, `env FOO=1 env -i` - with -, -i, a prefix of --ignore-environment, -u of a
    TASKUARY_ name, or the same inside -S/--split-string; `exec -c` among exec's own options."""
    for j, w in enumerate(ws):
        p = _prog(w)
        # the shell builtin only - as the segment's program, not `npm exec -c make`
        if p == 'exec' and all(re.fullmatch(r'[A-Za-z_]\w*=.*', v) or v.lower() in ('sudo', 'command', 'builtin', 'nohup') for v in ws[:j]):
            for a in ws[j + 1:]:
                if not a.startswith('-'): break
                if re.fullmatch(r'-[a-z]*c[a-z]*', a): return 'exec -c'
        if p != 'env': continue
        i = j + 1
        while i < len(ws) and ws[i].startswith('-'):
            o, val = ws[i].split('=', 1) if '=' in ws[i] else (ws[i], None)
            if val is not None and val[:1] in '"\'' and val[-1:] == val[:1]: val = val[1:-1]
            if o in ('-', '-i') or _long(o, '--ignore-environment') or re.fullmatch(r'-[a-z0]*i[a-z0]*', o) and not o.startswith('--'): return f'env {ws[i]}'
            split = val if val is not None and _long(o, '--split-string') else ws[i + 1] if o == '-S' and i + 1 < len(ws) else _uq(o[2:]) if o[:2] == '-S' else None
            if split and (why := _env_wipe(['env', *_WORD.findall(split)])): return why
            unset = o in ('-u',) or _long(o, '--unset') or re.fullmatch(r'-u\S+', o)
            named = val if val is not None else _uq(o[2:]) if re.fullmatch(r'-u\S+', o) else ws[i + 1] if unset and i + 1 < len(ws) else ''
            if unset and named.lower().startswith('taskuary_'): return f'env {o} {named}'
            i += 2 if (o in _ENV_VAL or _long(o, '--chdir') or _long(o, '--split-string') or _long(o, '--unset')) and val is None else 1
    return ''

def _snip(s: str) -> str: return ' '.join(s.split()).casefold()

def _line(text: str, m) -> str:
    "The whole line(s) a match sits on, normalised: the key a pattern hit is counted by, so its target is part of it (R38)."
    a, b = text.rfind('\n', 0, m.start()) + 1, text.find('\n', m.end())
    return _snip(text[a:] if b < 0 else text[a:b])

# Presence, not parsing (R39): a runner's options and a shell's are too many to parse, and the one a parser does not know
# walks past it. A segment that names a runner AND Taskuary is refused, whatever sits between them.
_RUNNER = re.compile(r'(?<![\w.-])(?:uvx?|pipx|poetry|pdm|hatch|pipenv|npx|npm|pnpm|pnpx|yarn|bunx?|rye|pixi|conda)(?:\.exe|\.cmd)?(?![\w.-])', re.I)
_TQ = re.compile(r'(?<![\w-])taskuary(?!\w)', re.I)     # taskuary, Taskuary.exe, taskuary-desktop - not TASKUARY_X
# A shell started with an inline command - `pwsh -c '...'` in a .sh, ['pwsh','-c','...'] in a .py, `bash -c`, `cmd /c` -
# is judged on everything after it, quotes stripped, by the rules of the shell it starts (PowerShell's for pwsh); an
# encoded PowerShell command, which no rule can read, is refused outright.
_SHELL = re.compile(r'(?<![\w.-])(?:(pwsh|powershell)|(?:ba|z|da|k)?sh|cmd)(?:\.exe)?(?![\w.-])', re.I)
_INLINE = re.compile(r'(?<![\w-])-[a-z]*c[a-z]*(?![\w-])|(?<![\w])/[ck](?!\w)', re.I)
_PS_OPT = re.compile(r'''(?:^|(?<=[\s"',\[(]))([-/])(\w+)(?=[\s"',:\])]|$)''')
_HEREDOC = re.compile(r'''<<-?\s*(["']?)(\w+)\1''')
# An argv list in code - ['taskuary', '--prompts'], spawn('taskuary', [...]) - is the command it runs: its words from
# `taskuary` on are held to the command rule. A one-word list (packages=['taskuary']) is argv only where a spawn call takes it.
_ARGV = re.compile(r'''(?:\[|[(,](?=\s*["'][^"'\n]*["']\s*,))\s*(["'])((?:[^"'\n]*[/\\])?taskuary(?:\.exe|-desktop)?)\1''', re.I)
_SPAWN = r'(?:subprocess\.\w+|Popen|check_call|check_output|call|run|os\.exec\w*|os\.spawn\w*|spawn\w*|exec\w*|execa\w*|(?-i:Command))\s*\(\s*'
_SPAWN_AT = re.compile(_SPAWN + r'$')
_STR = re.compile(r'''"((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)\'''')     # char classes, not a lookahead per character
# ...and a string a shell runs - os.system('taskuary --prompts'), execSync(...), subprocess.run('...', shell=True)
_SHELL_CALL = re.compile(r'''(?<![\w.])(?:os\.system|os\.popen|subprocess\.\w+|(?:child_process\.|cp\.)?exec(?:Sync)?)\s*\(\s*[fbru]?(["'`])((?:\\.|(?!\1)[^\\\n])*)\1''')

# ...and a spawn call's one string argument: spawn('taskuary'), execa('taskuary-desktop'), and a module's own spawn by its
# exact name - child_process.spawn('taskuary'), Bun.spawn. Any other method is not one: app.run, cur.execute, regex.exec
# (cp.exec is a shell string, _SHELL_CALL's), program.command('taskuary')
_QSPAWN = r'(?<=\.)(?:spawn(?:Sync)?|execFile(?:Sync)?|execSync|execa(?:Sync)?|fork|Popen)\s*\(\s*'
_SPAWN1 = re.compile(r'(?:(?<![\w.])' + _SPAWN + '|' + _QSPAWN + ')' + r'''(["'`])((?:[^"'`\n]*[/\\])?taskuary(?:\.exe|-desktop)?)\1''', re.I)
_TOK = re.compile(r'''"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|[()\[\]{}]''')
# every rule a launch's text is judged by needs one of these words: taskuary (the program, the package, a TASKUARY_ name),
# env (env -i, Env:, environ, SetEnvironmentVariable), compgen, -UseNew*, exec -c
_ANY_RULE = re.compile(r'taskuary|env|compgen|usen|exec', re.I)
_BUDGET = 2_000_000      # characters judged per call for the spans below; past it the call is refused, never let through

@lru_cache(maxsize=4)
def _brackets(text: str) -> tuple:
    "One linear pass, strings skipped: the bracket each string sits in, and where each bracket closes (never: the text's end)."
    enc, close, st = {}, {}, []
    for t in _TOK.finditer(text):
        c = t[0]
        if c[0] in '"\'': enc[t.start()] = st[-1] if st else -1
        elif c in '([{': st.append(t.start())
        elif st: close[st.pop()] = t.start()
    return enc, close

def _close(text: str, q: int) -> int:
    """Where the list or call the string at `q` sits in ends. No length cap: a string the pass did not see, or a bracket
    that never closes, runs to the end of the text - fail closed."""
    enc, close = _brackets(text)
    o = enc.get(q)
    return len(text) if o is None else _region(text, q) if o < 0 else close.get(o, len(text))

def _argv(text: str) -> list:
    out, spent = [], 0
    for m in [*_ARGV.finditer(text), *_SPAWN1.finditer(text)]:
        e = _close(text, m.start(1)); spent += e - m.end()
        if spent > _BUDGET: return out + [('it runs more code than the floor reads in one call', 'budget')]
        rest = [s[1] if s[1] is not None else s[2] for s in _STR.finditer(text, m.end(), e)]
        # no flag and no spawn call: a list of names (packages=['taskuary'], include=['taskuary', 'taskuary.*'])
        if m.re is _ARGV and not any(s.startswith('-') for s in rest) and _prog(m[2]) == 'taskuary' \
                and not _SPAWN_AT.search(text[max(0, m.start() - 60):m.start()]): continue
        out += [(f'{why} (from code)', _line(text, m)) for why in _taskuary_cmd([m[2], *rest])]
    return out

def _taskuary_cmd(ws: list) -> list:
    "Why the words `ws` - a command that runs `taskuary` - are refused: what is not one of the agent commands."
    p = _prog(ws[0])
    if p == 'taskuary-desktop': return ['it starts the Taskuary app']
    if p != 'taskuary': return []
    flags = [w.split('=', 1)[0].lower() for w in ws[1:] if w.startswith('-') and w != '-']
    bad = [f for f in flags if f not in TASKUARY_OK | _TASKUARY_WITH | _TASKUARY_ASK]
    if bad or not any(f in TASKUARY_OK | _TASKUARY_ASK for f in flags):
        return [f"`{' '.join(['taskuary', *(bad or ws[1:])])}` is not one of the agent commands a stranger's session runs"]
    return []

def _region(text: str, at: int) -> int:
    "Where the statement from `at` ends: lines are joined while a bracket or a quote is open, or the line goes on."
    end = at
    for _ in range(50):
        b = text.find('\n', end); b = len(text) if b < 0 else b
        r = text[at:b]
        open_ = sum(r.count(c) for c in '([{') > sum(r.count(c) for c in ')]}') or r.count('"') % 2 or r.count("'") % 2
        if b >= len(text) or not (open_ or r.rstrip()[-1:] in ('\\', '`', '^')): return b
        end = b + 1
    return end

def _shells(text: str) -> list:
    """Each launch's text is judged ONCE, by checks that do not look for shells again: a launch inside a launch is found by
    this same scan over the whole text, so recursing would judge it 2^k times. And a launch whose text ends where an
    earlier one's does is a suffix of what was already judged - `sh -c sh -c ...` is judged once, not once per `sh`."""
    out, seen, spent = [], set(), 0
    for m in _SHELL.finditer(text):
        # a quoted element of a list ['pwsh', '-c', ...] runs to that list's end; a shell word in a line, to its statement's
        q = m.start() - 1
        e = _close(text, q) if q >= 0 and text[q] in '"\'' and text[m.end():m.end() + 1] == text[q] else _region(text, m.end())
        if m[1]:     # its own options, up to the command or the script they start: an encoded command is refused outright
            for o in _PS_OPT.finditer(text, m.end(), e):
                f = o[2].lower()
                if f in ('e', 'ec') or len(f) > 1 and 'encodedcommand'.startswith(f):
                    out.append((f"it runs an encoded PowerShell command ({m[0]} {o[0]}), which no rule can read", _line(text, m))); break
                if o[1] == '-' and ('file'.startswith(f) or 'command'.startswith(f)): break
        r = text[m.end():e]
        if not m[1] and not _INLINE.search(r): continue
        if h := _HEREDOC.search(r):       # the heredoc's body is what the shell reads
            d = re.search(r'\n[ \t]*' + re.escape(h[2]) + r'[ \t]*(?:\n|$)', text[e:])
            r += text[e:e + d.start()] if d else text[e:]
        # keyed by where its text ends AFTER the heredoc: a later launch in the same statement may read a different one
        if (key := (e, m.end() + len(r), bool(m[1]))) in seen: continue
        seen.add(key); spent += len(r)
        if spent > _BUDGET: return out + [('it starts more inline shells than the floor reads in one call', 'budget')]
        if not _ANY_RULE.search(r): continue
        k, rq = _snip(m[0] + r), re.sub(r'''["'`]''', ' ', r)
        if t := _TQ.search(rq): out.append((f'it starts a shell ({m[0]}) that runs {t[0]}', k))
        why = [f"it runs Taskuary's own package ({x[0].strip()})" for x in _PKG.finditer(rq)]
        why += [f"it changes the session's own environment ({x[0].strip()})" for x in (_PS_MARKS if m[1] else _SCRIPT_MARKS).finditer(rq)]
        out += [(f'it starts a shell ({m[0]}) that {w[3:]}', k) for w in why + [w for w, _ in _segs(rq)]]
    return out

def _segs(text: str) -> list:
    "What each command segment of `text` is refused for - by its words, never by looking for shells or code inside them."
    out = []
    for seg in _SEG.split(text):
        raw, k = [_uq(w) for w in _WORD.findall(seg)], _snip(seg)
        if raw and _prog(raw[0]) != 'git' and (m := _PKG_ANY.search(seg)):
            out.append((f"it runs Taskuary's own package ({m[0].strip()}), which reads the owner's data in-process", k))
        if why := _env_wipe(raw): out.append((f"it empties the session's own environment ({why})", k))
        ws = _words(seg)
        if not ws: continue
        # a runner fetches or wraps a package outside every check below (R39: by presence)
        if _RUNNER.search(seg) and _TQ.search(seg): out.append((f"`{seg.strip()}` runs Taskuary through a runner, outside the agent commands", k))
        out += [(w, k) for w in _taskuary_cmd(ws)]
    return out

_READS = frozenset({'grep', 'egrep', 'fgrep', 'rg', 'findstr', 'select-string', 'sls', 'ls', 'dir', 'cat', 'type', 'head', 'tail', 'less', 'more', 'wc'})
_GIT_READS = frozenset({'grep', 'log', 'show', 'diff'})

def _searched(text: str, m) -> bool:
    """A bare TASKUARY_ name that is only an argument of a search or a listing - `grep -rn TASKUARY_ docs/` reads files, not
    the session. Never an expansion ($X, ${X}, %X%, Env:X), a redirection target, or the Env: drive itself."""
    if m[0].lower() != 'taskuary_' or m.start() and text[m.start() - 1] not in ' \t"\'': return False
    a = max((s.end() for s in _SEG.finditer(text, 0, m.start())), default=0)
    b = next((s.start() for s in _SEG.finditer(text, m.end())), len(text))
    seg = text[a:b]
    if re.search(r'''>\s*["']?\S*$''', seg[:m.start() - a]): return False
    ws = _words(seg)
    if not ws: return False
    p = _prog(ws[0])
    return p in _READS or p == 'git' and next((w.lower() for w in ws[1:] if not w.startswith('-')), '') in _GIT_READS

def _keyed(text: str, script: bool = False, ps: bool = False) -> list:
    """Every (reason, where) a command - or, `script`, the text of a file that will be run (`ps`: a PowerShell one) - is
    refused for, in the order they are checked. `where` is the hit's normalised line (a segment's, for what is judged per
    segment), so an edit that keeps a reason but changes its target - `env -i make` into `env -i taskuary`, `Test-Path
    Env:CI` into `rd Env:*` - is a new hit, and a reindent is not."""
    out = [(f"it runs Taskuary's own package ({m[0].strip()}), which reads the owner's data in-process", _line(text, m)) for m in _PKG.finditer(text)]
    out += [(f"it changes the session's own environment ({m[0].strip()})", _line(text, m))
            for m in ((_PS_MARKS if ps else _SCRIPT_MARKS) if script else _MARKS).finditer(text) if script or not _searched(text, m)]
    out += _shells(text) + _argv(text)
    out += [(f'{w} (from code)', _line(text, m)) for m in _SHELL_CALL.finditer(text) for w, _ in _segs(m[2])]
    return out + _segs(text)

def _hits(text: str, script: bool = False, ps: bool = False) -> list: return [r for r, _ in _keyed(text, script, ps)]

def _taskuary_hit(text: str, script: bool = False) -> str: return (_hits(text, script) or [''])[0]

# What a session runs without naming it: a script - and the files a task runner runs lines of (npm test, make, just,
# task). Other files - docs, YAML, JSON, TOML - are read, not run.
_PS_EXT = ('.ps1', '.psm1', '.psd1')
_SCRIPT_EXT = ('.sh', '.bash', '.zsh', *_PS_EXT, '.bat', '.cmd', '.py', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.mts', '.rb', '.pl')
_RUNNERS = ('package.json', 'makefile', 'gnumakefile', 'justfile', '.justfile', 'taskfile.yml', 'taskfile.yaml')

def _is_script(path: str, content: str = '') -> bool:
    "`content`: the file as it will be after this write or edit."
    if str(path or '').lower().endswith(_SCRIPT_EXT) or os.path.basename(str(path or '')).lower() in _RUNNERS: return True
    return str(content or '').startswith('#!')

def _is_ps(path: str, content: str = '') -> bool:
    return str(path or '').lower().endswith(_PS_EXT) or bool(re.match(r'#![^\n]*\b(pwsh|powershell)\b', str(content or ''), re.I))

def _before(path: str) -> str:
    try:
        with open(path, encoding='utf-8', errors='replace') as f: return f.read()
    except (OSError, ValueError): return ''

def _after(path: str, inp: dict) -> str:
    "The file's text once this call lands: a Write's content, or an Edit's replacement applied to what is there."
    if 'content' in inp: return str(inp.get('content') or '')
    text = _before(path)
    for e in [inp] + [e for e in inp.get('edits') or [] if isinstance(e, dict)]:
        if e.get('old_string') is None or e.get('new_string') is None: continue
        o, n = str(e['old_string']), str(e['new_string'])
        # not there as written, the CLI may still land it (it normalises quotes): what it adds is judged anyway
        text = text.replace(o, n, -1 if e.get('replace_all') else 1) if o and o in text else text + '\n' + n
    if inp.get('new_source') is not None: text += '\n' + str(inp['new_source'])     # a notebook cell: its source is what it adds
    return text

def _runner_text(path: str, text: str) -> str:
    "A runner's command lines, made plain: package.json's quoted strings and a YAML list's `- ` are where they sit."
    name = os.path.basename(str(path or '')).lower()
    if name == 'package.json': text = text.replace('"', '\n')
    if name.startswith('taskfile'): text = re.sub(r'(?m)^\s*-\s+', '', text)
    return text


# ── WHAT A LATER SESSION READS AS CONFIGURATION OR RUNS (wave B, B3) ────────────────────────────────────────────────
# Written by a stranger's session, each is an instruction or a hook that the OWNER's next session - full permissions -
# loads without asking: a CLI's settings, hooks, agents, commands and skills, its user instructions, a repository's git
# hooks and config, and the project files a CLI reads from the checkout. The repository's own CLAUDE.md / AGENTS.md stay
# editable: changing them is ordinary work on that repository, and a reviewer reads them as the repository's, not the owner's.
_CONF = re.compile(r'(^|/)(\.claude(/|$)|\.claude\.json$|\.mcp\.json$|\.git/(hooks(/|$)|config$)|\.codex/(config\.toml|hooks\.json|agents\.md)$'
                   r'|\.copilot(/|$)|\.gemini/settings\.json$)')
_WRITE_TOOLS = ('Write', 'Edit', 'MultiEdit', 'NotebookEdit')
_ALL_ARGS = {'tee', 'tee-object', 'set-content', 'sc', 'add-content', 'ac', 'out-file', 'new-item', 'ni', 'mkdir', 'md', 'touch', 'dd', 'truncate'}
_LAST_ARG = {'cp', 'copy', 'copy-item', 'cpi', 'mv', 'move', 'move-item', 'mi', 'ln', 'install', 'rsync', 'scp', 'robocopy', 'xcopy'}
_IN_PLACE = {'sed', 'perl', 'ruby'}             # with -i
_REDIR = re.compile(r'\d?\*?>{1,2}\|?\s*([^\s;&|<>]+)')

def _conf_dirs() -> list:
    "Where the CLIs are told to keep that configuration instead (CLAUDE_CONFIG_DIR and kin), as normalised roots."
    return [_norm(os.environ[v], real=rl) for v in ('CLAUDE_CONFIG_DIR', 'COPILOT_HOME') if os.environ.get(v) for rl in (True, False)]

def _is_conf(p: str) -> bool:
    "`p` normalised and folded: one of the files above, or anything in a relocated CLI home."
    return bool(_CONF.search(p)) or _under(p, _conf_dirs()) or bool(os.environ.get('CODEX_HOME')) and any(
        p == _norm(os.path.join(os.environ['CODEX_HOME'], f), real=rl) for f in ('config.toml', 'hooks.json', 'AGENTS.md') for rl in (True, False))

def _git_config_write(args: list) -> bool:
    "`git [-C dir] [-c k=v] config ...` that is not a read: it writes .git/config (or ~/.gitconfig) without naming either."
    i = 0
    while i < len(args) and args[i].startswith('-'): i += 2 if args[i] in ('-C', '-c') else 1
    if i >= len(args) or args[i].lower() != 'config': return False
    rest = args[i + 1:]
    return not any(a.startswith('--get') or a in ('--list', '-l') for a in rest) and (rest[:1] or [''])[0] not in ('get', 'list')

def _write_hit(text: str, cwd: str = '') -> str:
    "Why a shell command writes into one of them, or ''. Its targets: a redirection, or what a writing command writes to."
    h = _norm('~', real=False)
    cur = _norm(cwd) if cwd else ''
    def hit(tok):
        t = _HOME_VAR.sub(h, tok)
        q = _strip(os.path.expandvars(t))
        forms = {_cf(q)} | ({_norm(q, cur, rl) for rl in (True, False)} if cur or os.path.isabs(q) else set())
        return any(_is_conf(f) for f in forms)
    for seg in _SEG.split(text):
        targets = _REDIR.findall(seg)
        ws = _words(_REDIR.sub(' ', seg))
        if ws:
            p, args = _prog(ws[0]), ws[1:]
            plain = [a for a in args if not a.startswith('-') or a == '-']
            if p in _CD and plain: cur = _norm(plain[0], cur) if cur or os.path.isabs(plain[0]) else cur
            elif p in _ALL_ARGS: targets += plain + [a[3:] for a in args if a.lower().startswith('of=')]
            elif p in _LAST_ARG: targets += plain[-1:] + [args[i + 1] for i, a in enumerate(args[:-1]) if a.lower() in ('-destination', '-t', '--target-directory')]
            elif p in _IN_PLACE and any(re.fullmatch(r'-\w*i\S*|--in-place\S*', a) for a in args): targets += plain
            elif p == 'git' and _git_config_write(args): return "it changes git's configuration, which runs in the owner's next git command (core.hooksPath and kin)"
        for t in targets:
            if hit(t): return f'it writes {t}, which a later session of the owner reads as configuration or runs'
    return ''

def _added(old: str, new: str) -> str:
    "The lines of `new` that `old` does not have, counted: a second copy of a line is added."
    c, out = Counter(old.splitlines()), []
    for l in new.splitlines():
        if c[l] > 0: c[l] -= 1
        else: out.append(l)
    return '\n'.join(out)

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
            if tool in _WRITE_TOOLS and _is_conf(p): return _deny(f'{inp[k]} is read as configuration, or run, by a later session of the owner')
    if tool in _WRITE_TOOLS:    # a script written now and run by a command that names nothing: judged as the command it will be
        said = '\n'.join(str(o) for o in (inp.get('content'), inp.get('new_string'), inp.get('new_source'), *[e.get('new_string') for e in inp.get('edits') or [] if isinstance(e, dict)]) if o)
        f = next((str(inp[k]) for k in _FILE_KEYS if inp.get(k)), '')
        f = f if os.path.isabs(f) or not cwd else os.path.join(cwd, f)
        old, body = _before(f), _after(f, inp) or said      # the whole file as it will be: an edit can make a script of what is there
        # refused only for what this call ADDS (R36): an edit beside a `taskuary --demo` target already there is ordinary work.
        # Counted, so a second copy is new; a file that only now becomes a script brings everything in it.
        if _is_script(f, body):
            ow, ps = _is_script(f, old), _is_ps(f, body)
            was, now = Counter(_keyed(_runner_text(f, old), True, _is_ps(f, old)) if ow else []), Counter(_keyed(_runner_text(f, body), True, ps))
            # the file was already past the budget: its 'budget' is not this call's doing. The edit that CROSSES it is refused.
            new = [h for h in (now - was).elements() if h[1] != 'budget' or not any(k == 'budget' for _, k in was)]
            # past the budget a side was not read to its end, and its 'budget' key would cancel the other's: what this call
            # adds - the edit's new text, a Write's added lines - is judged on its own, by every rule
            if ow and any(k == 'budget' for _, k in was | now): new += _keyed(_runner_text(f, _added(old, body) if 'content' in inp else said), True, ps)
            if new:
                return _deny(f'it writes a script that, run, would be refused: {new[0][0]}')
    if why := _taskuary_hit(str(inp.get('command') or '')) or _write_hit(str(inp.get('command') or ''), cwd): return _deny(why)
    if tool in ('Grep', 'Glob'):    # these walk a tree: a root ABOVE a protected folder reaches it just as well
        sr = {_cf(os.path.normcase(os.path.abspath(o))) for o in ((inp.get('path') and _forms(inp['path'], cwd)) or ([cwd] if cwd else []))}
        for s in sr:
            if _above(s, prot): return _deny(f'searching from {inp.get("path") or cwd} would reach a protected folder')
    if why := _text_hit(' '.join(str(inp.get(k) or '') for k in _TEXT_KEYS), own, prot, cwd): return _deny(why)
    return {}
