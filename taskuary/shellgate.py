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
import contextvars, json, ntpath, os, re, shlex, shutil, subprocess, tempfile
from loguru import logger
from .browsergate import _segments, _deny, _tell, not_approved, NEXT, OWNER_NO

HELD = 'Taskuary held this for the owner'
# ...said to the agent the hold covers, as the browser's hold is (browserview.HOLD_LINE): told nothing, a general agent asked "Should I delete
# it?" in words, the owner said yes, and the delete was held for a second yes on the task (the overnight run, 2026-11-03)
HOLD_LINE = ("A DELETE ON THE OWNER'S COMPUTER outside your working folder, and a step that leaves the machine (a push, a merge, a publish, "
             "a mail from a script, data sent to a web address), is HELD for the owner's press: Taskuary refuses it with \"held for the owner\", "
             "puts it on the task, runs it once they approve and tells you what happened. So never ask the owner in words whether to delete - "
             "run the command, end your turn when it is held, and say in one line what waits for their Approve. The held step IS the owner's "
             "button: never ask \"will you run these\", never print the commands for them to copy. Draft no reply that says it is done while it waits: the reply is "
             "written once Taskuary tells you the step ran.")
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
HTTP = {'curl', 'wget', 'http', 'https', 'xh', 'invoke-webrequest', 'iwr', 'invoke-restmethod', 'irm'}
# curl's short flags are case-sensitive (-F is a form post, -f is --fail); the long ones and PowerShell's -Body / -InFile are not
_SHORT = ('-d', '-F', '-T')
_DATA = ('--data', '--data-raw', '--data-binary', '--data-urlencode', '--json', '--form', '--upload-file', '-body', '-infile',
         '--post-data', '--post-file', '--body-data', '--body-file')
_LOCAL = re.compile(r'^https?://(localhost|127\.\d+\.\d+\.\d+|\[::1\])(:\d+)?(/|$)', re.I)
_PREFIX = ('&', 'npx', 'command', 'call', 'exec', 'sudo', 'time', 'nohup')


def _name(tok: str) -> str:
    import re
    return re.sub(r'\.(exe|cmd|ps1|bat)$', '', os.path.basename(str(tok).replace('\\', '/')).lower())


def _words(argv: list) -> tuple:
    """(tool, its words with every option and an option's value taken out) of one simple command, through env prefixes and the like."""
    import re
    i = 0
    while i < len(argv) and re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', argv[i]): i += 1
    while i < len(argv) and argv[i].lower() in _PREFIX: i += 1
    if i >= len(argv): return '', []
    tool, rest, out, j = _name(argv[i]), argv[i + 1:], [], 0
    # git's own options before the subcommand that take a value (`git -C repo push`, `git -c k=v push`)
    while tool == 'git' and j < len(rest) and rest[j].startswith('-'): j += 2 if rest[j] in ('-C', '-c', '--git-dir', '--work-tree', '--namespace') else 1
    for t in rest[j:]:
        if not t.startswith('-'): out.append(t)
    return tool, out


def _http_write(argv: list) -> str:
    "'' unless this HTTP client writes to a host off this machine - then what it does, in words. Taskuary's own API answers its own guard."
    a = [str(t) for t in argv[1:]]
    urls = [t for t in a if re.match(r'^https?://', t, re.I)]
    if urls and all(_LOCAL.match(u) for u in urls): return ''
    meth = next((a[i + 1] for i, t in enumerate(a[:-1]) if t.lower() in ('-x', '--request', '-method')), '')
    meth = meth or next((t[2:] for t in a if t.startswith('-X') and len(t) > 2), '')
    data = any(t in _SHORT or t.lower().split('=', 1)[0] in _DATA or (t.startswith('-d') and not t.startswith('--') and len(t) > 2) for t in a)
    if meth.lower() not in _WRITES and not data: return ''
    host = re.sub(r'^https?://([^/?#]+).*', r'\1', urls[0]) if urls else 'a web address'
    return f'send data to {host} ({_name(argv[0])})'


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
UNDONE = "it can't be undone"
OUT = 'it leaves this computer'
# the calls that delete from a snippet or a PowerShell line, whatever runs them: .NET, Python, Node
_API_DEL = re.compile(r'\[(?:system\.)?io\.(?:file|directory)\]::delete\b|shutil\.rmtree\b|\bos\.(?:remove|unlink|rmdir|removedirs)\b'
                      r'|\bfs\.(?:rm|rmdir|unlink)(?:sync)?\b|\.delete\(\s*(?:\$true)?\s*\)|\.unlink\(\s*(?:missing_ok\s*=\s*true)?\s*\)', re.I)
