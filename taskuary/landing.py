"""LANDING A CODING TASK'S BRANCH (the owner, 2026-11-06: "rebase fast forward is a question on each one and they can ask").

Agents share the checkout (no copy per task - "let the agents figure it out"), so what a task changed is read off git against where it
started: `mark_start` notes the checkout, its branch and HEAD when the task's first session opens, and the close-out shows its work - its own
branch against where it left the base, or on a shared base only the commits and edits its own calls made (`own`) - and asks ONE question per task - Rebase and fast-forward, Merge commit, Open a PR - plus Discard, offered only when the agent made a
branch of its own (discarding the base would throw away what it shares with everyone).

Nothing lands half-done: a rebase or merge that conflicts is aborted, the checkout is as it was, and the conflict goes to the agent as its
next turn ("resolve these conflicts, then say done"). A merge commit onto a base nobody has checked out is written without touching the
working tree (merge-tree + commit-tree + a compare-and-swap of the branch ref), so the agents working in the checkout are not disturbed.

The agent may PROPOSE how (propose_land); the same question shows with its pick marked, and only the owner's answer lands anything.

WORK ON THE SHARED BASE IS A PUSH, ASKED WITH BUTTONS (the owner, 2026-11-09, ~20th time: "i thought actions should be cards/buttons??? why is
this text??"). A coding agent that committed straight onto master ended its turn "Ready to push 3a1b9a8 and deploy <app> (master -> deploy) - go
ahead?" over this card, which on a shared base asked nothing, so the owner typed "yes". Its own commits not yet on origin are the question now:
Push (origin/<base> up to its newest own commit) and, where a deploy branch is known - the agent's proposal, else the one last deployed to from
this repo - Push & deploy (that commit pushed to the deploy branch too). Never forced: a branch that moved refuses, and says so.
"""
from .timewords import plural
import json, os, re, time
from loguru import logger

from .store import task_ref

KEY = 'landing'                      # :<tid> -> {cwd, base, start, branch, proposal?, landed?}
HOW = {'rebase': 'Rebase and fast-forward', 'merge': 'Merge commit', 'pr': 'Open a PR', 'discard': 'Discard', 'push': 'Push', 'deploy': 'Push & deploy'}
OWN_HOW, PUSH_HOW = ('rebase', 'merge', 'pr', 'discard'), ('push', 'deploy')   # a branch of its own lands; work on the shared base is pushed
DEPLOY_KEY = 'deploy_branch'         # :<owner/repo> -> the branch the owner last pushed to deploy it - the next card's Push & deploy
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
# ...by name, never by `status --porcelain`'s columns: _git strips its output, and the first line's " M " lost a character of the file's name
def dirty(cwd) -> list:
    return [l for l in [*_git(cwd, 'diff', '--name-only', 'HEAD').splitlines(), *_git(cwd, 'ls-files', '--others', '--exclude-standard').splitlines()] if l.strip()]
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


def has_checkout(store, tid: int, cwd: str = '') -> bool:
    """CODE THINGS ONLY WHERE THERE IS CODE (the owner, 2026-11-06: "diff shows up if there is branch or checkout stuff available"): the task's
    work started in a checkout (mark_start), or a session of it works in a folder inside a git repo - whatever kind the task is."""
    if record(store, tid).get('start'): return True
    return bool(cwd) and os.path.isdir(cwd) and bool(sha(cwd, 'HEAD'))


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
    return not any(t.task_id != tid and norm(t.cwd) == norm(cwd) for t in peers.working())


def _stat(cwd, a, b) -> list:
    out = []
    for l in _git(cwd, 'diff', '--numstat', a, b).splitlines():
        p = l.split('\t')
        if len(p) >= 3: out.append({'path': p[2], 'plus': int(p[0]) if p[0].isdigit() else 0, 'minus': int(p[1]) if p[1].isdigit() else 0})
    return out


# ── WHAT IS THIS TASK'S OWN (the owner's live coding task, 2026-11-08: "518 files changed, +17417 -5334 since the task started" - every commit
# other agents and two releases made on the shared master since its first session, counted as its work). A task's changes are what ITS agent
# did: the commits its own commit calls made, and the files its own edit calls wrote, still uncommitted - read off the calls themselves (the
# ACP record kept beside the task, codingchat.record_update; the hooks a pty's CLI sends, hooks.receive -> saw), never off the branch's history.
# A commit call is matched to git's history by its time - the commits made on a local branch while it ran - as `git commit -q` prints no sha
_COMMIT = re.compile(r'''\bgit\b(?:\s+-[cC]\s+(?:"[^"]*"|'[^']*'|\S+))*\s+(?:commit|cherry-pick|revert|am)\b''')
_PATCHED = re.compile(r'^\*\*\* (?:Update|Add) File: (.+)$', re.M)
_EDITS = {'Edit', 'Write', 'MultiEdit', 'NotebookEdit', 'apply_patch', 'edit', 'write', 'create', 'str_replace_editor'}
SLACK = 3                           # seconds either side of a commit call: git's clock and ours are one machine's, read a beat apart
HOOK_RUN = 120                      # a hook says when a call ENDED, not when it began: its commits are the newest made within this


