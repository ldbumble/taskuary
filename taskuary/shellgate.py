"""A SHELL STEP THAT LEAVES THE MACHINE WAITS FOR THE OWNER'S PRESS (the Advisor design rev 2, the owner's ruling 2026-10-28: "hold risky
steps on the existing proposal card - the only automatic act; risky = send/forward, pay, sign up, delete, push/merge, new outside recipient").

browsergate.py holds a browser act that can't be undone. The same road out ran through the agent's own shell, guarded only by prose
("CODING.md says not to push" - guard.py's header on why prose is no control): `git push`, `gh pr merge`, a public comment, a release
deleted, a package published or a mail sent from a script went straight out, and a mail that talked the agent into one was all it took.

Where it is caught: the same PreToolUse hook on the shell tools (hooks.browser, matcher Bash|PowerShell). Which commands go out is each
tool's own GRAMMAR - git's `push`, the GitHub CLI's `pr merge` or `api -X DELETE`, a package manager's `publish`, a mail tool by its name -
never a judgement over words, and never the words of a mail. Everything else passes at once.
- ASKED, where the owner can answer in the CLI (the owner, 2026-10-29: "let's not mess with people's CLIs"): the hook answers `ask`
  and Claude Code draws its OWN permission prompt in the pane - the owner's yes there is the approval, and the task gets only a line
  saying what was asked. Held, the agent was refused, the owner typed "yes push" into the CLI, it tried again and was refused again:
  the one place the owner was looking could not say yes. Which sessions ask is read from the session (asks), never from words.
- HELD everywhere else (a headless chat, a workflow's run, a stranger's task, a CLI whose hook cannot ask): the tool call is refused
  with why, and the step goes on the task as a proposal (proposals.ACTIONS 'shell_act') - the card with Approve and Dismiss.
- APPROVED, Taskuary runs that exact command in the folder the agent ran it from, in the shell it was written for (Git Bash on
  Windows, never WSL's bash), and tells the agent what happened. Dismissed, the agent is told it was not done.

What this does not cover, said plainly: Codex, Devin and Copilot sessions (their hooks report, they cannot refuse a call - and Codex's
PreToolUse parses `ask` without supporting it yet); a session whose hook could not reach Taskuary (the call runs - the same as the
browser hook); and a step reached some other way than these tools by name (a script that pushes). This gates the commands agents use,
not every road there is.

AN HTTP CLIENT THAT WRITES OFF THIS MACHINE GOES OUT TOO (the north-star audit, 2026-11-10 - the owner: "it shoudl prompt you, should i deploy
and respond once deployed??? isnt' this the goal?"): `curl -X POST`, `-d`, `Invoke-RestMethod -Method Post` to a host that is not this
computer is one of the steps `acts` returns, read by each client's own flags. The ACP road refused it flatly ("only the owner sends") and the
hook road never looked, so a CLI's POST went out unseen; both read it here now and hold it as any push is held - the owner's one press.
Taskuary's own API on this machine is not a step out.

A DELETE ON THE OWNER'S COMPUTER WAITS TOO (the same ruling's "delete"; the desktop stress test, 2026-11-03: asked to remove the folder it
had just unzipped into Downloads, a general agent ran `Remove-Item -Recurse -Force` at once - gone for good, not in the Recycle Bin). What
is held is a delete tool by name (rm, del, Remove-Item, rmdir... and the .NET / Python calls that delete) aimed OUTSIDE the agent's own
folder: its working folder and the temp folder are its to tidy, everything else is the owner's. A target it cannot read - a variable set
somewhere else, a pipe into Remove-Item - is held, never let through for being hard to read.
"""
import contextvars, json, ntpath, os, re, shlex, shutil, subprocess, tempfile, threading
from loguru import logger
from .gate import TABLE, deny as _deny
from .browsergate import _segments, _tell, joined, launched, not_approved, NEXT, OWNER_NO, words

from .gate import HELD_SAID as HELD          # ...one wording for every road's hold (gate.py)
_FILING = threading.Lock()
ASKS = {'claude'}       # the CLIs whose PreToolUse hook can answer `ask` with their own prompt (measured: Claude 2.1.312 honours it)
# each tool's own words for a step that goes out, as (what it does, in the owner's words): its subcommand, or (subcommand, action)
GIT = {'push': 'push the agent\'s commits out of this computer'}
GH = {('pr', 'merge'): 'merge a pull request', ('pr', 'create'): 'open a pull request', ('pr', 'comment'): 'post a public comment on a pull request',
      ('pr', 'review'): 'post a review on a pull request', ('pr', 'close'): 'close a pull request', ('pr', 'ready'): 'mark a pull request ready',
      ('issue', 'create'): 'open an issue', ('issue', 'comment'): 'post a public comment on an issue', ('issue', 'close'): 'close an issue',
      ('issue', 'delete'): 'delete an issue', ('release', 'create'): 'publish a release', ('release', 'delete'): 'delete a release',
      ('release', 'upload'): 'upload files to a release', ('repo', 'delete'): 'delete a repository', ('repo', 'create'): 'create a repository',
      ('repo', 'archive'): 'archive a repository', ('repo', 'rename'): 'rename a repository', ('secret', 'set'): 'set a secret',
      ('secret', 'delete'): 'delete a secret', ('gist', 'create'): 'publish a gist', ('workflow', 'run'): 'start a workflow run',
      ('run', 'cancel'): 'cancel a workflow run', ('run', 'delete'): 'delete a workflow run'}
GLAB = {('mr', 'merge'): 'merge a merge request', ('mr', 'create'): 'open a merge request', ('mr', 'note'): 'post a public comment',
        ('issue', 'create'): 'open an issue', ('issue', 'note'): 'post a public comment', ('issue', 'delete'): 'delete an issue',
        ('release', 'create'): 'publish a release', ('release', 'delete'): 'delete a release'}
PUBLISH = {'npm', 'pnpm', 'yarn', 'cargo', 'poetry', 'gem', 'dotnet', 'nuget'}             # `<tool> publish` / `nuget push` publish a package
MAIL = {'sendmail': 'send an email', 'mailx': 'send an email', 'mutt': 'send an email', 'msmtp': 'send an email', 'send-mailmessage': 'send an email'}
_WRITES = {'post', 'put', 'patch', 'delete'}
HTTP = {'curl', 'wget', 'http', 'https', 'xh', 'xhs', 'invoke-webrequest', 'iwr', 'invoke-restmethod', 'irm'}
_PS, _PIE = {'invoke-webrequest', 'iwr', 'invoke-restmethod', 'irm'}, {'http', 'https', 'xh', 'xhs'}
# each client's own grammar for a write: curl's short flags are case-sensitive (-F a form post, -f --fail) and bundle (`-sXPOST`, `-sd x`) - the
# letters that take a value end a bundle; a long option that sends a body starts with one of these; -K/--config sends what a file it reads says
_CURL_VAL = 'AbcCdDeEFHKmoPQrtTuUwxXyYz'
_BODY = ('--data', '--form', '--upload', '--post-', '--body-', '--json', '--raw', '--config')
_PIE_VAL = 'aAop'
_VERBS = {'get', 'head', 'options', 'post', 'put', 'patch', 'delete'}
# the programs whose own grammar says a step goes out - what a launcher (`timeout 60 git push`) is read through to (browsergate.launched)
_TOOLS = frozenset({'git', 'gh', 'glab', 'twine', 'docker', 'bash', 'sh', 'powershell', 'pwsh', 'cmd', *PUBLISH, *MAIL, *HTTP})
_LOCAL = re.compile(r'^https?://(localhost|127\.\d+\.\d+\.\d+|\[::1\])(:\d+)?(/|$)', re.I)
# ...and Taskuary's own address as it hands it to a session (terminal.session_env), the way docsync.agent_systems spells the call to the
# owner's systems: held as "send data to a web address", a read of his own books was an Approve card. Never where the command sets it
_OWN = re.compile(r'^\$(TASKUARY_URL|\{TASKUARY_URL\})(/|$)')
_SETS_OWN = re.compile(r'\bTASKUARY_URL\s*=')
_PREFIX = ('&', 'npx', 'command', 'call', 'exec', 'sudo', 'time', 'nohup')