_DEL_WORDS = ('rm', 'del', 'erase', 'remove', 'unlink', 'shred', 'rd', 'rmtree')
_VAR = re.compile(r'\$(?:env:)?(\w+)|%(\w+)%', re.I)
_SPLIT = re.compile(r'\r?\n|;|&&|\|\||\||\{|\}')
_VALUED_DEL = frozenset('-erroraction -ea -filter -include -exclude -depth -credential -stream -warningaction -wa'.split())


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
    return [{'tool': found['tools'][0], 'what': what, 'why': UNDONE, 'where': (found['places'] or [''])[0], 'command': raw[:400]}]


def _deletes(raw: str, cwd: str, env: dict, here='') -> dict:
    # `here`: the folder the line has moved to - `cd ~/Downloads && rm -rf notes` deletes in Downloads, not in the agent's own folder
    # (the stress test's second delete, 2026-11-03). '' is the agent's own folder; None a `cd` it could not read
    named, places, blind, tools = [], [], False, []
    done = lambda: {'named': named, 'places': places, 'blind': blind, 'tools': tools, 'here': here}
    if not any(w in raw.lower() for w in _DEL_WORDS + ('cd', 'location')): return done()             # the cheap test first
    raw = re.sub(r'\$\{(\w+(?::\w+)?)\}', r'$\1', raw)                         # ${dst} is $dst - and its braces are not a block
    for seg in _SPLIT.split(raw):
        seg = seg.strip()
        if not seg: continue
        if (m := re.match(r'^\$?([A-Za-z_]\w*)\s*=\s*(\S.*)$', seg)) and not m.group(2).startswith('='):
            try: v = shlex.split(m.group(2), posix=False)
            except ValueError: v = []
            if len(v) == 1: env[m.group(1).lower()] = _expand(v[0].strip('"\''), env)
            continue
        try: w = [x.strip('"\'') for x in shlex.split(seg, posix=False)]
        except ValueError: w = [x.strip('"\'') for x in seg.split()]      # a quote the split cut in two (`cmd /c "cd X && rd Y"`)
        while w and (w[0].lower() in _PREFIX or w[0].lower() in ('if', 'else', 'elseif', 'then', 'do')): w = w[1:]
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


def _outward(cmd: str) -> list:
    """Every step in a shell command that goes out: [{'tool', 'what', 'why', 'command'}]. A command that cannot be read and names one of
    these tools is one step - held, never let through for being hard to read."""
    raw = str(cmd or '')
    low = raw.lower()
    if not any(w in low for w in ('git', 'gh', 'glab', 'publish', 'push', 'upload', 'mail', 'mutt', 'msmtp', 'http', 'curl', 'wget', 'xh', 'iwr', 'irm',
                                  'invoke-')): return []      # the cheap test first
    segs = _segments(raw)
    if segs is None:
        import re
        return [{'tool': '?', 'what': 'run a command that may push, publish or send', 'why': OUT, 'command': raw[:400]}] if re.search(
            r'\b(git\s+push|gh\s+(pr|issue|release|repo|api)|glab|publish|sendmail|send-mailmessage)\b', low) else []
    out = []
    for argv in segs:
        tool, w = _words(argv)
        if tool in ('bash', 'sh', 'powershell', 'pwsh', 'cmd'):                 # `bash -c "git push"`: the string is a command of its own
            for t in argv[1:]:
                if ' ' in t.strip(): out += _outward(t)
            continue
        what = (GIT.get(w[0]) if tool == 'git' and w else
                GH.get(tuple(w[:2])) if tool == 'gh' else GLAB.get(tuple(w[:2])) if tool == 'glab' else
                'publish a package' if (tool in PUBLISH and w[:1] in (['publish'], ['push'])) or (tool == 'twine' and w[:1] == ['upload'])
                or (tool == 'docker' and w[:1] == ['push']) else MAIL.get(tool))
        if not what and tool in ('gh', 'glab') and w[:1] == ['api'] and _api_writes(argv): what = 'change something on the code host through its API'
        if not what and tool == 'git' and w[:1] == ['push']: what = GIT['push']
        if not what and tool in HTTP: what = _http_write(argv)
        if what: out.append({'tool': tool, 'what': what, 'why': OUT, 'command': ' '.join(argv)[:400]})
    return out


