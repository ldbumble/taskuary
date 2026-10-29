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
browser hook); and a step reached some other way than these tools by name (a script that pushes, an HTTP call made by hand). This
gates the commands agents use, not every road there is.
"""
import json, os, shutil, subprocess
from loguru import logger
from .browsergate import _segments, _deny, _tell

HELD = 'Taskuary held this for the owner'
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


def acts(cmd: str) -> list:
    """Every step in a shell command that goes out: [{'tool', 'what', 'command'}]. A command that cannot be read and names one of
    these tools is one step - held, never let through for being hard to read."""
    raw = str(cmd or '')
    low = raw.lower()
    if not any(w in low for w in ('git', 'gh', 'glab', 'publish', 'push', 'upload', 'mail', 'mutt', 'msmtp')): return []      # the cheap test first
    segs = _segments(raw)
    if segs is None:
        import re
        return [{'tool': '?', 'what': 'run a command that may push, publish or send', 'command': raw[:400]}] if re.search(
            r'\b(git\s+push|gh\s+(pr|issue|release|repo|api)|glab|publish|sendmail|send-mailmessage)\b', low) else []
    out = []
    for argv in segs:
        tool, w = _words(argv)
        if tool in ('bash', 'sh', 'powershell', 'pwsh', 'cmd'):                 # `bash -c "git push"`: the string is a command of its own
            for t in argv[1:]:
                if ' ' in t.strip(): out += acts(t)
            continue
        what = (GIT.get(w[0]) if tool == 'git' and w else
                GH.get(tuple(w[:2])) if tool == 'gh' else GLAB.get(tuple(w[:2])) if tool == 'glab' else
                'publish a package' if (tool in PUBLISH and w[:1] in (['publish'], ['push'])) or (tool == 'twine' and w[:1] == ['upload'])
                or (tool == 'docker' and w[:1] == ['push']) else MAIL.get(tool))
        if not what and tool in ('gh', 'glab') and w[:1] == ['api'] and _api_writes(argv): what = 'change something on the code host through its API'
        if not what and tool == 'git' and w[:1] == ['push']: what = GIT['push']
        if what: out.append({'tool': tool, 'what': what, 'command': ' '.join(argv)[:400]})
    return out


def _pending(store, tid: int, sid: str, cmd: str):
    for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (tid,)):
        try: p = json.loads(r.get('DraftText') or '{}')
        except ValueError: continue
        if p.get('action') == 'shell_act' and p.get('sid') == str(sid) and p.get('command') == cmd: return r
    return None


def asks(store, t) -> bool:
    """Can the owner answer this session's own permission prompt? Only a CLI pane of ours (argv: a terminal, not a headless chat),
    started 'full' (a stranger's task runs 'auto' and its permit door is the owner's), whose CLI's hook answers `ask`, on a task that
    is not a workflow's run (nobody sits at a scheduled run's pane). Everything else is held for the task's Approve."""
    if not getattr(t, 'argv', None) or getattr(t, 'mode', 'full') != 'full': return False
    from . import clis
    if clis._base(getattr(t, 'cli', '') or t.argv[0]) not in ASKS: return False
    return (store.get_task(t.task_id) or {}).get('Source') != 'workflow'


def check(store, tid: int, sid: str, cmd: str, shell: str = 'Bash', cwd: str = '', ask: bool = False) -> dict:
    """The hook's answer for one shell command: {} lets it run; `ask` hands it to the CLI's own prompt (never an allow); else a refusal
    holds it and puts the step on the task. ONE step holds the whole command - the line is the agent's, and half of it is not what it asked."""
    todo = acts(cmd)
    if not todo: return {}
    what = '; '.join(dict.fromkeys(a['what'] for a in todo))
    if ask:
        store.audit('task', tid, 'shell_act_asked', 'taskuary', 'system', {'tools': [a['tool'] for a in todo], 'what': what})
        store.add_comment_once(tid, 'taskuary', 'agent', f"The agent asked to {what}: `{str(cmd)[:300]}` - its terminal asks you to allow it.")
        return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'ask',
                                       'permissionDecisionReason': f'Taskuary asks you first: {what} (it leaves this computer).'}}
    if not _pending(store, tid, sid, cmd):
        from . import proposals
        proposals.queue(store, tid, {'action': 'shell_act', 'sid': str(sid), 'command': str(cmd)[:4000], 'shell': shell, 'cwd': cwd or '',
                                     'what': what, 'why': 'it leaves this computer'}, 'agent')
        store.audit('task', tid, 'shell_act_held', 'taskuary', 'system', {'tools': [a['tool'] for a in todo], 'what': what})
    return _deny(f"{HELD}: {what} (it leaves this computer). It is on the task for the owner to approve; once they do, Taskuary runs this "
                 "exact command in the same folder and tells you what happened. Do not try it another way. End your turn now, or go on "
                 "with work that does not need it.")


