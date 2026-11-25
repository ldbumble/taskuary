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


def _push_as_agent(cwd, *args, timeout=180) -> tuple:
    """A push his press makes, run as the agent's own `git push` would run (shellgate.run_: its shell, its git, its credentials) - never
    Taskuary's own git, which on his machine is not always the one that can push. -> (exit code, what git said, '')."""
    import shlex
    from .shellgate import run_
    try: rc, said = run_({'command': 'git ' + ' '.join(shlex.quote(str(a)) for a in args), 'shell': 'Bash'}, cwd, timeout)
    except Exception as e: return 1, '', str(e)
    return rc, said.strip(), ''


def _git(cwd, *args) -> str: return _ok(_run(cwd, *args))
def _ok(r: tuple) -> str: return r[1] if r[0] == 0 else ''


def head_branch(cwd) -> str:
    b = _git(cwd, 'rev-parse', '--abbrev-ref', 'HEAD')
    return '' if b in ('', 'HEAD') else b


def sha(cwd, ref) -> str: return _git(cwd, 'rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}')
# ...by name, never by `status --porcelain`'s columns: _git strips its output, and the first line's " M " lost a character of the file's name
def dirty(cwd) -> list:
    return [l for l in [*_git(cwd, 'diff', '--name-only', 'HEAD').splitlines(), *_git(cwd, 'ls-files', '--others', '--exclude-standard').splitlines()] if l.strip()]
def is_ancestor(cwd, a, b) -> bool: return _fixed(cwd, 'merge-base', '--is-ancestor', a, b)[0] == 0


_FIXED, _SHA = {}, re.compile(r'[0-9a-f]{40}')
def _fixed(cwd, *args) -> tuple:
    """`_run`, kept where every ref it names is a commit's own sha: what git says of those never changes. A coding task's card asked git the
    same eight questions of its commits on every poll, ~0.1 s a process on Windows (the owner's live app, 2026-11-19: /landing 23 s)."""
    refs = [x for x in args if not x.startswith('-')][1:]
    if not refs or not all(_SHA.fullmatch(x) for x in refs): return _run(cwd, *args)
    k = (os.path.normcase(os.path.abspath(cwd)), args)
    if k not in _FIXED and (got := _run(cwd, *args))[0] in (0, 1): _FIXED[k] = got        # ...an answer, never a failure to give one
    return _FIXED.get(k) or _run(cwd, *args)
def conflicted(cwd) -> list: return [l for l in _git(cwd, 'diff', '--name-only', '--diff-filter=U').splitlines() if l.strip()]


def record(store, tid: int) -> dict:
    try: return json.loads(store.get_setting(f'{KEY}:{int(tid)}') or '{}') or {}
    except (TypeError, ValueError): return {}


def _save(store, tid: int, r: dict): store.set_setting(f'{KEY}:{int(tid)}', json.dumps(r), 'system')
def keep_then(store, tid: int, then: str):
    "The agent's own step after his press on the landing question it just raised (card.raising) - '' for none."
    if (r := record(store, tid)).get('proposal'):
        r['proposal'] = {**{k: v for k, v in r['proposal'].items() if k != 'then'}, **({'then': then} if then else {})}; _save(store, tid, r)


def mark_start(store, tid: int, cwd: str) -> dict | None:
    """Where this task's work starts from: the checkout, its branch and its HEAD - once, at its first session; a Continue keeps the first."""
    if record(store, tid).get('start') or not cwd or not os.path.isdir(cwd): return None
    start, base = sha(cwd, 'HEAD'), head_branch(cwd)
    if not start or not base: return None                      # not a git checkout, or a detached HEAD: nothing to land later
    r = {'cwd': cwd, 'base': base, 'start': start, 'at': time.strftime('%Y-%m-%d %H:%M:%S')}
    _save(store, tid, r)
    return r