def _tool(t: str) -> bool: return _name(t) in _TOOLS or _name(t) in DELETERS or _name(t) in ('find', 'cd', 'chdir', 'set-location', 'sl', 'pushd', 'push-location')


def _name(tok: str) -> str:
    import re
    return re.sub(r'\.(exe|cmd|ps1|bat)$', '', os.path.basename(str(tok).replace('\\', '/')).lower())


def _words(argv: list) -> tuple:
    """(tool, its words with every option and an option's value taken out) of one simple command, through env prefixes and the like."""
    import re
    if not argv: return '', []
    tool, rest, out, j = _name(argv[0]), argv[1:], [], 0
    # git's own options before the subcommand that take a value (`git -C repo push`, `git -c k=v push`)
    while tool == 'git' and j < len(rest) and rest[j].startswith('-'): j += 2 if rest[j] in ('-C', '-c', '--git-dir', '--work-tree', '--namespace') else 1
    for t in rest[j:]:
        if not t.startswith('-'): out.append(t)
    return tool, out


def _http_write(argv: list, own: bool = False) -> str:
    """'' unless this HTTP client writes to a host off this machine - then what it does, in words. Read by each client's own grammar: its
    method option (`-X`, `--request`, `--method`, PowerShell's `-Method` however abbreviated or `-Method:Post`), an option that sends a body,
    and httpie's / xh's own `[METHOD] URL item=value`. Taskuary's own API answers its own guard - `own`: $TASKUARY_URL is Taskuary's (nothing
    in the command set it)."""
    tool, a = _name(argv[0]), [str(t) for t in argv[1:]]
    meth, data, pos, i = '', False, [], 0
    while i < len(a):
        t, nxt = a[i], (a[i + 1] if i + 1 < len(a) else '')
        if t.startswith('--'):
            k, eq, v = t.partition('=')
            k = k.lower()
            if k in ('--request', '--method'): meth = v if eq else nxt; i += not eq
            elif k.startswith(_BODY) or (tool in _PIE and k == '--form'): data = True
        elif t.startswith('-') and len(t) > 1 and tool in _PS:
            k, col, v = t[1:].partition(':')
            k = k.lower()
            if len(k) > 1 and 'method'.startswith(k): meth = v if col else nxt; i += not col
            elif len(k) > 1 and ('body'.startswith(k) or 'infile'.startswith(k)): data = True
        elif t.startswith('-') and len(t) > 1 and tool == 'curl':
            for j, c in enumerate(t[1:], 1):
                if c in 'dFTK': data = True
                if c == 'X': meth = t[j + 1:] or nxt
                if c in _CURL_VAL:
                    i += j == len(t) - 1; break
        elif t.startswith('-') and len(t) > 1 and tool in _PIE: i += t[-1] in _PIE_VAL
        elif not t.startswith('-'): pos.append(t)
        i += 1
    urls = [t for t in pos if re.match(r'^https?://', t, re.I) or (own and _OWN.match(t))]
    if tool in _PIE and pos:
        # httpie / xh: [METHOD] URL then items - `k=v`, `k:=json`, `k@file` send a body (a POST), `k==v` is a query and `K:v` a header
        if len(pos) > 1 and pos[0].lower() in _VERBS: meth, pos = meth or pos[0], pos[1:]
        u = pos[0]
        urls = [u if re.match(r'^https?://', u, re.I) or (own and _OWN.match(u)) else 'http://' + ('localhost' + u if u.startswith(':') else u)]
        data = data or any(re.match(r'^[^:=@]*(:=|=(?!=)|@)', x) for x in pos[1:])
    if urls and all(_LOCAL.match(u) or (own and _OWN.match(u)) for u in urls): return ''
    if meth.lower() not in _WRITES and not data: return ''
    host = re.sub(r'^https?://([^/?#]+).*', r'\1', urls[0]) if urls else 'a web address'
    return f'send data to {host} ({tool})'


def _api_writes(argv: list) -> bool:
    """`gh api` / `glab api` with a method that writes, or fields (which make it a POST)."""
    a = [str(t) for t in argv]
    for k, t in enumerate(a):
        m = t.split('=', 1)
        if m[0] in ('-X', '--method'):
            v = (m[1] if len(m) > 1 else a[k + 1] if k + 1 < len(a) else '').lower()
            if v in _WRITES: return True
        elif t.startswith('-X') and t[2:].lower() in _WRITES: return True
        if m[0] in ('-f', '-F', '--field', '--raw-field', '--input'): return True
    return False


# ── deleting on this computer ───────────────────────────────────────────────────────────────────────────────────────────────────
DELETERS = frozenset('rm rmdir rd del erase remove-item ri unlink shred srm'.split())
UNDONE, OUT = TABLE['erase'].why, TABLE['out'].why          # said as the one table says them (gate.TABLE)
# the calls that delete from a snippet or a PowerShell line, whatever runs them: .NET, Python, Node
_API_DEL = re.compile(r'\[(?:system\.)?io\.(?:file|directory)\]::delete\b|shutil\.rmtree\b|\bos\.(?:remove|unlink|rmdir|removedirs)\b'
                      r'|\bfs\.(?:rm|rmdir|unlink)(?:sync)?\b|\.delete\(\s*(?:\$true)?\s*\)|\.unlink\(\s*(?:missing_ok\s*=\s*true)?\s*\)', re.I)
_DEL_WORDS = ('rm', 'del', 'erase', 'remove', 'unlink', 'shred', 'rd', 'rmtree')
_VAR = re.compile(r'\$(?:env:)?(\w+)|%(\w+)%', re.I)
_SPLIT = re.compile(r'\r?\n|;|&&|\|\||\||\{|\}')
_VALUED_DEL = frozenset('-erroraction -ea -filter -include -exclude -depth -credential -stream -warningaction -wa'.split())


_HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z_][\w.-]*)\1")
_SHELLS = ('bash', 'sh', 'zsh', 'dash', 'powershell', 'pwsh', 'cmd')


