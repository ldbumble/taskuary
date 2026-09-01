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
PRC_MARK = 'PR COMMENT'           # a human's comment on that PR, kept on the task's own thread
PUSH_MARK = 'PUSHED'              # the same, for work landed straight on the default branch
CI_MARK = 'CI FEEDBACK'           # what we have already handed back, so it goes back ONCE
BRANCH_SAFE = re.compile(r'[^a-zA-Z0-9._/-]+')
TOKEN_URL = re.compile(r'https://[^@/]*@')     # never let a PAT reach a log line or a comment


def _conn(store):
    c = store.get_connector_by_type('github', with_secret=True)
    if not (c and c.get('Secret')): raise RuntimeError('no GitHub PAT saved (Connections → GitHub)')
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


def landing_of(store, task_id: int):
    """Where this task's work actually WENT - a pull request or a direct push, whichever
    happened last. Both are the same question to everything downstream (what commit do I
    check CI on?), so both answer it the same way: {kind, repo, sha, url, ...}."""
    for c in reversed(store.list_comments(task_id)):
        body = str(c.get('Body') or '')
        for mark, kind in ((PR_MARK, 'pr'), (PUSH_MARK, 'push')):
            if body.startswith(mark):
                try: return {**json.loads(body[len(mark):].strip()), 'kind': kind}
                except ValueError: return None
    return None


def _save_pr(store, task_id: int, pr: dict, actor='ci'):
    store.add_comment(task_id, actor, 'agent', f'{PR_MARK} {json.dumps(pr)}')


def _save_push(store, task_id: int, info: dict, actor='ci'):
    store.add_comment(task_id, actor, 'agent', f'{PUSH_MARK} {json.dumps(info)}')


def flow(store) -> str:
    """'pr' (a draft pull request) or 'direct' (straight onto the default branch). The
    owner's call: on your own repo the PR is ceremony, on a shared one it is the review."""
    return store.get_settings().get('git_flow', 'pr')


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


def _where(store, task_id: int):
    """(cwd, repo, base, branch) for a task with a session - everything the two landing
    roads both need, and the same refusals for both."""
    from . import terminal as hub_term
    ses = hub_term.session_for(task_id)
    cwd = getattr(ses, 'cwd', None)
    if not cwd: raise RuntimeError('no session on this task to read a checkout from')
    repo, _ = hub_term.guess_repo(store, task_id, {})
    repo = repo or _cfg(store).get('default_repo')
    if not repo: raise RuntimeError('no repository known for this task')
    base = _cfg(store).get('default_base') or 'master'
    return cwd, repo, base, branch_for(store, task_id, cwd)


def push_direct(store, task_id: int, actor='owner') -> dict:
    """Land the work straight on the default branch - no pull request. What the owner of
    their own repo usually wants, and never the default.

    Deliberately narrow: it pushes COMMITS THAT ALREADY EXIST. A dirty tree is refused
    rather than committed on the agent's behalf (a generated commit message over changes
    nobody read is exactly the step this product does not take), and nothing ahead of the
    remote is 'nothing to do', not an error. Force is never passed: a rejected push means
    the branch moved underneath you, and the answer is to pull, not to overwrite."""
    from .agents import _git
    from .store import task_ref
    if store.get_settings().get('agent_push_enabled') != '1':
        raise RuntimeError("pushing is off - flip 'Agents may push / deploy' on the GitHub card first")
    cwd, repo, base, branch = _where(store, task_id)
    if _git(cwd, 'status', '--porcelain').strip():
        raise RuntimeError('the checkout has uncommitted changes - the agent should commit them first '
                           '(Taskuary will not write a commit message for work nobody has read)')
    _git(cwd, 'fetch', 'origin', base)
    ahead = (_git(cwd, 'rev-list', '--count', f'origin/{base}..HEAD') or '0').strip()
    if ahead in ('', '0'):
        raise RuntimeError(f'nothing to push - HEAD is not ahead of origin/{base}')
    sha = (_git(cwd, 'rev-parse', 'HEAD') or '').strip()
    out = _git(cwd, 'push', 'origin', f'HEAD:{base}')
    # git says nothing useful on success; a rejection is what we must not swallow
    if re.search(r'rejected|error:|fatal:', out or '', re.I):
        raise RuntimeError('git refused the push: ' + TOKEN_URL.sub('https://', out)[:300]
                           + ' - pull and rebase, then push again (Taskuary never force-pushes)')
    info = {'repo': repo, 'branch': base, 'from': branch, 'sha': sha, 'commits': int(ahead),
            'url': f'https://github.com/{repo}/commit/{sha}', 'state': 'pushed',
            'checks': None, 'checked_at': None}
    _save_push(store, task_id, info, actor)
    store.add_comment(task_id, actor, 'human',
                      f"Pushed {ahead} commit(s) straight to {base} ({sha[:7]}) - no pull request.")
    store.audit('task', task_id, 'pushed_direct', actor,
                detail={'repo': repo, 'base': base, 'sha': sha, 'commits': int(ahead)})
    logger.info(f'task {task_id}: {ahead} commit(s) pushed to {repo} {base} ({sha[:7]})')
    return info