# A CHECKOUT THE OWNER NAMED IS THE TASK'S, WHATEVER AGENT WORKS IT (design round 5, 2026-11-19: "fix the rounding bug - my checkout is at
# <path>" from New, on both CLIs. The fix was committed there, and the push was a dead end - a raw shell card in the agent's own folder on
# one, "only you can grant that folder access in Settings -> Agents" on the other). His naming it is the go-ahead (readgate.named): its
# first push asked - a `git push` there, or `propose` push - adopts it as where the task's work is, and the Push card asks it whatever the
# task's kind or Developer mode. Its own commits are the ones made there since the task began that no remote has yet (own).
def top(cwd) -> str: return _git(cwd, 'rev-parse', '--show-toplevel') if cwd and os.path.isdir(cwd) else ''


def named(store, tid: int) -> list:
    "The git checkouts the owner named in his own words on the task - each its top folder."
    from . import readgate
    return list(dict.fromkeys(t for d in readgate.named(store, tid) if (t := top(d))))


def adopt(store, tid: int, cwd: str = '') -> dict:
    """The task's landing record: kept as it is where it has one; else the checkout the owner named that `cwd` is in (none given: the one he
    named, where he named one), marked `named`. {} where neither."""
    r = record(store, tid)
    if r.get('cwd'): return r
    ns = named(store, tid)
    norm = lambda p: os.path.normcase(os.path.realpath(p))
    at = top(cwd) if cwd else (ns[0] if len(ns) == 1 else '')
    if not at or norm(at) not in map(norm, ns): return {}
    if not (r := mark_start(store, tid, at) or {}): return {}
    r['named'] = True; _save(store, tid, r)
    store.audit('task', int(tid), 'checkout_named', 'agent', detail={'cwd': at})
    return r


def shown(store, tid: int) -> bool:
    "The landing card is drawn: Developer mode on, or the work is in a checkout the owner named on this task (adopt)."
    from . import agents
    return agents.developer_mode(store) or bool(record(store, tid).get('named'))


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


def _seen_fold(st: tuple, u: dict):
    "One update into ([{t0, t1, n}], {path: at}, {call id: its start and command}) - read once, as it is appended (codingchat.follow)."
    c, p, calls = st
    if u.get('sessionUpdate') not in ('tool_call', 'tool_call_update'): return
    t = _epoch(u.get('_at'))
    o = calls.setdefault(str(u.get('toolCallId') or ''), {'t0': t, 'cmd': ''})
    if (cmd := _cmd((u.get('rawInput') or {}).get('command'))): o['cmd'] = cmd
    for b in u.get('content') or []:
        if isinstance(b, dict) and b.get('type') == 'diff' and b.get('path'): p[str(b['path'])] = t
    for l in (u.get('locations') or []) if u.get('kind') == 'edit' else []:
        if isinstance(l, dict) and l.get('path'): p[str(l['path'])] = t
    if u.get('status') in ('completed', 'failed') and (n := len(_COMMIT.findall(o['cmd']))): c.append({'t0': o['t0'] or t, 't1': t, 'n': n}); o['cmd'] = ''


def _acp_seen(tid: int) -> tuple:
    "([{t0, t1, n}], {path: at}) - the commit calls and the edits of every ACP session of the task, read off its kept record."
    from . import codingchat, session_artifacts
    calls, paths = [], {}
    for f in sorted((session_artifacts.root() / str(int(tid))).glob('acp-*.jsonl')):
        c, p = codingchat.follow(f, _seen_fold, lambda: ([], {}, {}), lambda st: (list(st[0]), dict(st[1])))
        calls += c; paths.update(p)
    return calls, paths


