"""An outside pull request fixed in GitHub's cloud, never on this machine.

A stranger's pull request on a public repository is reviewed here read-only (batch.read_only_argv), and that review can say
"changes needed". Making the changes means running the stranger's code - its tests, its build - and that is not done on the
owner's machine (the owner, 2026-10-12: "I still want to be able to process github public pr's maybe run on cloud hosted
version of claude/codex or on github?"). So Fix it runs a workflow in the repository itself, on a machine GitHub throws away:

  job `fix`   - a READ-ONLY token. Checks out exactly the head that was reviewed, runs Claude Code there with full freedom
                (tests, builds) and hands back a patch and a report. Nothing it does can push.
  job `push`  - never runs the pull request's code. Applies the patch and pushes it to the branch taskuary/pr-<n>.

Taskuary then opens the fix's pull request with the OWNER's token - one the workflow's own token opened would not trigger the
repository's CI - and the batch item carries it: the report is its finding and Merge merges the fix, the contributor's commits
with it. The workflow runs from the default branch, so a pull request cannot change what it does.

The one secret the workflow needs (CLAUDE_CODE_OAUTH_TOKEN, from `claude setup-token`) sits in job `fix` beside the stranger's
code: it can be read there and is revocable; it cannot reach the repository or this machine.
"""
import base64, io, json, zipfile
from datetime import datetime, timezone

import requests
from loguru import logger

from .store import task_ref

FILE = 'taskuary-fix.yml'
PATH = f'.github/workflows/{FILE}'
SECRET = 'CLAUDE_CODE_OAUTH_TOKEN'
NEVER_STARTED_MIN = 30          # a dispatch with no run to show for it after this long has failed to start
REPORT_CHARS = 1200

WORKFLOW = """# Taskuary: an outside pull request fixed on a machine GitHub throws away (taskuary/cloudfix.py).
# Job `fix` holds a read-only token and runs the agent; job `push` never runs the pull request's code.
name: Taskuary fix
run-name: 'Taskuary fix #${{ inputs.pr }}'
on:
  workflow_dispatch:
    inputs:
      pr: {description: Pull request number, required: true}
      sha: {description: The head that was reviewed, required: true}
      ask: {description: What to fix, required: true}
permissions: {}
concurrency: {group: 'taskuary-fix-${{ inputs.pr }}', cancel-in-progress: true}
jobs:
  fix:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    permissions: {contents: read}
    steps:
      - uses: actions/checkout@v4
        with: {ref: 'refs/pull/${{ inputs.pr }}/head', persist-credentials: false}
      - name: The head that was reviewed, and nothing pushed since
        env: {PR: '${{ inputs.pr }}', SHA: '${{ inputs.sha }}'}
        run: |
          [[ "$PR" =~ ^[0-9]+$ ]] || { echo "not a pull request number"; exit 1; }
          test "$(git rev-parse HEAD)" = "$SHA" || { echo "the pull request moved since it was reviewed"; exit 1; }
      - uses: actions/setup-node@v4
        with: {node-version: 22}
      - uses: actions/setup-python@v5
        with: {python-version: '3.12'}
      - run: npm install -g @anthropic-ai/claude-code
      - name: Fix
        env:
          CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          ASK: ${{ inputs.ask }}
        run: claude -p "$ASK" --permission-mode bypassPermissions > "$RUNNER_TEMP/report.md"
      - name: The patch
        if: always()
        run: |
          git add -A -- . ':!.github'
          git diff --cached --binary > "$RUNNER_TEMP/fix.patch"
          touch "$RUNNER_TEMP/report.md"
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: taskuary-fix
          path: |
            ${{ runner.temp }}/fix.patch
            ${{ runner.temp }}/report.md
  push:
    needs: fix
    runs-on: ubuntu-latest
    permissions: {contents: write}
    steps:
      - uses: actions/checkout@v4
        with: {ref: 'refs/pull/${{ inputs.pr }}/head'}
      - uses: actions/download-artifact@v4
        with: {name: taskuary-fix, path: '${{ runner.temp }}/fix'}
      - name: Push the fix to taskuary/pr-N
        env: {PR: '${{ inputs.pr }}', SHA: '${{ inputs.sha }}'}
        run: |
          [[ "$PR" =~ ^[0-9]+$ ]] || exit 1
          test "$(git rev-parse HEAD)" = "$SHA" || exit 1
          if [ ! -s "$RUNNER_TEMP/fix/fix.patch" ]; then echo "the agent changed nothing"; exit 0; fi
          git apply --index "$RUNNER_TEMP/fix/fix.patch"
          git -c user.name="taskuary[bot]" -c user.email="taskuary@users.noreply.github.com" commit -m "Taskuary's fix for #$PR"
          git push --force origin "HEAD:refs/heads/taskuary/pr-$PR"
"""