def shell_text(raw: str) -> str:
    """The line as its shell reads it: a heredoc's body fed to any program but a shell (`python - <<'PY'`, `cat > f <<EOF`) is that
    program's data, dropped - its words are not commands (the owner's live task, 2026-11-17: Python lines `del rows[unit]` held as
    "delete not in .., in in .., unit:"). A delete call inside a snippet is still caught on the whole line (_API_DEL)."""
    lines, out, i = str(raw or '').split('\n'), [], 0
    while i < len(lines):
        ln = lines[i]; out.append(ln); i += 1
        # ...and a PowerShell here-string (`@'` ... `'@`) is that program's data the same way (the HIPAA walk, 2026-11-21: a deck's Python,
        # piped from one into Set-Content, was read for paths - "$60 / day" held as a path built from a variable); its closing line's
        # command after the quote stays
        if (h := re.search(r"@(['\"])\s*$", ln)):
            body = []
            while i < len(lines) and not lines[i].startswith(h[1] + '@'): body.append(lines[i]); i += 1
            tail = lines[i][2:] if i < len(lines) else ''
            if re.search(r'\|\s*&?\s*(iex|invoke-expression|powershell|pwsh|bash|sh|cmd)\b', tail, re.I): out += body     # ...fed to a shell, it is commands
            out.append(tail); i += 1
            continue
        for m in _HEREDOC.finditer(ln):
            w = _SPLIT.split(ln[:m.start()])[-1].split()
            if w and _name(w[0]) in _SHELLS: continue
            while i < len(lines) and lines[i].strip() != m.group(2): i += 1
    return '\n'.join(out)


def _expand(t: str, env: dict) -> str:
    "A target with what the shell would fill in filled in: the line's own `$dst=...`, then the environment, then ~."
    def sub(m):
        n = (m.group(1) or m.group(2)).lower()
        if n in env: return env[n]
        v = next((v for k, v in os.environ.items() if k.lower() == n), None)
        return v if v is not None else os.path.expanduser('~') if n == 'home' else m.group(0)
    for _ in range(3):
        t2 = _VAR.sub(sub, t)
        if t2 == t: break
        t = t2
    return os.path.expanduser('~') + t[1:] if t.startswith('~') else t


def _real(p: str) -> str: return os.path.normcase(os.path.realpath(p))
def _under(p: str, root: str) -> bool:
    r = _real(root)
    return p != r and p.startswith(r.rstrip('\\/') + os.sep)


def _path(t: str) -> str: return re.sub(r'^/([a-zA-Z])(?=/|$)', r'\1:', t) if os.name == 'nt' else t     # Git Bash's /c/Users is C:/Users


def _target(t: str, cwd: str, here=None) -> tuple:
    """(is it the agent's own to delete - inside its working folder or the temp folder, how the owner reads it, the folder it is in).
    `here`: where the line has `cd`-ed to by now (None: somewhere it could not read). Unreadable is not its own."""
    here = cwd if here == '' else here
    if not t or re.search(r'[$`(%]', t): return False, '', ''
    t = _path(t)
    if not os.path.isabs(t):
        if here is None: return False, '', ''                                # after a `cd` it could not follow
        if not here: return '..' not in re.split(r'[\\/]', t), '', ''       # relative, with no folder to read it against: it stays where it is
        t = os.path.join(here, t)
    p, n = _real(t), os.path.normpath(t)
    name, parent = os.path.basename(n), os.path.basename(os.path.dirname(n))
    roots = [r for r in (cwd, tempfile.gettempdir(), '/tmp') if r]
    return any(_under(p, r) for r in roots), (f'{name} in {parent}' if parent and name else name or n), os.path.dirname(n)


def deletes(cmd: str, cwd: str = '', env: dict = None) -> list:
    """Every delete in a shell line aimed outside the agent's own folder: [{'tool', 'what', 'why', 'where', 'command'}], one per line at
    most - `where` the folder the first named target sits in, for the card's In. Read by the delete tools' own names, through
    `if (...) { ... }` blocks, `cmd /c` and `bash -c "..."`."""
    raw, env = str(cmd or ''), {} if env is None else env
    found = _deletes(raw, cwd, env)
    if not found['tools']: return []
    known = list(dict.fromkeys(found['named']))
    more = len(known) > 3 or (known and found['blind'])
    what = 'delete ' + (', '.join(known[:3]) + (' and more' if more else '') if known else 'files on this computer')
    return [{'tool': found['tools'][0], 'kind': 'erase', 'what': what, 'why': UNDONE, 'where': (found['places'] or [''])[0], 'command': raw[:400]}]


def _deletes(raw: str, cwd: str, env: dict, here='') -> dict:
    # `here`: the folder the line has moved to - `cd ~/Downloads && rm -rf notes` deletes in Downloads, not in the agent's own folder
    # (the stress test's second delete, 2026-11-03). '' is the agent's own folder; None a `cd` it could not read
    named, places, blind, tools = [], [], False, []
    done = lambda: {'named': named, 'places': places, 'blind': blind, 'tools': tools, 'here': here}
    if not any(w in joined(raw) for w in _DEL_WORDS + ('cd', 'location')): return done()             # the cheap test first
    raw = re.sub(r'\$\{(\w+(?::\w+)?)\}', r'$\1', raw)                         # ${dst} is $dst - and its braces are not a block
    for seg in _SPLIT.split(shell_text(raw)):
        seg = seg.strip()
        if not seg: continue
        if (m := re.match(r'^\$?([A-Za-z_]\w*)\s*=\s*(\S.*)$', seg)) and not m.group(2).startswith('='):
            try: v = shlex.split(m.group(2), posix=False)
            except ValueError: v = []
            if len(v) == 1: env[m.group(1).lower()] = _expand(v[0].strip('"\''), env)
            continue
        w = words(seg)
        while w and w[0].lower() in ('if', 'else', 'elseif', 'then', 'do'): w = w[1:]
        w = launched(w, _tool)
        if not w: continue
        tool = _name(w[0])
        if tool in ('cd', 'chdir', 'set-location', 'sl', 'pushd', 'push-location'):
            to = next((x for x in w[1:] if not x.startswith('-') and not re.match(r'^/\w$', x)), '~')       # cmd's `cd /d X`
            to = _path(_expand(to, env))
            base = cwd if here == '' else here
            here = None if re.search(r'[$`(%]', to) or (not os.path.isabs(to) and not base) else os.path.normpath(os.path.join(base or '', to))
            continue
        if tool in ('bash', 'sh', 'powershell', 'pwsh', 'cmd'):
            inner = next((i for i, x in enumerate(w) if x.lower() in ('-c', '-command', '/c', '/k')), None)
            if inner is not None:
                d = _deletes(' '.join(w[inner + 1:]), cwd, env, here)
                named += d['named']; places += d['places']; tools += d['tools']; blind, here = blind or d['blind'], d['here']
            continue
        finds = tool == 'find' and '-delete' in w
        if tool not in DELETERS and not finds: continue
        args, skip = [], False
        for x in w[1:]:
            if skip: skip = False; continue
            if x.lower() in _VALUED_DEL: skip = True; continue
            if x.startswith('-') or (tool in ('del', 'erase', 'rd', 'rmdir') and re.match(r'^/\w$', x)): continue
            args.append(x)
        if finds: args = args[:1] or ['.']
        if not args:
            if tool in ('remove-item', 'ri'): blind = True; tools.append(tool)  # piped in: what it deletes is not on the line
            continue
        for a in args:
            own, said, place = _target(_expand(a, env), cwd, here)
            if own: continue
            tools.append(tool)
            if said: named.append(said); places.append(place)
            else: blind = True
    if _API_DEL.search(raw): blind = True; tools.append('snippet')
    # VisualBasic's FileSystem.DeleteDirectory/DeleteFile: to the Recycle Bin it can be undone (the agent's own pick, 2026-11-03), else it can't
    low = raw.lower()
    if re.search(r'filesystem\]::delete(?:directory|file)\b', low) and 'sendtorecyclebin' not in low: blind = True; tools.append('snippet')
    return done()