def own(store, tid: int, r: dict = None) -> dict:
    """{'commits': [sha, ...] oldest first, 'paths': {path: at}, 'at'} - the task's own commits (still on a local branch) and the files its
    edits wrote. Each commit call takes the newest commits made while it ran, as many as it made: never one from before it or after it."""
    r = r if r is not None else record(store, tid)
    cwd = r.get('cwd') or ''
    if not cwd or not os.path.isdir(cwd): return {'commits': [], 'paths': {}, 'at': ''}
    if r.get('named'):                            # ...his checkout, adopted after its commits were made: what no remote has, made since the task began
        since = _stamp(_epoch((store.get_task(int(tid)) or {}).get('CreatedAt') or r.get('at')) + 1)   # ...not one in the second it was made: before it
        cs = _git(cwd, 'rev-list', '--reverse', f'--since={since}', '--max-count=200', 'HEAD', '--not', '--remotes').split()
        return {'commits': cs, 'paths': r.get('paths', {}), 'at': _stamp(int(_git(cwd, 'log', '-1', '--format=%ct', cs[-1]) or 0)) if cs else ''}
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
    for h in o['commits']: _numstat(_ok(_fixed(cwd, 'show', '--numstat', '--format=', h)), got)
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
           # ...WHERE IT STANDS IN THE CHAT: when its newest change came in - and once pushed on the shared base, where none of its own is
           # left to date it by, when it landed (the card gallery, 2026-11-25: the Push card had no place from its press on and was gone
           # from the chat - a line under the turn said what the card should have)
           'at': _stamp(int(_git(cwd, 'log', '-1', '--format=%ct', br) or 0)) if mine else o['at'] or (r.get('landed') or {}).get('at', ''),
           'files': files, 'changed': len(files), 'plus': sum(f['plus'] for f in files), 'minus': sum(f['minus'] for f in files),
           'landed': r.get('landed'), 'proposal': r.get('proposal')}
    out['name'] = out['repo'] or os.path.basename(os.path.normpath(cwd))      # ...the card names the repository it pushes to
    out['push'] = None if mine else _unpushed(store, cwd, base, o['commits'], r.get('proposal'), out['repo'])
    out['noRemote'] = bool(not mine and o['commits'] and not has_origin(cwd))
    out['ask'] = (mine and ahead > 0 and not r.get('landed')) or bool(out['push'])
    # ...a question the agent RAISED (its proposal) is passed once the conversation moves on (proposals.move_on): greyed, nothing pressable,
    # until the agent raises it again. Unpushed work with no proposal is the checkout's own fact, raised by no turn - it stays live
    # ...AND SO IS ONE NO TURN RAISED, once the chat moved on past it (the owner, 2026-11-16: "Push 2 commits to master and deploy" stood lit
    # above his newer line, and he scrolled up to press it): every card greys in place as an input comes after it - one rule (proposals._older)
    from . import proposals
    from .conversation import ep
    p_ = r.get('proposal') or {}
    since, moved = ep(p_.get('at') or out.get('at')), max(float(r.get('moved') or 0), proposals.moved_on(store, tid))
    out['passed'] = bool(out['ask'] and not r.get('landed') and (p_.get('passed') or since and moved > since))
    if out['passed']: out['ask'] = False
    # ...and a passed one keeps its answers: the page draws it as the card it was, its buttons greyed (the owner, 2026-11-18) - a press still
    # needs `ask` (land), so nothing it names can go
    hows = (OWN_HOW if mine else PUSH_HOW[:1 + bool((out['push'] or {}).get('deploy'))]) if out['ask'] or out['passed'] else ()
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
    # ...an origin with no copy of the base here yet (added, never fetched - the agent's `git remote add`): its push makes it
    if not (commits and (up or has_origin(cwd))): return None
    tip, on = '', sha(cwd, base) or base        # the newest by the graph, not the clock: two commits in one second sort either way
    for c in commits:
        if is_ancestor(cwd, c, on) and (not tip or is_ancestor(cwd, tip, c)): tip = c
    if not tip or (up and is_ancestor(cwd, tip, up)): return None
    ahead = int(_git(cwd, 'rev-list', '--count', f'{up}..{tip}') or 0) if up else sum(is_ancestor(cwd, c, tip) for c in commits)
    return {'tip': tip, 'ahead': ahead, 'to': base, 'deploy': _deploy_to(store, prop, repo)}


def has_origin(cwd) -> bool: return _run(cwd, 'remote', 'get-url', 'origin')[0] == 0
NO_REMOTE = "this checkout has no remote to push to"


