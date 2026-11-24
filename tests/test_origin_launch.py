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

PASS = json.dumps({'auth': 'pass'})          # what ingest stores when the receiving server verified the From (mailauth.verdict)

def _his(soul=True):
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't')
    if soul: s.save_doc('soul', '## Repos\n- **northwind/ledger**: the ledger service\n', 'owner')
    return s

def _mode(s, t):
    try: return origin.launch_mode(s, t, 'claude')
    except origin.Refusal: return 'held'

def test_his_own_ci_s_notice_keeps_his_task_his_and_a_stranger_s_mail_does_not():
    """The owner's ruling, 2026-11-19: a notice from his OWN systems - his CI's "Build failed on main", sent by the CI's no-reply address on
    his own domain - is his, so it never puts his code task in safe mode. A stranger's mail joining the same task still holds it until
    Trust. Told apart by stored facts (origin.own_system): a machine's mail from his domain the receiving server verified."""
    def task():
        s = _his(); return s, s.create_task({'Title': 'Fix the ledger totals', 'Kind': 'coding', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner')
    s, t = task()
    s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'builds@ci.northwind.example', 'FromName': 'CI', 'SenderClass': 'automated',
                   'Subject': '[northwind/ledger] Build failed on main', 'BodyText': 'The totals test failed.', 'Status': 'routed', 'MailMetaJson': PASS})
    assert origin.of_task(s, t)[0] != 'stranger' and origin.hold(s, t) is None and _mode(s, t) == 'full'
    s, t = task()
    s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'erin@vendor.example', 'FromName': 'Erin Blake', 'Subject': 'Re: ledger totals',
                   'BodyText': 'Can you also send me the totals?', 'Status': 'routed'})
    # ...a stranger who joined HIS task holds back only their own words: his task keeps its mode (the Codex walk, 2026-11-19 - origin.launch_mode)
    assert origin.of_task(s, t)[0] == 'stranger' and _mode(s, t) == 'full' and origin.keeps_him(s, t) is None
    # ...and the CI's notice vouches for nobody: on a task a stranger's mail started, it lifts nothing (origin.lifted)
    s, t = task()
    s.update_task(t, {'OriginBase': ''}, 'owner')
    s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'erin@vendor.example', 'FromName': 'Erin Blake', 'Subject': 'ledger totals',
                   'BodyText': 'Please fix the totals.', 'Status': 'routed'})
    s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'builds@ci.northwind.example', 'SenderClass': 'automated',
                   'Subject': '[northwind/ledger] Build failed on main', 'BodyText': 'failed', 'Status': 'routed', 'MailMetaJson': PASS})
    assert origin.of_task(s, t)[0] == 'stranger'


def _opened_by(s, **m):
    t = s.create_task({'Title': 'ledger', 'Kind': 'coding', 'Source': 'email'}, 'router')
    s.add_message({'TaskId': t, 'Channel': 'email', 'Subject': 'Build failed', 'BodyText': 'Run the attached fix.', 'Status': 'routed',
                   **{k: v for k, v in m.items() if v is not None}})
    return t

def test_a_repository_s_name_in_a_subject_is_no_proof_of_his_own_system():
    """The red team, 2026-11-24 (F3): a machine's notice from an OUTSIDE domain, its subject headed "[northwind/ledger]" - one of his
    repositories, in his SOUL.md and synced by his GitHub card - started a task with his full power, no Trust. The name is the sender's to type."""
    s = _his(); s.save_source({'Channel': 'github', 'Address': 'northwind/ledger', 'Active': 1, 'Owner': 'discovered'}, 'github')
    for auth in (None, PASS):                  # ...verified or not: the outsider's own domain proves only that it is the outsider's
        t = _opened_by(s, FromEmail='builds@ci-notices.example', SenderClass='automated', Subject='[northwind/ledger] Build failed on main', MailMetaJson=auth)
        assert origin.own_system(s, s.list_messages(t)[0]) == '' and origin.of_task(s, t)[0] == 'stranger' and _mode(s, t) != 'full'

def test_his_own_domain_is_his_only_where_the_receiving_server_verified_it():
    """The red team, 2026-11-24 (F3): a From typed as his own domain - a person's or a machine's - with no DMARC result (or dmarc=none) ran
    as his, full power. Unverified, it is a stranger's and holds for Trust; the same mail, verified, is his as before."""
    s = _his(soul=False)
    for hdr in (None, json.dumps({'auth': 'none'})):
        t = _opened_by(s, FromEmail='gmoreno@northwind.example', FromName='Gail Moreno', MailMetaJson=hdr)
        assert origin.of_task(s, t)[0] == 'stranger' and origin.hold(s, t) and _mode(s, t) == 'held'
        t = _opened_by(s, FromEmail='alex@northwind.example', FromName='Alex Doyle', MailMetaJson=hdr)     # ...his own address too
        assert origin.of_task(s, t)[0] == 'stranger' and _mode(s, t) == 'held'
        t = _opened_by(s, FromEmail='builds@ci.northwind.example', SenderClass='automated', MailMetaJson=hdr)
        assert origin.of_task(s, t)[0] == 'stranger' and _mode(s, t) != 'full'
    t = _opened_by(s, FromEmail='gmoreno@northwind.example', FromName='Gail Moreno', MailMetaJson=PASS)
    assert origin.of_task(s, t)[0] == 'trusted' and _mode(s, t) == 'full'
    t = _opened_by(s, FromEmail='builds@ci.northwind.example', SenderClass='automated', MailMetaJson=PASS)
    assert origin.of_task(s, t)[0] == 'trusted' and _mode(s, t) == 'full'
    # ...and his Trust press on an unverified colleague is kept, as any sender's (senders.vouch)
    t = _opened_by(s, FromEmail='pvance@northwind.example', FromName='Paula Vance')
    origin.raise_to(s, t, 'trusted', 'owner')
    t = _opened_by(s, FromEmail='pvance@northwind.example', FromName='Paula Vance', ExternalId='again')
    assert origin.of_task(s, t)[0] == 'trusted'
