"""A SHELL STEP THAT LEAVES THE MACHINE WAITS FOR THE OWNER'S PRESS (the Advisor design rev 2, the owner's ruling 2026-10-28: "hold risky
steps on the existing proposal card - the only automatic act; risky = send/forward, pay, sign up, delete, push/merge, new outside recipient").

browsergate.py holds a browser act that can't be undone. The same road out ran through the agent's own shell, guarded only by prose
("CODING.md says not to push" - guard.py's header on why prose is no control): `git push`, `gh pr merge`, a public comment, a release
deleted, a package published or a mail sent from a script went straight out, and a mail that talked the agent into one was all it took.

Where it is caught: the same PreToolUse hook on the shell tools (hooks.browser, matcher Bash|PowerShell). Which commands go out is each
tool's own GRAMMAR - git's `push`, the GitHub CLI's `pr merge` or `api -X DELETE`, a package manager's `publish`, a mail tool by its name -
never a judgement over words, and never the words of a mail. Everything else passes at once.
- HELD: the tool call is refused with why, and the step goes on the task as a proposal (proposals.ACTIONS 'shell_act') - the existing
  card with Approve and Dismiss, the exact command shown.
- APPROVED, Taskuary runs that exact command in the folder the agent ran it from, and tells the agent what happened. Dismissed, the
  agent is told it was not done.

What this does not cover, said plainly: Codex, Devin and Copilot sessions (their hooks report, they cannot refuse a call); a session whose
hook could not reach Taskuary (the call runs - the same as the browser hook); and a step reached some other way than these tools by name
(a script that pushes, an HTTP call made by hand). This gates the commands agents use, not every road there is.
"""
import json, os, shutil, subprocess
from loguru import logger
from .browsergate import _segments, _deny, _tell

HELD = 'Taskuary held this for the owner'
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


def check(store, tid: int, sid: str, cmd: str, shell: str = 'Bash', cwd: str = '') -> dict:
    """The hook's answer for one shell command: {} lets it run; a refusal holds it and puts the step on the task. ONE step held holds
    the whole command - the shell line is the agent's, and running half of it is not what it asked for."""
    todo = acts(cmd)
    if not todo: return {}
    what = '; '.join(dict.fromkeys(a['what'] for a in todo))
    if not _pending(store, tid, sid, cmd):
        from . import proposals
        proposals.queue(store, tid, {'action': 'shell_act', 'sid': str(sid), 'command': str(cmd)[:4000], 'shell': shell, 'cwd': cwd or '',
                                     'what': what, 'why': 'it leaves this computer'}, 'agent')
        store.audit('task', tid, 'shell_act_held', 'taskuary', 'system', {'tools': [a['tool'] for a in todo], 'what': what})
    return _deny(f"{HELD}: {what} (it leaves this computer). It is on the task for the owner to approve; once they do, Taskuary runs this "
                 "exact command in the same folder and tells you what happened. Do not try it another way. End your turn now, or go on "
                 "with work that does not need it.")


def _argv(shell: str, cmd: str) -> list:
    if str(shell).lower() == 'powershell':
        return [shutil.which('pwsh') or shutil.which('powershell') or 'powershell', '-NoProfile', '-NonInteractive', '-Command', cmd]
    return [shutil.which('bash') or 'bash', '-c', cmd]


def perform(store, tid: int, p: dict, run=None) -> dict:
    """The owner's yes: run the held command, as it was, in the folder it was held in. `run`: the runner (tests stand one in)."""
    cmd, cwd = str(p.get('command') or ''), str(p.get('cwd') or '')
    if not cmd: raise RuntimeError('this held step names no command')
    if cwd and not os.path.isdir(cwd): raise RuntimeError(f'the folder it was held in is gone ({cwd}) - nothing was done')
    def go(argv, folder):
        from . import spawn
        r = spawn.run(argv, cwd=folder or None, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
        return r.returncode, (r.stdout or '') + (r.stderr or '')
    rc, said = (run or go)(_argv(p.get('shell') or 'Bash', cmd), cwd)
    said = ' '.join(str(said or '').split())[-600:]
    if rc != 0: raise RuntimeError(f'it ran and failed: {said[-300:] or f"exit {rc}"}')
    _tell(store, tid, f"The owner approved it and Taskuary ran `{cmd[:300]}` in {cwd or 'its folder'}. It said: {said[-300:] or 'done'}. Carry on.")
    store.audit('task', tid, 'shell_act_done', 'owner', 'human', {'what': p.get('what')})
    return {'performed': p.get('what') or cmd[:200], 'said': said[-300:]}


def declined(store, tid: int, p: dict) -> None:
    _tell(store, tid, f"The owner did not approve it: {p.get('what') or 'the step'} (`{str(p.get('command') or '')[:200]}`) was NOT done. Do "
                      'not try it another way - carry on without it, or ask the owner what they want instead.')