def _cmd(x) -> str: return ' '.join(map(str, x)) if isinstance(x, list) else str(x or '')
def _epoch(at) -> float:
    try: return time.mktime(time.strptime(str(at)[:19].replace('T', ' '), '%Y-%m-%d %H:%M:%S'))
    except (TypeError, ValueError): return 0.
def _stamp(t) -> str: return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t)) if t else ''


def _rel(cwd, p) -> str:
    "A path as the checkout names it - '' for one outside it."
    p = str(p or '').strip()
    if not p: return ''
    try: r = os.path.relpath(p if os.path.isabs(p) else os.path.join(cwd, p), cwd)
    except ValueError: return ''                                 # another drive
    return '' if r.startswith('..') or os.path.isabs(r) else r.replace(os.sep, '/')


def saw(store, tid: int, tool: str, args: dict, at: float = None):
    """One finished tool call of the task's own agent (a hook's PostToolUse): a commit call is a window to find its commits in, an edit call
    the file it wrote. Anything else, or a task that never started in a checkout, changes nothing."""
    r = record(store, tid)
    if not r.get('cwd') or not isinstance(args, dict): return
    at, got = at or time.time(), False
    if (n := len(_COMMIT.findall(_cmd(args.get('command') or args.get('cmd'))))):
        r['calls'] = [*r.get('calls', []), {'t0': at - HOOK_RUN, 't1': at, 'n': n}][-500:]; got = True
    paths = [args.get(k) for k in ('file_path', 'notebook_path', 'path') if args.get(k)] if str(tool) in _EDITS else []
    for p in filter(None, (_rel(r['cwd'], x) for x in [*paths, *_PATCHED.findall(str(args.get('input') or args.get('patch') or ''))])):
        r.setdefault('paths', {})[p] = at; got = True
    if got: _save(store, tid, r)


_SCAN = {}                          # an ACP record's path -> ((mtime, size), (calls, paths)): read again only once it grew


def _scan(f) -> tuple:
    c, p, calls = [], {}, {}
    for line in f.read_text(encoding='utf-8', errors='replace').splitlines():
        if '"tool_call' not in line: continue
        try: u = json.loads(line)
        except ValueError: continue
        t = _epoch(u.get('_at'))
        o = calls.setdefault(str(u.get('toolCallId') or ''), {'t0': t, 'cmd': ''})
        if (cmd := _cmd((u.get('rawInput') or {}).get('command'))): o['cmd'] = cmd
        for b in u.get('content') or []:
            if isinstance(b, dict) and b.get('type') == 'diff' and b.get('path'): p[str(b['path'])] = t
        for l in (u.get('locations') or []) if u.get('kind') == 'edit' else []:
            if isinstance(l, dict) and l.get('path'): p[str(l['path'])] = t
        if u.get('status') in ('completed', 'failed') and (n := len(_COMMIT.findall(o['cmd']))): c.append({'t0': o['t0'] or t, 't1': t, 'n': n}); o['cmd'] = ''
    return c, p


def _acp_seen(tid: int) -> tuple:
    "([{t0, t1, n}], {path: at}) - the commit calls and the edits of every ACP session of the task, read off its kept record."
    from . import session_artifacts
    calls, paths = [], {}
    for f in sorted((session_artifacts.root() / str(int(tid))).glob('acp-*.jsonl')):
        try: st = f.stat(); key = (st.st_mtime, st.st_size)
        except OSError: continue
        if not ((hit := _SCAN.get(str(f))) and hit[0] == key): hit = _SCAN[str(f)] = (key, _scan(f))
        calls += hit[1][0]; paths.update(hit[1][1])
    return calls, paths


