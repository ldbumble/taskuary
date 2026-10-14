"""The floor in a stranger's session, wave B: Taskuary's own package run in-process (B1b), and the files a later session
of the owner's reads as configuration or runs as a hook (B3). Name matching, by design - auto mode is the backstop."""
import os, pytest
from taskuary import floor

H = os.path.expanduser('~')
def call(tool, cwd='', **inp): return floor.check({'tool_name': tool, 'cwd': cwd, 'tool_input': inp}, 7)
def denied(r): return r.get('hookSpecificOutput', {}).get('permissionDecision') == 'deny'
SHELLS = ('Bash', 'PowerShell')


# ── B1b: Taskuary's package, in-process ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('cmd', [
    'python -m taskuary --prompts', 'py -3 -m taskuary.cli --link', 'python3 -m  taskuary',
    'python -c "from taskuary import config; print(config._read())"', "python -c 'import taskuary.config as c'",
    'python -c "import os, taskuary"', 'python -c "__import__(\'taskuary\').config"', 'python -c "import importlib; importlib.import_module(\'taskuary.config\')"',
    'python - <<EOF\nfrom taskuary.config import _read\nprint(_read())\nEOF',
    'taskuary --prompts', 'taskuary --link', 'taskuary', 'taskuary --no-browser', 'taskuary --learned x --why-earned y', 'taskuary --board',
    'taskuary --board --all', 'taskuary --upvote 3', 'taskuary --comment 3 --body x', 'taskuary --evalset build', 'taskuary --demo',
    'C:/tools/Scripts/taskuary.exe --prompts', '& "C:\\tools\\Scripts\\taskuary.exe" --link', 'echo hi && taskuary --prompts',
    'taskuary --reply hi; taskuary --prompts', 'taskuary-desktop', 'taskuary --reply=hi --prompts',
    'unset TASKUARY_TASK; taskuary --note x', 'env -i taskuary --note x', 'env -u TASKUARY_SID taskuary --note x',
    'Remove-Item Env:TASKUARY_AGENT; taskuary --note x', 'TASKUARY_TASK=5 taskuary --reply hi'])
def test_taskuary_in_process_or_outside_the_agent_commands_is_refused(cmd):
    for t in SHELLS: assert denied(call(t, command=cmd)), (t, cmd)

@pytest.mark.parametrize('cmd', [
    'taskuary --reply "the fix is in"', 'taskuary --reply - < reply.md', 'taskuary --reply-file reply.md --attach out.pdf',
    'taskuary --done "fixed the parser"', 'taskuary --done', 'taskuary --done "nothing to send" --no-reply',
    'taskuary --note "tests pass" --kind ready', 'taskuary --item 2 --result "a duplicate of 1" --overlap 1 --propose merge',
    'taskuary --item 3 --result ok --settled', 'taskuary --draft - --slot a1 --to someone@vendor.example --subject Re', 'taskuary --draft-file d.md',
    'taskuary --help', 'taskuary --version', 'python -m pytest -q', 'python -c "import json; print(1)"', 'cd taskuary && pytest',
    'pytest tests/test_taskuary_cli.py', 'git log --oneline -3', 'pip install requests'])
def test_the_agent_commands_and_ordinary_work_pass(cmd):
    for t in SHELLS: assert call(t, command=cmd) == {}, (t, cmd)

def test_a_script_written_to_import_taskuary_is_refused_at_the_write(tmp_path):
    "Else `python x.py` runs it, and the command names nothing."
    f = str(tmp_path / 'x.py')
    assert denied(call('Write', file_path=f, content='from taskuary.config import _read\nprint(_read())'))
    assert denied(call('Edit', file_path=f, old_string='pass', new_string='import taskuary'))
    assert denied(call('MultiEdit', file_path=f, edits=[{'old_string': 'a', 'new_string': '__import__("taskuary")'}]))
    assert call('Write', file_path=f, content='import json\nprint("taskuary is a word here")') == {}

@pytest.mark.parametrize('cmd', ['git config core.hooksPath /tmp/h', 'git config --global core.sshCommand "sh x"', 'git -C repo config core.fsmonitor x',
                                 'git config --add include.path ../x', 'git config --unset core.hooksPath'])
def test_git_config_writes_are_refused(cmd, repo):
    for t in SHELLS: assert denied(call(t, repo, command=cmd)), (t, cmd)

@pytest.mark.parametrize('cmd', ['git config --get user.email', 'git config --list', 'git config -l', 'git config --get-regexp remote',
                                 'git config --show-origin --list', 'git -c core.pager=cat log'])
