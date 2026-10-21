import json, pytest
from taskuary import agents, clis, origin
from taskuary.store import MemoryStore
_real = origin._claude_version   # the autouse fixture patches it out; the cache test needs the real one

@pytest.fixture(autouse=True)
def _claude(monkeypatch):
    monkeypatch.setattr(origin, '_claude_version', lambda cmd='claude': (2, 1, 300))   # nothing here may launch a real claude

def _stranger(s):
    t = s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'email'}, 'router')
    s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'someone@vendor.example', 'Status': 'routed'}); return t

def test_claude_auto_drops_the_bypass_and_loads_no_mcp():
    a = clis.auto_args('claude', ['-p', '--dangerously-skip-permissions', '--output-format', 'stream-json'])
    assert '--dangerously-skip-permissions' not in a
    assert a[a.index('--permission-mode') + 1] == 'auto' and '--strict-mcp-config' in a

def test_owner_and_trusted_work_launch_full():
    s = MemoryStore(); t = s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner')
    assert origin.launch_mode(s, t, 'codex') == 'full' and origin.launch_mode(s, t, 'claude') == 'full'

def test_a_stranger_s_task_runs_auto_on_claude_and_is_refused_elsewhere():
    s = MemoryStore(); t = _stranger(s)
    assert origin.launch_mode(s, t, 'claude') == 'auto'
    with pytest.raises(origin.Refusal, match="no built-in reviewer") as e: origin.launch_mode(s, t, 'gemini')
    assert 'claude' not in str(e.value)          # no claude is connected here, so the refusal never offers one

def test_an_old_claude_is_refused_stranger_work(monkeypatch):
    s = MemoryStore(); t = _stranger(s)
    monkeypatch.setattr(origin, '_claude_version', lambda cmd='claude': (2, 1, 200))
    with pytest.raises(origin.Refusal, match='2.1.295'): origin.launch_mode(s, t, 'claude')

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
    assert origin._claude_version() == () and origin._claude_version() == (2, 1, 300) and origin._claude_version() == (2, 1, 300)