def said(s: dict) -> str:
    "One line: what changed and what is asked."
    if not s: return ''
    n = f"{plural(s['changed'], 'file')} changed, +{s['plus']} -{s['minus']}"
    if s.get('landed'): return f"{s['branch']} landed ({HOW.get(s['landed'].get('how'), s['landed'].get('how'))}) - {n}."
    if (p := s.get('push')): return (f"{plural(p['ahead'], 'commit')} on {s['base']} of {s['name']} not on origin yet, up to {p['tip'][:7]}: {n}. Push it"
                                     + (f" and deploy it to {p['deploy']}?" if p['deploy'] else '?'))
    if s.get('noRemote'): return f"{plural(s['commits'], 'commit')} on {s['base']} of {s['name']}, not pushed - {NO_REMOTE}: {n}."
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
    r = record(store, tid)
    # ...raised again after it was passed (pass_over): asking is the agent's to judge, never refused - its card is live again
    prev = dict(r.get('proposal') or {})
    # ...asked now, it is after every input it heard - in that input's own second too (`moved`, pass_over)
    if [(r.get('proposal') or {}).pop('passed', None), r.pop('moved', None)] != [None, None]: _save(store, tid, r)
    if deploy:                                    # ...read into the question below: its Push & deploy button is drawn from it
        r['proposal'] = {**(r.get('proposal') or {}), 'deploy': deploy}; _save(store, tid, r)
    s = state(store, tid)
    if not s:
        from .agenttools import refusal
        raise ValueError(refusal('no session of this task started in a git checkout - there is nothing to land yet',
                                 'work in the checkout the change belongs in - use_repo picks it (find_repos lists them)'))
    if s.get('noRemote'): raise ValueError(f"{s['line']} The owner sees that on the card. Where he gave you its address, `git remote add origin <url>` "
                                           "and ask for the push again; else ask him for it in one question.")
    if not shown(store, tid):                     # ...a card the page would not draw is never told to its agent as on his screen (round 6, D1)
        from .agenttools import refusal
        raise ValueError(refusal('no Push card can be drawn here: Developer mode is off and this is not a checkout the owner named on this task',
                                 'ask him in one question for the folder of his checkout this work belongs in'))
    if not s['ask']: raise ValueError(s['line'])
    if how == 'discard' and not s['own']: raise ValueError('discard is only for a branch of your own')
    if how not in {a['how'] for a in s['answers']}: raise ValueError(f"how is one of: {', '.join(a['how'] for a in s['answers'])} here - {s['line']}")
    r = record(store, tid)
    # ...and asked again while it still stands (a press refused, a better why) it keeps its place in the line of cards (cardqueue): recorded
    # on the real CLI, 2026-11-16 - a Push refused and raised again went behind the email announcing it, and the agent took the email back
    stands = prev.get('at') and not prev.get('passed') and str((r.get('landed') or {}).get('at') or '') < str(prev['at'])
    r['proposal'] = {'how': how, 'why': ' '.join(str(why or '').split())[:400], 'at': time.strftime('%Y-%m-%d %H:%M:%S'), **({'deploy': deploy} if deploy else {}),
                     **({'first': prev.get('first') or prev['at']} if stands else {})}
    _save(store, tid, r)
    store.add_comment(tid, actor, 'agent', f"Proposes to land {s['branch']}: {HOW[how]}" + (f' to {deploy}' if deploy else '') + (f" - {r['proposal']['why']}" if r['proposal']['why'] else '') + '.')
    store.audit('task', tid, 'land_proposed', actor, detail={'how': how})
    try:                                          # ...and asked on a chat bound to the task (agentchannels.py): answered there by the owner alone
        from . import agentchannels
        agentchannels.landing_proposed(store, tid)
    except Exception as e: logger.debug(f'{task_ref(tid)}: the landing question was not put on its channel - {e}')
    return {'ok': True, 'says': where(store, tid, how)}


def where(store, tid: int, how: str) -> str:
    "Where the landing card the agent just raised stands, as the page draws it (cardqueue.state) - never 'on his screen' while it waits its turn."
    from . import cardqueue
    q = cardqueue.state(store, int(tid))
    if cardqueue.LAND in q['live']: return f"The owner sees the {HOW[how]} card now - nothing lands until they press it; you are told when they do."
    return (f"The {HOW[how]} card is raised but NOT on his screen yet: it comes forward once the card before it is answered. Say that if you "
            "name it - never that it waits for his press now.")


