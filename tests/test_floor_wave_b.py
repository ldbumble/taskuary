"""The floor in a stranger's session, wave B: Taskuary's own package run in-process (B1b), and the files a later session
of the owner's reads as configuration or runs as a hook (B3). Name matching, by design - auto mode is the backstop."""
import os, pytest
from taskuary import floor

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

@pytest.mark.parametrize('cmd', ['python -mtaskuary --prompts', 'python -m "taskuary" --prompts', "python -m'taskuary.cli'",
                                 'unset ${!TASKUARY_*}', 'Get-ChildItem Env:TASKUARY_* | Remove-Item', 'Get-ChildItem Env: | Remove-Item',
                                 'Remove-Item Env:*', 'export TASKUARY_TOKEN=', 'for v in $(compgen -e); do unset $v; done',
                                 '[Environment]::SetEnvironmentVariable("X", $null)', 'echo $TASKUARY_HOME'])
def test_plain_forms_without_markers_are_refused_too(cmd):
    for t in SHELLS: assert denied(call(t, command=cmd)), (t, cmd)

def test_a_script_that_unsets_the_markers_and_runs_taskuary_is_refused_at_the_write(tmp_path):
    f = str(tmp_path / 'x.sh')
    assert denied(call('Write', file_path=f, content='#!/bin/sh\nunset TASKUARY_TASK TASKUARY_SID\ntaskuary --prompts\n'))
    assert denied(call('Write', file_path=f, content='#!/bin/sh\ntaskuary --link\n'))
    assert denied(call('Edit', file_path=f, old_string='a', new_string='env -i taskuary --note x'))
    assert call('Write', file_path=f, content='#!/bin/sh\ntaskuary --reply "done"\npytest -q\n') == {}

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


# ── round 2: the environment emptied by any option order; written content judged only where it will run ──────────────
@pytest.mark.parametrize('cmd', ['env - taskuary --note x', 'env -v -i taskuary --note x', 'env --chdir=/ -i taskuary --note x',
                                 'env -vi taskuary --note x', 'env -C / --ignore-environment taskuary --note x', 'env -u TASKUARY_SID taskuary --note x',
                                 'env --unset=TASKUARY_TASK taskuary --note x', 'exec -c taskuary --note x', 'exec -cl taskuary --note x',
                                 'Start-Process taskuary -ArgumentList "--note x" -UseNewEnvironment',
                                 '[Environment]::SetEnvironmentVariable("TASKUARY_SID", $null)', 'Remove-Item Env:FOO', 'Remove-Item -Path Env:*'])
def test_every_way_of_emptying_the_environment_is_refused(cmd):
    for t in SHELLS: assert denied(call(t, command=cmd)), (t, cmd)

@pytest.mark.parametrize('cmd', ['env', 'printenv PATH', 'env FOO=1 npm test', 'env -C dir npm test', 'env -u FOO npm test',
                                 'git commit -m "Taskuary fix"', 'git commit -m "data from Taskuary, import Taskuary docs"',
                                 'echo $env:PATH'])
def test_ordinary_environment_and_commit_commands_pass(cmd):
    for t in SHELLS: assert call(t, command=cmd) == {}, (t, cmd)

@pytest.mark.parametrize('name,content', [
    ('.github/workflows/ci.yml', 'jobs:\n  test:\n    env:\n      NODE_ENV: test\n    steps:\n      - run: taskuary --demo\n'),
    ('.eslintrc.js', 'module.exports = { env: { node: true } }\n'),
    ('README.md', 'taskuary --demo opens a demo\n\nRun `taskuary --link` for a link.\n'),
    ('docs/setup.txt', 'taskuary --prompts\nunset TASKUARY_TASK\n'),
    ('app/config.py', 'import os\ntask = os.environ["TASKUARY_TASK"]\nprint("taskuary --demo")\n'),
    ('conf.toml', 'cmd = "python -m taskuary"\n'), ('notes.json', '{"run": "env -i taskuary --note x"}')])
def test_ordinary_files_that_mention_taskuary_are_written(name, content, tmp_path):
    assert call('Write', file_path=str(tmp_path / name), content=content) == {}, name

