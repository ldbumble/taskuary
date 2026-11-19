import json, pytest
from taskuary import agents, clis, origin
from taskuary.store import MemoryStore
_real = origin._claude_version   # the autouse fixture patches it out; the cache test needs the real one

@pytest.fixture(autouse=True)
def _claude(monkeypatch):
    monkeypatch.setattr(origin, '_claude_version', lambda cmd='claude': (2, 1, 300))   # nothing here may launch a real claude

def _stranger(s):
    t = s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'email'}, 'router')
    # ...a stranger with NO SENDER TO TRUST - Taskuary's own words from what it read: an untrusted sender's task starts no agent at all (origin.hold)
    s.add_message({'TaskId': t, 'Channel': 'assistant', 'FromEmail': 'someone@vendor.example', 'Status': 'routed'}); return t

def test_claude_auto_drops_the_bypass_and_loads_no_mcp():
    a = clis.auto_args('claude', ['-p', '--dangerously-skip-permissions', '--output-format', 'stream-json'])
    assert '--dangerously-skip-permissions' not in a
    assert a[a.index('--permission-mode') + 1] == 'auto' and '--strict-mcp-config' in a

def test_owner_and_trusted_work_launch_full():
    s = MemoryStore(); t = s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner')
    assert origin.launch_mode(s, t, 'codex') == 'full' and origin.launch_mode(s, t, 'claude') == 'full'

def test_a_stranger_s_task_runs_auto_on_claude_reads_only_where_a_cli_can_and_is_refused_elsewhere():
    """The owner, 2026-11-10 ("this is also weird bug?"): a monitor's task on a CLI with no reviewer was refused outright, "couldn't start". A
    CLI with a read-only mode of its own (clis.READONLY) reads and answers in it; only one with neither is refused, in words that name the move."""
    s = MemoryStore(); t = _stranger(s)
    assert origin.launch_mode(s, t, 'claude') == 'auto' and origin.launch_mode(s, t, 'gemini') == 'look' and origin.launch_mode(s, t, 'codex') == 'look'
    with pytest.raises(origin.Refusal, match="Trust them if you know who wrote it") as e: origin.launch_mode(s, t, 'copilot')
    assert 'claude' not in str(e.value) and 'reviewer' not in str(e.value)     # never another tool, never our jargon

def test_an_old_claude_reads_only_on_stranger_work(monkeypatch):
    s = MemoryStore(); t = _stranger(s)
    monkeypatch.setattr(origin, '_claude_version', lambda cmd='claude': (2, 1, 200))
    assert origin.launch_mode(s, t, 'claude') == 'look'          # a reviewer too old to refuse is no reviewer: its read-only mode

def test_an_old_claude_does_not_touch_owner_work(monkeypatch):
    s = MemoryStore(); t = s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner')
    monkeypatch.setattr(origin, '_claude_version', lambda cmd='claude': (1, 0, 0))
    assert origin.launch_mode(s, t, 'claude') == 'full'

def test_the_session_file_carries_both_hooks_fail_closed_and_the_theme():
    s = MemoryStore(); t = _stranger(s)
    d = json.load(open(origin.session_settings(s, t, theme='dark'), encoding='utf-8'))
    pre, perm = d['hooks']['PreToolUse'][0]['hooks'][0], d['hooks']['PermissionRequest'][0]['hooks'][0]
    assert '/api/hooks/claude/floor' in pre['command'] and pre['onFailure'] == 'block'
    assert '/api/hooks/claude/permit' in perm['command'] and perm['onFailure'] == 'block' and perm['timeout'] == 604800
    assert f'task={t}' in pre['command'] and d['theme'] == 'dark' and d['autoMode']['environment']
    assert 'has not authorised running' in ' '.join(d['autoMode']['environment']) and origin.SETTINGS_HOOKS_MERGE

