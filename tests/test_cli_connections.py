import copy
import json
from unittest import mock

from taskuary import agents, cli_connections, aidefaults
from taskuary.store import MemoryStore


def legacy():
    return {'agents': {
        'coder': {'cmd': 'claude', 'args': ['-p', '--verbose'], 'kind': 'coding', 'rules_doc': 'coder'},
        'codex': {'cmd': 'codex', 'args': ['exec'], 'kind': 'coding', 'rules_doc': 'coder'},
        'researcher': {'cmd': 'claude', 'args': ['-p'], 'kind': 'research', 'purpose': 'Research public sources', 'model': 'sonnet', 'light_model': 'haiku'},
        'analyst': {'cmd': 'claude', 'args': ['-p'], 'kind': 'analysis', 'purpose': 'Analyse our numbers', 'model': 'opus'},
    }}


def test_migration_shares_commands_preserves_roles_and_models_and_is_idempotent():
    cfg = legacy()
    assert cli_connections.migrate(cfg)
    assert set(cfg['cli_connections']) == {'claude', 'codex'}
    assert cfg['cli_connections']['claude']['args'] == ['-p', '--verbose']
    assert cfg['agents']['researcher']['provider'] == 'cli:claude'
    assert cfg['agents']['researcher']['model'] == 'sonnet'
    assert cfg['agents']['researcher']['light_model'] == 'haiku'
    assert all(not set(p).intersection(cli_connections.COMMAND_FIELDS) for p in cfg['agents'].values())
    assert not cli_connections.migrate(cfg)
    assert cfg['agents']['codex']['rules_doc'] == 'coder'
    assert cli_connections.cli_key(r'C:\tools\cursor-agent.cmd') == 'cursor'


def test_command_only_claude_gets_headless_defaults_on_migration_and_legacy_creation():
    cfg = {'agents': {'coder': {'cmd': 'claude'}}}
    cli_connections.migrate(cfg)
    connection = cfg['cli_connections']['claude']
    assert connection['args'] == ['-p', '--dangerously-skip-permissions', '--output-format', 'stream-json', '--verbose']
    assert connection['resume_args'] == ['--resume']
    assert connection['timeout'] == 1500
    assert not cli_connections.migrate(cfg)
    cfg['cli_connections']['claude'] = {'cmd': 'claude'}
    assert cli_connections.migrate(cfg)  # repair configs already split by the earlier migration
    assert '--dangerously-skip-permissions' in cli_connections.resolve(cfg, cfg['agents']['coder'])['args']
    fresh = {}
    cli_connections.set_profile(fresh, MemoryStore(), 'coder', {'cmd': 'claude'})
    assert '--dangerously-skip-permissions' in fresh['cli_connections']['claude']['args']


def test_saved_custom_or_explicitly_empty_arguments_are_preserved():
    for args in ([], ['-p', '--custom']):
        cfg = {'agents': {'coder': {'provider': 'cli:claude'}}, 'cli_connections': {'claude': {'cmd': 'claude', 'args': args}}}
        cli_connections.migrate(cfg)
        assert cfg['cli_connections']['claude']['args'] == args
        assert cli_connections.resolve(cfg, cfg['agents']['coder'])['args'] == args


def test_connection_edits_reach_all_profiles_and_provider_switch_is_independent():
    cfg, store = legacy(), MemoryStore()
    cli_connections.migrate(cfg)
    cli_connections.sync(cfg, store)
    cfg['cli_connections']['claude']['args'] = ['-p', '--new-shared-flag']
    cli_connections.sync(cfg, store)
    for name in ('coder', 'researcher', 'analyst'):
        assert json.loads(store.get_agent(name)['Config'])['args'] == ['-p', '--new-shared-flag']
    cli_connections.set_profile(cfg, store, 'researcher', {'provider': 'cli:codex', 'model': 'test-model'})
    cli_connections.sync(cfg, store, 'researcher')
    research = json.loads(store.get_agent('researcher')['Config'])
    assert research['cmd'] == 'codex' and research['args'] == ['exec'] and research['model'] == 'test-model'
    assert research['purpose'] == 'Research public sources'
    assert 'light_model' not in research
    assert json.loads(store.get_agent('analyst')['Config'])['model'] == 'opus'
    assert json.loads(store.get_agent('coder')['Config'])['cmd'] == 'claude'
    assert '- researcher:' in agents.roster(store)


def test_settings_model_edit_keeps_shared_command_reference():
    cfg, store = legacy(), MemoryStore()
    cli_connections.migrate(cfg)
    cli_connections.sync(cfg, store)
    with mock.patch('taskuary.config.save'):
        result = aidefaults.apply(store, cfg, 'default_agent', value='researcher', model='opus')
    assert result['cli'] == 'claude'
    assert cfg['agents']['researcher']['model'] == 'opus'
    assert 'cmd' not in cfg['agents']['researcher']
    assert json.loads(store.get_agent('researcher')['Config'])['cmd'] == 'claude'


def test_connection_api_has_one_row_per_cli_and_validates_references():
    from fastapi.testclient import TestClient
    from taskuary import server
    cfg, store = legacy(), MemoryStore()
    cli_connections.migrate(cfg)
    cli_connections.sync(cfg, store)
    cfg['server'] = copy.deepcopy(server.cfg['server'])
    with mock.patch.object(server, 'cfg', cfg), mock.patch.object(server, 'store', store), mock.patch('taskuary.config.save'):
        c = TestClient(server.app)
        rows = c.get('/api/cli/connections').json()['data']
        assert sum(r['name'] == 'claude' for r in rows) == 1
        assert not {'coder', 'researcher', 'analyst'}.intersection(r['name'] for r in rows)
        assert c.put('/api/cli/connections/claude-copy', json={'cmd': 'claude'}).status_code == 409
        assert c.put('/api/cli/connections/claude', json={'cmd': 'claude', 'args': ['-p', '--shared']}).status_code == 200
        assert json.loads(store.get_agent('analyst')['Config'])['args'] == ['-p', '--shared']
        before = copy.deepcopy(cfg)
        assert c.put('/api/agents/researcher', json={'provider': 'cli:missing'}).status_code == 422
        assert cfg == before
        assert c.delete('/api/cli/connections/claude').status_code == 409
        assert c.put('/api/cli/connections/custom', json={'cmd': 'custom', 'args': []}).status_code == 200
        assert store.get_agent('custom') is None
        assert c.delete('/api/cli/connections/custom').status_code == 200
        assert c.put('/api/cli/connections/claude', json={'cmd': 'claude', 'timeout': -1}).status_code == 422