def git_bash() -> str:
    """The bash an agent's Bash tool runs on Windows: Git's, beside git.exe. NEVER System32's bash.exe - WSL's launcher, which on a box
    with no distribution answered an approved push with "no distribution installed", in UTF-16 (2026-10-29). '' when none is found."""
    if os.name != 'nt': return shutil.which('bash') or ''
    cands, g = [os.environ.get('CLAUDE_CODE_GIT_BASH_PATH') or ''], shutil.which('git')     # Claude Code's own setting for that bash first
    if g:                                       # git.exe sits in <Git>\cmd, <Git>\bin or <Git>\mingw64\bin
        d = os.path.dirname(os.path.abspath(g))
        cands += [os.path.join(r, *b) for r in (os.path.dirname(d), os.path.dirname(os.path.dirname(d))) for b in (('bin', 'bash.exe'), ('usr', 'bin', 'bash.exe'))]
    cands += [os.path.join(os.environ[v], *b) for v in ('ProgramFiles', 'ProgramW6432', 'LOCALAPPDATA') if os.environ.get(v)
              for b in (('Git', 'bin', 'bash.exe'), ('Programs', 'Git', 'bin', 'bash.exe'))]
    w, sysroot = shutil.which('bash') or '', os.path.normcase(os.environ.get('SystemRoot') or r'C:\Windows')
    if w and not os.path.normcase(os.path.abspath(w)).startswith(sysroot) and 'windowsapps' not in w.lower(): cands.append(w)
    return next((c for c in cands if c and os.path.isfile(c)), '')


def _argv(shell: str, cmd: str) -> list:
    "The held command in the shell it was written in: the agent's PowerShell tool in PowerShell, its Bash tool in Git Bash."
    if str(shell).lower() == 'powershell':
        return [shutil.which('pwsh') or shutil.which('powershell') or 'powershell', '-NoProfile', '-NonInteractive', '-Command', cmd]
    b = git_bash()
    if not b: raise RuntimeError('The held step was not run: no Git Bash (the bash beside git.exe) was found to run it in - nothing was done')
    return [b, '-c', cmd]


def text(raw) -> str:
    """A child's output as words: UTF-16 when its bytes say so (a byte-order mark, or NULs in every other place - wsl.exe writes it),
    else UTF-8 with whatever does not decode replaced. Read as UTF-8, WSL's sentence reached the owner as r\\0i\\0b\\0u\\0t\\0i\\0o\\0n."""
    if raw is None or isinstance(raw, str): return raw or ''
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'): return raw.decode('utf-16', errors='replace')
    odd, even = raw[1::2].count(0), raw[::2].count(0)
    if len(raw) >= 4 and odd * 2 >= len(raw) // 2 and odd > even: return raw.decode('utf-16-le', errors='replace')
    return raw.decode('utf-8', errors='replace')


def failed(said: str, rc: int) -> str:
    "What the owner reads when the held step failed: its first lines, which are where WSL, git and gh say why."
    lines = [l.strip() for l in str(said or '').splitlines() if l.strip()]
    return f"The held step failed: {' / '.join(lines[:4])[:300] or f'exit {rc}'}"


def perform(store, tid: int, p: dict, run=None) -> dict:
    """The owner's yes: run the held command, as it was, in the folder it was held in. `run`: the runner (tests stand one in)."""
    cmd, cwd = str(p.get('command') or ''), str(p.get('cwd') or '')
    if not cmd: raise RuntimeError('this held step names no command')
    if cwd and not os.path.isdir(cwd): raise RuntimeError(f'the folder it was held in is gone ({cwd}) - nothing was done')
    def go(argv, folder):
        from . import spawn
        r = spawn.run(argv, cwd=folder or None, capture_output=True, timeout=300, stdin=subprocess.DEVNULL)   # bytes: text() reads them
        return r.returncode, text(r.stdout) + text(r.stderr)
    rc, said = (run or go)(_argv(p.get('shell') or 'Bash', cmd), cwd)
    if rc != 0: raise RuntimeError(failed(said, rc))
    said = ' '.join(str(said or '').split())[-600:]
    _tell(store, tid, f"The owner approved it and Taskuary ran `{cmd[:300]}` in {cwd or 'its folder'}. It said: {said[-300:] or 'done'}. Carry on.")
    store.audit('task', tid, 'shell_act_done', 'owner', 'human', {'what': p.get('what')})
    return {'performed': p.get('what') or cmd[:200], 'said': said[-300:]}


def declined(store, tid: int, p: dict) -> None:
    _tell(store, tid, f"The owner did not approve it: {p.get('what') or 'the step'} (`{str(p.get('command') or '')[:200]}`) was NOT done. Do "
                      'not try it another way - carry on without it, or ask the owner what they want instead.')