@pytest.mark.parametrize('name,content', [
    ('x.sh', 'unset TASKUARY_TASK TASKUARY_SID\ntaskuary --note "x"\n'), ('x.ps1', 'Remove-Item Env:TASKUARY_*\ntaskuary --note x\n'),
    ('x.py', 'from taskuary.config import _read\n'), ('x.py', 'import os\nos.environ.pop("TASKUARY_TASK")\n'),
    ('x.py', 'import os\ndel os.environ["TASKUARY_SID"]\n'), ('x.bat', 'set TASKUARY_TASK=\ntaskuary --note x\n'),
    ('x.sh', 'taskuary --prompts\n'), ('x.cmd', 'python -m taskuary --prompts\n'), ('run', '#!/bin/sh\nenv -i taskuary --note x\n')])
# (a command a program builds in a string - execSync("env - taskuary ...") - is auto mode's: a string is not a command position)
def test_a_script_that_would_be_refused_when_run_is_refused_at_the_write(name, content, tmp_path):
    assert denied(call('Write', file_path=str(tmp_path / name), content=content)), name

def test_an_edit_to_an_extensionless_script_is_judged_by_its_shebang(tmp_path):
    f = tmp_path / 'run'; f.write_text('#!/bin/sh\necho hi\n')
    assert denied(call('Edit', file_path=str(f), old_string='echo hi', new_string='taskuary --prompts'))
    g = tmp_path / 'notes'; g.write_text('plain words\n')
    assert call('Edit', file_path=str(g), old_string='plain', new_string='taskuary --prompts') == {}


# ── round 3 (R35): for a command, the broad check OR the precise one; the narrowing is for written non-script content ─
@pytest.mark.parametrize('cmd', [
    'python -W ignore -m taskuary --prompts', 'python3 -X utf8 -m taskuary --prompts', 'uv run -m taskuary --prompts',
    'env FOO=1 env -i taskuary --note x', 'nice env -i taskuary --note x', 'timeout 5 env -i taskuary --note x',
    'Remove-Item "Env:$n"', 'Remove-Item -Path "Env:*"', 'Get-Item Env:* | Remove-Item',
    'env --ign taskuary --note x', 'env --ignore taskuary --note x', 'env -S "-i taskuary --note x"', 'env -S-i taskuary --note x',
    'env --split-string="-i taskuary" --note x', 'Start-Process taskuary -UseNew', 'Start-Process taskuary -UseNewEnv'])
def test_the_broad_forms_are_refused_again(cmd):
    for t in SHELLS: assert denied(call(t, command=cmd)), (t, cmd)

@pytest.mark.parametrize('cmd', ['exec python -c "print(1)"', 'exec bash -c "npm test"', 'git commit -m "Taskuary fix"', 'env', 'printenv PATH',
                                 'env FOO=1 npm test', 'env -C dir npm test', 'echo $env:PATH'])
def test_still_ordinary(cmd):
    for t in SHELLS: assert call(t, command=cmd) == {}, (t, cmd)

@pytest.mark.parametrize('name,content', [
    ('package.json', '{"name": "x", "scripts": {"test": "env -i taskuary --note x"}}'), ('Makefile', 'test:\n\tpython -m taskuary --prompts\n'),
    ('GNUmakefile', 'all:\n\ttaskuary --link\n'), ('justfile', 'go:\n    taskuary --prompts\n'), ('Taskfile.yml', 'tasks:\n  go:\n    cmds:\n      - taskuary --prompts\n'),
    ('x.ts', 'import { execSync } from "child_process"\n'), ('x.ts', '#!/usr/bin/env node\n'), ('x.mts', 'import taskuary\n'),
    ('x.py', 'import os\nos.environ.update(TASKUARY_SID="")\n'), ('x.py', 'import os\nos.unsetenv("TASKUARY_SID")\n'),
    ('x.py', 'import os\nos.putenv("TASKUARY_TASK", "5")\n')])
def test_task_runner_files_and_typescript_are_judged_as_scripts(name, content, tmp_path):
    r = call('Write', file_path=str(tmp_path / name), content=content)
    assert denied(r) == (name != 'x.ts'), (name, content)                  # the two .ts files are ordinary scripts

def test_a_package_json_without_them_is_written(tmp_path):
    assert call('Write', file_path=str(tmp_path / 'package.json'), content='{"scripts": {"test": "env FOO=1 node --test", "build": "vite build"}}') == {}

def test_an_edit_that_makes_a_file_a_script_is_judged_as_one(tmp_path):
    f = tmp_path / 'run'; f.write_text('echo hi\ntaskuary --prompts\n')
    assert denied(call('Edit', file_path=str(f), old_string='echo hi', new_string='#!/bin/sh\necho hi'))