def _pending(store, tid: int, sid: str, cmd: str):
    for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (tid,)):
        try: p = json.loads(r.get('DraftText') or '{}')
        except ValueError: continue
        if p.get('action') == 'shell_act' and p.get('sid') == str(sid) and p.get('command') == cmd: return r
    return None


def asks(store, t) -> str:
    """WHERE the owner answers this session's own permission prompt - '' where nobody can. Only a CLI pane of ours (argv: a terminal, not a
    headless chat), started 'full' (a stranger's task runs 'auto' and its permit door is the owner's), whose CLI's hook answers `ask`, on a
    task that is not a workflow's run (nobody sits at a scheduled run's pane). Everything else is held for the task's Approve.
    'terminal': the CLI's own prompt in its pane. 'chat': the same CLI over ACP has no terminal - its ask comes back to Taskuary's own
    gate (acpgate.answerer), which draws the landing card, the owner's buttons or the Approve card itself."""
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
    if not cwd: return ''
    from . import spawn
    try: url = spawn.run(['git', '-C', cwd, 'remote', 'get-url', 'origin'], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError): return ''
    m = re.search(r'[:/]([^/:]+/[^/]+?)(?:\.git)?/?$', url)
    return m.group(1) if m and ('github' in url or 'gitlab' in url) else ''


def trusted(store, cwd: str, todo: list) -> str:
    "The repo whose card's Authority covers every step in `todo` - '' when any step is not covered."
    # ...asked of git only when some code-host card trusts its repos at all: a command on a machine with none never runs `git remote`
    srcs = [s for s in store.list_sources(active_only=False) if s.get('Channel') in ('github', 'gitlab') and s.get('ConnectorId')]
    if not any(RANK.get(str((store.get_connector(s['ConnectorId']) or {}).get('Scope') or 'read').lower(), 0) >= 1 for s in srcs): return ''
    repo = repo_of(cwd)
    if not repo: return ''
    src = next((s for s in srcs if str(s.get('Address') or '').lower() == repo.lower()), None)
    card = store.get_connector(src['ConnectorId']) if src else None
    if not card: return ''
    level = RANK.get(str(card.get('Scope') or card.get('ScopeDefault') or 'read').lower(), 0)
    ok = ADMIN_OK if level >= 2 else WRITE_OK if level >= 1 else set()
    return repo if all(a.get('what') in ok and a.get('why') == OUT for a in todo) else ''


