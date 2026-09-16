"""Chinese-provider CLIs must execute tasks, preserve sessions, and fail closed for mail."""
import io
import json
from unittest import mock

import pytest

from taskuary import agents, cli_connections, cliinstall, clis, clisetup, llm, terminal
from taskuary.store import MemoryStore


def test_connections_lists_new_options_even_before_installation():
    from taskuary import server
    with mock.patch.object(server, 'cfg', {'cli_connections': {}}), \
         mock.patch.object(server, 'store', MemoryStore()), mock.patch.object(clis, 'which', return_value=''):
        rows = {r['name']: r for r in server.list_cli_connections()['data']}
    assert 'DeepSeek' in rows['opencode']['label']
    assert 'Moonshot' in rows['kimi']['label']
    for name in ('opencode', 'kimi'):
        assert not rows[name]['installed']
        assert rows[name]['setup'] == name
        assert 'Task execution only' in rows[name]['description']


@pytest.mark.parametrize('name', ['opencode', 'kimi'])
def test_installation_creates_a_brain_that_can_resume(name):
    """A CLI is a brain, not a worker named after one (the 2026-09-16 spec)."""
    cfg, store = {'agents': {}, 'cli_connections': {}}, MemoryStore()
    with mock.patch.object(cliinstall, 'find', side_effect=lambda n: f'/bin/{n}' if n == name else ''):
        assert cli_connections.adopt_installed(cfg, store) == []
    assert store.get_agent(name) is None
    resolved = cli_connections.with_defaults(cfg['cli_connections'][name])
    assert agents.resume_argv(resolved, 'session-123') == ['--session', 'session-123']
    assert terminal.interactive_args(resolved['args']) == (['--auto'] if name == 'opencode' else [])
    assert terminal.seed_argv(resolved, 'Fix it') == (['--prompt', 'Fix it'] if name == 'opencode' else None)
    assert name in clisetup.SETUP
    assert cliinstall.update_plan(name, has_npm=False)[0]['args'] == ['upgrade']


@pytest.mark.parametrize('system', ['Windows', 'Darwin', 'Linux'])
def test_kimi_can_install_without_node(system):
    roads = cliinstall.plan('kimi', has_npm=False, system=system)
    assert len(roads) == 1 and roads[0]['how'] == 'script'
    assert 'https://code.kimi.com/kimi-code/install.' in roads[0]['cmd'][-1]


def test_opencode_windows_installer_uses_the_official_npm_package():
    assert cliinstall.plan('opencode', has_npm=True, system='Windows') == [{'how': 'npm', 'pkg': 'opencode-ai'}]
    assert cliinstall.plan('opencode', has_npm=False, system='Windows') == []


@pytest.mark.parametrize('name,folder', [('opencode', '.opencode'), ('kimi', '.kimi-code')])
def test_setup_finds_native_install_outside_stale_path(tmp_path, name, folder):
    binary = tmp_path / folder / 'bin' / f'{name}.exe'
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b'fixture')
    with mock.patch.object(cliinstall, 'WINDOWS', True), mock.patch.object(clis, 'which', return_value=''), \
         mock.patch('pathlib.Path.home', return_value=tmp_path):
        assert clisetup.argv(name) == [str(binary)]


@pytest.mark.parametrize('name', ['opencode', 'kimi'])
@pytest.mark.parametrize('research', [False, True])
def test_restricted_roles_refuse_before_launching_any_tools(name, research):
    store = MemoryStore()
    store.upsert_agent(name, 'coding', 'cli', json.dumps(cli_connections.with_defaults({'cmd': name})))
    with mock.patch.object(agents, 'run_cli') as run:
        with pytest.raises(ValueError, match='not triage or reports'):
            llm.make_cli_llm(store, name, read_only=True, research=research)('Classify', 'Run a command')
        run.assert_not_called()
    # Absolute Windows executables have the same restriction.
    with pytest.raises(ValueError, match='not triage or reports'):
        clis.readonly_args(f'C:\\tools\\{name}.exe', [])