# ── round 4 (R36): an edit is judged by what it ADDS; the script marks look like PowerShell before they count ─────────
@pytest.mark.parametrize('name,before,old,new', [
    ('test_x.py', 'import taskuary\n\ndef test_a(): assert 1\n', 'assert 1', 'assert 2'),
    ('Makefile', 'demo:\n\ttaskuary --demo\ntest:\n\tpytest\n', 'pytest', 'pytest -q'),
    ('package.json', '{"scripts": {"demo": "taskuary --demo", "test": "vitest"}}', '"vitest"', '"vitest run"')])
def test_an_edit_beside_an_existing_hit_is_written(name, before, old, new, tmp_path):
    f = tmp_path / name; f.write_text(before)
    assert call('Edit', file_path=str(f), old_string=old, new_string=new) == {}, name
    assert call('MultiEdit', file_path=str(f), edits=[{'old_string': old, 'new_string': new}]) == {}, name
    assert call('Write', file_path=str(f), content=before.replace(old, new)) == {}, name     # a rewrite that keeps them, too

@pytest.mark.parametrize('name,before,old,new', [
    ('test_x.py', 'import json\n\ndef test_a(): assert 1\n', 'import json', 'import json\nimport taskuary'),
    ('test_x.py', 'import taskuary\n\ndef test_a(): assert 1\n', 'assert 1', 'assert 1\nimport taskuary'),    # a second copy is new
    ('x.sh', '#!/bin/sh\ntaskuary --demo\npytest\n', 'pytest', 'env -i taskuary --note x'),
    ('x.sh', '#!/bin/sh\ntaskuary --demo\npytest\n', 'pytest', 'unset TASKUARY_TASK; pytest'),
    ('Makefile', 'demo:\n\ttaskuary --demo\ntest:\n\tpytest\n', 'pytest', 'pytest; taskuary --prompts')])
def test_an_edit_that_adds_a_hit_is_refused(name, before, old, new, tmp_path):
    f = tmp_path / name; f.write_text(before)
    assert denied(call('Edit', file_path=str(f), old_string=old, new_string=new)), (name, new)
    assert denied(call('Write', file_path=str(f), content=before.replace(old, new))), (name, new)

def test_an_edit_whose_old_text_is_not_there_is_judged_by_what_it_adds(tmp_path):
    "The CLI may still land it (quote normalisation): fail closed."
    f = tmp_path / 'x.py'; f.write_text('print(1)\n')
    assert denied(call('Edit', file_path=str(f), old_string='print(“1”)', new_string='import taskuary'))

def test_a_shebang_added_over_an_existing_hit_is_refused(tmp_path):
    f = tmp_path / 'run'; f.write_text('echo hi\nimport taskuary\n')
    assert denied(call('Edit', file_path=str(f), old_string='echo hi', new_string='#!/usr/bin/env python\necho hi'))

@pytest.mark.parametrize('name,content', [('a.js', 'const o = {env:"prod"}\n'), ('a.ts', 'const cli = meow({ env: process.env })\n'),
                                          ('a.py', '# rm the cache, env: prod\n'), ('a.py', 'parser.add_argument("--usenet")\n')])
def test_object_syntax_and_prose_are_not_powershell(name, content, tmp_path):
    assert call('Write', file_path=str(tmp_path / name), content=content) == {}, content

@pytest.mark.parametrize('content', ['Remove-Item Env:TASKUARY_*\n', 'Remove-Item -Path Env:\\TASKUARY_TASK\n', 'Remove-Item "Env:$n"\n',
                                     'Get-ChildItem Env: | Remove-Item\n', 'Get-Item Env:* | Remove-Item\n', 'Remove-Item -Path "Env:*"\n',
                                     'Start-Process taskuary -UseNewEnvironment\n', 'ri env:FOO\n'])
def test_the_powershell_removal_forms_stay_refused_in_a_script(content, tmp_path):
    assert denied(call('Write', file_path=str(tmp_path / 'x.ps1'), content=content)), content

@pytest.mark.parametrize('cmd', ['env -S"-i taskuary" --note x', "env -S'-i taskuary' --note x", 'pipx run taskuary --prompts',
                                 'pipx run --spec taskuary==1.0 taskuary --prompts'])
def test_a_glued_split_string_and_pipx_are_refused(cmd):
    for t in SHELLS: assert denied(call(t, command=cmd)), (t, cmd)


# ── round 5 (R37): the script marks know PowerShell from the rest; a hit is counted by what it names ────────────────
PS_REMOVALS = ['Remove-Item Env:$n', 'Remove-Item -Path Env:$n', 'Remove-Item Env:${n}', 'Set-Item Env:$n $null', 'rd Env:*', 'rmdir Env:*',
               'erase Env:*', 'dir Env:* | Remove-Item', 'ls env:* | rm', 'Remove-Item -Path:Env:*']