# A GIT ACT PROPOSED ANY WAY IS THE CARD'S BUTTONS (the owner, 2026-11-09: "actions should be cards/buttons"): `propose {"action": "push"}`,
# a TASKUARY-PROPOSE mark of `land` or `open_pr` - with "Agents may push / deploy" off a land/open_pr proposal was REFUSED, and the agent,
# left with no road, asked "go ahead?" in words. On a task whose work is in a checkout each is the landing card's question instead: the
# owner's press is the push, so no agent switch gates it. Elsewhere (no checkout, nothing to land) the proposal goes its old way.
GIT_ACTS = {'push': 'push', 'deploy': 'push', 'push_direct': 'push', 'land': '', 'open_pr': 'pr'}


def from_proposal(store, tid: int, p: dict) -> dict | None:
    "A proposed git act as the landing card's question (propose) - None when it is not one, or the task has nothing to land."
    a = str((p or {}).get('action') or '').strip()
    if a not in GIT_ACTS: return None
    if a in ('push', 'deploy'): adopt(store, tid, str(p.get('cwd') or p.get('folder') or p.get('path') or ''))   # ...his named checkout, where it is one
    s = state(store, tid)
    if a in ('push', 'deploy') and not s:
        from .agenttools import refusal
        raise ValueError(refusal('this task has no checkout to push from', 'give `cwd`: the git checkout the owner named for this work'))
    if s and s.get('noRemote'): return propose(store, tid, 'push')        # ...refused with why, and the way past
    if not (s and (s['ask'] or s.get('passed'))): return None        # ...a passed question is raised again
    how = 'pr' if s['own'] and GIT_ACTS[a] in ('', 'pr') else 'push' if not s['own'] else GIT_ACTS[a]
    if s['own'] and how == 'push': how = 'pr'                     # a branch of its own goes out as a pull request, never straight over the base
    return propose(store, tid, how, str(p.get('why') or ''), deploy=str(p.get('deploy') or p.get('target') or '') if not s['own'] else '')


# AN AGENT'S OWN `git push` IS THE CARD'S QUESTION TOO (the agent walk, 2026-11-09). Told to call propose_land, a coding agent ran
# `git add ... && git commit ... && git push` in its shell instead, and the owner got "THE AGENT ASKS - It wants to run ..." with Allow once /
# Reject - the line cut mid-word, the push not on it - beside a card built to ask it with one Push. A plain push of the task's own work from
# its own checkout is that card's question, on every road a shell step is held by (shellgate.check, gate.tool_call). What the button is
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


def _where(segs, cwd) -> str | None:
    "The folder a line's pushes run in: `cwd`, moved by each `cd` before them - None for a move after one, or one that names no single folder."
    for a in segs:
        if _push_of(a): return cwd if not any(_moves(b) for b in segs[segs.index(a):]) else None
        if _moves(a):
            w = [t for t in a[1:] if not t.startswith('-')]
            if len(w) != 1: return None
            cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(w[0])))
    return cwd


def _moves(argv) -> bool:
    from .shellgate import _words
    return _words(argv)[0] in _MOVES


