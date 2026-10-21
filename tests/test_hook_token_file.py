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
