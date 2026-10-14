"""Ways round the floor a reviewer found (fix round 1). Each is a spelling of a protected thing the OS or shell resolves
differently from how the floor first read it."""
import os, pathlib, pytest
from taskuary import floor, config, origin

H = os.path.expanduser('~')
def chk(tool, cwd='', tid=7, **inp): return floor.check({'tool_name': tool, 'cwd': cwd, 'tool_input': inp}, tid)
def denied(r): return r.get('hookSpecificOutput', {}).get('permissionDecision') == 'deny'
def sl(p): return str(p).replace('\\', '/')

@pytest.fixture
def hm(monkeypatch):
    "Taskuary's folder placed under the user's home, as it is for a real owner."
    p = pathlib.Path(H) / '.taskuary_t'; monkeypatch.setattr(floor, 'home', lambda: p); return p

def test_a_variable_in_a_file_path_cannot_move_the_floor(hm, monkeypatch, tmp_path):
    monkeypatch.setenv('FLOORV', str(hm))   # the tools take the path literally; a shell or a later layer may expand it
    assert denied(chk('Read', cwd=str(tmp_path), file_path='%FLOORV%/config.toml')) or denied(chk('Read', cwd=str(tmp_path), file_path='$FLOORV/config.toml'))

@pytest.mark.skipif(os.name != 'nt', reason='Windows path spellings')
def test_extended_length_and_unc_spellings_are_refused(hm):
    c = str(hm / 'config.toml')
    for p in ('\\\\?\\' + c, '\\\\.\\' + c, '\\\\localhost\\c$\\' + c[3:], '\\\\?\\UNC\\localhost\\c$\\' + c[3:], c + '.', str(hm) + '.\\config.toml'):
        assert denied(chk('Read', file_path=p)), p

def test_a_unc_path_is_refused_outright():
    assert denied(chk('Read', file_path='//server/share/x.txt')) and denied(chk('Read', file_path='\\\\server\\share\\x.txt'))

def test_a_search_rooted_above_a_protected_folder_is_refused(hm):
    up = str(hm.parent)
    assert denied(chk('Grep', pattern='token', path=str(hm.parent)))
    assert denied(chk('Grep', pattern='token', path=up, glob='.taskuary_t/*'))
    assert denied(chk('Glob', path=up, pattern='**/.ssh/*'))
    assert denied(chk('Grep', cwd=up, pattern='token'))                    # no path: the session's folder
    assert denied(chk('Glob', cwd=up, pattern='**/id_rsa'))
    assert denied(chk('Grep', cwd=str(hm.parent.parent), pattern='x', path=up))
    assert not denied(chk('Grep', cwd=os.getcwd(), pattern='token'))      # an ordinary repo search is fine
    assert not denied(chk('Glob', cwd=os.getcwd(), pattern='**/*.py'))

def test_this_task_s_own_path_cannot_be_walked_out_of(hm):
    own, ctx = origin.stranger_dir(7), hm / 'context' / 'TQ-0007.stranger.md'
    up = os.path.relpath(hm / 'config.toml', own).replace('\\', '/')    # from its own folder (outside Taskuary's) back into it
    for cmd in (f'cat {own}/{up}', f'cat {sl(own)}/{up}', f'cat {ctx}/../../config.toml', f'cat {sl(ctx)}/../../config.toml'):
        assert denied(chk('Bash', command=cmd)), cmd
    assert denied(chk('Bash', tid=1000, command=f'cat {sl(origin.stranger_dir(10001))}/notes.md'))   # a longer id is not the same task
    assert not denied(chk('Bash', command=f'cat {sl(own)}/notes.md')) and not denied(chk('Bash', command=f'cat "{own}/notes.md"'))