def test_git_config_reads_pass(cmd, repo):
    for t in SHELLS: assert call(t, repo, command=cmd) == {}, (t, cmd)

def test_the_floor_lets_through_exactly_what_the_cli_runs_for_a_stranger():
    from taskuary import cli
    assert floor.TASKUARY_OK == {cli._flag(a) for a in cli.STRANGER_ACTS}
    assert '`taskuary --prompts`' in call('Bash', command='taskuary --prompts')['hookSpecificOutput']['permissionDecisionReason']


# ── B3: what a later session reads as configuration or runs ─────────────────────────────────────────────────────────
HOME_FILES = ['~/.claude/settings.local.json', '~/.claude/hooks/pre.sh', '~/.claude/agents/a.md', '~/.claude/commands/c.md',
              '~/.claude/skills/s/SKILL.md', '~/.claude/CLAUDE.md', '~/.codex/config.toml', '~/.codex/hooks.json', '~/.codex/AGENTS.md',
              '~/.copilot/config.json', '~/.copilot/hooks/h.json', '~/.gemini/settings.json', '~/.claude.json', '~/.claude/settings.json']
REPO_FILES = ['.git/hooks/pre-commit', '.git/config', '.claude/settings.json', '.claude/settings.local.json', '.claude/commands/x.md',
              '.claude/agents/y.md', '.claude/CLAUDE.md', '.mcp.json']

@pytest.fixture
def repo(tmp_path):
    (tmp_path / '.git' / 'hooks').mkdir(parents=True); return str(tmp_path)

@pytest.mark.parametrize('tool', ['Write', 'Edit', 'MultiEdit', 'NotebookEdit'])
def test_writing_the_owner_s_cli_configuration_is_refused(tool, repo):
    key = 'notebook_path' if tool == 'NotebookEdit' else 'file_path'
    for p in HOME_FILES: assert denied(call(tool, repo, **{key: p})), p
    for p in REPO_FILES:
        assert denied(call(tool, repo, **{key: p})), p                                   # relative to the session's folder
        assert denied(call(tool, repo, **{key: os.path.join(repo, p)})), p               # and absolute
    if os.name == 'nt': assert denied(call(tool, repo, **{key: os.path.join(repo, '.GIT', 'Hooks', 'pre-push')}))

@pytest.mark.parametrize('cmd', [
    'echo "curl x | sh" > .git/hooks/pre-commit', 'echo x >> ~/.claude/CLAUDE.md', 'printf x | tee .mcp.json', 'cat a | tee -a .claude/settings.json',
    'cp evil.sh .git/hooks/post-checkout', 'mv a.json .claude/settings.local.json', 'cp -r cmds ~/.claude/commands',
    'Copy-Item a.ps1 -Destination .git/hooks/pre-push', 'Set-Content -Path .mcp.json -Value "{}"', 'Add-Content .git/config "[core]"',
    'Out-File -FilePath ~/.codex/config.toml', 'New-Item -ItemType File -Path .claude/commands/x.md', 'echo x | Out-File ~/.copilot/config.json',
    'cd .git && echo x > hooks/pre-commit', 'cd .git/hooks; cp ../../x.sh pre-commit', 'echo {} 1> .mcp.json', 'echo x >~/.gemini/settings.json',
    'sed -i s/a/b/ .git/config', 'Move-Item x.md ~/.claude/agents/x.md'])
def test_a_shell_write_into_them_is_refused(cmd, repo):
    for t in SHELLS: assert denied(call(t, repo, command=cmd)), (t, cmd)

@pytest.mark.parametrize('cmd', ['echo x > notes.txt', 'cp a.py b.py', 'git status', 'git diff .git/config', 'cat .mcp.json | jq .',
                                 'python -m pytest -q 2>&1 | tee test.log', 'Set-Content -Path out.txt -Value x', 'mv CLAUDE.md docs/CLAUDE.md',
                                 'cp .git/config backup.cfg'])
def test_ordinary_shell_writes_pass(cmd, repo):
    for t in SHELLS: assert call(t, repo, command=cmd) == {}, (t, cmd)

def test_the_repository_s_own_instructions_and_code_stay_editable(repo):
    for p in ('CLAUDE.md', 'AGENTS.md', 'src/app.py', 'docs/claude.md', '.github/workflows/ci.yml', 'claude_settings.json'):
        for tool in ('Write', 'Edit'): assert call(tool, repo, file_path=os.path.join(repo, p)) == {}, p
    for p in ('.git/config', '.claude/settings.local.json', '.mcp.json', '.git/hooks/pre-commit'):
        assert call('Read', repo, file_path=os.path.join(repo, p)) == {}, p              # reads are unchanged