@pytest.mark.parametrize('content', PS_REMOVALS)
@pytest.mark.parametrize('name', ['x.ps1', 'x.psm1', 'x.psd1', 'run'])
def test_every_env_drive_removal_is_refused_in_a_powershell_file(name, content, tmp_path):
    body = ('#!/usr/bin/env pwsh\n' if name == 'run' else '') + content + '\n'
    assert denied(call('Write', file_path=str(tmp_path / name), content=body)), (name, content)

@pytest.mark.parametrize('name', ['a.js', 'a.ts', 'a.py'])
@pytest.mark.parametrize('content', ['const o = {env:"prod"}\n', 'const cli = meow({ env: process.env })\n', '# rm the cache, env: prod\n',
                                     'parser.add_argument("--usenet")\n'])
def test_the_narrowed_marks_hold_for_other_languages(name, content, tmp_path):
    assert call('Write', file_path=str(tmp_path / name), content=content) == {}, (name, content)

def test_a_powershell_read_of_one_variable_is_written(tmp_path):
    assert call('Write', file_path=str(tmp_path / 'x.ps1'), content='$p = $env:PATH\n$env:FOO = "1"\nWrite-Output $p\n') == {}

def test_an_edit_that_changes_what_a_hit_runs_is_refused(tmp_path):
    "Same reason, new target: `env -i make test` turned into `env -i taskuary --reply x` is a new hit."
    f = tmp_path / 'x.sh'; f.write_text('#!/bin/sh\nenv -i make test\n')
    assert denied(call('Edit', file_path=str(f), old_string='env -i make test', new_string='env -i taskuary --reply x'))
    assert call('Edit', file_path=str(f), old_string='#!/bin/sh', new_string='#!/bin/sh\n# runs the tests') == {}

def test_uv_tool_run_is_refused(tmp_path):
    for t in SHELLS: assert denied(call(t, command='uv tool run taskuary --prompts')), t
    assert denied(call('Write', file_path=str(tmp_path / 'x.sh'), content='#!/bin/sh\nuv tool run taskuary --prompts\n'))
    for t in SHELLS: assert call(t, command='uv tool run ruff check .') == {}, t


# ── follow-up (R38): a hit is keyed on its line; runners are unwrapped; PowerShell inside other files is PowerShell ────
@pytest.mark.parametrize('before,old,new', [
    ('Test-Path Env:CI\nWrite-Output hi\n', 'Test-Path Env:CI', 'rd Env:*'),
    ('Remove-Item Env:FOO\nWrite-Output hi\n', 'Remove-Item Env:FOO', 'Remove-Item Env:TASKUARY_SID'),
    ('[Environment]::SetEnvironmentVariable("A","1")\n', 'SetEnvironmentVariable("A","1")', 'SetEnvironmentVariable("TASKUARY_SID",$null)')])
def test_an_edit_that_retargets_a_powershell_hit_is_refused(before, old, new, tmp_path):
    f = tmp_path / 'x.ps1'; f.write_text(before)
    assert denied(call('Edit', file_path=str(f), old_string=old, new_string=new)), new
    assert denied(call('Write', file_path=str(f), content=before.replace(old, new))), new

def test_a_reindent_or_an_edit_elsewhere_in_a_powershell_file_is_written(tmp_path):
    f = tmp_path / 'x.ps1'; f.write_text('if ($ci) {\nTest-Path Env:CI\n}\nWrite-Output hi\n')
    assert call('Edit', file_path=str(f), old_string='Test-Path Env:CI', new_string='    Test-Path  Env:CI') == {}
    assert call('Edit', file_path=str(f), old_string='Write-Output hi', new_string='Write-Output bye') == {}

RUNNERS = ['uv run taskuary --prompts', 'uv run --with taskuary taskuary --prompts', 'poetry run taskuary --prompts', 'npx taskuary --prompts',
           'pdm run taskuary', 'hatch run taskuary', 'pipenv run taskuary', 'uv run -- taskuary --link', 'npx -y taskuary --demo',
           'uv run --python 3.12 taskuary --prompts', 'npx --package taskuary taskuary --board', 'uv run poetry run taskuary --prompts']