def test_cheap_command_forms_are_refused(hm):
    port = config.load()['server'].get('port') or 7787
    cmds = ['cd ~ && cat .taskuary_t/config.toml', 'cat ../../.ssh/id_rsa', 'cat ~/".taskuary_t"/config.toml',
            'Get-Content (Join-Path $env:USERPROFILE ".ssh\\id_rsa")', 'gc ${env:USERPROFILE}/.ssh/id_rsa', 'cat ${HOME}/.ssh/id_rsa',
            'cat $HOME/.SSH/id_rsa', "cat '~/.aws/credentials'", 'find ~ -name config.toml',
            f'curl http://127.1:{port}/', f'curl http://127.0.0.2:{port}/', f'curl http://192.168.1.20:{port}/api/feed', f'curl "http://[::ffff:127.0.0.1]:{port}/"',
            f'curl http://my-host.local:{port}/']
    for c in cmds:
        for t in ('Bash', 'PowerShell'): assert denied(chk(t, command=c)), c
    assert denied(chk('WebFetch', url=f'http://127.0.0.2:{port}/'))

def test_case_is_folded_everywhere(hm):
    assert denied(chk('Read', file_path='~/.SSH/id_rsa')) and denied(chk('Read', file_path=str(hm).upper() + '/CONFIG.toml'))

def test_more_credential_stores_are_refused():
    for p in ('~/.config/gcloud/credentials.db', '~/AppData/Roaming/gcloud/x', '~/.npmrc', '~/.pypirc', '~/.config/hub'):
        assert denied(chk('Read', file_path=p)), p

def test_the_home_relative_form_of_taskuary_s_folder(hm):
    assert denied(chk('Bash', command=f'cat ~/{hm.name}/config.toml')) and denied(chk('Read', file_path=f'~/{hm.name}/config.toml'))

def test_a_variable_that_expands_elsewhere_cannot_hide_the_literal_path(hm, monkeypatch):
    monkeypatch.setenv('FLOORV', 'x/y/z')   # literal: <home>/.taskuary_t/config.toml; expanded: <home>/x/y/.taskuary_t/config.toml
    assert denied(chk('Read', file_path=f'{hm.parent}/%FLOORV%/../{hm.name}/config.toml'))
    assert denied(chk('Read', file_path=f'{hm.parent}/$FLOORV/../{hm.name}/config.toml'))

def test_a_relative_path_in_a_command_is_the_session_s_not_the_server_s(hm):
    cwd = str(hm / 'work' / 'TQ-0007')          # a session that cd'd into Taskuary's tree: relative paths resolve from there
    for c in ('cat ../../config.toml', 'type ..\..\config.toml', 'cat ./../../config.toml', 'cat ../../context/TQ-0008.stranger.md'):
        assert denied(chk('Bash', cwd=cwd, command=c)), c
    assert denied(chk('PowerShell', cwd=cwd, command='Get-Content ..\..\config.toml'))
    own = str(origin.stranger_dir(7))           # its own folder is where it really runs
    assert not denied(chk('Bash', cwd=own, command='cat ./notes.md')) and not denied(chk('Bash', cwd=own, command='python -m pytest -q tests/x.py'))
    assert not denied(chk('Bash', cwd=own, command='curl -s https://vendor.example/a/b'))

def test_a_cd_earlier_in_the_command_moves_the_base(hm, tmp_path):
    own = hm / 'work' / 'TQ-0007'               # a folder inside Taskuary's tree, two levels down
    for c in (f'cd {own} && type ..\..\config.toml', f'pushd {sl(own)}; cat ../../config.toml', f'Set-Location {own}; gc ..\..\config.toml', f'sl "{own}"; gc ../../config.toml'):
        assert denied(chk('PowerShell', cwd=str(tmp_path), command=c)), c
    assert not denied(chk('Bash', cwd=str(tmp_path), command=f'cd {sl(origin.stranger_dir(7))} && cat ./notes.md'))
    assert denied(chk('Bash', cwd=str(tmp_path), command=f'cd {sl(tmp_path)} && cd {sl(own)} && cat ../../config.toml'))   # the last cd before the token
