"""LANDING A CODING TASK'S BRANCH (the owner, 2026-11-06: "rebase fast forward is a question on each one and they can ask").

Agents share the checkout (no copy per task - "let the agents figure it out"), so what a task changed is read off git against where it
started: `mark_start` notes the checkout, its branch and HEAD when the task's first session opens, and the close-out shows the diff since
then and asks ONE question per task - Rebase and fast-forward, Merge commit, Open a PR - plus Discard, offered only when the agent made a
branch of its own (discarding the base would throw away what it shares with everyone).

Nothing lands half-done: a rebase or merge that conflicts is aborted, the checkout is as it was, and the conflict goes to the agent as its
next turn ("resolve these conflicts, then say done"). A merge commit onto a base nobody has checked out is written without touching the
working tree (merge-tree + commit-tree + a compare-and-swap of the branch ref), so the agents working in the checkout are not disturbed.

The agent may PROPOSE how (propose_land); the same question shows with its pick marked, and only the owner's answer lands anything.
"""
import json, os, re, time
from loguru import logger

from .store import task_ref

KEY = 'landing'                      # :<tid> -> {cwd, base, start, branch, proposal?, landed?}
HOW = {'rebase': 'Rebase and fast-forward', 'merge': 'Merge commit', 'pr': 'Open a PR', 'discard': 'Discard'}
DIFF_CAP = 400_000


