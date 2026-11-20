"""An API card's agent runs on the Codex CLI road, pointed at the card (harness.py): its own CODEX_HOME, the card as Codex's model
provider, the key in the environment and never on disk, and every road to OpenAI closed. The gears are the card's own models."""
import json
try: import tomllib
except ImportError: import tomli as tomllib
from unittest import mock

import pytest

from taskuary import agents, cliinstall, harness, llm
from taskuary.store import MemoryStore

KEY = 'sk-card-secret-0001'


def _card(s, **cfg):
    cfg = {'base_url': 'https://gateway.example/v1', 'model': 'hydrogen', 'light_model': 'flash', 'strong_model': 'neon', **cfg}
    return s.save_connector({'Type': 'hipaa_ai', 'Name': 'HIPAA AI', 'ConfigJson': json.dumps(cfg), 'Secret': KEY, 'Active': 1}, 't')


def _row(s, cid): return next(c for c in s.list_connectors() if c['ConnectorId'] == cid)


@pytest.fixture
def here(monkeypatch):
    "Codex and OpenCode both on this machine; no install is started."
    harness._TRIED.clear(); monkeypatch.setattr(harness, 'ON', True)
    monkeypatch.setattr(cliinstall, 'find', lambda n: {'codex': '/bin/codex', 'opencode': '/bin/opencode'}.get(n, ''))
    started = []
    monkeypatch.setattr(cliinstall, 'start', lambda n, **k: started.append(n))
    return started


def test_an_api_cards_agent_launches_codex_on_the_cards_provider_with_the_key_in_env_not_on_disk(here):
    s = MemoryStore(); cid = _card(s)
    assert harness.road(s, f'connector:{cid}') == f'cli:card-{cid}'
    prof = json.loads(agents.agent_row(s, f'card-{cid}')['Config'])
    assert agents.cli_of(prof) == 'codex' and prof['args'][0] == 'exec'
    home = prof['env']['CODEX_HOME']
    assert prof['env'][harness.KEY_ENV] == KEY and agents.spawn_env(prof)[harness.KEY_ENV] == KEY      # handed in at launch
    text = (harness.folder(cid) / 'codex' / 'config.toml').read_text(encoding='utf-8')
    assert home == str(harness.folder(cid) / 'codex') and KEY not in text                                 # ...and never written
    c = tomllib.loads(text)
    p = c['model_providers'][c['model_provider']]
    assert (p['base_url'], p['env_key'], p['wire_api'], c['model']) == ('https://gateway.example/v1', harness.KEY_ENV, 'responses', 'hydrogen')
    # HIPAA: nothing reaches OpenAI - telemetry, the update check, feedback, hosted search, a ChatGPT login and its apps all off
    assert c['analytics']['enabled'] is False and c['feedback']['enabled'] is False and c['otel']['exporter'] == 'none'
    assert c['check_for_update_on_startup'] is False and c['web_search'] == 'disabled' and c['forced_login_method'] == 'api'
    assert not any(c['features'][k] for k in ('apps', 'plugins', 'remote_plugin', 'image_generation', 'in_app_updates'))
    assert harness.KEY_ENV in c['shell_environment_policy']['exclude']


def test_the_agent_turn_builds_the_codex_brain_and_triage_keeps_the_card(here):
    s = MemoryStore(); cid = _card(s)
    with mock.patch.object(llm, 'make_cli_llm', return_value=lambda *a, **k: 'ok') as cli, mock.patch.object(llm, 'make_llm') as api:
        llm._build_llm(s, f'connector:{cid}', keep='general:7', task_id=7, gear='main', cli_tools=True)
        assert cli.call_args.args[1] == f'card-{cid}' and not api.called
        llm._build_llm(s, f'connector:{cid}', gear='light')                               # triage: the card's own one-shot call
        assert api.called and cli.call_count == 1


def test_a_header_keyed_card_reads_its_key_from_env_by_header():
    t = harness.codex_config(3, 'Azure', 'https://res.example/openai/v1', 'api-key', {}, 'dep')
    p = tomllib.loads(t)['model_providers']['card3']
    assert p['env_http_headers'] == {'api-key': harness.KEY_ENV} and 'env_key' not in p