def own(store, tid: int, r: dict = None) -> dict:
    """{'commits': [sha, ...] oldest first, 'paths': {path: at}, 'at'} - the task's own commits (still on a local branch) and the files its
    edits wrote. Each commit call takes the newest commits made while it ran, as many as it made: never one from before it or after it."""
    r = r if r is not None else record(store, tid)
    cwd = r.get('cwd') or ''
    if not cwd or not os.path.isdir(cwd): return {'commits': [], 'paths': {}, 'at': ''}
    calls, seen_ = _acp_seen(tid)
    calls, paths = [*calls, *r.get('calls', [])], {**{q: t for k, t in seen_.items() if (q := _rel(cwd, k))}, **r.get('paths', {})}
    hist = [(x[0], int(x[1])) for l in _git(cwd, 'log', '--branches', '-n', '5000', '--format=%H %ct').splitlines()
            if len(x := l.split()) == 2 and x[1].isdigit()] if calls else []
    mine = {}
    for c in calls: mine.update([(h, t) for h, t in hist if c['t0'] - SLACK <= t <= c['t1'] + SLACK and h not in mine][:c['n']])   # newest first
    return {'commits': [h for h, _ in sorted(mine.items(), key=lambda x: x[1])], 'paths': paths, 'at': _stamp(max([*mine.values(), *paths.values()], default=0))}


def _numstat(out: str, got: dict = None) -> dict:
    got = {} if got is None else got
    for l in out.splitlines():
        p = l.split('\t')
        if len(p) < 3: continue
        f = got.setdefault(p[2], {'path': p[2], 'plus': 0, 'minus': 0})
        f['plus'] += int(p[0]) if p[0].isdigit() else 0; f['minus'] += int(p[1]) if p[1].isdigit() else 0
    return got


def _edited(cwd, paths) -> list:
    "Of the files the task's edits wrote, those still uncommitted in the checkout."
    d = set(dirty(cwd)) if paths else set()
    return [p for p in paths if p in d]


def _untracked(cwd, paths) -> list:
    return [l for l in _git(cwd, 'ls-files', '--others', '--exclude-standard', '--', *paths).splitlines() if l.strip()][:NEW_N] if paths else []


def _new_diff(cwd, f) -> str: return _run(cwd, 'diff', '--no-index', '--', '/dev/null', f)[1]    # git exits 1 when they differ: its output is the diff


def _own_files(cwd, o) -> list:
    got, ed = {}, _edited(cwd, list(o['paths']))
    for h in o['commits']: _numstat(_git(cwd, 'show', '--numstat', '--format=', h), got)
    if ed: _numstat(_git(cwd, 'diff', '--numstat', 'HEAD', '--', *ed), got)
    for n in _untracked(cwd, ed):
        try:
            with open(os.path.join(cwd, n), encoding='utf-8', errors='replace') as f: lines = sum(1 for _ in f)
        except OSError: lines = 0
        got.setdefault(n, {'path': n, 'plus': lines, 'minus': 0})
    return list(got.values())


def merged(diffs) -> str:
    """Several unified diffs as one, each file once: a file two commits touched is its first header with every part under it, in order - the
    way a pull request lists a file once however many commits changed it."""
    heads, parts = {}, {}
    for d in diffs:
        for blk in re.split(r'(?m)^(?=diff --git )', d or ''):
            if not blk.startswith('diff --git '): continue
            head, at, body = blk.partition('\n@@')
            k = blk.split('\n', 1)[0]
            heads.setdefault(k, head.rstrip('\n') + '\n'); parts.setdefault(k, [])
            if at: parts[k].append('@@' + body if body.endswith('\n') else '@@' + body + '\n')
    return ''.join(heads[k] + ''.join(parts[k]) for k in heads)


def _own_diff(cwd, o) -> str:
    ed = _edited(cwd, list(o['paths']))
    return merged([*(_git(cwd, 'show', '--format=', '-p', h) for h in o['commits']), _git(cwd, 'diff', 'HEAD', '--', *ed) if ed else '',
                   *(_new_diff(cwd, f) for f in _untracked(cwd, ed))])


def _fork(cwd, base, br, start) -> str:
    "Where the agent's own branch left its base - what a pull request of it starts from; the task's start where git cannot say."
    return _git(cwd, 'merge-base', base, br) or start