def _run(cwd, *args, timeout=60) -> tuple:
    "(exit code, stdout, stderr) - landing reads git's own exit, never an empty string."
    from . import spawn
    try:
        p = spawn.run(['git', '-C', cwd, *args], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
        return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()
    except Exception as e: return 1, '', str(e)


def _git(cwd, *args) -> str:
    rc, out, _ = _run(cwd, *args)
    return out if rc == 0 else ''


def head_branch(cwd) -> str:
    b = _git(cwd, 'rev-parse', '--abbrev-ref', 'HEAD')
    return '' if b in ('', 'HEAD') else b


def sha(cwd, ref) -> str: return _git(cwd, 'rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}')
def dirty(cwd) -> list: return [l[3:].strip().strip('"') for l in _git(cwd, 'status', '--porcelain').splitlines() if len(l) > 3]
def is_ancestor(cwd, a, b) -> bool: return _run(cwd, 'merge-base', '--is-ancestor', a, b)[0] == 0
def conflicted(cwd) -> list: return [l for l in _git(cwd, 'diff', '--name-only', '--diff-filter=U').splitlines() if l.strip()]


def record(store, tid: int) -> dict:
    try: return json.loads(store.get_setting(f'{KEY}:{int(tid)}') or '{}') or {}
    except (TypeError, ValueError): return {}


def _save(store, tid: int, r: dict): store.set_setting(f'{KEY}:{int(tid)}', json.dumps(r), 'system')


def mark_start(store, tid: int, cwd: str) -> dict | None:
    """Where this task's work starts from: the checkout, its branch and its HEAD - once, at its first session; a Continue keeps the first."""
    if record(store, tid).get('start') or not cwd or not os.path.isdir(cwd): return None
    start, base = sha(cwd, 'HEAD'), head_branch(cwd)
    if not start or not base: return None                      # not a git checkout, or a detached HEAD: nothing to land later
    r = {'cwd': cwd, 'base': base, 'start': start, 'at': time.strftime('%Y-%m-%d %H:%M:%S')}
    _save(store, tid, r)
    return r


def seen(store, tid: int) -> dict:
    """The agent's branch, as the checkout shows it now - kept, so another agent switching the shared checkout later does not lose it."""
    r = record(store, tid)
    if not r.get('cwd') or not os.path.isdir(r['cwd']): return r
    b = head_branch(r['cwd'])
    # the first branch it is seen on is its own; another is taken only once that one is gone (renamed, or deleted by the agent)
    if b and b != r.get('base') and b != r.get('branch') and not r.get('landed') and not (r.get('branch') and sha(r['cwd'], f"refs/heads/{r['branch']}")):
        r['branch'] = b; _save(store, tid, r)
    return r


def _alone(tid, cwd) -> bool:
    "No other task's live session works in this checkout."
    from . import peers
    from .blackboard import norm
    return not any(t.task_id != tid and norm(t.cwd) == norm(cwd) for t in peers._cli_sessions())


def _stat(cwd, a, b) -> list:
    out = []
    for l in _git(cwd, 'diff', '--numstat', a, b).splitlines():
        p = l.split('\t')
        if len(p) >= 3: out.append({'path': p[2], 'plus': int(p[0]) if p[0].isdigit() else 0, 'minus': int(p[1]) if p[1].isdigit() else 0})
    return out


def state(store, tid: int, full: bool = False) -> dict | None:
    """What the task's work is against where it started, and the question to land it - None when no session of it started in a checkout."""
    r = record(store, tid)
    # the checkout's HEAD is this task's branch only while its agent is the one in there: with a peer in the same checkout it may be the
    # peer's, so it is read then only at this task's own close (wrapup -> seen)
    if r.get('cwd') and _alone(tid, r['cwd']): r = seen(store, tid)
    cwd, base, start = r.get('cwd'), r.get('base'), r.get('start')
    if not (cwd and base and start and os.path.isdir(cwd)): return None
    br = r.get('branch') or ''
    own = bool(br) and bool(sha(cwd, f'refs/heads/{br}'))
    tip = br if own else base
    files = _stat(cwd, start, tip) if sha(cwd, tip) else []
    ahead = int(_git(cwd, 'rev-list', '--count', f'{base}..{br}') or 0) if own else 0
    out = {'task': task_ref(tid), 'cwd': cwd, 'repo': _repo(cwd), 'base': base, 'branch': br if own else base, 'own': own, 'ahead': ahead,
           'files': files, 'changed': len(files), 'plus': sum(f['plus'] for f in files), 'minus': sum(f['minus'] for f in files),
           'landed': r.get('landed'), 'proposal': r.get('proposal')}
    out['ask'] = own and ahead > 0 and not r.get('landed')
    out['answers'] = [{'how': k, 'label': v} for k, v in HOW.items() if k != 'discard' or own] if out['ask'] else []
    out['line'] = said(out)
    if full: out['diff'] = _git(cwd, 'diff', start, tip)[:DIFF_CAP]
    return out


def said(s: dict) -> str:
    "One line: what changed and what is asked."
    if not s: return ''
    n = f"{s['changed']} file{'s' if s['changed'] != 1 else ''} changed, +{s['plus']} -{s['minus']}"
    if s.get('landed'): return f"{s['branch']} landed ({HOW.get(s['landed'].get('how'), s['landed'].get('how'))}) - {n}."
    if s['ask']: return f"{s['branch']} is {s['ahead']} commit{'s' if s['ahead'] != 1 else ''} ahead of {s['base']}: {n}. How should it land?"
    if s['own']: return f"{s['branch']} has nothing {s['base']} does not already have."
    return f"The agent worked on {s['base']} itself - {n} since it started; there is no branch of its own to land."


def _repo(cwd) -> str:
    from . import shellgate
    return shellgate.repo_of(cwd)


def propose(store, tid: int, how: str, why: str = '', actor: str = 'agent') -> dict:
    """The agent's own read of how its work should land: the close-out's question shows it marked. It lands nothing."""
    how = str(how or '').strip().lower()
    if how not in HOW: raise ValueError(f"how is one of: {', '.join(HOW)}")
    s = state(store, tid)
    if not s: raise ValueError('no session of this task started in a git checkout - there is nothing to land')
    if not s['ask']: raise ValueError(s['line'])
    if how == 'discard' and not s['own']: raise ValueError('discard is only for a branch of your own')
    r = record(store, tid)
    r['proposal'] = {'how': how, 'why': ' '.join(str(why or '').split())[:400], 'at': time.strftime('%Y-%m-%d %H:%M:%S')}
    _save(store, tid, r)
    store.add_comment(tid, actor, 'agent', f"Proposes to land {s['branch']}: {HOW[how]}" + (f" - {r['proposal']['why']}" if r['proposal']['why'] else '') + '.')
    store.audit('task', tid, 'land_proposed', actor, detail={'how': how})
    try:                                          # ...and asked on a chat bound to the task (agentchannels.py): answered there by the owner alone
        from . import agentchannels
        agentchannels.landing_proposed(store, tid)
    except Exception as e: logger.debug(f'{task_ref(tid)}: the landing question was not put on its channel - {e}')
    return {'ok': True, 'says': f"The owner sees the landing question with {HOW[how]} marked - nothing lands until they answer it."}


class Refused(RuntimeError): pass


def _conflict(store, tid: int, s: dict, how: str, files: list) -> dict:
    """Aborted, so nothing landed half-done - and the conflict is the agent's next turn."""
    from . import waitroom
    names = ', '.join(files[:30]) or 'files git did not name'
    text = (f"LANDING CONFLICT: {HOW[how]} of {s['branch']} onto {s['base']} stopped on conflicts in {names}. It was aborted - nothing "
            f"landed and the checkout is as it was. Resolve these conflicts on {s['branch']} (rebase it onto {s['base']}, or merge "
            f"{s['base']} into it), commit, then say done - the owner lands it again.")
    store.add_comment(tid, 'router', 'agent', f"{HOW[how]} stopped on conflicts in {names} - aborted, nothing landed; the agent has it now.")
    store.audit('task', tid, 'land_conflict', 'router', 'agent', {'how': how, 'files': files[:30]})
    try: waitroom.add(store, tid, text, 'router')
    except Exception as e: logger.warning(f'{task_ref(tid)}: the landing conflict could not be handed to the agent - {e}')
    return {'ok': False, 'conflict': files, 'says': f"Conflicts in {names} - nothing landed. The agent is resolving them."}


def _ff(cwd, base, br):
    "Move `base` to `br`'s tip: in the tree when `base` is checked out, else by its ref alone (compare-and-swap)."
    if head_branch(cwd) == base:
        rc, out, err = _run(cwd, 'merge', '--ff-only', br)
        if rc: raise Refused(f'fast-forwarding {base} was refused: {(err or out)[:300]}')
        return
    rc, _, err = _run(cwd, 'update-ref', f'refs/heads/{base}', sha(cwd, br), sha(cwd, base))
    if rc: raise Refused(f'{base} moved while landing - nothing changed ({err[:200]})')


def land(store, tid: int, how: str, actor: str = 'owner') -> dict:
    """The owner's answer to the landing question, carried out. {'ok', 'says', ...}; a conflict is {'ok': False, 'conflict': [...]}."""
    how = str(how or '').strip().lower()
    if how not in HOW: raise ValueError(f"how is one of: {', '.join(HOW)}")
    s = state(store, tid)
    if not s or not s['ask']: raise ValueError((s or {}).get('line') or 'nothing to land on this task')
    if how == 'discard' and not s['own']: raise ValueError('discard is only offered for a branch the agent made itself')
    cwd, base, br = s['cwd'], s['base'], s['branch']
    head, said_ = head_branch(cwd), ''
    if how == 'rebase':
        if not is_ancestor(cwd, base, br):
            if head != br: raise Refused(f'rebasing {br} needs it checked out in {cwd}, and the checkout is on {head or "a detached HEAD"} - nothing changed')
            if (d := dirty(cwd)): raise Refused(f"the checkout has uncommitted changes ({', '.join(d[:5])}) - commit or stash them first; nothing changed")
            rc, out, err = _run(cwd, 'rebase', base, timeout=300)
            if rc:
                files = conflicted(cwd)
                _run(cwd, 'rebase', '--abort')
                if files: return _conflict(store, tid, s, how, files)
                raise Refused(f'the rebase was refused: {(err or out)[:300]} - nothing changed')
        _ff(cwd, base, br)
        said_ = f'Rebased {br} onto {base} and fast-forwarded {base} to it ({sha(cwd, base)[:7]}).'
    elif how == 'merge':
        msg = f"Merge {br} ({task_ref(tid)})"
        if head == base:
            rc, out, err = _run(cwd, 'merge', '--no-ff', '--no-edit', '-m', msg, br, timeout=300)
            if rc:
                files = conflicted(cwd)
                _run(cwd, 'merge', '--abort')
                if files: return _conflict(store, tid, s, how, files)
                raise Refused(f'the merge was refused: {(err or out)[:300]} - nothing changed')
        else:
            rc, out, err = _run(cwd, 'merge-tree', '--write-tree', '--name-only', base, br, timeout=300)
            lines = out.splitlines()
            if rc == 1: return _conflict(store, tid, s, how, out.partition('\n\n')[0].splitlines()[1:31])    # the tree, the conflicted names, a blank line, git's messages
            if rc or not lines: raise Refused(f'the merge could not be worked out: {(err or out)[:300]} - nothing changed')
            old = sha(cwd, base)
            rc, new, err = _run(cwd, 'commit-tree', lines[0], '-p', old, '-p', sha(cwd, br), '-m', msg)
            if rc or not new: raise Refused(f'the merge commit could not be written: {err[:200]} - nothing changed')
            rc, _, err = _run(cwd, 'update-ref', f'refs/heads/{base}', new, old)
            if rc: raise Refused(f'{base} moved while landing - nothing changed ({err[:200]})')
        said_ = f'Merged {br} into {base} with a merge commit ({sha(cwd, base)[:7]}).'
    elif how == 'pr': return _pr(store, tid, s, actor)
    else:
        if head == br:
            if (d := dirty(cwd)): raise Refused(f"the checkout is on {br} with uncommitted changes ({', '.join(d[:5])}) - nothing was discarded")
            rc, out, err = _run(cwd, 'checkout', base)
            if rc: raise Refused(f'could not leave {br}: {(err or out)[:200]} - nothing was discarded')
        rc, out, err = _run(cwd, 'branch', '-D', br)
        if rc: raise Refused(f'{br} could not be deleted: {(err or out)[:200]}')
        said_ = f"Discarded {br} - its {s['ahead']} commit{'s' if s['ahead'] != 1 else ''} are gone from {base}'s checkout."
    return _landed(store, tid, how, said_, actor, sha(cwd, base))


# ── REVIEW BEFORE IT LANDS: a part turned down is taken back out (the owner, 2026-11-06: "i do like you can review the code diffs") ──
# Safe only where it touches nothing anyone else is using: the task's own branch checked out, no agent at work in the checkout (its own
# included - it would be editing the very file), nothing uncommitted in the files it reverts, and each part exactly as the owner saw it
# (its text matched against the diff now). Then `git apply -R` of those hunks alone, checked first, and ONE commit on the branch saying
# so - a revert the owner can read in the log, and undo with git like any commit. Anything else changes nothing and says why.
def _raw(cwd, *args) -> bytes:
    "git's stdout as BYTES: a patch is applied as git wrote it - a text read loses a CRLF file's \\r and a last line's trailing spaces."
    from . import spawn
    p = spawn.run(['git', '-C', cwd, *args], capture_output=True, timeout=60)
    if p.returncode: raise Refused(f"git {args[0]} failed: {(p.stderr or b'').decode('utf-8', 'replace')[:200]}")
    return p.stdout or b''


def hunks_of(diff: bytes) -> tuple:
    "(header, [hunk, ...]) of ONE file's diff, as bytes: the lines before the first @@, then each @@ and the lines under it."
    lines = diff.split(b'\n')
    if lines and lines[-1] == b'': lines.pop()
    at = [i for i, l in enumerate(lines) if l.startswith(b'@@')]
    if not at: return lines, []
    return lines[:at[0]], [lines[a:b] for a, b in zip(at, at[1:] + [len(lines)])]


_norm = lambda s: str(s).replace('\r\n', '\n').replace('\r', '').rstrip('\n')


def revert(store, tid: int, picks: list, actor: str = 'owner') -> dict:
    """Take the parts the owner turned down back out of the task's branch: picks [{path, index, text}] - the hunk's index in that file's diff
    since the task started, and its text as the viewer showed it. Nothing changes unless every part still reads as shown."""
    import tempfile
    from . import peers
    from .blackboard import norm
    s = state(store, tid)
    if not s: raise ValueError('no session of this task started in a git checkout - there is nothing to review')
    if s.get('landed'): raise Refused('it has already landed - nothing changed')
    if not picks: raise ValueError('no part was marked to revert')
    cwd, br, start = s['cwd'], s['branch'], record(store, tid).get('start')
    if (head := head_branch(cwd)) != br: raise Refused(f'reverting a part needs {br} checked out in {cwd}; it is on {head or "a detached HEAD"} - nothing changed')
    if any(norm(t.cwd) == norm(cwd) for t in peers._cli_sessions()):
        raise Refused('an agent is working in this checkout - stop it or let it finish first; nothing changed')
    by = {}
    for p in picks: by.setdefault(str(p.get('path') or ''), []).append(p)
    if (d := [f for f in dirty(cwd) if f in by]): raise Refused(f"{', '.join(d[:5])} {'has' if len(d) == 1 else 'have'} uncommitted changes - nothing changed")
    patch = b''
    for path, ps in by.items():
        head_, hs = hunks_of(_raw(cwd, 'diff', start, br, '--', path))
        if not hs: raise Refused(f'{path} has no change to revert any more - nothing changed')
        for p in ps:
            i = int(p.get('index', -1))
            if not 0 <= i < len(hs) or _norm(b'\n'.join(hs[i]).decode('utf-8', 'replace')) != _norm(p.get('text') or ''):
                raise Refused(f'{path} changed since you looked at it - open the diff again; nothing changed')
        patch += b'\n'.join(head_ + [l for i in sorted({int(p['index']) for p in ps}) for l in hs[i]]) + b'\n'
    with tempfile.NamedTemporaryFile('wb', suffix='.patch', delete=False) as f: f.write(patch)
    try:
        rc, out, err = _run(cwd, 'apply', '-R', '--check', '--whitespace=nowarn', f.name)
        if rc: raise Refused(f'those parts no longer take back cleanly: {(err or out)[:200]} - nothing changed')
        rc, out, err = _run(cwd, 'apply', '-R', '--whitespace=nowarn', f.name)
        if rc: raise Refused(f'git refused the revert: {(err or out)[:200]} - nothing changed')
        n = len(picks)
        msg = f"Revert {n} part{'s' if n != 1 else ''} turned down in review ({task_ref(tid)})"
        rc, out, err = _run(cwd, 'commit', '-q', '-m', msg, '--', *by)
        if rc:
            _run(cwd, 'apply', '--whitespace=nowarn', f.name)          # put the tree back as it was: the revert is all or nothing
            raise Refused(f'the revert could not be committed: {(err or out)[:200]} - nothing changed')
    finally:
        try: os.unlink(f.name)
        except OSError: pass
    said_ = f"Reverted {n} part{'s' if n != 1 else ''} of {', '.join(by)} on {br} ({sha(cwd, br)[:7]})."
    store.add_comment(tid, actor, 'human', said_)
    store.audit('task', tid, 'land_review_revert', actor, detail={'files': list(by)[:30], 'parts': n})
    return {'ok': True, 'says': said_, 'state': state(store, tid)}


def _landed(store, tid, how, said_, actor, at_sha='', **extra) -> dict:
    r = record(store, tid)
    r['landed'] = {'how': how, 'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'sha': at_sha, **extra}
    _save(store, tid, r)
    store.add_comment(tid, actor, 'human', said_)
    store.audit('task', tid, 'landed', actor, detail={'how': how, 'sha': at_sha[:12], **extra})
    return {'ok': True, 'how': how, 'says': said_, **extra}


def _pr(store, tid, s, actor) -> dict:
    """Open a PR: the branch pushed and a draft pull request opened through the GitHub card. Reached only by the owner's answer - their
    press is the push's press (an agent's propose_land only marks the question)."""
    from . import ci, github
    cwd, base, br, repo = s['cwd'], s['base'], s['branch'], s['repo']
    if not repo: raise Refused("this checkout's origin is not a GitHub repository - push it and open the pull request by hand")
    c = ci._conn(store, repo)
    rc, out, err = _run(cwd, 'push', '-u', 'origin', br, timeout=180)
    if rc: raise Refused(f"the push of {br} was refused: {ci.TOKEN_URL.sub('https://', (err or out))[:300]} - no pull request opened")
    t = store.get_task(tid) or {}
    body = f"Opened by Taskuary for {task_ref(tid)}.\n\n{(t.get('Summary') or '')[:1500]}"
    pr = github.open_pr(c['Secret'], repo, br, base, f"[{task_ref(tid)}] {t.get('Title') or 'work'}"[:120], body)
    pr['repo'], pr['checks'], pr['checked_at'] = repo, None, None
    ci._save_pr(store, tid, pr, actor)
    return _landed(store, tid, 'pr', f"Pushed {br} and opened pull request #{pr['number']} into {base}: {pr.get('url')}", actor,
                   sha(cwd, br), pr=pr['number'], url=pr.get('url'))
