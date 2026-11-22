"""The hook commands carry a path to the token, never the token: a command line is in every process listing while it runs."""
import json, os, tempfile
from taskuary import hooks

def test_the_token_is_a_file_in_taskuarys_home_never_on_the_command_line():
    for cmd in (hooks.command('http://127.0.0.1:1', 'sekrit-tok', 'claude'), hooks.ask_command('http://127.0.0.1:1', 'sekrit-tok')):
        assert 'sekrit-tok' not in cmd and 'X-Taskuary-Token' not in cmd
        f = cmd.split('-H "@')[1].split('"')[0]
        assert open(f, encoding='utf-8').read() == 'X-Taskuary-Token: sekrit-tok\n' and '\\' not in f
    assert 'X-Taskuary-Token' not in hooks.command('http://127.0.0.1:1', '', 'claude') and '@' not in hooks.command('http://127.0.0.1:1', '', 'claude').split('@-')[0]

def test_two_tokens_two_files_and_a_rewrite_changes_nothing():
    a, b = hooks.header_file('one'), hooks.header_file('two')
    assert a != b and hooks.header_file('one') == a and open(a, encoding='utf-8').read().endswith('one\n')
    assert not [n for n in os.listdir(os.path.dirname(a)) if n.endswith('.tmp')]

def test_every_installed_hook_file_is_free_of_the_token():
    with tempfile.TemporaryDirectory() as home:
        for cli in hooks.HOOKED: hooks.install_user(cli, base='http://127.0.0.1:1', token='sekrit-tok', home=home)
        for root, _, fs in os.walk(home):
            for n in fs:
                body = open(os.path.join(root, n), encoding='utf-8').read()
                if n.endswith('.hdr'): assert os.path.dirname(os.path.join(root, n)).endswith(os.path.join('.taskuary', 'hooks'))
                else: assert 'sekrit-tok' not in body, n
        args = json.load(open(os.path.join(home, '.copilot', 'hooks', 'taskuary.json'), encoding='utf-8'))['hooks']['Stop'][0]['args']
        assert any(a.startswith('@') and a.endswith('.hdr') for a in args)


def test_the_event_hook_ends_quietly_when_taskuary_is_closed(tmp_path):
    """2026-11-21: with the app shut, every tool call of the owner's own Claude read "PostToolUse:Bash hook failed" - curl's refused
    connection (exit 7) was the hook's exit. The line, run by a shell against a port nothing listens on, ends 0."""
    import shutil, subprocess
    from taskuary import hooks
    if not shutil.which('curl.exe' if os.name == 'nt' else 'curl'): return
    import sys
    run = tmp_path / 'hook.py'        # ...run the one way the suite lets a test start a process: an isolated script of its own
    cmd = hooks.command('http://127.0.0.1:9', '', 'claude', home=str(tmp_path))
    run.write_text(f"import subprocess, sys\nr = subprocess.run({cmd!r}, shell=True, input='{{}}', text=True, capture_output=True, timeout=20)\n"
                   "sys.exit(r.returncode)\n", encoding='utf-8')
    assert subprocess.run([sys.executable, '-I', str(run)], timeout=40).returncode == 0