def state(store, tid: int, full: bool = False) -> dict | None:
    """What the task's work is, and the question to land it - None when no session of it started in a checkout. On a branch of its own: that
    branch against where it left its base. On the base itself, shared with every other agent and release: only its own commits and edits."""
    r = record(store, tid)
    # the checkout's HEAD is this task's branch only while its agent is the one in there: with a peer in the same checkout it may be the
    # peer's, so it is read then only at this task's own close (wrapup -> seen)
    if r.get('cwd') and _alone(tid, r['cwd']): r = seen(store, tid)
    cwd, base, start = r.get('cwd'), r.get('base'), r.get('start')
    if not (cwd and base and start and os.path.isdir(cwd)): return None
    br = r.get('branch') or ''
    mine = bool(br) and bool(sha(cwd, f'refs/heads/{br}'))
    o = None if mine else own(store, tid, r)
    files = (_stat(cwd, _fork(cwd, base, br, start), br) if mine else _own_files(cwd, o)) if sha(cwd, br if mine else base) else []
    ahead = int(_git(cwd, 'rev-list', '--count', f'{base}..{br}') or 0) if mine else 0
    out = {'task': task_ref(tid), 'cwd': cwd, 'repo': _repo(cwd), 'base': base, 'branch': br if mine else base, 'own': mine, 'ahead': ahead,
           'shared': not mine, 'commits': ahead if mine else len(o['commits']),
           'at': _stamp(int(_git(cwd, 'log', '-1', '--format=%ct', br) or 0)) if mine else o['at'],
           'files': files, 'changed': len(files), 'plus': sum(f['plus'] for f in files), 'minus': sum(f['minus'] for f in files),
           'landed': r.get('landed'), 'proposal': r.get('proposal')}
    out['push'] = None if mine else _unpushed(store, cwd, base, o['commits'], r.get('proposal'), out['repo'])
    out['ask'] = (mine and ahead > 0 and not r.get('landed')) or bool(out['push'])
    out['held'] = bool(out['ask'] and r.get('held'))             # the owner's Not now stands on it (hold): the card draws folded, no button lit
    hows = (OWN_HOW if mine else PUSH_HOW[:1 + bool((out['push'] or {}).get('deploy'))]) if out['ask'] else ()
    out['answers'] = [{'how': k, 'label': HOW[k]} for k in hows]
    out['line'] = said(out)
    if full: out['diff'] = (_git(cwd, 'diff', _fork(cwd, base, br, start), br) if mine else _own_diff(cwd, o))[:DIFF_CAP]
    return out


NEW_N = 40                           # new files read into one Changes diff: past this, the agent made a tree, not a fix


def changes(store, tid: int) -> dict | None:
    """THE TASK'S WORK SO FAR, AS ONE DIFF (the owner, 2026-11-06: "where is the diff button to see code changed?"): its own branch since it left
    the base - committed or not, new files too, while the agent works - or, on the shared base, its own commits and edits alone (own). None
    when no session of it started in a checkout."""
    r = record(store, tid)
    # ...its own branch as the checkout shows it, read as state() reads it: only while no peer's session is in the same checkout
    alone = bool(r.get('cwd')) and _alone(tid, r['cwd'])
    if alone: r = seen(store, tid)
    cwd, start, base, br = r.get('cwd'), r.get('start'), r.get('base'), r.get('branch') or ''
    if not (cwd and start and os.path.isdir(cwd) and sha(cwd, start)): return None
    mine = bool(br) and bool(sha(cwd, f'refs/heads/{br}'))
    if not mine: diff = _own_diff(cwd, own(store, tid, r))
    # ...the working tree is its own branch's only while that branch is checked out and no peer works in it - else what it committed is its
    elif alone and head_branch(cwd) == br:
        new = [l for l in _git(cwd, 'ls-files', '--others', '--exclude-standard').splitlines() if l.strip()][:NEW_N]
        diff = '\n'.join([_git(cwd, 'diff', _fork(cwd, base, br, start)), *(_new_diff(cwd, f) for f in new)])
    else: diff = _git(cwd, 'diff', _fork(cwd, base, br, start), br)
    return {'base': base, 'start': start[:7], 'since': r.get('at'), 'shared': not mine, 'diff': diff[:DIFF_CAP], 'cut': len(diff) > DIFF_CAP}


_BRANCH = re.compile(r'(?!-)(?!.*(?:\.\.|//|@\{|\.lock$|/$|\.$))[A-Za-z0-9._/-]{1,100}')
def _branch_ok(b) -> bool: return bool(_BRANCH.fullmatch(str(b or '')))    # git's own ref rules, the ones a name typed by an agent breaks


def _deploy_to(store, prop, repo) -> str:
    "The branch a push deploys to: the agent's proposal, else the one the owner last deployed this repo to - '' when neither says."
    d = (prop or {}).get('deploy') or (store.get_setting(f'{DEPLOY_KEY}:{repo.lower()}', '') if repo else '')
    return d if _branch_ok(d) else ''


