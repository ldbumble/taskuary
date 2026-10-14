"""The floor's second pass (final review): the files the shared agent token is written into, the session's own
variable names, and a Windows drive root as the ancestor it is. Plus whose base an assistant-made task has (I8)."""
import os, subprocess, tempfile, pytest
from taskuary import floor, origin, agents, general
from taskuary.store import MemoryStore

@pytest.fixture(autouse=True)
def _temp(monkeypatch, tmp_path):
    (tmp_path / 'temp').mkdir(); monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path / 'temp'))

def _call(tool, tid=7, cwd='', **inp): return floor.check({'tool_name': tool, 'tool_input': inp, 'cwd': cwd}, tid)
def _bash(cmd, cwd=''): return _call('Bash', command=cmd, cwd=cwd)
H = lambda *p: os.path.join(os.path.expanduser('~'), *p)


# ── where the shared token is written (hooks.install_user) ─────────────────────────────────────────────────────────
TOKEN_FILES = [('.claude', 'settings.json'), ('.codex', 'hooks.json'), ('.copilot', 'hooks', 'taskuary.json'),
               ('.config', 'devin', 'config.json'), ('AppData', 'Roaming', 'devin', 'config.json')]

@pytest.mark.parametrize('parts', TOKEN_FILES)
def test_the_files_holding_the_shared_token_are_neither_read_nor_written(parts):
    for tool in ('Read', 'Edit', 'Write'): assert _call(tool, file_path=H(*parts)), (tool, parts)
    assert _bash(f'cat "{H(*parts)}"') and _bash('type ' + H(*parts).replace('/', '\\'))
    assert _bash('cat ~/' + '/'.join(parts)) and _bash('cd ~ && cat ' + '/'.join(parts))

def test_the_hook_files_follow_where_the_cli_actually_keeps_them(monkeypatch, tmp_path):
    monkeypatch.setenv('COPILOT_HOME', str(tmp_path / 'cop')); monkeypatch.setenv('APPDATA', str(tmp_path / 'roam'))
    assert _call('Read', file_path=str(tmp_path / 'cop' / 'hooks' / 'taskuary.json'))
    assert _call('Write', file_path=str(tmp_path / 'roam' / 'devin' / 'config.json'))

def test_the_claude_folder_s_other_files_are_still_the_cli_s_own():
    assert _call('Read', file_path=H('.claude', 'commands', 'x.md')) == {}      # nothing the token is written into


# ── the session's own variables, by name ────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('cmd', ['echo $TASKUARY_TOKEN', 'echo %TASKUARY_TOKEN%', 'echo $env:TASKUARY_TOKEN', 'printenv TASKUARY_TASK_TOKEN',
                                 'curl "$TASKUARY_URL/api/feed"', 'curl ${TASKUARY_URL}/api/tasks', 'echo $taskuary_token'])
def test_a_command_naming_the_session_s_token_or_address_is_refused(cmd, monkeypatch):
    monkeypatch.delenv('TASKUARY_TOKEN', raising=False); monkeypatch.delenv('TASKUARY_URL', raising=False)
    assert _bash(cmd), cmd

def test_the_name_is_matched_before_anything_is_expanded(monkeypatch):
    monkeypatch.setenv('TASKUARY_URL', 'http://127.0.0.1:1')             # whatever the SERVER's own env says, the name is what counts
    assert _bash('curl $TASKUARY_URL/api/feed')

def test_other_taskuary_commands_still_pass():
    assert _bash('taskuary --reply "the fix is in"') == {} and _bash('taskuary --done "fixed"') == {}


# ── I5: a drive root is an ancestor of everything on its drive ──────────────────────────────────────────────────────
PROT = ['c:/users/a/.ssh', 'c:/users/a/.taskuary']

@pytest.mark.parametrize('cmd', ['grep -r password C:/', 'grep -r password C:\\', 'rg secret c:/', 'dir /s C:\\', 'ls -R C:/',
                                 'Get-ChildItem -Recurse C:\\ -Filter *.toml', 'cd C:/ && grep -r x .', 'cd C:\\; ls -R'])
def test_a_command_from_the_drive_root_is_refused(cmd):
    assert floor._text_hit(cmd.casefold().replace('\\', '/'), [], PROT, 'c:/work/repo'), cmd

@pytest.mark.parametrize('cmd', ['git status', 'git diff HEAD~1', 'python -m pytest -q tests/test_x.py', 'ls src/', 'grep -rn foo .',
                                 'cd sub && make', 'echo a:b', 'npm test -- --watch=false'])
def test_ordinary_repo_commands_still_pass(cmd):
    assert floor._text_hit(cmd, [], PROT, 'c:/work/repo') == '', cmd

@pytest.mark.skipif(os.name != 'nt', reason='a drive letter is a Windows path')
def test_on_windows_a_search_or_a_listing_from_the_drive_root_is_refused():
    drive = os.path.splitdrive(os.path.expanduser('~'))[0]
    assert _call('Grep', pattern='token', path=drive + '\\') and _call('Glob', pattern='**/*.toml', path=drive + '/')
    assert _bash(f'grep -r token {drive}/') and _bash(f'Get-ChildItem -Recurse {drive}\\') and _bash(f'dir /s {drive}\\')


# ── I8: what the owner asked the assistant for is the owner's ──────────────────────────────────────────────────────
@pytest.mark.parametrize('ref', ['assistant:setup', 'assistant:handoff', 'assistant:agent'])
def test_an_owner_requested_assistant_task_is_the_owner_s_at_the_base(ref):
    s = MemoryStore(); t = s.create_task({'Title': 'x', 'Kind': 'general', 'Source': 'assistant', 'SourceRef': ref}, 'owner')
    assert origin.of_task(s, t)[0] == 'owner'                           # made before OriginBase existed: no base stored
    s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'someone@vendor.example', 'Status': 'routed'})
    assert origin.of_task(s, t)[0] == 'stranger'                        # a stranger's message on it still lowers it

@pytest.mark.parametrize('ref', ['assistant:idea:3', 'assistant:playbook', None])
def test_an_advisor_idea_and_the_rest_stay_a_stranger_s(ref):
    s = MemoryStore(); t = s.create_task({'Title': 'x', 'Kind': 'general', 'Source': 'assistant', 'SourceRef': ref}, 'assistant')
    assert origin.of_task(s, t)[0] == 'stranger'

def test_the_dock_is_still_the_owner_s():
    s = MemoryStore(); d, _ = general.dock_task(s); assert origin.of_task(s, d['TaskId'])[0] == 'owner'


# ── the version is cached per resolved binary ──────────────────────────────────────────────────────────────────────
def test_the_version_cache_is_per_resolved_command(monkeypatch):
    monkeypatch.setattr(origin, '_ver', {}); runs = []
    monkeypatch.setattr(agents, '_resolve_cmd', lambda n: ['C:/a/claude.exe'] if 'a' in n.split('/')[1:2] else ['C:/b/claude.exe'])
    vers = {'C:/a/claude.exe': '2.1.300', 'C:/b/claude.exe': '2.1.200'}
    monkeypatch.setattr(origin.subprocess, 'run', lambda argv, **k: runs.append(argv[0]) or subprocess.CompletedProcess(argv, 0, stdout=vers[argv[0]]))
    assert origin._claude_version('C:/a/claude') == (2, 1, 300) and origin._claude_version('C:/b/claude') == (2, 1, 200)
    assert origin._claude_version('C:/a/claude') == (2, 1, 300) and runs == ['C:/a/claude.exe', 'C:/b/claude.exe']