def acts(cmd: str, cwd: str = '') -> list:
    """Every step in a shell command that waits for the owner: one that goes out (_outward), and a delete outside the agent's own folder
    (deletes) - [{'tool', 'what', 'why', 'command'}]."""
    return _outward(cmd) + deletes(cmd, cwd)


def _outward(cmd: str, own: bool = True) -> list:
    """Every step in a shell command that goes out: [{'tool', 'what', 'why', 'command'}]. A command that cannot be read and names one of
    these tools is one step - held, never let through for being hard to read."""
    raw = shell_text(str(cmd or ''))
    low = joined(raw)
    own = own and not _SETS_OWN.search(raw)
    if not any(w in low for w in ('git', 'gh', 'glab', 'publish', 'push', 'upload', 'mail', 'mutt', 'msmtp', 'http', 'curl', 'wget', 'xh', 'iwr', 'irm',
                                  'invoke-')): return []      # the cheap test first
    segs = _segments(raw)
    if segs is None:
        import re
        return [{'tool': '?', 'kind': 'out', 'what': 'run a command that may push, publish or send', 'why': OUT, 'command': raw[:400]}] if re.search(
            r'\b(git\s+push|gh\s+(pr|issue|release|repo|api)|glab|publish|sendmail|send-mailmessage)\b', low) else []
    out, moved = [], False
    for argv in segs:
        whole, argv = argv, launched(argv, lambda t: _name(t) in _TOOLS)   # `timeout 60 git push` is git's push, read as git's - its env still aims it
        tool, w = _words(argv)
        if tool in MOVES: moved = True
        if tool in ('bash', 'sh', 'powershell', 'pwsh', 'cmd'):                 # `bash -c "git push"`: the string is a command of its own
            for t in argv[1:]:
                if ' ' in t.strip(): out += _outward(t, own)
            continue
        what = (GIT.get(w[0]) if tool == 'git' and w else
                GH.get(tuple(w[:2])) if tool == 'gh' else GLAB.get(tuple(w[:2])) if tool == 'glab' else
                'publish a package' if (tool in PUBLISH and w[:1] in (['publish'], ['push'])) or (tool == 'twine' and w[:1] == ['upload'])
                or (tool == 'docker' and w[:1] == ['push']) else MAIL.get(tool))
        if not what and tool in ('gh', 'glab') and w[:1] == ['api'] and _api_writes(argv): what = 'change something on the code host through its API'
        if not what and tool == 'git' and w[:1] == ['push']: what = GIT['push']
        if not what and tool in HTTP: what = _http_write(argv, own)
        if what: out.append({'tool': tool, 'kind': 'out', 'what': what, 'why': OUT, 'command': ' '.join(argv)[:400], 'to': '?' if moved else _to(tool, whole, w),
                             **({'refs': w[2:]} if tool == 'git' and w[:1] == ['push'] else {})})
    return out


# WHERE A STEP GOES, as its tool's own grammar names it (trusted): '' the checkout's own origin, else the owner/name it names, '?' when the
# line names some other place - a URL or another remote for git, another folder, a `cd` before it. The trust is one repository's.
MOVES = {'cd', 'pushd', 'popd', 'chdir', 'set-location', 'sl', 'push-location', 'pop-location'}


def _named(n: str) -> str:
    "owner/name of a repository a GitHub or GitLab CLI flag or URL names - `owner/name`, `HOST/owner/name` or an item's URL; '?' off the code hosts."
    if n == '?': return '?'
    m = re.match(r'^(?:https?://)?(?:([^/\s]+\.[^/\s]+)/)?([\w.-]+/[\w.-]+?)(?:\.git)?(?:/.*)?$', n, re.I)
    if not m or (m.group(1) and m.group(1).lower() not in HOSTS): return '?'
    return m.group(2).lower()


_API_VALUED = {'-X', '--method', '-H', '--header', '-f', '-F', '--field', '--raw-field', '--input', '-q', '--jq', '-t', '--template', '--hostname',
               '--cache', '-p', '--preview'}


def _to(tool: str, argv: list, w: list) -> str:
    a = [str(t) for t in argv]
    env = {t.split('=', 1)[0].upper() for t in a if re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', t)}
    if env & {'GIT_DIR', 'GIT_WORK_TREE', 'GH_REPO', 'GH_HOST', 'GITLAB_HOST'}: return '?'
    if tool == 'git':
        if any(t in ('--git-dir', '--work-tree') or t.startswith(('--git-dir=', '--work-tree=', '--repo', '--receive-pack', '--exec')) for t in a): return '?'
        # ...`git -C <folder>` runs in that folder: '@<folder>', its own origin read where it is checked (trusted) - a worktree of the same repo
        # is the same repo (the owner's live task, 2026-11-19: every push from the agent's worktree was a card on a repo he trusts)
        at = [a[i + 1] for i, t in enumerate(a[:-1]) if t == '-C']
        if len(at) > 1 or (at and re.search(r'[$`(%]', at[0])): return '?'
        remote = w[1] if len(w) > 1 else ''
        if remote in ('', 'origin'): return '@' + at[0] if at else ''
        h, r = host_repo(remote) if re.match(r'^([a-z][a-z0-9+.-]*://|[^@/\s]+@)', remote, re.I) else ('', '')
        return r if h in HOSTS and r else '?'
    named = [a[i + 1] for i, t in enumerate(a[:-1]) if t in ('-R', '--repo')] + [t.split('=', 1)[1] for t in a if t.startswith('--repo=')]
    named += [t[2:] for t in a if t.startswith('-R') and len(t) > 2]
    if w[:1] == ['api']:
        rest, end = a[a.index('api') + 1:] if 'api' in a else [], ''
        while rest and not end:
            t = rest.pop(0)
            if t in _API_VALUED: rest = rest[1:]
            elif not t.startswith('-'): end = t
        m = re.match(r'^/?(?:repos|projects)/([^/]+/[^/]+)(?:/|$)', end)
        named.append(m.group(1) if m else '?')
    named += [t for t in w if re.match(r'^https?://', t, re.I)]
    got = {_named(n) for n in named}
    got.discard('{owner}/{repo}')                                                       # gh fills these from the checkout itself
    return '' if not got else got.pop() if len(got) == 1 else '?'


def _pending(store, tid: int, sid: str, cmd: str, reads: list = ()):
    for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (tid,)):
        try: p = json.loads(r.get('DraftText') or '{}')
        except ValueError: continue
        if p.get('action') == 'shell_act' and p.get('sid') == str(sid) and p.get('command') == cmd and p.get('reads', []) == list(reads): return r
    return None


def asks(store, t) -> str:
    """WHERE the owner answers this session's own permission prompt - '' where nobody can. Only a CLI pane of ours (argv: a terminal, not a
    headless chat), started 'full' (a stranger's task runs 'auto' and its permit door is the owner's), whose CLI's hook answers `ask`, on a
    task that is not a workflow's run (nobody sits at a scheduled run's pane). Everything else is held for the task's Approve.
    'terminal': the CLI's own prompt in its pane. 'chat': the same CLI over ACP has no terminal - its ask comes back to Taskuary's own
    gate (gate.answerer), which draws the landing card, the owner's buttons or the Approve card itself."""
    if not getattr(t, 'argv', None) or getattr(t, 'mode', 'full') != 'full': return ''
    from . import clis, terminal
    if clis._base(getattr(t, 'cli', '') or t.argv[0]) not in ASKS or (store.get_task(t.task_id) or {}).get('Source') == 'workflow': return ''
    return 'chat' if terminal.is_acp(t) else 'terminal'