def _unpushed(store, cwd, base, commits, prop, repo) -> dict | None:
    """The task's own commits on the shared base that origin does not have yet: {'tip', 'ahead', 'to', 'deploy'} - None when there is no
    origin to push to, or nothing of its own left to push. The tip is its newest own commit still on the base."""
    up = sha(cwd, f'refs/remotes/origin/{base}')
    if not (up and commits): return None
    tip = ''                                     # the newest by the graph, not the clock: two commits in one second sort either way
    for c in commits:
        if is_ancestor(cwd, c, base) and (not tip or is_ancestor(cwd, tip, c)): tip = c
    if not tip or is_ancestor(cwd, tip, up): return None
    return {'tip': tip, 'ahead': int(_git(cwd, 'rev-list', '--count', f'{up}..{tip}') or 0), 'to': base, 'deploy': _deploy_to(store, prop, repo)}


def said(s: dict) -> str:
    "One line: what changed and what is asked."
    if not s: return ''
    n = f"{plural(s['changed'], 'file')} changed, +{s['plus']} -{s['minus']}"
    if s.get('landed'): return f"{s['branch']} landed ({HOW.get(s['landed'].get('how'), s['landed'].get('how'))}) - {n}."
    if (p := s.get('push')): return (f"{plural(p['ahead'], 'commit')} on {s['base']} not on origin yet, up to {p['tip'][:7]}: {n}. Push it"
                                     + (f" and deploy it to {p['deploy']}?" if p['deploy'] else '?'))
    if s['ask']: return f"{s['branch']} is {plural(s['ahead'], 'commit')} ahead of {s['base']}: {n}. How should it land?"
    if s['own']: return f"{s['branch']} has nothing {s['base']} does not already have."
    return f"The agent worked on {s['base']} itself, shared with other agents - {n} by its own commits and edits; there is no branch of its own to land."


def _repo(cwd) -> str:
    from . import shellgate
    return shellgate.repo_of(cwd)


def propose(store, tid: int, how: str, why: str = '', actor: str = 'agent', deploy: str = '') -> dict:
    """The agent's own read of how its work should land: the close-out's question shows it marked. It lands nothing. On the shared base
    that is a push - `deploy` names the branch a push to deploys (the card's Push & deploy)."""
    how, deploy = str(how or '').strip().lower(), str(deploy or '').strip()
    if how not in HOW: raise ValueError(f"how is one of: {', '.join(HOW)}")
    if deploy and not _branch_ok(deploy): raise ValueError(f'{deploy!r} is not a branch name to deploy to')
    if how == 'push' and deploy: how = 'deploy'
    if how == 'deploy' and not deploy: raise ValueError('deploy needs the branch it deploys to: `deploy`')
    if (w := asked_again(store, tid)): raise ValueError(w)
    r = record(store, tid)
    if deploy:                                    # ...read into the question below: its Push & deploy button is drawn from it
        r['proposal'] = {**(r.get('proposal') or {}), 'deploy': deploy}; _save(store, tid, r)
    s = state(store, tid)
    if not s: raise ValueError('no session of this task started in a git checkout - there is nothing to land')
    if not s['ask']: raise ValueError(s['line'])
    if how == 'discard' and not s['own']: raise ValueError('discard is only for a branch of your own')
    if how not in {a['how'] for a in s['answers']}: raise ValueError(f"how is one of: {', '.join(a['how'] for a in s['answers'])} here - {s['line']}")
    r = record(store, tid)
    r['proposal'] = {'how': how, 'why': ' '.join(str(why or '').split())[:400], 'at': time.strftime('%Y-%m-%d %H:%M:%S'), **({'deploy': deploy} if deploy else {})}
    _save(store, tid, r)
    store.add_comment(tid, actor, 'agent', f"Proposes to land {s['branch']}: {HOW[how]}" + (f' to {deploy}' if deploy else '') + (f" - {r['proposal']['why']}" if r['proposal']['why'] else '') + '.')
    store.audit('task', tid, 'land_proposed', actor, detail={'how': how})
    try:                                          # ...and asked on a chat bound to the task (agentchannels.py): answered there by the owner alone
        from . import agentchannels
        agentchannels.landing_proposed(store, tid)
    except Exception as e: logger.debug(f'{task_ref(tid)}: the landing question was not put on its channel - {e}')
    return {'ok': True, 'says': f"The owner sees the landing question with {HOW[how]} marked - nothing lands until they answer it."}


# A GIT ACT PROPOSED ANY WAY IS THE CARD'S BUTTONS (the owner, 2026-11-09: "actions should be cards/buttons"): `propose {"action": "push"}`,
# a TASKUARY-PROPOSE mark of `land` or `open_pr` - with "Agents may push / deploy" off a land/open_pr proposal was REFUSED, and the agent,
# left with no road, asked "go ahead?" in words. On a task whose work is in a checkout each is the landing card's question instead: the
# owner's press is the push, so no agent switch gates it. Elsewhere (no checkout, nothing to land) the proposal goes its old way.
GIT_ACTS = {'push': 'push', 'deploy': 'push', 'push_direct': 'push', 'land': '', 'open_pr': 'pr'}