def test_gears_quick_is_the_cards_model_thinking_less_hard_is_its_strong_model_never_flash(here):
    s = MemoryStore(); cid = _card(s)
    prof = json.loads(agents.agent_row(s, f'card-{cid}')['Config'])
    assert (prof['light_model'], prof['model'], prof['strong_model']) == ('hydrogen@low', 'hydrogen', 'neon')
    assert harness.spell(s, f'cli:card-{cid}', 'flash') == ''                   # the router's light model is not agent work's
    assert harness.spell(s, f'cli:card-{cid}', 'hydrogen@low') == 'hydrogen@low'
    # ...a card with no strong model works hard on its one model at high effort; Codex takes it as model_reasoning_effort
    assert harness.gears({}, 'hydrogen') == ('hydrogen@low', 'hydrogen', 'hydrogen@high')
    assert agents._model_args({'model': 'hydrogen@low'}, 'codex') == ['--model', 'hydrogen', '-c', 'model_reasoning_effort=low']


def test_opencode_is_the_second_launcher_on_the_same_road(here):
    s = MemoryStore(); cid = _card(s, harness='opencode')
    prof = json.loads(agents.agent_row(s, f'card-{cid}')['Config'])
    assert agents.cli_of(prof) == 'opencode' and prof['model'] == 'card/hydrogen' and prof['light_model'] == 'card/hydrogen-low'
    f = json.loads((harness.folder(cid) / 'opencode.json').read_text(encoding='utf-8'))
    assert KEY not in json.dumps(f) and f['provider']['card']['options']['apiKey'] == '{env:TASKUARY_AI_KEY}'
    assert f['share'] == 'disabled' and f['autoupdate'] is False and f['provider']['card']['models']['hydrogen-low']['id'] == 'hydrogen'
    assert prof['env']['OPENCODE_DISABLE_AUTOUPDATE'] == '1' and prof['env']['OPENCODE_CONFIG'].endswith('opencode.json')


def test_install_no_api_card_installs_nothing_and_an_opencode_card_installs_only_opencode(monkeypatch):
    harness._TRIED.clear(); monkeypatch.setattr(harness, 'ON', True)
    started = []
    monkeypatch.setattr(cliinstall, 'find', lambda n: '')
    monkeypatch.setattr(cliinstall, 'plan', lambda n, **k: [{'how': 'npm'}])
    monkeypatch.setattr(cliinstall, 'start', lambda n, **k: started.append(n))
    s = MemoryStore()
    assert harness.road(s, 'cli:claude') == 'cli:claude' and harness.road(s, '') == '' and started == []
    cid = _card(s, harness='opencode')
    for c in s.list_connectors(): harness.line(s, c)
    assert harness.road(s, f'connector:{cid}') == f'connector:{cid}'           # ...its own loop (apiagent) until it is in
    assert started == ['opencode']


def test_a_card_switched_off_starts_no_install(monkeypatch):
    harness._TRIED.clear(); monkeypatch.setattr(harness, 'ON', True)
    started = []
    monkeypatch.setattr(cliinstall, 'find', lambda n: '')
    monkeypatch.setattr(cliinstall, 'plan', lambda n, **k: [{'how': 'npm'}])
    monkeypatch.setattr(cliinstall, 'start', lambda n, **k: started.append(n))
    s = MemoryStore(); cid = _card(s); s.save_connector({'ConnectorId': cid, 'Active': 0}, 't')
    line = harness.line(s, _row(s, cid))
    assert started == [] and 'once this card is on' in line['line']


def test_no_harness_can_run_here_so_the_agent_keeps_its_own_loop_and_the_card_says_so(monkeypatch):
    harness._TRIED.clear(); monkeypatch.setattr(harness, 'ON', True)
    monkeypatch.setattr(cliinstall, 'find', lambda n: '')
    monkeypatch.setattr(cliinstall, 'plan', lambda n, **k: [])
    s = MemoryStore(); cid = _card(s)
    assert harness.road(s, f'connector:{cid}') == f'connector:{cid}'
    assert "can't run on this computer" in harness.line(s, _row(s, cid))['line']