@pytest.mark.parametrize('cmd', RUNNERS)
def test_a_runner_s_program_is_held_to_the_taskuary_rules(cmd, tmp_path):
    for t in SHELLS: assert denied(call(t, command=cmd)), (t, cmd)
    assert denied(call('Write', file_path=str(tmp_path / 'x.sh'), content=f'#!/bin/sh\n{cmd}\n')), cmd
    assert denied(call('Write', file_path=str(tmp_path / 'package.json'), content='{"scripts": {"x": "%s"}}' % cmd)), cmd

@pytest.mark.parametrize('cmd', ['uv run pytest', 'npx vitest', 'poetry run pytest -q', 'pdm run lint', 'npm test', 'pnpm build'])
def test_a_runner_s_ordinary_program_passes(cmd, tmp_path):
    for t in SHELLS: assert call(t, command=cmd) == {}, (t, cmd)
    assert call('Write', file_path=str(tmp_path / 'x.sh'), content=f'#!/bin/sh\n{cmd}\n') == {}, cmd

@pytest.mark.parametrize('name,content', [
    ('x.sh', "#!/bin/sh\npwsh -c 'rd Env:*'\n"), ('x.py', "import subprocess\nsubprocess.run(['pwsh','-c','rd Env:*'])\n"),
    ('x.cmd', 'powershell -c "dir Env:* | Remove-Item"\n'), ('x.sh', '#!/bin/sh\npwsh -NoProfile -Command "Remove-Item Env:$n"\n'),
    ('x.py', "import subprocess\nsubprocess.run([\n    'pwsh',\n    '-Command',\n    'rd Env:*',\n])\n"),
    ('x.sh', '#!/bin/sh\npwsh -EncodedCommand ZABpAHIA\n'), ('x.py', "subprocess.run(['powershell.exe', '-enc', 'ZABpAHIA'])\n"),
    ('x.js', "execSync('pwsh -e ZABpAHIA')\n")])
def test_powershell_inside_another_language_is_judged_as_powershell(name, content, tmp_path):
    assert denied(call('Write', file_path=str(tmp_path / name), content=content)), (name, content)

@pytest.mark.parametrize('cmd', ['pwsh -EncodedCommand ZABpAHIA', 'powershell -enc ZABpAHIA', 'pwsh -NoProfile -ec ZABpAHIA'])
def test_an_encoded_powershell_command_is_refused(cmd):
    for t in SHELLS: assert denied(call(t, command=cmd)), (t, cmd)

@pytest.mark.parametrize('name,content', [
    ('x.sh', "#!/bin/sh\npwsh -c 'Write-Output $env:PATH'\n"), ('x.sh', '#!/bin/sh\npwsh -NoProfile -File build.ps1 -Environment prod\n'),
    ('x.py', "subprocess.run(['pwsh', '-c', 'Get-Date'])\nconfig = {'env': 'prod'}\n")])
def test_ordinary_powershell_inside_another_language_is_written(name, content, tmp_path):
    assert call('Write', file_path=str(tmp_path / name), content=content) == {}, (name, content)
    for t in SHELLS: assert call(t, command='pwsh -NoProfile -File build.ps1 -Environment prod') == {}, t


# ── follow-up fix round 1 (R39): presence, not parsing - one more flag or quote must not walk past a runner or a shell ─
PRESENT = ['uv --directory . run taskuary --prompts', 'uv -q run taskuary --prompts', 'poetry -C . run taskuary --prompts',
           'npm --prefix . exec taskuary --prompts', 'pnpm --dir . dlx taskuary --prompts', 'hatch -e default run taskuary --prompts',
           'pdm -v run taskuary --prompts', 'uv run --no-extra dev taskuary --prompts', 'npx --registry https://r.example taskuary',
           'npm exec --loglevel silent taskuary', 'npx -c "taskuary --prompts"', 'yarn taskuary', 'bun x taskuary', 'uv run Taskuary.exe --link',
           'rye run taskuary', 'pixi run "taskuary" --prompts', 'nice uv run taskuary-desktop']

@pytest.mark.parametrize('cmd', PRESENT)
def test_a_runner_naming_taskuary_anywhere_is_refused(cmd, tmp_path):
    for t in SHELLS: assert denied(call(t, command=cmd)), (t, cmd)
    assert denied(call('Write', file_path=str(tmp_path / 'x.sh'), content=f'#!/bin/sh\n{cmd}\n')), cmd

