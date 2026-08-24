"""Proof of work: the evidence behind a task, gathered so approving is a JUDGEMENT and not
an act of faith. Every other agent runner asks you to trust the agent; this one asks you to
approve it - and an approval is only worth the evidence in front of it.

Nothing here is generated prose. Files come from git, tests from what the session actually
ran, timings from the run rows, CI from the checks API. A claim we cannot substantiate is
left OUT rather than guessed at: 'no test run detected' is information, 'probably fine' is
not.
"""
import re
from datetime import datetime
from loguru import logger

# What a test run looks like on screen, per runner. Deliberately narrow: a line that only
# MENTIONS pytest is not a test result, and counting it as one would turn the card into a
# rubber stamp. Each pattern captures the numbers the runner itself printed.
TEST_LINES = [
    # pytest: "12 passed, 1 failed in 3.2s" / "322 passed in 100.54s"
    (r'(\d+) passed(?:, (\d+) failed)?(?:, \d+ \w+)* in [\d.]+s', 'pytest'),
    # jest/vitest: "Tests:  3 failed, 12 passed, 15 total"
    (r'Tests:\s+(?:(\d+) failed,\s+)?(\d+) passed', 'jest'),
    # go test
    (r'^(ok|FAIL)\s+\S+\s+[\d.]+s', 'go'),
    # dotnet: "Passed! - Failed: 0, Passed: 12"
    (r'(?:Passed|Failed)!\s*-\s*Failed:\s*(\d+),\s*Passed:\s*(\d+)', 'dotnet'),
]
FAIL_WORDS = re.compile(r'\b(FAILED|FAIL|failed|error:|Error:|Traceback)\b')


def tests_from(text: str) -> dict:
    """What the session actually ran, read off the transcript. {ran, runner, passed, failed,
    line} - ran=False when nothing recognizable ran, which the card SAYS instead of hiding."""
    if not text: return {'ran': False}
    for pat, runner in TEST_LINES:
        m = None
        for m in re.finditer(pat, text, re.M): pass      # the LAST run is the current truth
        if not m: continue
        g = [x for x in m.groups() if x is not None]
        nums = [int(x) for x in g if str(x).isdigit()]
        if runner == 'pytest':
            passed, failed = nums[0], (nums[1] if len(nums) > 1 else 0)
        elif runner == 'jest':
            failed, passed = (nums[0], nums[1]) if len(nums) > 1 else (0, nums[0])
        elif runner == 'dotnet':
            failed, passed = (nums[0], nums[1]) if len(nums) > 1 else (0, 0)
        else:
            passed, failed = (0, 0) if m.group(1) == 'ok' else (0, 1)
        return {'ran': True, 'runner': runner, 'passed': passed, 'failed': failed,
                'line': m.group(0).strip()[:120]}
    return {'ran': False}


def files_from(diff: str) -> list:
    """[{path, added, removed}] straight out of a unified diff - what MOVED, per git, not
    per the agent's account of itself."""
    return [{k: f[k] for k in ('path', 'added', 'removed')} for f in split_files(diff)]


def split_files(diff: str) -> list:
    """The same walk, keeping each file's own PATCH: a five-file change reviews as five
    things you open one at a time, not one wall you scroll past. Everything before the first
    'diff --git' (git prints nothing there, but a --no-index run can) is dropped."""
    out, cur = [], None
    for l in (diff or '').splitlines():
        if l.startswith('diff --git'):
            cur = {'path': l.split(' b/')[-1].strip(), 'added': 0, 'removed': 0, 'lines': []}
            out.append(cur)
        if cur is None: continue
        cur['lines'].append(l)
        if l.startswith('+') and not l.startswith('+++'): cur['added'] += 1
        elif l.startswith('-') and not l.startswith('---'): cur['removed'] += 1
    for f in out:
        f['patch'] = '\n'.join(f.pop('lines'))
        # git says "Binary files a/x and b/x differ" and stops - there is no patch to read,
        # and a row that opens onto nothing is worse than one that says why
        f['binary'] = not f['added'] and not f['removed'] and 'Binary files' in f['patch']
    return out


# A generated bundle is not a review. Past this the file is listed with its counts and the
# patch is withheld, because nobody reads a 200k-character diff and pretending otherwise
# just makes the panel unusable for the files that DO matter.
MAX_PATCH = 200_000


def _git(cwd, *args, ok=(0,)):
    """git, tolerating the exit codes that are not failures: `diff --no-index` returns 1 when
    the files DIFFER, which is the entire question we are asking it."""
    import subprocess
    try:
        p = subprocess.run(['git', '-C', cwd, *args], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=30)
        return p.stdout if p.returncode in ok else ''
    except Exception as e:
        logger.warning(f'git {" ".join(args)} in {cwd} failed: {e}')
        return ''


def push_base(cwd: str) -> tuple:
    """What a push would measure against, and how many commits are already stacked on it.

    HEAD was the wrong answer and the panel proved it: an agent that finishes its work with
    `git commit` - which is what CODER.md tells it to do, commit locally and stop - left the
    reviewer saying "the working tree is clean" over a completed job. Committed-but-unpushed
    IS what a push carries. So the base is the upstream branch when the checkout tracks one,
    and only a checkout with nowhere to push falls back to HEAD.
    """
    up = _git(cwd, 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}').strip()
    if not up: return 'HEAD', 0, ''
    ahead = _git(cwd, 'rev-list', '--count', f'{up}..HEAD').strip()
    return up, int(ahead or 0), up


