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
    assert KEY not in json.dumps(f) and f['provider']['card']['options']['apiKey'] == '{env:TASKUARY_CARD_KEY}'
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


def test_every_switch_the_gateway_proof_needed_is_pinned():
    "Without these Codex reached OpenAI's telemetry host and GitHub; with them the gateway was the only host in 32 runs (2026-11-20)."
    c = tomllib.loads(harness.codex_config(1, 'AI', 'https://gateway.example/v1', '', {}, 'hydrogen'))
    p = c['model_providers'][c['model_provider']]
    assert (p['env_key'], p['wire_api'], harness.KEY_ENV) == ('TASKUARY_CARD_KEY', 'responses', 'TASKUARY_CARD_KEY')
    assert c['model_context_window'] == 1_000_000 and c['check_for_update_on_startup'] is False and c['web_search'] == 'disabled'
    assert c['analytics'] == {'enabled': False} and c['feedback'] == {'enabled': False}
    assert all(c['otel'][k] == 'none' for k in ('exporter', 'trace_exporter', 'metrics_exporter'))
    assert all(c['features'][k] is False for k in ('apps', 'plugins', 'remote_plugin'))


def test_a_chat_completions_only_card_defaults_to_opencode_and_its_websearch_is_off(here):
    assert harness.harness_of({}, 'hipaa_ai') == 'codex' and harness.harness_of({}, 'vertex_ai') == 'opencode'
    assert harness.harness_of({'harness': 'codex'}, 'groq') == 'codex'                       # ...his pick stands
    f = harness.opencode_config('AI', 'https://x.example/v1', '', {}, 'm', '')
    assert f['tools']['websearch'] is False and f['provider']['card']['models']['m']['tool_call'] is True


def test_the_card_agents_web_search_is_its_models_own_through_the_tool_server(here):
    from taskuary import agenttools
    s = MemoryStore(); cid = _card(s)
    tid = s.create_task({'Title': 'look something up'}, 't')
    s.save_session(tid, f'connector:{cid}', 'hydrogen', '', 'k')
    asked = []
    brain = type('B', (), {'search': lambda self, q: asked.append(q) or 'Answer, with sources.'})()
    with mock.patch.object(harness, 'searcher', return_value=brain):
        out = agenttools.call(s, tid, 'web_search', {'query': 'capital of Peru'}, {})
    assert 'Answer, with sources.' in out and asked == ['capital of Peru']
    assert harness.on_card(s, tid) and not harness.on_card(s, tid + 999)


def test_a_card_session_is_served_tool_schemas_its_model_takes():
    "Gemini behind the gateway refused the whole turn: propose's parameters were a top-level anyOf, not an OBJECT (the gateway walk, 2026-11-20)."
    from taskuary import agenttools
    raw = {t['name']: t['inputSchema'] for t in agenttools.listing()}
    fit = {t['name']: t['inputSchema'] for t in agenttools.listing(portable=True)}
    assert 'anyOf' in raw['propose'] and fit['propose']['type'] == 'object' and 'anyOf' not in fit['propose']


def test_the_cards_models_are_in_codexs_own_catalogue_so_no_metadata_warning_fires(here, monkeypatch):
    "Codex runs a model it has no catalogue entry for on fallback metadata, and says so above every answer (the gateway walk, 2026-11-20)."
    tpl = {'slug': 'gpt-x', 'base_instructions': 'You are Codex, an agent based on GPT-6. Use apply_patch.', 'tool_mode': 'code_mode_only',
           'supports_search_tool': True, 'multi_agent_version': 'v2',
           'model_messages': {'instructions_template': 'You are Codex, an agent based on GPT-6. Hi.'},
           'service_tiers': [{'id': 'priority'}], 'available_access_programs': {'cyber': ['standard']}, 'context_window': 1}
    monkeypatch.setattr(harness, 'bundled', lambda cmd: tpl)
    s = MemoryStore(); cid = _card(s)
    prof = json.loads(agents.agent_row(s, f'card-{cid}')['Config'])
    home = harness.folder(cid) / 'codex'
    c = tomllib.loads((home / 'config.toml').read_text(encoding='utf-8'))
    assert c['model_catalog_json'] == str(home / 'models.json').replace(chr(92), '/')
    ms = json.loads((home / 'models.json').read_text(encoding='utf-8'))['models']
    assert [m['slug'] for m in ms] == ['hydrogen', 'neon']
    # ...each told the model it is, Codex's how-to kept, and no sub-agents of its own (the HIPAA walk, 2026-11-23)
    assert [m['base_instructions'] for m in ms] == ['You are hydrogen, an agent running in Codex. Use apply_patch.',
                                                    'You are neon, an agent running in Codex. Use apply_patch.']
    assert ms[0]['model_messages']['instructions_template'] == 'You are hydrogen, an agent running in Codex. Hi.'
    assert all(m['multi_agent_version'] is None for m in ms) and c['features']['multi_agent'] is False
    assert all(m['tool_mode'] is None and m['supports_search_tool'] is False and m['service_tiers'] == [] and m['context_window'] == 1_000_000 for m in ms)
    assert prof['env']['CODEX_HOME'] == str(home)


def test_the_chip_names_the_harness_that_runs_the_cards_agent(here):
    from taskuary import general
    s = MemoryStore(); cid = _card(s)
    row = next(o for o in general.provider_options(s) if o['pick'] == f'connector:{cid}')
    assert (row['label'], row['model']) == ('HIPAA AI · Codex', 'hydrogen')


def test_the_card_names_its_harness_once(monkeypatch):
    "The design walk, 2026-11-20: 'Its agent runs on' was the picker's label, the box named the harness, and the line under it said both again."
    harness._TRIED.clear(); monkeypatch.setattr(harness, 'ON', True)
    monkeypatch.setattr(cliinstall, 'find', lambda n: '')
    monkeypatch.setattr(cliinstall, 'plan', lambda n, **k: [])
    s = MemoryStore(); cid = _card(s)
    for active in (1, 0):
        s.save_connector({'ConnectorId': cid, 'Active': active}, 't')
        said = harness.line(s, _row(s, cid))['line']
        assert 'runs on' not in said and not any(v in said for v in harness.LABEL.values()), said