def push_asked(store, tid: int, cmd: str, cwd: str = '', about: str = '') -> tuple | None:
    """A shell line that pushes this task's own work, as the card's question. (True, words for the agent): the push is on the card, marked.
    (False, words): the line does more than push - none of it runs, and the agent is told to ask with propose_land after the rest.
    None: the card's buttons are not this push (or there is no card: Developer mode off, no checkout) - held like any other step."""
    from . import shellgate
    from .browsergate import _segments
    todo, segs = shellgate.acts(cmd, cwd), _segments(_TO_NOWHERE.sub(' ', str(cmd or ''))) or []
    pushes = [p for a in segs if (p := _push_of(a))]
    if not cwd or not todo or len(pushes) != len(todo) or any(a['what'] != shellgate.GIT['push'] for a in todo): return None
    if (at := _where(segs, cwd)) is None: return None
    r = record(store, tid) or adopt(store, tid, at)
    if not (r.get('cwd') and shown(store, tid)) or _top(at) != _top(r['cwd']): return None
    s = state(store, tid)
    if not s: return None
    cur, to = head_branch(at), set()
    for src, dst in pushes:
        src, dst = (cur if x in ('', 'HEAD') else x.removeprefix('refs/heads/') for x in (src, dst))
        if not src or src != s['branch'] or (s['own'] and dst != src) or not _branch_ok(dst): return None
        to.add(dst)
    live = set() if s['own'] else to - {s['base']}
    if len(live) > 1: return None
    how, deploy = 'pr' if s['own'] else 'push', next(iter(live), '')
    button = HOW['deploy' if deploy else how]
    if any(not _push_of(a) and not _moves(a) for a in segs):   # the commit in the same line has not run: nothing to put on the card yet
        from .general import GENERAL_KINDS
        ask = (f"propose (action push, cwd {s['cwd']}{f', deploy {deploy}' if deploy else ''})" if (store.get_task(tid) or {}).get('Kind') in GENERAL_KINDS
               else f"propose_land (how {how}{f', deploy {deploy}' if deploy else ''})")
        return False, (f"Taskuary did not run this line: a push from this task's checkout is the owner's {button} button, never a shell step. Run "
                       f"the rest of it without the push, then call {ask} - they get the button, and Taskuary tells you when it went.")
    # ...a passed question is still the owner's press: the agent's own push raises it again, never runs (proposals.move_on)
    if not (s['ask'] or s.get('passed')): return None
    try:
        if s.get('passed') or ((s['proposal'] or {}).get('how'), (s['proposal'] or {}).get('deploy') or '') != ('deploy' if deploy else how, deploy):
            propose(store, tid, how, about, deploy=deploy)
    except ValueError: return None
    return True, (f"{shellgate.HELD}: this push is the owner's {button} button on the task now, not a shell step - {state(store, tid)['line']} Nothing "
                  "is pushed until they press it. " + __import__("taskuary.selfclose", fromlist=["CARD_TAIL"]).CARD_TAIL)




def asked(store, tid) -> bool:
    """Does a landing question of the agent's wait, as the record alone says it (no git - a rail build asks): it proposed one, nothing landed
    since, and the conversation has not moved past it (pass_over)."""
    r = record(store, tid); p = r.get('proposal') or {}
    return bool(p) and not p.get('passed') and str((r.get('landed') or {}).get('at') or '') < str(p.get('at') or '')


def pass_over(store, tid: int, before: float = None) -> bool:
    """The landing question the agent raised, passed as the chat moves on past it (proposals.set_aside_drafts: an input at `before` - one rule
    with every card's). True when one was."""
    from .conversation import ep
    r = record(store, tid); p = r.get('proposal') or {}
    # ...and when it moved on, for the question the checkout raises by itself (state): no turn raised it, so no proposal carries its mark
    if before and r.get('start') and before > float(r.get('moved') or 0): r['moved'] = before; _save(store, tid, r)
    if not p or p.get('passed') or str((r.get('landed') or {}).get('at') or '') >= str(p.get('at') or ''): return False
    if before is not None and ep(p.get('at')) >= before: return False
    r['proposal'] = {**p, 'passed': time.strftime('%Y-%m-%d %H:%M:%S')}; _save(store, tid, r)
    return True


class Refused(RuntimeError): pass


def _conflict(store, tid: int, s: dict, how: str, files: list) -> dict:
    """Aborted, so nothing landed half-done - and the conflict is the agent's next turn."""
    names = ', '.join(files[:30]) or 'files git did not name'
    text = (f"LANDING CONFLICT: {HOW[how]} of {s['branch']} onto {s['base']} stopped on conflicts in {names}. It was aborted - nothing "
            f"landed and the checkout is as it was. Resolve these conflicts on {s['branch']} (rebase it onto {s['base']}, or merge "
            f"{s['base']} into it), commit, then say done - the owner lands it again.")
    store.add_comment(tid, 'router', 'agent', f"{HOW[how]} stopped on conflicts in {names} - aborted, nothing landed; the agent has it now.")
    store.audit('task', tid, 'land_conflict', 'router', 'agent', {'how': how, 'files': files[:30]})
    _hand_back(store, tid, text)
    return {'ok': False, 'conflict': files, 'says': f"Conflicts in {names} - nothing landed. The agent is resolving them."}