# A TRUSTED REPO'S OWN STEPS GO THROUGH (the owner, 2026-11-05, a coding agent's push and deploy promote stopped by the ask: "i thought for
# trusted things we don't need this??"). The repo the command runs in, by its origin, and the GitHub card that reaches it - by that repo's own
# source row, never the default card's trust - grant what its Authority covers: `write` a push (a deploy branch too - the owner: "same as a
# push"), a pull request opened, commented or reviewed, a workflow run; `admin` also a merge, a close, a release. Never trusted, on any repo:
# a delete of something on the host, a secret, a package published, a mail - and a delete on the owner's computer (they keep their own `why`).
WRITE_OK = {'push the agent\'s commits out of this computer', 'open a pull request', 'post a public comment on a pull request',
            'post a review on a pull request', 'mark a pull request ready', 'post a public comment on an issue', 'open an issue',
            'start a workflow run', 'cancel a workflow run', 'open a merge request', 'post a public comment'}
ADMIN_OK = WRITE_OK | {'merge a pull request', 'close a pull request', 'close an issue', 'merge a merge request', 'publish a release',
                       'upload files to a release', 'change something on the code host through its API'}
RANK = {'read': 0, 'write': 1, 'admin': 2}


def repo_of(cwd: str) -> str:
    "owner/repo of the checkout the command runs in, from its origin - '' when it is not one."
    return next((r for _, r in _remote(cwd)), '')


_URL = re.compile(r'^(?:[a-z][a-z0-9+.-]*://)?(?:[^@/\s]+@)?([^/:\s]+)(?::\d+)?[:/]+(.+?)(?:\.git)?/*$', re.I)


def host_repo(url: str) -> tuple:
    "(host, owner/name) of a git remote's URL - https, ssh or scp form - else ('', '')."
    m = _URL.match(str(url or '').strip())
    if not m: return '', ''
    parts = [p for p in m.group(2).split('/') if p]
    return (m.group(1).lower(), '/'.join(parts[-2:])) if len(parts) >= 2 else ('', '')


def _remote(cwd: str, push: bool = False) -> list:
    "[(host, owner/name)] of origin's URLs, insteadOf rewrites applied by git itself - every push URL when `push`, else only a code host's."
    if not cwd: return []
    from . import spawn
    try: out = spawn.run(['git', '-C', cwd, 'remote', 'get-url', *(['--push', '--all'] if push else []), 'origin'], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError): return []
    urls = [u.strip() for u in str(out or '').splitlines() if u.strip()]
    return [host_repo(u) for u in urls if push or 'github' in u or 'gitlab' in u]       # a push's every URL counts: the card's host decides


def card_host(card: dict) -> str:
    "The host a code-host card reaches: github.com, or a GitLab card's own instance (gitlab.com unless its base_url says otherwise)."
    if str(card.get('Type') or '').lower() != 'gitlab': return 'github.com'
    try: base = str((json.loads(card.get('ConfigJson') or '{}') or {}).get('base_url') or '')
    except (TypeError, ValueError): base = ''
    return (host_repo((base or 'https://gitlab.com').rstrip('/') + '/x/y')[0]) or 'gitlab.com'


HOSTS = {'github.com', 'gitlab.com'}


def folder(cwd: str, to: str) -> str:
    "The folder a step runs in: `cwd`, or the one its `git -C` names ('@<folder>', _to) read against it."
    return os.path.normpath(os.path.join(cwd, _path(str(to)[1:]))) if str(to).startswith('@') and cwd else cwd


def trusted(store, cwd: str, todo: list) -> str:
    "The repo whose card's Authority covers every step in `todo` - '' when any step is not covered."
    from . import scopes
    # ...an unset Authority is what the card SHOWS it to be (scopes.scope_of: full) - read here as 'read', every push of the owner's live task on
    # a card he left at its default was a card of its own (2026-11-19). One reading of a card's Authority, the same as every tool call's
    level = lambda c: RANK.get(scopes.scope_of(c or {}), 0)
    # ...asked of git only when some code-host card trusts its repos at all: a command on a machine with none never runs `git remote`
    srcs = [s for s in store.list_sources(active_only=False) if s.get('Channel') in ('github', 'gitlab') and s.get('ConnectorId')]
    if not any(level(store.get_connector(s['ConnectorId'])) >= 1 for s in srcs): return ''
    if any(a.get('why') != OUT for a in todo): return ''
    # ...WHERE A PUSH GOES, not what the fetch URL says: origin's push URLs, every one of them on the card's own host. An origin that only
    # mentions a code host (`https://evil.example/github/northwind/ledger.git`) or a pushurl set apart from it is not that repository
    got = set(_remote(cwd, push=True))
    if len(got) != 1: return ''
    host, repo = got.pop()
    src = next((s for s in srcs if str(s.get('Address') or '').lower() == repo.lower()), None)
    card = store.get_connector(src['ConnectorId']) if src else None
    if not card or host not in (card_host(card), 'ssh.' + card_host(card)): return ''
    lv = level(card)
    ok = ADMIN_OK if lv >= 2 else WRITE_OK if lv >= 1 else set()
    def same(to):
        to = str(to if to is not None else '?')
        if to.startswith('@'): return set(_remote(folder(cwd, to), push=True)) == {(host, repo)}
        return to.lower() in ('', repo.lower())
    return repo if all(a.get('what') in ok and same(a.get('to', '?')) for a in todo) else ''