def from_proposal(store, tid: int, p: dict) -> dict | None:
    "A proposed git act as the landing card's question (propose) - None when it is not one, or the task has nothing to land."
    a = str((p or {}).get('action') or '').strip()
    if a not in GIT_ACTS: return None
    s = state(store, tid)
    if not (s and s['ask']): return None
    how = 'pr' if s['own'] and GIT_ACTS[a] in ('', 'pr') else 'push' if not s['own'] else GIT_ACTS[a]
    if s['own'] and how == 'push': how = 'pr'                     # a branch of its own goes out as a pull request, never straight over the base
    return propose(store, tid, how, str(p.get('why') or ''), deploy=str(p.get('deploy') or p.get('target') or '') if not s['own'] else '')


# AN AGENT'S OWN `git push` IS THE CARD'S QUESTION TOO (the agent walk, 2026-11-09). Told to call propose_land, a coding agent ran
# `git add ... && git commit ... && git push` in its shell instead, and the owner got "THE AGENT ASKS - It wants to run ..." with Allow once /
# Reject - the line cut mid-word, the push not on it - beside a card built to ask it with one Push. A plain push of the task's own work from
# its own checkout is that card's question, on every road a shell step is held by (shellgate.check, acpgate.decide). What the button is
# not - forced, tags, a delete, another remote or checkout, a push inside another shell's string - is held the way any other step is.
_PUSH_OPTS = frozenset('-u --set-upstream -q --quiet -v --verbose --progress --porcelain'.split())
_TO_NOWHERE = re.compile(r'\s\d?>{1,2}\s*(?:&\d|/dev/null|\$null|nul)(?=\s|$|[;&|)])', re.I)     # `2>&1`, `>/dev/null`: no part of what is pushed
_MOVES = frozenset('cd pushd popd chdir set-location sl'.split())


def _push_of(argv: list) -> tuple | None:
    "(src, dst) of one plain `git push [origin [src[:dst]]]`, '' where git's own default decides - None for anything else."
    from .shellgate import _name
    if len(argv) < 2 or _name(argv[0]) != 'git' or argv[1] != 'push': return None
    opts, w = {t for t in argv[2:] if t.startswith('-')}, [t for t in argv[2:] if not t.startswith('-')]
    if opts - _PUSH_OPTS or len(w) > 2 or w[:1] not in ([], ['origin']): return None
    src, _, dst = (w[1] if len(w) > 1 else '').partition(':')
    if src.startswith('+') or (len(w) > 1 and not src): return None             # forced, or `:branch` - a delete
    return src, dst or src


def _top(cwd) -> str: return os.path.normcase(os.path.realpath(_git(cwd, 'rev-parse', '--show-toplevel') or cwd))


def push_asked(store, tid: int, cmd: str, cwd: str = '', about: str = '') -> tuple | None:
    """A shell line that pushes this task's own work, as the card's question. (True, words for the agent): the push is on the card, marked.
    (False, words): the line does more than push - none of it runs, and the agent is told to ask with propose_land after the rest.
    None: the card's buttons are not this push (or there is no card: Developer mode off, no checkout) - held like any other step."""
    from . import agents, shellgate
    from .browsergate import _segments
    r = record(store, tid)
    if not (cwd and r.get('cwd') and agents.developer_mode(store)): return None
    todo, segs = shellgate.acts(cmd, cwd), _segments(_TO_NOWHERE.sub(' ', str(cmd or ''))) or []
    pushes = [p for a in segs if (p := _push_of(a))]
    if not todo or len(pushes) != len(todo) or any(a['what'] != shellgate.GIT['push'] for a in todo): return None
    if any(shellgate._words(a)[0] in _MOVES for a in segs) or _top(cwd) != _top(r['cwd']): return None
    s = state(store, tid)
    if not s: return None
    cur, to = head_branch(cwd), set()
    for src, dst in pushes:
        src, dst = (cur if x in ('', 'HEAD') else x.removeprefix('refs/heads/') for x in (src, dst))
        if not src or src != s['branch'] or (s['own'] and dst != src) or not _branch_ok(dst): return None
        to.add(dst)
    live = set() if s['own'] else to - {s['base']}
    if len(live) > 1: return None
    how, deploy = 'pr' if s['own'] else 'push', next(iter(live), '')
    button = HOW['deploy' if deploy else how]
    if len(segs) > len(pushes):                   # the commit in the same line has not run: there is nothing to put on the card yet
        return False, (f"Taskuary did not run this line: a push from this task's checkout is the owner's {button} button, never a shell step. Run "
                       f"the rest of it without the push, then call propose_land (how {how}{f', deploy {deploy}' if deploy else ''}) - they get "
                       "the button, and Taskuary tells you when it went.")
    if not s['ask']: return None
    if (w := asked_again(store, tid)): return True, f'{shellgate.HELD}: {w}'       # ...no second card for a push they put off
    try:
        if ((s['proposal'] or {}).get('how'), (s['proposal'] or {}).get('deploy') or '') != ('deploy' if deploy else how, deploy):
            propose(store, tid, how, about, deploy=deploy)
    except ValueError: return None
    return True, (f"{shellgate.HELD}: this push is the owner's {button} button on the task now, not a shell step - {state(store, tid)['line']} Nothing "
                  "is pushed until they press it, and Taskuary tells you when it went. Do not push another way. The button is the ask: say in "
                  "one line what waits on it - never ask in words. End your turn now, or go on with work that does not need it.")