def working_diff(cwd: str) -> str:
    """Everything a push would carry: commits made and not pushed, edits not committed, and
    files the agent created that git has never seen. Three questions, because `git diff HEAD`
    answers only the middle one - it goes quiet the moment work is committed, and says nothing
    ever about an untracked file."""
    import os
    if not cwd or not os.path.isdir(cwd): return ''
    base, _ahead, _ = push_base(cwd)
    out = [_git(cwd, 'diff', base)]                            # committed, staged and unstaged
    status = _git(cwd, 'status', '--porcelain', '-uall')       # -uall: a new FOLDER lists its files
    for line in status.splitlines():
        if not line.startswith('??'): continue
        path = line[3:].strip().strip('"')
        # '/dev/null' is git's own spelling for the empty side, understood on Windows too
        out.append(_git(cwd, 'diff', '--no-index', '--', '/dev/null', path, ok=(0, 1)))
    return '\n'.join(x for x in out if x.strip())


def review(store, task_id: int) -> dict:
    """The uncommitted change on a task's checkout, per file, for the look you take before
    anything is pushed. The live session's OWN cwd is the truth when there is one - it is
    where the agent is actually typing, and it beats any tag or map."""
    from . import terminal as hub_term
    t = store.get_task(task_id) or {}
    repo = (re.search(r'repo:([^\s,]+)', str(t.get('Tags') or '')) or [None, None])[1]
    sess = hub_term.for_task(task_id)
    cwd = (sess or {}).get('cwd') or (hub_term.path_for_repo(store, repo) if repo else None)
    if not cwd:
        return {'cwd': None, 'repo': repo, 'files': [],
                'why': 'no checkout for this task yet - start a session, or pick the repository '
                       'from the task menu, and the changes show up here'}
    files = split_files(working_diff(cwd))
    for f in files:
        if len(f['patch']) > MAX_PATCH: f['patch'], f['truncated'] = '', True
    base, ahead, upstream = push_base(cwd)
    return {'cwd': cwd, 'repo': repo, 'branch': _git(cwd, 'rev-parse', '--abbrev-ref', 'HEAD').strip(),
            # what the diff is measured AGAINST, said out loud: "3 commits ahead of origin/main"
            # is the difference between a clean tree and a finished job nobody has pushed
            'ahead': ahead, 'upstream': upstream, 'files': files,
            'added': sum(f['added'] for f in files), 'removed': sum(f['removed'] for f in files)}


def _secs(a, b):
    try:
        return max(0, int((datetime.fromisoformat(str(b).replace(' ', 'T'))
                           - datetime.fromisoformat(str(a).replace(' ', 'T'))).total_seconds()))
    except (ValueError, TypeError):
        return None


def gather(store, task_id: int) -> dict:
    """The whole card for one task. Cheap enough to call on every panel open."""
    from . import terminal as hub_term
    t = store.get_task(task_id) or {}
    runs = store.list_runs(task_id)
    diff = next((r['DiffText'] for r in runs if r.get('DiffText')), '')
    transcript, agent, _sid = '', None, None
    try: transcript, agent, _sid = hub_term.transcript_for(store, task_id)
    except Exception as e: logger.warning(f'proof: transcript for {task_id} failed: {e}')
    # the coder's own report is a CLAIM; it sits beside the evidence, never as evidence
    rep = next((c['Body'] for c in reversed(store.list_comments(task_id))
                if str(c.get('Body') or '').startswith('CODER REPORT')), None)
    attempts = [{'run': r['RunId'], 'agent': r.get('AgentName'), 'status': r.get('Status'),
                 'started': r.get('StartedAt'), 'seconds': _secs(r.get('StartedAt'), r.get('FinishedAt') or r.get('UpdatedAt')),
                 'error': (r.get('LastError') or '')[:200] or None} for r in runs]
    files = files_from(diff)
    return {
        'taskId': task_id, 'title': t.get('Title'), 'status': t.get('Status'), 'agent': agent,
        'files': files,
        'diffstat': {'files': len(files), 'added': sum(f['added'] for f in files),
                     'removed': sum(f['removed'] for f in files)},
        'tests': tests_from(transcript),
        'attempts': attempts,
        'seconds': _secs(t.get('CreatedAt'), t.get('ClosedAt') or t.get('UpdatedAt')),
        'reported': bool(rep),
        'ci': ci_state(store, task_id),
        # the card's button has to say what it will actually DO, and that is the owner's setting
        'flow': store.get_settings().get('git_flow', 'pr'),
        # said plainly so a thin card cannot be mistaken for a clean one
        'gaps': [g for g in (
            'no file changes recorded - the agent may not have committed, or only read'
            if not files else None,
            'no test run detected in the session' if not tests_from(transcript).get('ran') else None,
            'not landed anywhere yet - no pull request and nothing pushed'
            if not ci_state(store, task_id) else None,
        ) if g],
    }


def ci_state(store, task_id: int):
    """Where this task's work landed and what CI made of it - a pull request or a direct
    push onto the default branch (see ci.py). None when it has not landed anywhere, which
    is an absence, not a failure."""
    from .ci import landing_of
    at = landing_of(store, task_id)
    if not at: return None
    return {'kind': at.get('kind'), 'repo': at.get('repo'), 'number': at.get('number'),
            'branch': at.get('branch'), 'sha': (at.get('sha') or '')[:7], 'commits': at.get('commits'),
            'url': at.get('url'), 'state': at.get('state'), 'checks': at.get('checks'),
            'checkedAt': at.get('checked_at')}