def test_the_hook_commands_carry_the_task_s_own_token_the_task_and_fail_on_http_errors():
    from taskuary import guard, config
    s = MemoryStore(); t = _stranger(s); srv = config.load()['server']
    d = json.load(open(origin.session_settings(s, t), encoding='utf-8'))
    for c in (d['hooks']['PreToolUse'][0]['hooks'][0]['command'], d['hooks']['PermissionRequest'][0]['hooks'][0]['command']):
        f = c.split('-H "@')[1].split('"')[0]
        assert open(f, encoding='utf-8').read() == f'X-Taskuary-Token: {guard.stranger_token(srv, t)}\n' and f'?task={t}' in c and ' -f ' in c
        assert guard.stranger_token(srv, t) not in c                       # in a file, off the command line (hooks.header_file)
        assert srv['agent_token'] not in c + open(f, encoding='utf-8').read() and guard.TASK_HDR not in c     # never the shared token (R28)

def test_claude_version_caches_only_a_success(monkeypatch):
    import subprocess
    monkeypatch.setattr(origin, '_claude_version', _real); monkeypatch.setattr(origin, '_ver', {})
    outs = iter([OSError('busy'), subprocess.CompletedProcess([], 0, stdout='2.1.300 (Claude Code)'), AssertionError('cached')])
    def run(*a, **k):
        o = next(outs)
        if isinstance(o, BaseException): raise o
        return o
    monkeypatch.setattr(origin.subprocess, 'run', run); monkeypatch.setattr(agents, '_resolve_cmd', lambda c: ['claude.exe'])
    assert origin._claude_version('claude') == () and origin._claude_version('claude') == (2, 1, 300) and origin._claude_version('claude') == (2, 1, 300)

def test_his_own_ci_s_notice_keeps_his_task_his_and_a_stranger_s_mail_does_not():
    """The owner's ruling, 2026-11-19: a notice from his OWN systems - his CI's "[northwind/ledger] Build failed on main", sent by the CI's
    no-reply address on its own domain - is his, so it never puts his code task in safe mode: the agent keeps full tools and hears it. A
    stranger's mail joining the same task still holds it until Trust. Told apart by stored facts (origin.own_system): a machine's mail
    (SenderClass) naming one of his repositories (the SOUL.md map) in the subject's [owner/repo] marker."""
    def task():
        s = MemoryStore(); s.save_doc('soul', '## Repos\n- **northwind/ledger**: the ledger service\n', 'owner')
        return s, s.create_task({'Title': 'Fix the ledger totals', 'Kind': 'coding', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner')
    def mode(s, t):
        try: return origin.launch_mode(s, t, 'claude')
        except origin.Refusal: return 'held'
    s, t = task()
    s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'builds@ci.example', 'FromName': 'CI', 'SenderClass': 'automated',
                   'Subject': '[northwind/ledger] Build failed on main', 'BodyText': 'The totals test failed.', 'Status': 'routed'})
    assert origin.of_task(s, t)[0] != 'stranger' and origin.hold(s, t) is None and mode(s, t) == 'full'
    s, t = task()
    s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'erin@vendor.example', 'FromName': 'Erin Blake', 'Subject': 'Re: ledger totals',
                   'BodyText': 'Can you also send me the totals?', 'Status': 'routed'})
    assert origin.of_task(s, t)[0] == 'stranger' and mode(s, t) != 'full'
    # ...and the CI's notice vouches for nobody: on a task a stranger's mail started, it lifts nothing (origin.lifted)
    s, t = task()
    s.update_task(t, {'OriginBase': ''}, 'owner')
    s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'erin@vendor.example', 'FromName': 'Erin Blake', 'Subject': 'ledger totals',
                   'BodyText': 'Please fix the totals.', 'Status': 'routed'})
    s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'builds@ci.example', 'SenderClass': 'automated',
                   'Subject': '[northwind/ledger] Build failed on main', 'BodyText': 'failed', 'Status': 'routed'})
    assert origin.of_task(s, t)[0] == 'stranger'


def test_a_repository_his_github_card_reaches_is_his_own_too():
    "Not only the SOUL.md map: the repositories his GitHub card syncs (its sources) are his systems, a stored fact (origin.own_system)."
    s = MemoryStore()
    note = {'Channel': 'email', 'FromEmail': 'builds@ci.example', 'SenderClass': 'automated', 'Subject': '[northwind/portal] Build failed on main'}
    assert origin.own_system(s, note) == ''
    s.save_source({'Channel': 'github', 'Address': 'northwind/portal', 'Active': 1, 'Owner': 'discovered'}, 'github')
    assert 'northwind/portal' in origin.own_system(s, note)