INLINE = ["pwsh -c 'taskuary --prompts'", 'pwsh -c "taskuary --prompts"', "powershell 'rd Env:*'", 'powershell -NoProfile rd Env:*',
          "pwsh -wd /f -c 'rd Env:*'", "pwsh -Command - <<'X'\nrd Env:*\nX", 'bash -c "taskuary --prompts"', 'uv run sh -c "taskuary --prompts"',
          "sh -lc 'unset TASKUARY_TASK'", 'cmd /c "taskuary --prompts"', "zsh -c 'env -i make'", 'pwsh -NoLogo -NonInteractive -enc ZABpAHIA']

@pytest.mark.parametrize('cmd', INLINE)
def test_a_shell_launched_with_an_inline_command_is_judged_on_all_of_it(cmd, tmp_path):
    for t in SHELLS: assert denied(call(t, command=cmd)), (t, cmd)
    assert denied(call('Write', file_path=str(tmp_path / 'x.sh'), content=f'#!/bin/sh\n{cmd}\n')), cmd
    assert denied(call('Write', file_path=str(tmp_path / 'x.cmd'), content=f'{cmd}\n')), cmd

@pytest.mark.parametrize('cmd', ['pwsh -File build.ps1 -e prod', "pwsh -c 'npm test'", 'bash -c "npm test"', 'npm exec -c make', "pnpm exec -c 'make'"])
def test_an_ordinary_inline_shell_passes(cmd, tmp_path):
    for t in SHELLS: assert call(t, command=cmd) == {}, (t, cmd)
    assert call('Write', file_path=str(tmp_path / 'x.sh'), content=f'#!/bin/sh\n{cmd}\n') == {}, cmd

def test_prose_naming_a_powershell_option_is_written(tmp_path):
    assert call('Write', file_path=str(tmp_path / 'x.py'), content='# run it with PowerShell -Command if you must\nprint(1)\n') == {}

@pytest.mark.parametrize('name,content', [('x.py', "import subprocess\nsubprocess.run(['taskuary','--prompts'])\n"),
                                          ('x.py', "subprocess.run(['uv', 'run', 'taskuary', '--link'])\n"),
                                          ('x.js', "spawn('taskuary', ['--prompts'])\n"), ('x.ts', 'execFile("taskuary", ["--board"])\n'),
                                          ('x.py', "subprocess.run([\n    'taskuary',\n    '--demo',\n])\n")])
def test_an_argv_list_running_taskuary_is_refused(name, content, tmp_path):
    assert denied(call('Write', file_path=str(tmp_path / name), content=content)), content

@pytest.mark.parametrize('name,content', [('x.py', "subprocess.run(['taskuary', '--reply', 'done'])\n"),
                                          ('x.js', "spawn('taskuary', ['--note', 'tests pass'])\n"), ('x.py', "subprocess.run(['pytest', '-q'])\n")])
def test_an_argv_list_running_an_agent_command_is_written(name, content, tmp_path):
    assert call('Write', file_path=str(tmp_path / name), content=content) == {}, content

def test_exec_c_is_a_wipe_only_as_the_segment_s_program():
    for t in SHELLS: assert denied(call(t, command='exec -c make')), t


# ── follow-up fix round 2: an inline shell is judged once (no blow-up); an argv array is held to the whole command rule ─
@pytest.mark.parametrize('n', [16, 100])
def test_many_inline_shells_in_one_file_are_judged_fast(n, tmp_path):
    import time
    body = 'TASKS = {\n' + ''.join(f"    't{i}': ['bash', '-c', 'make t{i}'],\n" for i in range(n)) + '}\n'
    t = time.perf_counter(); r = call('Write', file_path=str(tmp_path / 'tasks.py'), content=body)
    assert r == {} and time.perf_counter() - t < 0.2, time.perf_counter() - t

def test_a_chain_of_inline_shells_is_judged_fast_and_still_refused():
    import time
    t = time.perf_counter(); r = call('Bash', command='echo ' + 'sh -c ' * 50 + '; taskuary --prompts')
    assert denied(r) and time.perf_counter() - t < 0.2, time.perf_counter() - t

@pytest.mark.parametrize('content', ["subprocess.run(['taskuary','--reply','hi','--prompts'])\n", "subprocess.run(['taskuary-desktop'])\n",
                                     "subprocess.run(['C:/tools/taskuary.exe', '--link'])\n", "subprocess.run(['taskuary'])\n",
                                     "os.system('taskuary --prompts')\n", "subprocess.run('taskuary --prompts', shell=True)\n",
                                     "os.popen('taskuary --board')\n", "subprocess.run(\n    ['taskuary', '--note', 'x',\n     '--demo'])\n"])
