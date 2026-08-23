"""Closing the git loop: a task's branch becomes a DRAFT pull request, its CI is watched,
and a red build - or a human's review comment - goes back to the agent that wrote the code
instead of to nobody.

The human gate never moves. Taskuary opens drafts, never merges; pushing at all still needs
the GitHub card's 'Agents may push / deploy'. What this adds is the half that was missing:
after the agent stops typing, something watches what its work did to CI and hands the
failure back with the failing check named.

The PR lives on the task as a comment marker (PR_MARK) - no schema change, and the whole
history of what was opened stays readable in the task itself.
"""
import json, re
from datetime import datetime
from loguru import logger

PR_MARK = 'PULL REQUEST'          # comment marker: 'PULL REQUEST {json}'
CI_MARK = 'CI FEEDBACK'           # what we have already handed back, so it goes back ONCE
BRANCH_SAFE = re.compile(r'[^a-zA-Z0-9._/-]+')


def _conn(store):
    c = store.get_connector_by_type('github', with_secret=True)
    if not (c and c.get('Secret')): raise RuntimeError('no GitHub PAT saved (Connectors → GitHub)')
    return c


def _cfg(store) -> dict:
    c = store.get_connector_by_type('github') or {}
    try: return json.loads(c.get('ConfigJson') or '{}')
    except ValueError: return {}


def pr_of(store, task_id: int):
    """The pull request opened for this task, if any - read back off its comments."""
    for c in reversed(store.list_comments(task_id)):
        body = str(c.get('Body') or '')
        if body.startswith(PR_MARK):
            try: return json.loads(body[len(PR_MARK):].strip())
            except ValueError: return None
    return None


def _save_pr(store, task_id: int, pr: dict, actor='ci'):
    store.add_comment(task_id, actor, 'agent', f'{PR_MARK} {json.dumps(pr)}')


def branch_for(store, task_id: int, cwd: str) -> str:
    """The branch the agent actually worked on. Whatever is checked out IS the answer - the
    agent chose it (or stayed on the default), and guessing a name we did not create would
    open a PR for a branch that does not exist."""
    from .agents import _git
    b = (_git(cwd, 'rev-parse', '--abbrev-ref', 'HEAD') or '').strip()
    return BRANCH_SAFE.sub('-', b) if b and b != 'HEAD' else ''


def open_for_task(store, task_id: int, actor='owner') -> dict:
    """Open (or find) the draft PR for this task's branch. Refuses the default branch: a PR
    from main to main is not a thing, and it is the shape a mis-detected branch takes."""
    from . import github, terminal as hub_term
    from .store import task_ref
    c = _conn(store)
    if not store.get_settings().get('agent_push_enabled') == '1':
        raise RuntimeError("pushing is off - flip 'Agents may push / deploy' on the GitHub card first")
    ses = hub_term.session_for(task_id)
    cwd = getattr(ses, 'cwd', None)
    if not cwd: raise RuntimeError('no session on this task to read a branch from')
    repo, _ = hub_term.guess_repo(store, task_id, {})
    repo = repo or _cfg(store).get('default_repo')
    if not repo: raise RuntimeError('no repository known for this task')
    branch = branch_for(store, task_id, cwd)
    base = _cfg(store).get('default_base') or 'master'
    if not branch or branch == base:
        raise RuntimeError(f"the checkout is on '{branch or 'a detached HEAD'}' - the agent needs its own "
                           'branch before a pull request can be opened')
    t = store.get_task(task_id) or {}
    body = (f"Opened by Taskuary for {task_ref(task_id)}.\n\n{(t.get('Summary') or '')[:1500]}\n\n"
            '_Draft: review and merge yourself - Taskuary never merges._')
    pr = github.open_pr(c['Secret'], repo, branch, base, f"[{task_ref(task_id)}] {t.get('Title') or 'work'}"[:120], body)
    pr['repo'], pr['checks'], pr['checked_at'] = repo, None, None
    _save_pr(store, task_id, pr, actor)
    store.audit('task', task_id, 'pr_opened', actor, detail={'repo': repo, 'number': pr['number']})
    logger.info(f'PR #{pr["number"]} opened for task {task_id} ({repo} {branch} -> {base})')
    return pr


def _already_fed(store, task_id: int) -> set:
    """Which failures this task has already been told about - a red build must reach the
    agent once, not on every poll until it is fixed."""
    out = set()
    for c in store.list_comments(task_id):
        b = str(c.get('Body') or '')
        if b.startswith(CI_MARK): out.add(b.split('\n', 1)[0][len(CI_MARK):].strip())
    return out


def check_task(store, task_id: int, llm=None) -> dict:
    """Poll one task's PR: refresh its checks, and when they are RED hand the failure back
    to the live session (or file it on the task when nothing is running). Returns what it
    did, and never raises into the poller."""
    from . import github, terminal as hub_term
    pr = pr_of(store, task_id)
    if not pr: return {'state': 'no-pr'}
    try:
        c = _conn(store)
        fresh = github.pr(c['Secret'], pr['repo'], pr['number'])
        ck = github.checks(c['Secret'], pr['repo'], fresh['sha'])
    except Exception as e:
        logger.warning(f'ci check failed for task {task_id}: {e}')
        return {'state': 'error', 'error': str(e)[:200]}
    pr = {**pr, **fresh, 'checks': ck, 'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    _save_pr(store, task_id, pr)
    if ck['state'] != 'failure': return {'state': ck['state'], 'pr': pr['number']}
    key = f"{fresh['sha'][:10]}:{','.join(sorted(f['name'] or '?' for f in ck['failed']))}"
    if key in _already_fed(store, task_id): return {'state': 'failure', 'fed': False, 'pr': pr['number']}
    named = '\n'.join(f"- {f['name']}: {f['summary'] or 'see the run log'}" for f in ck['failed'])
    text = (f"CI is failing on the pull request for this task (#{pr['number']}, commit {fresh['sha'][:7]}). "
            f"The failing checks are:\n{named}\nFix the cause and push again; do not merge.")
    store.add_comment(task_id, 'ci', 'agent', f'{CI_MARK} {key}\n{text}')
    handed = hub_term.say_to_task(store, task_id, {'FromName': 'CI', 'Channel': 'github', 'BodyText': text}, 'ci')
    if not handed:
        # nobody is at the keyboard: it becomes work waiting on the owner, not a silent red
        store.update_task(task_id, {'Status': 'open'}, 'ci')
    store.audit('task', task_id, 'ci_failure', 'ci', detail={'pr': pr['number'], 'checks': [f['name'] for f in ck['failed']],
                                                             'handed_to_agent': handed})
    return {'state': 'failure', 'fed': True, 'handed': handed, 'pr': pr['number']}


def poll(store, llm=None) -> int:
    """Every task with an open PR, checked once. Called from the same sync as everything
    else; off unless the owner turned ci_watch on."""
    if store.get_settings().get('ci_watch', 'off') == 'off': return 0
    n = 0
    for t in store.list_tasks():
        if t['Status'] in ('done', 'dropped'): continue
        pr = pr_of(store, t['TaskId'])
        if not pr or pr.get('state') == 'closed': continue
        out = check_task(store, t['TaskId'], llm)
        n += 1 if out.get('fed') else 0
    return n
