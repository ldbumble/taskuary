"""Safe outputs: an agent PROPOSES a high-impact action, deterministic code validates it,
and it happens only after you approve. The best security idea in the field (GitHub's
agentic-workflows calls them safe outputs) and the one that actually fits here, because
Taskuary already has the approval queue to put a proposal in.

The distinction that matters: an agent with an auto-approve flag on your machine can already
do anything YOU can, so a permission profile Taskuary does not enforce would be theater.
What is real is moving the blast-radius actions OFF that road entirely - the agent cannot
open a pull request or post to a public thread by itself, it can only ask, in a shape this
module can check, and the answer is a review you approve.

The agent emits, anywhere in its transcript:

    TASKUARY-PROPOSE {"action": "open_pr", "why": "tests pass, ready for review"}

Unknown actions, bad shapes and unpermitted actions are REFUSED and recorded - a malformed
proposal is never a partially-executed one.
"""
import json, re
from loguru import logger

MARK = 'TASKUARY-PROPOSE'
BLOCK = re.compile(MARK + r'\s*(\{.*?\})', re.S)
MAX = 5                      # per transcript: a loop proposing 200 pushes is a bug, not intent

# action -> (what it does in words, required keys, the switch that must be ON for it to be
# proposable at all). Nothing here executes without an approved review.
ACTIONS = {
    'open_pr': ('open a DRAFT pull request for this task', (), 'agent_push_enabled'),
    'comment_issue': ('post a PUBLIC comment on the linked issue/PR', ('body',), 'github_reply'),
    'close_issue': ('close the linked GitHub issue', (), 'use_as_tracker'),
    'run_tool': ('run one query/script through a tool connection', ('type',), None),
}


def _switch_ok(store, name) -> bool:
    if not name: return True
    if name in ('agent_push_enabled',): return store.get_settings().get(name) == '1'
    import json as _j
    c = store.get_connector_by_type('github') or {}
    try: cfg = _j.loads(c.get('ConfigJson') or '{}')
    except ValueError: cfg = {}
    return bool(cfg.get({'github_reply': 'reply_comments'}.get(name, name)))


def parse(text: str) -> list:
    """Every well-formed proposal in a transcript. Junk is skipped, not guessed at."""
    out = []
    for m in BLOCK.finditer(text or ''):
        try: j = json.loads(m.group(1))
        except ValueError: continue
        a = str(j.get('action') or '').strip()
        if a in ACTIONS: out.append({**j, 'action': a})
        if len(out) >= MAX: break
    return out


def validate(store, p: dict) -> tuple:
    """(ok, reason). The whole gate: known action, required fields present, switch on."""
    a = p.get('action')
    if a not in ACTIONS: return False, f'unknown action {a!r}'
    words, need, switch = ACTIONS[a]
    missing = [k for k in need if not str(p.get(k) or '').strip()]
    if missing: return False, f'{a} needs {", ".join(missing)}'
    if not _switch_ok(store, switch):
        return False, f'{a} is not permitted - the owner has that switch off'
    return True, words


def collect(store, task_id: int, transcript: str, actor='coder') -> list:
    """Turn an agent's proposals into pending reviews. Returns what was queued; refusals are
    recorded on the task so a refused proposal is visible, not silently dropped."""
    made = []
    for p in parse(transcript):
        ok, why = validate(store, p)
        if not ok:
            store.add_comment(task_id, actor, 'agent', f'PROPOSAL REFUSED ({p.get("action")}): {why}')
            store.audit('task', task_id, 'proposal_refused', actor, detail={'action': p.get('action'), 'why': why})
            continue
        rid = store.add_review({'TaskId': task_id, 'Kind': 'action', 'Status': 'pending',
                                'DraftText': json.dumps(p),
                                'Reason': f'the agent proposes to {why}'
                                          + (f" - {p['why'][:200]}" if p.get('why') else '')})
        store.audit('review', rid, 'proposed', actor, detail={'action': p['action']})
        made.append({'reviewId': rid, 'action': p['action']})
        logger.info(f'task {task_id}: proposal queued - {p["action"]} (rv{rid})')
    return made


def execute(store, rv: dict, actor='owner') -> dict:
    """Run an APPROVED proposal. Called from the verdict road, and it re-validates: the
    switch may have gone off between proposing and approving, and the approval does not
    grant the permission."""
    p = json.loads(rv.get('DraftText') or '{}')
    ok, why = validate(store, p)
    if not ok: raise RuntimeError(f'refused at execution: {why}')
    tid, a = rv.get('TaskId'), p['action']
    if a == 'open_pr':
        from .ci import open_for_task
        pr = open_for_task(store, tid, actor)
        out = {'pr': pr['number'], 'url': pr['url']}
    elif a in ('comment_issue', 'close_issue'):
        from . import github
        from .ci import _conn
        c, t = _conn(store), store.get_task(tid) or {}
        ref = str(t.get('SourceRef') or '')
        m = re.search(r'github\.com/([^/]+/[^/]+)/(?:issues|pull)/(\d+)', ref)
        if not m: raise RuntimeError('this task carries no GitHub issue/PR to act on')
        repo, num = m.group(1), int(m.group(2))
        if a == 'comment_issue':
            url = github.comment_issue(c['Secret'], repo, num, p['body'])
            out = {'commented': f'{repo}#{num}', 'url': url}
        else:
            github.close_issue(c['Secret'], repo, num, p.get('body'))
            out = {'closed': f'{repo}#{num}'}
    else:                                   # run_tool
        from .reports import REGISTRY, resolve_cfg
        head, body = REGISTRY[p['type']](resolve_cfg(store, {k: v for k, v in p.items() if k != 'action'}))
        out = {'headline': str(head)[:200], 'output': (body or '')[:2000]}
    store.add_comment(tid, actor, 'human', f'APPROVED PROPOSAL ({a}): {json.dumps(out)[:600]}')
    store.audit('review', rv['ReviewId'], 'proposal_executed', actor, detail={'action': a, 'result': out})
    return out