def check(store, tid: int, sid: str, cmd: str, shell: str = 'Bash', cwd: str = '', ask: bool | str = False, about: str = '') -> dict:
    """The hook's answer for one shell command: {} lets it run; `ask` (asks) hands it to the CLI's own prompt (never an allow); else a
    refusal holds it and puts the step on the task. ONE step holds the whole command - the line is the agent's, and half of it is not what it asked.
    `about`: the agent's own words for the call (a CLI's shell tool takes a `description`) - the card leads with them (the owner, 2026-11-09)"""
    todo = acts(cmd, cwd)
    if not todo: return {}
    what, why = ('; '.join(dict.fromkeys(a[k] for a in todo)) for k in ('what', 'why'))
    if (repo := trusted(store, cwd, todo)):
        store.audit('task', tid, 'shell_act_trusted', 'taskuary', 'system', {'tools': [a['tool'] for a in todo], 'what': what, 'repo': repo})
        store.add_comment_once(tid, 'taskuary', 'agent', f"The agent went on to {what} on {repo} - a repo you trust to act on its own.")
        return {}
    if ask:
        store.audit('task', tid, 'shell_act_asked', 'taskuary', 'system', {'tools': [a['tool'] for a in todo], 'what': what})
        # ...said only where a terminal does ask (agent walk 2, 2026-11-10: the line stood on a task whose agent has no terminal, over a
        # push its own gate had already answered with the landing card)
        if ask != 'chat': store.add_comment_once(tid, 'taskuary', 'agent', f"The agent asked to {what}: `{str(cmd)[:300]}` - its terminal asks you to allow it.")
        return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'ask',
                                       'permissionDecisionReason': f'Taskuary asks you first: {what} ({why}).'}}
    from . import landing
    if (lands := landing.push_asked(store, tid, cmd, cwd, about)): return _deny(lands[1])      # the landing card's own button, never a second card
    if not _pending(store, tid, sid, cmd):
        from . import proposals
        proposals.queue(store, tid, {'action': 'shell_act', 'sid': str(sid), 'turn': turn_of(store, tid), 'command': str(cmd)[:4000], 'shell': shell, 'cwd': cwd or '',
                                     # the card's In: the folder a delete aims at, never the agent's own scratch folder it ran from
                                     'what': what, 'why': why, 'where': next((a['where'] for a in todo if a.get('where')), ''),
                                     **({'about': ' '.join(str(about).split())[:300]} if str(about or '').strip() else {})}, 'agent')
        store.audit('task', tid, 'shell_act_held', 'taskuary', 'system', {'tools': [a['tool'] for a in todo], 'what': what})
    return _deny(f"{HELD}: {what} ({why}). It is on the task as the owner's Approve button; once they press it, Taskuary runs this "
                 "exact command in the same folder and tells you what happened. Do not try it another way. The button is the ask: say in one "
                 "line what it waits on - never ask them to run it, never print the command for them to copy. End your turn now, or go on "
                 "with work that does not need it.")


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


def _argv(shell: str, cmd: str) -> list:
    "The held command in the shell it was written in: the agent's PowerShell tool in PowerShell, its Bash tool in Git Bash (the system bash off Windows)."
    if str(shell).lower() == 'powershell':
        return [shutil.which('pwsh') or shutil.which('powershell') or 'powershell', '-NoProfile', '-NonInteractive', '-Command', cmd]
    b = git_bash()
    if not b: raise RuntimeError('The held step was not run: ' + ('no Git Bash (the bash beside git.exe)' if os.name == 'nt' else 'no bash or sh')
                                 + ' was found to run it in - nothing was done')
    return [b, '-c', cmd]


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
_LISTED = re.compile(r'^([ MADRCU?!]{1,2}\s+\S+|[0-9a-f]{7,40}\s.*|[^\s:]+[/\\][^\s]+)$')
_SAYS_WHY = re.compile(r'^(error|fatal|ERROR|FATAL)\b')
def failed(said: str, rc: int) -> str:
    "What the owner reads when the held step failed: the one line where WSL, git or gh says why."
    lines = [l.strip() for l in str(said or '').splitlines() if l.strip()]
    told = [l for l in lines if not _LISTED.match(l) and not l.lower().startswith('hint:')] or lines
    why = next((l for l in told if _SAYS_WHY.match(l)), told[0] if told else '')
    return f"The held step failed: {why[:240] or f'exit {rc}'}"


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