def branch(n) -> str: return f'taskuary/pr-{n}'
def enabled(store) -> bool: return str(store.get_setting('outside_prs') or 'review') == 'cloud'
def _now() -> str: return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _gh(store):
    from . import batch, github
    return github, batch._token(store)


def setup_state(store, repo) -> dict:
    """Is this repository ready: the workflow on its default branch, and the secret it needs? `secret` is None when the
    token may not look (reading a secret's NAME needs admin rights) - the run then says so itself."""
    github, tok = _gh(store)
    out = {'repo': repo, 'workflow': False, 'secret': None,
           'secret_url': f'https://github.com/{repo}/settings/secrets/actions/new', 'secret_name': SECRET}
    if not tok: return {**out, 'why': 'the GitHub card has no token'}
    r = requests.get(f'{github.GH}/repos/{repo}/contents/{PATH}', headers=github._h(tok), timeout=20)
    out['workflow'] = r.status_code == 200
    s = requests.get(f'{github.GH}/repos/{repo}/actions/secrets/{SECRET}', headers=github._h(tok), timeout=20)
    out['secret'] = True if s.status_code == 200 else False if s.status_code == 404 else None
    return out


def install(store, repo, actor='owner') -> dict:
    """Commit the workflow to the default branch - the owner's press, never a side effect. Kept as is when it already matches."""
    github, tok = _gh(store)
    if not tok: raise RuntimeError('the GitHub card has no token - connect it under Connections first')
    url = f'{github.GH}/repos/{repo}/contents/{PATH}'
    cur = requests.get(url, headers=github._h(tok), timeout=20)
    sha = cur.json().get('sha') if cur.status_code == 200 else None
    if sha and base64.b64decode(cur.json().get('content') or '').decode('utf-8', 'replace') == WORKFLOW: return {'ok': True, 'changed': False}
    body = {'message': 'Taskuary: fix outside pull requests on GitHub\'s machines, not the owner\'s',
            'content': base64.b64encode(WORKFLOW.encode()).decode(), **({'sha': sha} if sha else {})}
    github._ok(requests.put(url, headers=github._h(tok), json=body, timeout=30), f'add {PATH}')
    store.audit('repo', 0, 'cloudfix_install', actor, detail={'repo': repo})
    return {'ok': True, 'changed': True}


def ask_for(it: dict, n: int, extra: str = '') -> str:
    """The agent's whole brief - the prompt is all it gets on that machine."""
    return ' '.join(f"""You are on a checkout of pull request #{n} ({it.get('Title') or ''}) - an outside contributor's change. A
    reviewer read it and said: {it.get('Result') or 'it needs changes'}. Make the changes the review asks for, keeping the
    contributor's intent. Run the project's own tests and build the way its README and CI configuration do, and fix what they
    find. Leave .github alone. Change nothing unrelated. {extra.strip()} Finish with a short report: what you changed, and what
    the tests and the build said.""".split())


def start(store, tid, it: dict, extra: str = '', actor='owner') -> dict:
    """Fix it, for an outside item: dispatch the workflow on the reviewed head. Polled from the sync (poll)."""
    from . import batch
    github, tok = _gh(store)
    p = batch.pull(it.get('Link'))
    if not p: return {'ok': False, 'why': 'only a GitHub pull request can be fixed in the cloud'}
    if not tok: return {'ok': False, 'why': 'the GitHub card has no token - connect it under Connections first'}
    repo, n = p
    st = setup_state(store, repo)
    if not st['workflow']: return {'ok': False, 'setup': st, 'why': f'{repo} does not have the cloud-fix workflow yet - set it up first'}
    if st['secret'] is False: return {'ok': False, 'setup': st, 'why': f'{repo} has no {SECRET} secret - add it on GitHub first'}
    try:
        sha = it.get('Sha') or github.pr(tok, repo, n)['sha']
        ref = github.repo_info(tok, repo).get('default_branch') or 'main'
        github._ok(requests.post(f'{github.GH}/repos/{repo}/actions/workflows/{FILE}/dispatches', headers=github._h(tok), timeout=20,
                                 json={'ref': ref, 'inputs': {'pr': str(n), 'sha': sha, 'ask': ask_for(it, n, extra)}}), 'start the cloud fix')
    except Exception as e:
        return {'ok': False, 'why': str(e)[:300]}
    store.update_batch_item(tid, it['ConversationId'], {'Fix': 'running', 'FixAt': _now(), 'FixLink': None, 'State': 'working'})
    store.add_comment(tid, actor, 'human' if actor == 'owner' else 'agent', f"{it.get('Title') or ''}: sent to be fixed in GitHub's cloud.")
    return {'ok': True, 'state': 'working', 'fix': 'running'}