# NOT NOW (the owner, 2026-11-10: 'Add "Not now"'). The question had no answer but its buttons: an owner not ready to push left the card
# standing lit, and the agent - never told - asked again a turn later. Not now is a press of its own: nothing goes, the card folds (state
# 'held' - its buttons stay, none filled), it is a line in the chat and the agent hears it with their next words (general.PRESSES). Asked
# again before the owner has written on the task, the agent is refused in these words; after, asking is its own to judge from what they
# wrote - no word list here - and its ask unfolds the card. Their own press on the folded card is the answer as it always was (land).
NOT_NOW = ("The owner pressed Not now on this: nothing is pushed or landed, and the question waits folded on the task for their own press. "
           "Do not ask for it again - in words, by a tool or by running it - until they write that they want it. Go on with work that does "
           "not need it, or end your turn.")


def _wrote_since(store, tid: int, after) -> bool:
    "The owner has written a line of their own on the task after comment `after` - Taskuary's briefs are not theirs."
    from .general import BRIEF_ACTOR, USER_TYPE
    return bool(store._one('SELECT 1 AS x FROM comment WHERE TaskId=? AND CommentId>? AND ActorType=? AND Actor<>? LIMIT 1',
                           (int(tid), int(after or 0), USER_TYPE, BRIEF_ACTOR)))


def asked_again(store, tid: int) -> str:
    "NOT_NOW for an agent asking to land over the owner's Not now - '' with none standing; one the owner has written since is lifted here."
    r = record(store, tid)
    if not (h := r.get('held')): return ''
    if not _wrote_since(store, tid, h.get('after')): return NOT_NOW
    r.pop('held'); _save(store, tid, r)
    return ''


def hold(store, tid: int, actor: str = 'owner') -> dict:
    "The owner's Not now on the landing question: nothing lands, and it stands until they press the card or write on the task."
    s = state(store, tid)
    if not s or not s['ask']: raise ValueError((s or {}).get('line') or 'nothing waits to land on this task')
    r = record(store, tid)
    r['held'] = {'at': time.strftime('%Y-%m-%d %H:%M:%S'),
                 'after': (store._one('SELECT MAX(CommentId) AS n FROM comment WHERE TaskId=?', (int(tid),)) or {}).get('n') or 0}
    _save(store, tid, r)
    store.audit('task', tid, 'land_held', actor, detail={'what': 'push' if s['push'] else 'landing'})
    return {'ok': True, 'held': True, 'says': 'Not now - nothing went out. It waits on the task for your press.'}