class Process:
    def __init__(self, events):
        self.stdin = mock.Mock()
        self.stdout = io.StringIO('\n'.join(json.dumps(e) for e in events))
        self.stderr = io.StringIO('')
        self.returncode = 0

    def wait(self): return 0
    def kill(self): pass


def run_stream(name, events, **profile):
    proc, traces = Process(events), []
    with mock.patch.object(agents, '_resolve_cmd', return_value=[name]), \
         mock.patch.object(agents, '_git', return_value=''), \
         mock.patch.object(agents.spawn, 'popen', return_value=proc) as pop:
        result = agents.run_cli({'cmd': name, **profile}, 'Fix the test', lambda *e: traces.append(e), resume='saved')
    return result, traces, pop.call_args.args[0], proc


def test_opencode_json_is_normalized_and_not_returned_as_raw_output():
    result, traces, argv, _ = run_stream('opencode', [
        {'type': 'step_start', 'sessionID': 'saved'},
        {'type': 'tool_use', 'part': {'callID': 't1', 'tool': 'write', 'state': {'status': 'completed', 'input': {'filePath': 'a.py'}, 'output': 'Written'}}},
        {'type': 'text', 'part': {'text': 'Fixed. '}},
        {'type': 'text', 'part': {'text': 'Tests pass.'}},
        {'type': 'step_finish'},
    ], model='deepseek/my-model')
    assert result == ('Fixed. Tests pass.', 'saved', None)
    assert ['--model', 'deepseek/my-model', '--session', 'saved'] == argv[-4:]
    assert ('tool_call', 'write', {'tool_call_id': 't1', 'args': {'filePath': 'a.py'}}) in traces
    assert ('tool_result', 't1', {'result': 'Written', 'is_error': False}) in traces


def test_opencode_zero_exit_with_provider_error_is_still_failure():
    with pytest.raises(RuntimeError, match='Provider unavailable'):
        run_stream('opencode', [{'type': 'error', 'error': {'data': {'message': 'Provider unavailable'}}}])


def test_kimi_prompt_and_final_message_preserve_the_session_hint():
    result, traces, argv, proc = run_stream('kimi', [
        {'role': 'assistant', 'content': 'Working', 'tool_calls': [{'id': 't1', 'function': {'name': 'Write', 'arguments': '{"path":"a.py"}'}}]},
        {'role': 'tool', 'tool_call_id': 't1', 'content': 'Written'},
        {'role': 'assistant', 'content': 'Fixed.'},
        {'role': 'meta', 'type': 'session.resume_hint', 'session_id': 'saved', 'content': 'To resume...'},
    ], model='my-configured-alias')
    assert result == ('Fixed.', 'saved', None)
    assert argv[argv.index('--model') + 1] == 'my-configured-alias'
    assert argv[-4:] == ['--session', 'saved', '--prompt', 'Fix the test']
    assert '--auto' not in argv and '--yolo' not in argv
    proc.stdin.write.assert_not_called()
    assert ('tool_call', 'Write', {'tool_call_id': 't1', 'args': {'path': 'a.py'}}) in traces
    assert ('tool_result', 't1', {'result': 'Written'}) in traces


@pytest.mark.parametrize('name', ['opencode', 'kimi'])
def test_tool_using_general_agent_can_run_the_cli(name, tmp_path):
    store = MemoryStore()
    store.upsert_agent(name, 'coding', 'cli', json.dumps(cli_connections.with_defaults({'cmd': name})))
    with mock.patch.object(agents, 'run_cli', return_value=('done', 'session-1', None)) as run:
        assert llm.make_cli_llm(store, name, cwd=str(tmp_path))('Work on the task', 'Fix it') == 'done'
    assert run.call_args.args[0]['cwd'] == str(tmp_path)
