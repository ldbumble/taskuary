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
    out, cur = [], None
    for l in (diff or '').splitlines():
        if l.startswith('diff --git'):
            p = l.split(' b/')[-1].strip()
            cur = {'path': p, 'added': 0, 'removed': 0}
            out.append(cur)
        elif cur and l.startswith('+') and not l.startswith('+++'): cur['added'] += 1
        elif cur and l.startswith('-') and not l.startswith('---'): cur['removed'] += 1
    return out


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
        # said plainly so a thin card cannot be mistaken for a clean one
        'gaps': [g for g in (
            'no file changes recorded - the agent may not have committed, or only read'
            if not files else None,
            'no test run detected in the session' if not tests_from(transcript).get('ran') else None,
            'no CI checked (no pull request linked)' if not ci_state(store, task_id) else None,
        ) if g],
    }


def ci_state(store, task_id: int):
    """The PR and its checks for this task, if one was opened - see ci.py. None when the
    task has no pull request, which is not a failure, just an absence."""
    from .ci import pr_of
    pr = pr_of(store, task_id)
    if not pr: return None
    return {'repo': pr.get('repo'), 'number': pr.get('number'), 'url': pr.get('url'),
            'state': pr.get('state'), 'checks': pr.get('checks'), 'checkedAt': pr.get('checked_at')}