def asked(store, tid) -> bool:
    "Does a landing question of the agent's wait, as the record alone says it (no git - a rail build asks): it proposed one, nothing landed since."
    r = record(store, tid); p = r.get('proposal') or {}
    return bool(p) and str((r.get('landed') or {}).get('at') or '') < str(p.get('at') or '')


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
    if how not in {a['how'] for a in s['answers']}: raise ValueError(f"{HOW[how]} is not offered here - {s['line']}")
    if (r := record(store, tid)).pop('held', None): _save(store, tid, r)       # their own press is the answer Not now put off
    if how in PUSH_HOW: return _push(store, tid, s, how, actor)
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
        said_ = f"Discarded {br} - its {plural(s['ahead'], 'commit')} are gone from {base}'s checkout."
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
    cwd, br = s['cwd'], s['branch']
    start = _fork(cwd, s['base'], br, record(store, tid).get('start'))           # the parts as the card's diff numbered them (state)
    if (head := head_branch(cwd)) != br: raise Refused(f'reverting a part needs {br} checked out in {cwd}; it is on {head or "a detached HEAD"} - nothing changed')
    if any(norm(t.cwd) == norm(cwd) for t in peers.working(at_rest=False)):
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
        msg = f"Revert {plural(n, 'part')} turned down in review ({task_ref(tid)})"
        rc, out, err = _run(cwd, 'commit', '-q', '-m', msg, '--', *by)
        if rc:
            _run(cwd, 'apply', '--whitespace=nowarn', f.name)          # put the tree back as it was: the revert is all or nothing
            raise Refused(f'the revert could not be committed: {(err or out)[:200]} - nothing changed')
    finally:
        try: os.unlink(f.name)
        except OSError: pass
    said_ = f"Reverted {plural(n, 'part')} of {', '.join(by)} on {br} ({sha(cwd, br)[:7]})."
    store.add_comment(tid, actor, 'human', said_)
    store.audit('task', tid, 'land_review_revert', actor, detail={'files': list(by)[:30], 'parts': n})
    return {'ok': True, 'says': said_, 'state': state(store, tid)}


def _landed(store, tid, how, said_, actor, at_sha='', **extra) -> dict:
    r = record(store, tid)
    r['landed'] = {'how': how, 'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'sha': at_sha, **extra}
    _save(store, tid, r)
    store.add_comment(tid, actor, 'human', said_)
    store.audit('task', tid, 'landed', actor, detail={'how': how, 'sha': at_sha[:12], **extra})
    # ...AND THE AGENT GOES ON, as it does after a push (_push): a branch landed or a pull request opened was the press its turn waited on
    # (the owner, 2026-11-09: "when you hit approve the agent continues and says what it did and what the next steps are")
    if how not in PUSH_HOW:
        try:
            from . import waitroom
            from .browsergate import NEXT
            waitroom.add(store, tid, f"{said_} The owner pressed {HOW[how]} on your branch. {NEXT}", 'router')
        except Exception as e: logger.debug(f'{task_ref(tid)}: the landing was not handed back to the agent - {e}')
    return {'ok': True, 'how': how, 'says': said_, **extra}


def _push(store, tid, s, how, actor) -> dict:
    """Push the task's own commits on the shared base: origin/<base> up to its newest one, and for Push & deploy that commit to the deploy
    branch too. Never forced - a branch that moved refuses, and says what was and was not pushed. Kept as ci's PUSHED mark, so the CI watch
    follows it as it follows any push."""
    from . import ci
    cwd, base, p = s['cwd'], s['base'], s['push']
    tip, done = p['tip'], []
    for b in [base] + ([p['deploy']] if how == 'deploy' else []):
        rc, out, err = _run(cwd, 'push', 'origin', f'{tip}:refs/heads/{b}', timeout=180)
        if rc:
            why = ci.TOKEN_URL.sub('https://', (err or out))[:300]
            fix = ' - pull and rebase, then push again (never forced)' if re.search(r'non-fast-forward|fetch first|rejected', why) else ''
            raise Refused(f"the push of {tip[:7]} to {b} was refused: {why}{fix}" + (f' - {done[0]} was pushed' if done else ' - nothing was pushed'))
        done.append(b)
    if how == 'deploy' and s['repo']: store.set_setting(f"{DEPLOY_KEY}:{s['repo'].lower()}", p['deploy'], actor)
    ci._save_push(store, tid, {'repo': s['repo'], 'branch': base, 'from': base, 'sha': tip, 'commits': p['ahead'], 'state': 'pushed',
                               'url': f"https://github.com/{s['repo']}/commit/{tip}" if s['repo'] else '', 'checks': None, 'checked_at': None}, actor)
    said_ = f"Pushed {plural(p['ahead'], 'commit')} to origin/{base} ({tip[:7]})" + (f" and deployed it to {p['deploy']}." if how == 'deploy' else '.')
    out = _landed(store, tid, how, said_, actor, tip, **({'deploy': p['deploy']} if how == 'deploy' else {}))
    try:                                          # ...the press was the go-ahead the agent waits on: its next turn checks it and finishes
        from . import waitroom
        waitroom.add(store, tid, f"{said_} The owner pressed {HOW[how]} on your proposal. " + ("Check it is live, then finish."
                     if how == 'deploy' else "Finish the task."), 'router')
    except Exception as e: logger.debug(f'{task_ref(tid)}: the push was not handed back to the agent - {e}')
    return out


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