def perform(store, tid: int, p: dict, run=None) -> dict:
    """The owner's yes: run the held command, as it was, in the folder it was held in. `run`: the runner (tests stand one in)."""
    cmd, cwd = str(p.get('command') or ''), str(p.get('cwd') or '')
    if not cmd: raise RuntimeError('this held step names no command')
    if (busy := mid_turn(store, tid, p.get('sid'))): raise RuntimeError(busy)
    if cwd and not os.path.isdir(cwd): raise RuntimeError(f'the folder it was held in is gone ({cwd}) - nothing was done')
    def go(argv, folder):
        from . import spawn
        r = spawn.run(argv, cwd=folder or None, capture_output=True, timeout=300, stdin=subprocess.DEVNULL)   # bytes: text() reads them
        return r.returncode, text(r.stdout) + text(r.stderr)
    rc, said = (run or go)(_argv(p.get('shell') or 'Bash', cmd), cwd)
    if rc != 0: raise RuntimeError(failed(said, rc))
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
    rvs = [store.get_review(int(r)) for r in rids]
    if not rvs or any(not r or r.get('Kind') != 'action' or json.loads(r.get('DraftText') or '{}').get('action') != 'shell_act' for r in rvs):
        raise ValueError('only held shell steps are approved together')
    if len({r.get('TaskId') for r in rvs}) != 1: raise ValueError('held steps of one task only')
    tid, told, done, failed = rvs[0]['TaskId'], [], [], None
    if verb == 'approve' and (busy := mid_turn(store, tid, json.loads(rvs[0].get('DraftText') or '{}').get('sid'))):
        return {'ok': False, 'done': [], 'failed': None, 'left': [r['ReviewId'] for r in rvs], 'busy': busy}
    tok = _batch.set(told)
    try:
        for i, rv in enumerate(rvs):
            out = decide(store, rv, verb, actor=actor)
            if not out.get('ok'): failed = {'review': rv['ReviewId'], 'step': i + 1, 'error': out.get('send_error') or 'it did not run'}; break
            done.append({'review': rv['ReviewId'], 'result': out.get('result')})
    finally: _batch.reset(tok)
    left = [r['ReviewId'] for r in rvs[len(done) + (1 if failed else 0):]]
    ran = '; '.join(told) or 'nothing ran'
    if verb != 'approve': _tell(store, tid, f"The owner dismissed {len(rvs)} held steps: {ran} - NOT done. {OWNER_NO}")
    elif failed:
        # ...A STEP THAT FAILED IS OVER, AND THE AGENT'S (the owner, 2026-11-10: "no idea what this is. it's broken"): the card read "1 of 2 ran -
        # the rest wait" with Approve still lit under the failure, and the agent - told they still waited - worked the failure while the owner's
        # next press ran the same step into it again. The card is now its record: the failed step and those after it settled, never pressable;
        # the agent is started on what failed, and what it holds next is a new card in its new turn
        for r in [failed['review'], *left]: store.decide_review(r, 'superseded', None, 'taskuary', FAILED if r == failed['review'] else NOT_RUN)
        _tell(store, tid, f"The owner approved {len(rvs)} held steps together. Taskuary ran {len(done)} of them ({ran}); step {failed['step']} "
                          f"failed: {failed['error'][:300]}. Nothing on that card waits on the owner now - the steps after it were not run. Find out "
                          "why and put it right if you can; a step still needed is run again by you and held as a new card for their press. " + NEXT,
              wake=True)
    else: _tell(store, tid, f"The owner approved {len(rvs)} held steps together and Taskuary ran them in order: {ran}. " + NEXT, wake=True)
    return {'ok': not failed, 'done': done, 'failed': failed, 'left': left}


def declined(store, tid: int, p: dict) -> None:
    if (told := _batch.get()) is not None: return told.append(f"{p.get('what') or 'the step'} (`{str(p.get('command') or '')[:200]}`)")
    _tell(store, tid, not_approved(f"{p.get('what') or 'the step'} (`{str(p.get('command') or '')[:200]}`)"))