def land(store, task_id: int, actor='owner') -> dict:
    """Publish this task's work the way the owner configured it: a draft pull request, or
    straight onto the default branch. One door, so the button, the endpoint and an approved
    proposal cannot disagree about which flow is in force."""
    return (push_direct if flow(store) == 'direct' else open_for_task)(store, task_id, actor)


def _already_fed(store, task_id: int) -> set:
    """Which failures this task has already been told about - a red build must reach the
    agent once, not on every poll until it is fixed."""
    out = set()
    for c in store.list_comments(task_id):
        b = str(c.get('Body') or '')
        if b.startswith(CI_MARK): out.add(b.split('\n', 1)[0][len(CI_MARK):].strip())
    return out


def check_task(store, task_id: int, llm=None) -> dict:
    """Poll where this task's work landed - a PR or a direct push - refresh its checks, and
    when they are RED hand the failure back to the live session (or put the task back on
    the owner when nothing is running). Never raises into the poller."""
    from . import github, terminal as hub_term
    at = landing_of(store, task_id)
    if not at: return {'state': 'not-landed'}
    try:
        c = _conn(store)
        if at['kind'] == 'pr':
            fresh = github.pr(c['Secret'], at['repo'], at['number'])
            at = {**at, **fresh}
        ck = github.checks(c['Secret'], at['repo'], at['sha'])
    except Exception as e:
        logger.warning(f'ci check failed for task {task_id}: {e}')
        return {'state': 'error', 'error': str(e)[:200]}
    at = {**at, 'checks': ck, 'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    where = f"the pull request for this task (#{at['number']}" if at['kind'] == 'pr' \
        else f"{at['branch']} (the commit this task pushed"
    (_save_pr if at['kind'] == 'pr' else _save_push)(store, task_id, {k: v for k, v in at.items() if k != 'kind'})
    ref = at.get('number') if at['kind'] == 'pr' else at['sha'][:7]
    if ck['state'] != 'failure': return {'state': ck['state'], 'at': ref, 'kind': at['kind']}
    key = f"{at['sha'][:10]}:{','.join(sorted(f['name'] or '?' for f in ck['failed']))}"
    if key in _already_fed(store, task_id): return {'state': 'failure', 'fed': False, 'at': ref}
    named = '\n'.join(f"- {f['name']}: {f['summary'] or 'see the run log'}" for f in ck['failed'])
    # direct mode has no PR to hold the change back, so the instruction changes with it:
    # the broken commit is ALREADY on the branch, and that is the thing to say out loud
    tail = ('Fix the cause and push again; do not merge.' if at['kind'] == 'pr'
            else 'This commit is ALREADY on the branch - fix it forward and push again.')
    text = (f"CI is failing on {where}, commit {at['sha'][:7]}). "
            f"The failing checks are:\n{named}\n{tail}")
    store.add_comment(task_id, 'ci', 'agent', f'{CI_MARK} {key}\n{text}')
    handed = hub_term.say_to_task(store, task_id, {'FromName': 'CI', 'Channel': 'github', 'BodyText': text}, 'ci')
    if not handed:
        # nobody is at the keyboard: it becomes work waiting on the owner, not a silent red
        store.update_task(task_id, {'Status': 'open'}, 'ci')
    store.audit('task', task_id, 'ci_failure', 'ci', detail={'at': ref, 'kind': at['kind'],
                                                             'checks': [f['name'] for f in ck['failed']],
                                                             'handed_to_agent': handed})
    return {'state': 'failure', 'fed': True, 'handed': handed, 'at': ref, 'kind': at['kind']}


def pull_comments(store, task_id: int, at: dict) -> int:
    """Somebody commented on our pull request - put it on the TIMELINE, on this task.

    github.pr_review_comments has existed since the CI watcher was written, its docstring
    calling review comments "the other thing that should reach the agent", and nothing has ever
    called it. So a reviewer could ask for a change and the only place it existed was GitHub:
    the task sat there looking finished, and the owner found out by remembering to go and look.

    Each comment becomes a message ON THE SAME TASK - it is the same piece of work, not a new
    one - which is what puts the task back in front of the owner as needs-you. A live session
    is told as well, because a reviewer's note is exactly what the agent should act on next."""
    from . import github, terminal as hub_term
    from .store import task_ref
    if at.get('kind') != 'pr': return 0
    try:
        c = _conn(store)
        comments = github.pr_review_comments(c['Secret'], at['repo'], at['number'])
    except Exception as e:
        logger.warning(f'reading PR comments for task {task_id} failed: {e}')
        return 0
    n, newest = 0, None
    for cm in comments:
        ext = f"ghc:{at['repo']}#{at['number']}:{cm.get('id')}"
        if not cm.get('id') or store.message_exists(ext): continue
        where = f" on {cm['path']}" if cm.get('path') else ''
        body = f"{cm['who']} commented{where} on pull request #{at['number']}:\n\n{cm['body']}"
        mid = store.add_message({
            'TaskId': task_id, 'ExternalId': ext, 'Channel': 'github',
            'ConversationId': f"pr:{at['repo']}#{at['number']}", 'SourceName': at['repo'],
            'Subject': f"PR #{at['number']} - {cm['kind']} comment from {cm['who']}",
            'FromName': cm['who'], 'FromEmail': f"{cm['who']}@users.noreply.github.com",
            'SentAt': str(cm.get('at') or '').replace('T', ' ').rstrip('Z'),
            'BodyText': body, 'SourceLink': cm.get('url') or at.get('url'), 'Status': 'routed'})
        store.add_route(mid, task_id, 'attach', None,
                        f"a human commented on the pull request for {task_ref(task_id)} - "
                        'time to look at it again', [], 'github')
        newest, n = body, n + 1
    if newest:
        store.add_comment(task_id, 'github', 'agent', f'{PRC_MARK} {newest[:400]}')
        # a live session gets it typed in; with nobody at the keyboard the task goes back to open,
        # so the timeline row it just grew is not the only thing carrying the news
        if not hub_term.say_to_task(store, task_id, {'FromName': 'GitHub', 'Channel': 'github',
                                                     'BodyText': newest}, 'github'):
            store.update_task(task_id, {'Status': 'open'}, 'github')
        store.audit('task', task_id, 'pr_comments', 'github', detail={'new': n, 'pr': at.get('number')})
    return n


def poll(store, llm=None) -> int:
    """Every task whose work has landed - PR or direct push - looked at once. Called from the
    same sync as everything else.

    Two different things, and only one of them is opt-in. A human commenting on our pull request
    is INBOUND WORK arriving, which is the whole point of the app, so it lands on the timeline
    whatever the settings say. Handing a RED BUILD to a running agent is the automation, and that
    is what ci_watch gates - it ships off, and gating the comments behind it too would have meant
    the default install never told anybody their PR had been reviewed."""
    watch = store.get_settings().get('ci_watch', 'off') != 'off'
    n = 0
    for t in store.list_tasks():
        if t['Status'] in ('done', 'dropped'): continue
        at = landing_of(store, t['TaskId'])
        # a merged/closed PR is finished business; a direct push is only ever checked while
        # its checks could still be running, which the state below settles
        if not at or at.get('state') == 'closed': continue
        try:
            n += pull_comments(store, t['TaskId'], at)
        except Exception as e:
            logger.warning(f'PR comments for task {t["TaskId"]} failed: {e}')
        if not watch: continue
        out = check_task(store, t['TaskId'], llm)
        n += 1 if out.get('fed') else 0
    return n