def _hand_back(store, tid, text):
    "Taskuary's words to the task's agent by the one road (general.to_agent) - and where none ever worked it, the task says so, once."
    from . import general
    try: told = general.to_agent(store, tid, text, 'router')
    except Exception as e: told = logger.warning(f'{task_ref(tid)}: the landing was not handed back to the agent - {e}')
    if not told: store.add_comment_once(tid, 'taskuary', 'agent', 'No agent has worked this task, so none was told what landed.')


def _ff(cwd, base, br):
    "Move `base` to `br`'s tip: in the tree when `base` is checked out, else by its ref alone (compare-and-swap)."
    if head_branch(cwd) == base:
        rc, out, err = _run(cwd, 'merge', '--ff-only', br)
        if rc: raise Refused(f'fast-forwarding {base} was refused: {(err or out)[:300]}')
        return
    rc, _, err = _run(cwd, 'update-ref', f'refs/heads/{base}', sha(cwd, br), sha(cwd, base))
    if rc: raise Refused(f'{base} moved while landing - nothing changed ({err[:200]})')


def land(store, tid: int, how: str, actor: str = 'owner') -> dict:
    """The owner's answer to the landing question, carried out. {'ok', 'says', ...}; a conflict is {'ok': False, 'conflict': [...]}.
    A REFUSED PRESS IS KEPT, AND ITS AGENT HAS IT (rules part 4, the stress round 2026-11-10): a push the remote turned down - someone pushed
    first: "pull and rebase, then push again" - was said only in the press's own answer. Nothing on the task after a reload, the agent that
    could rebase never told, and the next Push refused the same way. A line in the chat, and the refusal handed to the agent by the one road."""
    how = str(how or '').strip().lower()
    try: return _land(store, tid, how, actor)
    except Refused as e:
        store.audit('task', tid, 'land_refused', actor, detail={'how': how, 'why': str(e)[:300]})
        _hand_back(store, tid, f"The owner pressed {HOW.get(how, how)} on your work and it was refused: {e}. The question "
                               "stays on the task. Do what that needs from your side, then ask for it again (propose_land) - or say in a line why you cannot.")
        raise


def _land(store, tid: int, how: str, actor: str) -> dict:
    if how not in HOW: raise ValueError(f"how is one of: {', '.join(HOW)}")
    s = state(store, tid)
    if s and s.get('passed'):
        # ...refused with the sentence its greyed card reads (proposals.passed_why, 2026-11-17), its question standing as a card would
        from .proposals import passed_why
        p = s.get('proposal') or {}
        raise ValueError(passed_why(store, {'TaskId': tid, 'CreatedAt': p.get('at') or s.get('at'), 'DecidedAt': p.get('passed')}))
    if not s or not s['ask']: raise ValueError((s or {}).get('line') or 'nothing to land on this task')
    if how == 'discard' and not s['own']: raise ValueError('discard is only offered for a branch the agent made itself')
    if how not in {a['how'] for a in s['answers']}: raise ValueError(f"{HOW[how]} is not offered here - {s['line']}")
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
        from .browsergate import NEXT
        _went(store, tid, f"{said_} The owner pressed {HOW[how]} on your branch. {NEXT}")
    return {'ok': True, 'how': how, 'says': said_, **extra}


def _went(store, tid, text):
    "What his press landed, to the agent: woken only where its proposal named a step of its own after it (card.carries_on), else said in its next turn."
    from . import card, events
    if card.carries_on(record(store, tid).get('proposal')): return _hand_back(store, tid, text)     # at work or at rest (general.approved)
    events.note(store, int(tid), text)