def check(store, tid: int, sid: str, cmd: str, shell: str = 'Bash', cwd: str = '', ask: bool | str = False, about: str = '', reads: list = (),
          argv: list = None) -> dict:
    """The hook's answer for one shell command: {} lets it run; `ask` (asks) hands it to the CLI's own prompt (never an allow); else a
    refusal holds it and puts the step on the task. ONE step holds the whole command - the line is the agent's, and half of it is not what it asked.
    `about`: the agent's own words for the call (a CLI's shell tool takes a `description`) - the card leads with them (the owner, 2026-11-09)
    `reads`: what it reads outside its work (readgate.judge) - held on the same card; Approve also lets the task read those folders.
    `argv`: the call as the brain's own tool made it, where it gave a list (Codex) - replayed as it is on Approve (replay)."""
    todo = (acts(cmd, cwd) if cmd else []) + list(reads or [])
    if not todo: return {}
    from . import gate
    # ...THE ONE RULE FIRST (gate.decide): a repo he trusts, or the same step he already approved on this task, runs; one he dismissed is his no
    how, said = gate.decide(store, tid, todo, cwd)
    if how in ('trusted', 'approved'):
        store.audit('task', tid, f'shell_act_{how}', 'taskuary', 'system', {'tools': [a['tool'] for a in todo], 'what': '; '.join(a['what'] for a in todo)})
        if said: store.add_comment_once(tid, 'taskuary', 'agent', said)
        return {}
    if how == 'dismissed': return _deny(said)
    what, why = ('; '.join(dict.fromkeys(a[k] for a in todo)) for k in ('what', 'why'))
    if ask:
        store.audit('task', tid, 'shell_act_asked', 'taskuary', 'system', {'tools': [a['tool'] for a in todo], 'what': what})
        # ...said only where a terminal does ask (agent walk 2, 2026-11-10: the line stood on a task whose agent has no terminal, over a
        # push its own gate had already answered with the landing card)
        if ask != 'chat': store.add_comment_once(tid, 'taskuary', 'agent', f"The agent asked to {what}" + (f": `{str(cmd)[:300]}`" if cmd else '') + " - its terminal asks you to allow it.")
        return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'ask',
                                       'permissionDecisionReason': f'Taskuary asks you first: {what} ({why}).'}}
    from . import landing
    if cmd and (lands := landing.push_asked(store, tid, cmd, cwd, about)): return _deny(lands[1])      # the landing card's own button, never a second card
    folders = [a['folder'] for a in reads or [] if a.get('folder')]
    # ...ONE CARD FOR ONE CALL, EVEN WHEN TWO GATES HEAR IT AT ONCE (recorded on the real CLI, 2026-11-16: the hook and the ACP gate held the
    # same command in the same millisecond, and the card read "2 steps" and ran it twice): the look and the filing are one step
    with _FILING:
        if not _pending(store, tid, sid, cmd, folders):
            from . import proposals
            proposals.queue(store, tid, {'action': 'shell_act', 'sid': str(sid), 'turn': turn_of(store, tid), 'command': str(cmd)[:4000], 'shell': shell, 'cwd': cwd or '',
                                         # the card's In: the folder a delete aims at, never the agent's own scratch folder it ran from
                                         # ...a push named by its repo and branch, in his words (gate.words), and what his answer is remembered by
                                         'what': '; '.join(dict.fromkeys(gate.words(a, cwd) for a in todo)), 'why': why,
                                         'where': next((a['where'] for a in todo if a.get('where')), ''), 'keys': gate.keys(todo, cwd),
                                         **({'argv': [str(x) for x in argv]} if argv else {}),
                                         **({'reads': folders} if folders else {}),
                                         **({'about': ' '.join(str(about).split())[:300]} if str(about or '').strip() else {})}, 'agent')
            store.audit('task', tid, 'shell_act_held', 'taskuary', 'system', {'tools': [a['tool'] for a in todo], 'what': what})
    from .selfclose import CARD_TAIL
    then = ('Taskuary runs this exact command in the same folder and tells you what happened' if cmd else
            'the folder is yours to read for the rest of this task and you are told to go on')
    return _deny(f"{HELD}: {what} ({why}). Once they press it, {then}. {CARD_TAIL}")


def turn_of(store, tid) -> int:
    """WHICH TURN HELD IT (the owner, 2026-11-09: "this should be one action button and one card"): the owner's last line on the task. Steps
    held under the same line are one action - one card, one Approve; a step held after the owner wrote again is a new card."""
    from .general import USER_TYPE
    return max((c['CommentId'] for c in store.list_comments(tid, internal=True) if c.get('ActorType') == USER_TYPE), default=0)


def git_bash() -> str:
    """The bash an agent's Bash tool runs on Windows: Git's, beside git.exe. NEVER System32's bash.exe - WSL's launcher, which on a box
    with no distribution answered an approved push with "no distribution installed", in UTF-16 (2026-10-29). '' when none is found.
    Off Windows it is the system's own bash, else sh - there is no Git Bash to look for there."""
    if os.name != 'nt': return shutil.which('bash') or shutil.which('sh') or next((c for c in ('/bin/bash', '/bin/sh') if os.path.isfile(c)), '')
    P = ntpath                                  # Windows paths, read as Windows paths whatever runs this
    cands, g = [os.environ.get('CLAUDE_CODE_GIT_BASH_PATH') or ''], shutil.which('git')     # Claude Code's own setting for that bash first
    if g:                                       # git.exe sits in <Git>\cmd, <Git>\bin or <Git>\mingw64\bin
        d = P.dirname(P.abspath(g))
        cands += [P.join(r, *b) for r in (P.dirname(d), P.dirname(P.dirname(d))) for b in (('bin', 'bash.exe'), ('usr', 'bin', 'bash.exe'))]
    cands += [P.join(os.environ[v], *b) for v in ('ProgramFiles', 'ProgramW6432', 'LOCALAPPDATA') if os.environ.get(v)
              for b in (('Git', 'bin', 'bash.exe'), ('Programs', 'Git', 'bin', 'bash.exe'))]
    w, sysroot = shutil.which('bash') or '', P.normcase(os.environ.get('SystemRoot') or r'C:\Windows')
    if w and not P.normcase(P.abspath(w)).startswith(sysroot) and 'windowsapps' not in w.lower(): cands.append(w)
    return next((c for c in cands if c and os.path.isfile(c)), '')