def _report(github, tok, repo, run_id) -> str:
    arts = github._ok(requests.get(f'{github.GH}/repos/{repo}/actions/runs/{run_id}/artifacts', headers=github._h(tok), timeout=20),
                      'read the run').json().get('artifacts') or []
    a = next((x for x in arts if x.get('name') == 'taskuary-fix'), None)
    if not a: return ''
    z = requests.get(a['archive_download_url'], headers=github._h(tok), timeout=60)
    if not z.ok: return ''
    with zipfile.ZipFile(io.BytesIO(z.content)) as f:
        return f.read('report.md').decode('utf-8', 'replace') if 'report.md' in f.namelist() else ''


def _settle(store, it: dict, **fields):
    from . import batch
    batch.set_item(store, it['TaskId'], it['ConversationId'], 'router', **fields)


def poll(store) -> int:
    """Every running fix: still going, failed, or done - and when done, the fix's own pull request opened and on the item."""
    rows = store.batch_items_fixing()
    if not rows: return 0
    github, tok = _gh(store)
    if not tok: return 0
    from . import batch
    moved = 0
    for it in rows:
        p = batch.pull(it.get('Link'))
        if not p: continue
        repo, n = p
        try:
            runs = github._ok(requests.get(f'{github.GH}/repos/{repo}/actions/workflows/{FILE}/runs', headers=github._h(tok), timeout=20,
                                           params={'event': 'workflow_dispatch', 'per_page': 30}), 'read the cloud fix').json().get('workflow_runs') or []
            run = next((r for r in runs if r.get('display_title') == f'Taskuary fix #{n}' and str(r.get('created_at') or '') >= str(it.get('FixAt') or '')), None)
            if not run:
                at = datetime.strptime(str(it.get('FixAt')), '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - at).total_seconds() > NEVER_STARTED_MIN * 60:
                    _settle(store, it, Fix='failed', State='needs_you', Result='The cloud fix never started on GitHub - try Fix it again.'); moved += 1
                continue
            if run.get('status') != 'completed': continue
            report = ' '.join(_report(github, tok, repo, run['id']).split())[:REPORT_CHARS]
            if run.get('conclusion') != 'success':
                _settle(store, it, Fix='failed', FixLink=run.get('html_url'), State='needs_you',
                        Result=f"The cloud fix failed ({run.get('conclusion')}). " + (report or 'Its log is on GitHub.')); moved += 1
                continue
            b = requests.get(f'{github.GH}/repos/{repo}/branches/{branch(n)}', headers=github._h(tok), timeout=20)
            if b.status_code != 200:
                _settle(store, it, Fix='nothing', State='needs_you', Result=report or 'The cloud agent changed nothing.'); moved += 1
                continue
            head = b.json()['commit']['sha']
            base = github.repo_info(tok, repo).get('default_branch') or 'main'
            fixed = github.open_pr(tok, repo, branch(n), base, f"{it.get('Title') or f'#{n}'} - with Taskuary's fix",
                                   f"Builds on #{n}: the contributor's commits plus the fix below. Merging this merges theirs.\n\n{report}", draft=False)
            _settle(store, it, Fix='done', FixLink=fixed['url'], Sha=head, State='needs_you', Propose='merge',
                    Result=report or 'Fixed in the cloud - see its pull request.')
            store.add_comment(it['TaskId'], 'router', 'agent', f"{it.get('Title') or ''}: fixed in GitHub's cloud - {fixed['url']}")
            moved += 1
        except Exception as e:
            logger.info(f"cloudfix: {task_ref(it['TaskId'])} item {it.get('Place')} not read this time ({e})")
    return moved
