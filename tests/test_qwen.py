"""Qwen must be runnable from Connections, resumable, and restricted when reading mail."""
import json
from unittest import mock

import pytest

from taskuary import agents, cli_connections, cliinstall, clis, clisetup, llm, terminal
from taskuary.store import MemoryStore


def test_installed_qwen_becomes_a_brain_with_resumable_native_acp_connection():
    """A CLI is a brain, not a worker named after one (the 2026-09-16 spec) - so what adopting
    leaves behind is a CONNECTION carrying everything needed to run it."""
    cfg, store = {'agents': {}, 'cli_connections': {}}, MemoryStore()
    with mock.patch.object(cliinstall, 'find', side_effect=lambda n: '/bin/qwen' if n == 'qwen' else ''):
        assert cli_connections.adopt_installed(cfg, store) == []
    assert store.get_agent('qwen') is None
    resolved = cli_connections.with_defaults(cfg['cli_connections']['qwen'])
    assert resolved['acp'] == ['--acp']
    assert agents.resume_argv(resolved, 'session-123') == ['--resume', 'session-123']
    assert terminal.seed_argv(resolved, 'Fix the test') == ['-i', 'Fix the test']
    # Headless output flags must not turn the interactive coding pane into a pipe.
    assert terminal.interactive_args(resolved['args']) == ['--yolo']


def test_qwen_connection_defaults_preserve_an_owners_explicit_acp_choice():
    assert cli_connections.with_defaults({'cmd': 'qwen'})['acp'] == ['--acp']
    assert cli_connections.with_defaults({'cmd': 'qwen', 'acp': []})['acp'] == []


@pytest.mark.parametrize('system', ['Windows', 'Darwin', 'Linux'])
def test_qwen_has_a_standalone_installer_without_node(system):
    roads = cliinstall.plan('qwen', has_npm=False, system=system)
    assert len(roads) == 1 and roads[0]['how'] == 'script'
    assert 'qwen-code-assets.oss-cn-hangzhou.aliyuncs.com' in roads[0]['cmd'][-1]


def test_qwen_setup_finds_the_windows_standalone_install_after_path_changes(tmp_path):
    binary = tmp_path / 'qwen-code' / 'bin' / 'qwen.cmd'
    binary.parent.mkdir(parents=True)
    binary.write_text('@echo off\n', encoding='utf-8')
    with mock.patch.object(cliinstall, 'WINDOWS', True), mock.patch.object(clis, 'which', return_value=''), \
         mock.patch.dict('os.environ', {'LOCALAPPDATA': str(tmp_path)}):
        assert cliinstall.find('qwen') == str(binary)
        assert clisetup.argv('qwen') == [str(binary)]


def test_qwen_triage_does_not_inherit_coding_permissions_or_acp(tmp_path):
    store = MemoryStore()
    store.upsert_agent('qwen', 'coding', 'cli', json.dumps(cli_connections.with_defaults({'cmd': 'qwen'})))
    seen = {}
    with mock.patch.object(agents, 'run_cli', side_effect=lambda profile, *a, **kw: (seen.update(profile), ('ok', None, None))[1]):
        llm.make_cli_llm(store, 'qwen')('Classify this message.', 'Please run a command.')
    assert not seen.get('acp_ok')
    assert '--yolo' not in seen['args']
    assert '--safe-mode' in seen['args']
    assert '--max-tool-calls=0' in seen['args']
    assert '--approval-mode=plan' in seen['args']


def test_qwen_tool_using_general_agent_keeps_acp_after_connection_resolution(tmp_path):
    store = MemoryStore()
    store.upsert_agent('qwen', 'coding', 'cli', json.dumps(cli_connections.with_defaults({'cmd': 'qwen'})))
    seen = {}
    with mock.patch.object(agents, 'run_cli', side_effect=lambda profile, *a, **kw: (seen.update(profile), ('ok', None, None))[1]):
        llm.make_cli_llm(store, 'qwen', cwd=str(tmp_path))('Work on this task.', 'Read the project.')
    assert seen['acp'] == ['--acp'] and seen['acp_ok']


def test_qwen_acp_receives_the_workers_model_override(tmp_path):
    profile = {**cli_connections.with_defaults({'cmd': 'qwen'}), 'acp_ok': True,
               'cwd': str(tmp_path), 'model': 'my-configured-model'}
    with mock.patch.object(agents, '_resolve_cmd', return_value=['qwen']), \
         mock.patch.object(agents.acp_mod, 'ACPClient') as Client:
        Client.return_value.connect.return_value = {}
        Client.return_value.prompt.return_value = ('end_turn', 'ok')
        agents.run_cli(profile, 'Work on the task.', lambda *a: None)
    assert Client.call_args.args == ('qwen', ['--acp', '--model', 'my-configured-model'])