def _shell_exe(shell: str) -> str:
    "The program for a shell by its name: PowerShell (pwsh before Windows' own), cmd, else Git Bash (the system bash off Windows)."
    n = _name(shell)
    if n in ('powershell', 'pwsh'):
        # ...Windows' own, where it always is, when the PATH this app was started with names neither (the recorded walk, 2026-11-11: the
        # approved step answered "[WinError 2] The system cannot find the file specified" - the shell, not the file it was to delete)
        own = ntpath.join(os.environ.get('SystemRoot') or r'C:\Windows', 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
        return (shutil.which('pwsh') if n == 'pwsh' else None) or shutil.which('powershell') or shutil.which('pwsh') or (own if os.path.isfile(own) else 'powershell')
    if n == 'cmd': return shutil.which('cmd') or 'cmd'
    b = git_bash()
    if not b: raise RuntimeError('The held step was not run: ' + ('no Git Bash (the bash beside git.exe)' if os.name == 'nt' else 'no bash or sh')
                                 + ' was found to run it in - nothing was done')
    return b


_FLAG = {'powershell': ('-command', '-c'), 'pwsh': ('-command', '-c'), 'bash': ('-c', '-lc'), 'sh': ('-c',), 'zsh': ('-c', '-lc'), 'cmd': ('/c',)}
_LAUNCH = re.compile(r"""^\s*&?\s*("[^"]+"|'[^']+'|\S+)\s+(.*)$""", re.S)


def _exe(tok: str) -> str:
    "A launcher's program as written: its quotes off, and a path printed with doubled backslashes (`C:\\WINDOWS`) as a path."
    t = tok[1:-1] if tok[:1] in ('"', "'") and tok[-1:] == tok[:1] else tok
    return t.replace('\\\\', '\\')


def unwrap(cmd: str) -> tuple:
    """(argv, script) when the line IS a shell started on a script of its own - how Codex reports every call it runs, its argv joined by
    POSIX quoting (`"<Windows folder>\\powershell.exe" -Command '$out = "C:'"\\Users\\..."'`) - else (None, the line). The argv is read back by
    that same grammar, so the script is exactly what ran: unquoted by hand, a script whose quoting switched mid-word came back broken and
    every Approve of it failed in PowerShell's parser (the HIPAA walk, 2026-11-21)."""
    cmd = str(cmd or '')
    m = _LAUNCH.match(cmd)
    if not m or not (flags := _FLAG.get(_name(_exe(m.group(1))))): return None, cmd
    try: rest = shlex.split(m.group(2), posix=True)
    except ValueError: return None, cmd
    for i, w in enumerate(rest):
        if w.lower() in flags: return ([_exe(m.group(1)), *rest[:i + 1], ' '.join(rest[i + 1:])], ' '.join(rest[i + 1:])) if i + 1 < len(rest) else (None, cmd)
        if not w.startswith(('-', '/')): return None, cmd
    return None, cmd


def _launcher(cmd: str) -> list | None:
    """[program, *its options, flag, the inner line] when the held line IS a shell started on a line of its own (unwrap) - else None. Wrapped
    again in the shell it was recorded under, PowerShell read the quoted program and its `-Command` as one expression and every Approve failed
    "At line:1 char:66" (the owner's live task, 2026-11-19)."""
    a = unwrap(cmd)[0]
    if not a: return None
    return [a[0] if os.path.isabs(a[0]) and os.path.isfile(a[0]) else _shell_exe(a[0]), *a[1:]]


# ...AND IN UTF-8 (the owner, 2026-11-25): Windows PowerShell 5.1 reads a child's output in the console's code page, pipes its own strings out
# as ASCII and writes a file in UTF-16 - a Python's "a – b" sent to a file came back "a ΓÇô b", and "c — d" piped on as "c ? d"
PS_UTF8 = ("$OutputEncoding=[Console]::InputEncoding=[Console]::OutputEncoding=New-Object Text.UTF8Encoding $false;"
           "'Out-File','Set-Content','Add-Content'|%{$PSDefaultParameterValues[\"$($_):Encoding\"]='utf8'};")
# A BARE @ref ON A POWERSHELL LINE IS A SPLAT OF A VARIABLE NOBODY SET, AND EXPANDS TO NOTHING (walk 24's re-run, 2026-11-26, HIPAA AI: `agent-browser
# fill @e4 "..."` ran as `fill "..."` and `click @e6` as a bare `click` - the tool said Done, the post box stayed empty, and the agent told him
# the words were in). The guide asks every agent to quote one; on the lines Taskuary itself runs it is code: a word `@name` outside quotes,
# whose `$name` the line never sets, is passed as the word it is
_SPLAT = re.compile(r"(?<![\w'\"`$@.-])@([A-Za-z_]\w*)(?![\w({'\"])")
def no_splat(cmd: str) -> str:
    from .readgate import _quoted
    qs = _quoted(cmd)
    return _SPLAT.sub(lambda m: m[0] if any(a <= m.start() < b for a, b in qs) or re.search(r'\$' + m[1] + r'\s*=', cmd, re.I) else f"'{m[0]}'", cmd)


def replay(p: dict) -> list:
    """THE HELD CALL AS THE AGENT'S OWN TOOL WOULD HAVE RUN IT - the one road an Approve runs by: the argv its brain gave (Codex's list), a line
    that is itself a shell started on a line (`powershell.exe -Command '...'`, `bash -lc '...'`) as that shell, else the line in the shell its tool
    is: the PowerShell tool in PowerShell, the Bash tool in Git Bash (the system bash off Windows)."""
    if (a := p.get('argv')) and isinstance(a, list) and len(a) > 1:
        a = [str(x) for x in a]
        return [a[0] if os.path.isabs(a[0]) and os.path.isfile(a[0]) else _shell_exe(a[0]) if _name(a[0]) in _FLAG else (shutil.which(a[0]) or a[0]), *a[1:]]
    cmd, shell = str(p.get('command') or ''), str(p.get('shell') or 'Bash')
    if (l := _launcher(cmd)): return l
    if _name(shell) in ('powershell', 'pwsh'): return [_shell_exe(shell), '-NoProfile', '-NonInteractive', '-Command', PS_UTF8 + no_splat(cmd)]
    return [_shell_exe('bash'), '-c', cmd]


def _argv(shell: str, cmd: str) -> list: return replay({'shell': shell, 'command': cmd})


def run_(p: dict, cwd: str = '', timeout: int = 300) -> tuple:
    """THE ONE EXECUTOR FOR A STEP TAKEN ON HIS PRESS (the roads audit, 2026-11-19 #8): the call as the agent's own tool would have run it
    (replay), in its folder, no input, its output read as words (text) -> (exit code, what it said). A held shell step's Approve and the
    landing card's Push / Open a PR (landing._push, _pr) both run through it, so a push he pressed meets the git, the credentials and the
    shell the agent's own `git push` would have - never a second git of Taskuary's own PATH."""
    from . import spawn
    r = spawn.run(replay(p), cwd=cwd or None, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)   # bytes: text() reads them
    return r.returncode, text(r.stdout) + text(r.stderr)


def text(raw) -> str:
    """A child's output as words: UTF-16 when its bytes say so (a byte-order mark, or NULs in every other place - wsl.exe writes it),
    else UTF-8 with whatever does not decode replaced. Read as UTF-8, WSL's sentence reached the owner as r\\0i\\0b\\0u\\0t\\0i\\0o\\0n."""
    if raw is None or isinstance(raw, str): return raw or ''
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'): return raw.decode('utf-16', errors='replace')
    odd, even = raw[1::2].count(0), raw[::2].count(0)
    if len(raw) >= 4 and odd * 2 >= len(raw) // 2 and odd > even: return raw.decode('utf-16-le', errors='replace')
    return raw.decode('utf-8', errors='replace')


# ...ONE LINE THAT SAYS WHY, never git's list of files (the owner, 2026-11-10: "no idea what this is" over "U site/demo/assets/...js / U ...").
# By the tools' own grammar, not by meaning: a status entry, a commit line or a bare path is not a reason, and git, gh and WSL put theirs on
# an `error:` / `fatal:` line; else its first line, where WSL says it
# ...AND AS IT ENDED, NEVER GUESSED (walk 20: an approved API post went out, printed the site's {"ok":true}, exited 6 on a stray word, and the
# card read "failed: {"ok":true}"): a tool's own error line is its failure; any other end is its exit code and what it printed
def failed(said: str, rc: int, what: str = '') -> str:
    "What the owner reads when the held step ended badly: the step in his words, and the tool's error line - else its exit code and output."
    from . import say
    why, step = say.reason(said), str(what or 'the held step').split(';')[0].strip()
    step = step[:1].upper() + step[1:]
    return f"{step} failed: {why or f'exit {rc}'}" if not why or not rc or say._SAYS_WHY.match(why) else f"{step} exited with code {rc}: {why}"


# THE OWNER'S PRESS NEVER RACES THE AGENT IN ITS OWN FOLDER (the owner, 2026-11-10: "no idea what this is. it's broken"): a second Approve
# re-ran a failed push while the agent was mid-merge in that checkout, and it failed again. A step its own agent's turn is still working
# beside waits for that turn to end - said in words, nothing run
BUSY = 'The agent is working in that folder right now, so nothing was run - press it again once its turn has ended.'
def mid_turn(store, tid: int, sid: str) -> str:
    "BUSY while the agent session that held a step is in a turn, else ''."
    from . import terminal as term, workerstate as ws
    s = term.SESSIONS.get(str(sid or ''))
    if s is None or not getattr(s, 'alive', False): return ''
    st = ws.status(store, tid)
    return BUSY if getattr(s, 'busy', False) or (str(st.get('sid')) == str(sid) and st.get('state') == 'working') else ''


_FAILED_LINE = re.compile(r'^\s*(?:error|fatal):|^\s*! \[(?:rejected|remote rejected)\]', re.M)


def perform(store, tid: int, p: dict, run=None) -> dict:
    """The owner's yes: run the held command, as it was, in the folder it was held in. `run`: the runner (tests stand one in)."""
    cmd, cwd = str(p.get('command') or ''), str(p.get('cwd') or '')
    from . import readgate
    readgate.grant(store, tid, p.get('reads'))
    if not cmd and p.get('reads'):
        v = 'write' if str(p.get('what') or '').startswith('write') else 'read'        # ...what his yes let it do, as the card said it (readgate._said, settings)
        said = f"The owner let you {v} {', '.join(p['reads'])} for the rest of this task. {v.title()} what you needed there now. " + NEXT
        if (told := _batch.get()) is not None: told.append(p.get('what') or 'a read')
        else: _tell(store, tid, said, wake=True)
        store.audit('task', tid, 'shell_act_done', 'owner', 'human', {'what': p.get('what'), 'reads': p['reads']})
        return {'performed': p.get('what') or 'a read', 'said': ''}
    if not cmd: raise RuntimeError('this held step names no command')
    if cwd and not os.path.isdir(cwd): raise RuntimeError(f'the folder it was held in is gone ({cwd}) - nothing was done')
    from . import gate
    gate.remember(store, tid, p.get('keys'), 'approved')       # his yes to this kind of step on this target stands for the task
    rc, said = run_(p, cwd) if run is None else run(replay(p), cwd)
    # ...A STEP IS AS IT ENDED, NOT AS ITS LAST PIPE DID (the Claude walk, 2026-11-19: a push piped through `| tail` exited 0 and its card read
    # "Approved · it ran" with the refused push's address under it): a tool's own failure line - git's `error:` / `fatal:`, its "! [rejected]" -
    # in what it printed is a failure, read off that grammar
    if rc != 0 or _FAILED_LINE.search(str(said or '')):
        store.audit('task', tid, 'shell_act_failed', 'owner', 'human', {'what': p.get('what'), 'command': cmd[:300], 'said': str(said or '')[-1500:]})
        raise RuntimeError(failed(said, rc, p.get('what')))
    said = ' '.join(str(said or '').split())[-600:]
    if (told := _batch.get()) is not None: told.append(f"`{cmd[:300]}` said: {said[-200:] or 'done'}")
    else: _tell(store, tid, f"The owner approved it and Taskuary ran `{cmd[:300]}` in {cwd or 'its folder'}. It said: {said[-300:] or 'done'}. "
                    + NEXT, wake=True)
    store.audit('task', tid, 'shell_act_done', 'owner', 'human', {'what': p.get('what'), 'about': p.get('about'), 'command': cmd[:300], 'said': said[-300:]})
    return {'performed': p.get('what') or cmd[:200], 'said': said[-300:]}


FAILED, NOT_RUN = 'it failed - the agent was told and goes on from there', 'not run - a step before it failed'
# ONE APPROVE FOR A TURN'S HELD STEPS (approve_steps): each step is approved through the one decide door, in order; the agent hears once, at the end
_batch = contextvars.ContextVar('shellgate_batch', default=None)

def approve_steps(store, rids: list, decide, actor: str = 'owner', verb: str = 'approve') -> dict:
    """The owner's one Approve on a held-steps card: each review, in the order given, through `decide` (verdicts.decide - the same checks a
    single Approve gets: pending, re-validated, run by perform). Stops at the first that does not go and says which; the rest stay waiting.
    `verb` 'reject': the card's one Dismiss - every step dismissed, the agent told once."""
    from .timewords import plural
    rvs = [store.get_review(int(r)) for r in rids]
    if not rvs or any(not r or r.get('Kind') != 'action' or json.loads(r.get('DraftText') or '{}').get('action') != 'shell_act' for r in rvs):
        raise ValueError('only held shell steps are approved together')
    if len({r.get('TaskId') for r in rvs}) != 1: raise ValueError('held steps of one task only')
    tid, told, done, failed, refused, busy = rvs[0]['TaskId'], [], [], None, '', ''
    tok = _batch.set(told)
    try:
        for i, rv in enumerate(rvs):
            out = decide(store, rv, verb, actor=actor)
            # ...A STEP REFUSED BEFORE IT RAN DID NOT FAIL (the held-steps round, 2026-11-18): a second press of an answered card - a double
            # click, a page or phone that had not read the first - woke the agent with "step 1 failed: this one was already approved". Only a
            # step that ran and failed (its act's own error) is a failure; a refusal stops the card, leaves every step as it stands, tells nobody
            # ...and one its agent's turn is working beside (mid_turn, said by the decide door) waits, lit, for the press it asks for
            if not out.get('ok') and not out.get('act_failed'): refused, busy = out.get('send_error') or 'it was answered already', out.get('busy') or ''; break
            if not out.get('ok'): failed = {'review': rv['ReviewId'], 'step': i + 1, 'error': out.get('send_error') or 'it did not run'}; break
            done.append({'review': rv['ReviewId'], 'result': out.get('result')})
    finally: _batch.reset(tok)
    left = [r['ReviewId'] for r in rvs[len(done) + (1 if failed else 0):]]
    if refused and not done: return {'ok': False, **({'busy': busy} if busy else {'already': True}), 'send_error': refused, 'done': [], 'failed': None, 'left': left}
    ran = '; '.join(told) or 'nothing ran'
    if verb != 'approve': _tell(store, tid, f"The owner dismissed {plural(len(done), 'held step')}: {ran} - NOT done. {OWNER_NO}")
    elif failed:
        # ...A STEP THAT FAILED IS OVER, AND THE AGENT'S (the owner, 2026-11-10: "no idea what this is. it's broken"): the card read "1 of 2 ran -
        # the rest wait" with Approve still lit under the failure, and the agent - told they still waited - worked the failure while the owner's
        # next press ran the same step into it again. The card is now its record: the failed step and those after it settled, never pressable;
        # the agent is started on what failed, and what it holds next is a new card in its new turn
        for r in [failed['review'], *left]: store.decide_review(r, 'superseded', None, 'taskuary', FAILED if r == failed['review'] else NOT_RUN)
        _tell(store, tid, f"The owner approved {len(rvs)} held steps together. Taskuary ran {len(done)} of them ({ran}); step {failed['step']} "
                          f"failed: {failed['error'][:300]}" + (f"\n\nWhat it printed:\n{raw}\n\n" if (raw := _printed(store, tid)) else '. ') + "Nothing on that card waits on the owner now - the steps after it were not run. Find out "
                          "why and put it right if you can; a step still needed is run again by you and held as a new card for their press. " + NEXT,
              wake=True)
    else: _tell(store, tid, f"The owner approved {plural(len(done), 'held step')} together and Taskuary ran them in order: {ran}. " + NEXT, wake=True)
    return {'ok': not (failed or refused), 'done': done, 'failed': failed, 'left': left, **({'send_error': refused} if refused else {})}


def _printed(store, tid: int) -> str:
    "What the last held step that failed on this task printed, whole - the agent's to read; the owner's card says it in one line (failed)."
    r = store._one("SELECT Detail FROM audit WHERE EntityType='task' AND EntityId IN (?,?) AND Action='shell_act_failed' ORDER BY Id DESC LIMIT 1", (int(tid), str(tid)))
    try: return str(json.loads((r or {}).get('Detail') or '{}').get('said') or '').strip()[-1500:]
    except (TypeError, ValueError): return ''


def declined(store, tid: int, p: dict) -> None:
    from . import gate
    gate.remember(store, tid, p.get('keys'), 'dismissed')
    if (told := _batch.get()) is not None: return told.append(f"{p.get('what') or 'the step'} (`{str(p.get('command') or '')[:200]}`)")
    _tell(store, tid, not_approved(f"{p.get('what') or 'the step'} (`{str(p.get('command') or '')[:200]}`)"))