def _push(store, tid, s, how, actor) -> dict:
    """Push the task's own commits on the shared base: origin/<base> up to its newest one, and for Push & deploy that commit to the deploy
    branch too. Never forced - a branch that moved refuses, and says what was and was not pushed. Kept as ci's PUSHED mark, so the CI watch
    follows it as it follows any push."""
    from . import ci
    cwd, base, p = s['cwd'], s['base'], s['push']
    tip, done, refused = p['tip'], [], ''
    for b in [base] + ([p['deploy']] if how == 'deploy' else []):
        rc, out, err = _push_as_agent(cwd, 'push', 'origin', f'{tip}:refs/heads/{b}')
        if rc:
            why = ci.TOKEN_URL.sub('https://', (err or out))[:300]
            fix = ' - pull and rebase, then push again (never forced)' if re.search(r'non-fast-forward|fetch first|rejected', why) else ''
            if not done: raise Refused(f"the push of {tip[:7]} to {b} was refused: {why}{fix} - nothing was pushed")
            # ...THE BASE WENT, THE DEPLOY DID NOT (stress round, 2026-11-18): refused as a whole, the agent heard "Nothing went out, and the
            # question stays" - and none stayed, the base having nothing left to push. What went is kept as the push it is; the rest is said
            refused = f" The deploy to {b} was refused: {why}{fix}."
            break
        done.append(b)
    went = 'deploy' if how == 'deploy' and not refused else 'push'
    if went == 'deploy' and s['repo']: store.set_setting(f"{DEPLOY_KEY}:{s['repo'].lower()}", p['deploy'], actor)
    ci._save_push(store, tid, {'repo': s['repo'], 'branch': base, 'from': base, 'sha': tip, 'commits': p['ahead'], 'state': 'pushed',
                               'url': f"https://github.com/{s['repo']}/commit/{tip}" if s['repo'] else '', 'checks': None, 'checked_at': None}, actor)
    said_ = f"Pushed {plural(p['ahead'], 'commit')} to origin/{base} ({tip[:7]})" + (f" and deployed it to {p['deploy']}." if went == 'deploy' else '.') + refused
    out = _landed(store, tid, went, said_, actor, tip, **({'deploy': p['deploy']} if went == 'deploy' else {}))
    # ...a deploy refused is handed back; what went wakes it only where it named a step of its own after the press (_went)
    (_hand_back if refused else _went)(store, tid, f"{said_} The owner pressed {HOW[how]} on your proposal." + (
        f" Do what the refusal needs, then deploy {tip[:7]} to {p['deploy']} with your own `git push` - it is held for the owner's press - or say in a line why you cannot."
        if refused else ''))
    return out


def _pr(store, tid, s, actor) -> dict:
    """Open a PR: the branch pushed and a draft pull request opened through the GitHub card. Reached only by the owner's answer - their
    press is the push's press (an agent's propose_land only marks the question)."""
    from . import ci, github
    cwd, base, br, repo = s['cwd'], s['base'], s['branch'], s['repo']
    if not repo: raise Refused("this checkout's origin is not a GitHub repository - push it and open the pull request by hand")
    # ...GITHUB'S NO IS THE LANDING'S NO (stress round, 2026-11-18): its own error passed land()'s handler - no line kept, the agent never told
    try: c = ci._conn(store, repo)
    except RuntimeError as e: raise Refused(f'{e} - nothing was pushed') from e
    rc, out, err = _push_as_agent(cwd, 'push', '-u', 'origin', br)
    if rc: raise Refused(f"the push of {br} was refused: {ci.TOKEN_URL.sub('https://', (err or out))[:300]} - no pull request opened")
    t = store.get_task(tid) or {}
    body = f"Opened by Taskuary for {task_ref(tid)}.\n\n{(t.get('Summary') or '')[:1500]}"
    try: pr = github.open_pr(c['Secret'], repo, br, base, f"[{task_ref(tid)}] {t.get('Title') or 'work'}"[:120], body)
    except Exception as e: raise Refused(f"{br} was pushed, but no pull request was opened: {str(e)[:300]}") from e
    pr['repo'], pr['checks'], pr['checked_at'] = repo, None, None
    ci._save_pr(store, tid, pr, actor)
    return _landed(store, tid, 'pr', f"Pushed {br} and opened pull request #{pr['number']} into {base}: {pr.get('url')}", actor,
                   sha(cwd, br), pr=pr['number'], url=pr.get('url'))