def test_code_that_runs_taskuary_outside_the_agent_commands_is_refused(content, tmp_path):
    assert denied(call('Write', file_path=str(tmp_path / 'x.py'), content=content)), content

@pytest.mark.parametrize('name,content', [('x.js', "execSync('taskuary --prompts')\n"), ('x.ts', 'exec("taskuary --link")\n'),
                                          ('x.js', "spawn('taskuary', ['--reply', 'x', '--board'])\n")])
def test_js_that_runs_taskuary_outside_the_agent_commands_is_refused(name, content, tmp_path):
    assert denied(call('Write', file_path=str(tmp_path / name), content=content)), content

@pytest.mark.parametrize('content', ["log = logging.getLogger('taskuary')\n", "setup(packages=['taskuary'])\n",
                                     "subprocess.run(['taskuary', '--reply', 'hi', '--attach', 'out.pdf'])\n",
                                     "os.system('taskuary --done \"fixed\"')\n", "find_packages(include=['taskuary', 'taskuary.*'])\n"])
def test_code_that_names_taskuary_otherwise_is_written(content, tmp_path):
    assert call('Write', file_path=str(tmp_path / 'x.py'), content=content) == {}, content


# ── follow-up fix round 3: no length past which the floor stops looking; one-argument spawns; a search may name a marker ─
@pytest.mark.parametrize('content', ["subprocess.run(['bash','-c', '" + ' ' * 4100 + "taskuary --prompts'])\n",
                                     "subprocess.run(['taskuary','--reply','" + 'x' * 4100 + "','--prompts'])\n",
                                     "subprocess.run(['bash','-c', '" + ' ' * 50000 + "taskuary --prompts'])\n"], ids=['shell', 'argv', 'shell-50k'])
def test_padding_does_not_hide_what_code_runs(content, tmp_path):
    assert denied(call('Write', file_path=str(tmp_path / 'x.py'), content=content))

def test_a_thousand_inline_shells_stay_fast(tmp_path):
    import time
    body = 'TASKS = {\n' + ''.join(f"    't{i}': ['bash', '-c', 'make t{i}'],\n" for i in range(1000)) + '}\n'
    call('Write', file_path=str(tmp_path / 'warm.py'), content="['bash', '-c', 'make']\n")     # first-call setup is not the floor's work
    t = time.perf_counter(); r = call('Write', file_path=str(tmp_path / 'tasks.py'), content=body)
    assert r == {} and time.perf_counter() - t < 0.2, time.perf_counter() - t

@pytest.mark.parametrize('content', ["spawnSync('taskuary-desktop')\n", "spawn('taskuary')\n", "execa('taskuary-desktop')\n",
                                     "execFile('taskuary.exe')\n", "spawn(\"taskuary\", ['--link'])\n"])
def test_a_one_argument_spawn_of_taskuary_is_refused(content, tmp_path):
    assert denied(call('Write', file_path=str(tmp_path / 'x.js'), content=content)), content

def test_a_one_argument_spawn_of_an_agent_command_is_written(tmp_path):
    assert call('Write', file_path=str(tmp_path / 'x.js'), content="spawn('taskuary', ['--reply', 'done'])\nspawn('make')\n") == {}

@pytest.mark.parametrize('cmd', ['grep -rn taskuary_ docs/', 'rg "TASKUARY_HOME" taskuary/', 'git grep -n taskuary_home', 'git log -S TASKUARY_X',
                                 'Select-String -Pattern TASKUARY_DEMO -Path *.py', 'findstr /s taskuary_ *.md', 'cat taskuary_notes.txt'])
def test_a_search_that_names_a_marker_passes(cmd):
    for t in SHELLS: assert call(t, command=cmd) == {}, (t, cmd)

@pytest.mark.parametrize('cmd', ['grep x $TASKUARY_HOME/config.toml', 'cat ${TASKUARY_HOME}/x', 'ls Env:', 'cat Env:TASKUARY_SID',
                                 'grep x . > taskuary_out; unset TASKUARY_SID', 'grep taskuary_ x; export TASKUARY_TASK=', 'echo TASKUARY_X',
                                 'grep -rn TASKUARY_TOKEN .'])
def test_a_search_does_not_launder_an_expansion_or_a_wipe(cmd):
    for t in SHELLS: assert denied(call(t, command=cmd)), (t, cmd)


# ── follow-up fix round 4: past the work budget an edit is judged on what it adds; module-qualified spawns ───────────
_BIG = 'x = (\n' + ("    'bash -c " + 'a' * 70000 + "',\n") * 35 + ')\n'       # 2.45M characters of inline shells: past the budget
_BUNDLES = sorted((__import__('pathlib').Path(floor.__file__).parent / 'web' / 'assets').glob('index-*.js'))

def _edit(f, old, add):
    f.write_text(old, encoding='utf-8', newline='')
    return call('Edit', file_path=str(f), old_string=old[-20:], new_string=old[-20:] + add)

@pytest.mark.parametrize('add', ["\nsubprocess.run(['bash','-c','taskuary --prompts'])\n", "\nsubprocess.run(['pwsh','-c','rd Env:*'])\n"])
def test_an_edit_to_a_file_past_the_budget_is_judged_on_what_it_adds(add, tmp_path):
    assert denied(_edit(tmp_path / 'x.py', _BIG, add)), add
    assert denied(call('Write', file_path=str(tmp_path / 'x.py'), content=_BIG + add)), add

def test_an_ordinary_edit_to_a_file_past_the_budget_is_written(tmp_path):
    assert _edit(tmp_path / 'x.py', _BIG, '\ny = 1\n') == {}
    assert call('Write', file_path=str(tmp_path / 'x.py'), content=_BIG + '\ny = 1\n') == {}

# a bundle past the budget only: code splitting took the entry to 1.8M (0.3.9.10), and under the budget the whole file is read - a
# minified line such as `sh(c,h,w,...)` is taken for a shell, so an edit to that line is refused, which over-refuses (the safe side)
@pytest.mark.skipif(not _BUNDLES or len(_BUNDLES[-1].read_text(encoding='utf-8')) <= floor._BUDGET, reason='no built bundle past the budget')
def test_an_edit_to_the_built_bundle_is_judged_on_what_it_adds(tmp_path):
    old = _BUNDLES[-1].read_text(encoding='utf-8')
    assert denied(_edit(tmp_path / 'index.js', old, "\nspawnSync('bash',['-c','taskuary --prompts'])\n"))
    assert _edit(tmp_path / 'index.js', old, '\nconst y = 1;\n') == {}

@pytest.mark.parametrize('content', ["child_process.spawn('taskuary')\n", "cp.spawnSync('taskuary-desktop')\n", "require('child_process').spawn('taskuary')\n",
                                     "childProcess.execFileSync('taskuary-desktop')\n", "cp.execFile('taskuary')\n", "cp.spawn('taskuary', [])\n"])
def test_a_module_qualified_spawn_of_taskuary_is_refused(content, tmp_path):
    assert denied(call('Write', file_path=str(tmp_path / 'x.js'), content=content)), content

def test_a_cli_command_named_taskuary_is_written(tmp_path):
    assert call('Write', file_path=str(tmp_path / 'x.js'), content="program.command('taskuary')\n") == {}

def test_the_edit_that_crosses_the_budget_is_refused(tmp_path):
    "Under the budget before, past it after: the floor stopped reading what this edit made, so it is refused."
    under = ''.join(f"X{i} = \"bash -c {'y' * 70000}\"\n" for i in range(28))
    assert denied(_edit(tmp_path / 'm.py', under, ''.join(f"X{i} = \"bash -c {'y' * 70000}\"\n" for i in (28, 29))))

@pytest.mark.parametrize('content', ["re.exec('taskuary')\n", "app.run('taskuary')\n", "rpc.call('taskuary')\n", "cur.execute('taskuary')\n",
                                     "reports.executor_for('taskuary')\n", "program.command('taskuary')\n"])
def test_a_method_named_like_a_spawn_is_written(content, tmp_path):
    assert call('Write', file_path=str(tmp_path / 'x.js'), content=content) == {}, content

@pytest.mark.parametrize('content', ["child_process.fork('taskuary')\n", "cp.execSync('taskuary')\n", "execa.execaSync('taskuary-desktop')\n",
                                     "subprocess.Popen('taskuary')\n", "Bun.spawn('taskuary')\n", "cp.exec('taskuary')\n"])
def test_a_module_qualified_spawn_name_is_refused(content, tmp_path):
    assert denied(call('Write', file_path=str(tmp_path / 'x.js'), content=content)), content

def test_a_later_launch_with_its_own_heredoc_is_judged(tmp_path):
    "Two launches in one statement end their regions at one place, but each reads on to its own heredoc's end."
    body = "pwsh -c 'echo' <<A && pwsh -c \"$(cat)\" <<B\nok\nA\nrd Env:*\nB\n"
    assert denied(call('Write', file_path=str(tmp_path / 'x.sh'), content=body))
