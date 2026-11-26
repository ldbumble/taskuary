"""An API card's agent runs on the Codex CLI road, pointed at the card (harness.py): its own CODEX_HOME, the card as Codex's model
provider, the key in the environment and never on disk, and every road to OpenAI closed. The gears are the card's own models."""
import json
try: import tomllib
except ImportError: import tomli as tomllib
from unittest import mock

import pytest

from taskuary import agents, cliinstall, config, harness, llm, relay
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
    # WHAT IT SENDS LEAVES THROUGH TASKUARY'S RELAY (relay.py, the owner 2026-11-26): the CLI is pointed at this computer and handed the
    # relay's token for its card - the card's own address and key are nowhere in its config or its environment
    srv = config.load()['server']
    tok = relay.token(srv, cid)
    assert prof['env'][harness.KEY_ENV] == tok and agents.spawn_env(prof)[harness.KEY_ENV] == tok      # handed in at launch
    text = (harness.folder(cid) / 'codex' / 'config.toml').read_text(encoding='utf-8')
    assert home == str(harness.folder(cid) / 'codex') and tok not in text                                 # ...and never written
    assert not any(KEY in str(v) for v in prof['env'].values()) and KEY not in text and 'gateway.example' not in text
    c = tomllib.loads(text)
    p = c['model_providers'][c['model_provider']]
    assert (p['base_url'], p['env_key'], p['wire_api'], c['model']) == (relay.base(srv, cid), harness.KEY_ENV, 'responses', 'hydrogen')
    assert p['base_url'].startswith('http://127.0.0.1:') and p['base_url'].endswith(f'/relay/card-{cid}')
    # HIPAA: nothing reaches OpenAI - telemetry, the update check, feedback, hosted search, a ChatGPT login and its apps all off
    assert c['analytics']['enabled'] is False and c['feedback']['enabled'] is False and c['otel']['exporter'] == 'none'
    assert c['check_for_update_on_startup'] is False and c['web_search'] == 'disabled' and c['forced_login_method'] == 'api'
    assert not any(c['features'][k] for k in ('apps', 'plugins', 'remote_plugin', 'image_generation', 'in_app_updates'))
    assert harness.KEY_ENV in c['shell_environment_policy']['exclude']


def test_the_relays_address_is_loopback_wherever_the_server_listens_there_else_its_one_address():
    at = lambda h: relay.base({'host': h, 'port': 7799}, 3)
    for h in ('0.0.0.0', '::', '', None, 'localhost'): assert at(h) == 'http://127.0.0.1:7799/relay/card-3', h
    assert at('127.0.0.1') == 'http://127.0.0.1:7799/relay/card-3' and at('::1') == 'http://[::1]:7799/relay/card-3'
    assert at('192.0.2.10') == 'http://192.0.2.10:7799/relay/card-3'            # bound to one address and no loopback: that one (relay.here)
    assert relay.here('127.0.0.1', '192.0.2.10') and relay.here('192.0.2.10', '192.0.2.10') and relay.here('::1', '')
    assert not relay.here('192.0.2.11', '192.0.2.10') and not relay.here('192.0.2.11', '') and not relay.here('', '') and not relay.here('testclient', 'testclient')


def test_the_agent_turn_builds_the_codex_brain_and_triage_keeps_the_card(here):
    s = MemoryStore(); cid = _card(s)
    with mock.patch.object(llm, 'make_cli_llm', return_value=lambda *a, **k: 'ok') as cli, mock.patch.object(llm, 'make_llm') as api:
        llm._build_llm(s, f'connector:{cid}', keep='general:7', task_id=7, gear='main', cli_tools=True)
        assert cli.call_args.args[1] == f'card-{cid}' and not api.called
        llm._build_llm(s, f'connector:{cid}', gear='light')                               # triage: the card's own one-shot call
        assert api.called and cli.call_count == 1


def test_a_header_keyed_cards_harness_signs_in_to_the_relay_which_adds_the_cards_own_header(here):
    s = MemoryStore()
    cid = s.save_connector({'Type': 'vertex_ai', 'Name': 'Vertex', 'ConfigJson': json.dumps({'project': 'northwind-ai', 'model': 'm', 'harness': 'codex'}),
                            'Secret': KEY, 'Active': 1}, 't')
    agents.agent_row(s, f'card-{cid}')
    p = tomllib.loads((harness.folder(cid) / 'codex' / 'config.toml').read_text(encoding='utf-8'))['model_providers'][f'card{cid}']
    assert p['env_key'] == harness.KEY_ENV and 'env_http_headers' not in p and 'http_headers' not in p
    sent = {}
    class Answer: status_code, headers, iter_content, close = 200, {}, lambda self, chunk_size=None: iter([b'{}']), lambda self: None
    with mock.patch('requests.request', lambda method, url, **kw: sent.update(url=url, **kw) or Answer()):
        relay.send(s, cid, 'POST', 'responses', '', {'authorization': 'Bearer x', 'content-type': 'application/json'}, b'{}')
    assert sent['headers']['x-goog-api-key'] == KEY and not any(k.lower() == 'authorization' for k in sent['headers'])
    assert sent['url'].startswith('https://aiplatform.googleapis.com/') and sent['url'].endswith('/endpoints/openapi/responses')


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
    assert f['provider']['card']['options']['baseURL'] == relay.base(config.load()['server'], cid)          # the relay, as Codex is (relay.py)
    assert prof['env'][harness.KEY_ENV] == relay.token(config.load()['server'], cid)
    assert f['share'] == 'disabled' and f['autoupdate'] is False and f['provider']['card']['models']['hydrogen-low']['id'] == 'hydrogen'
    assert prof['env']['OPENCODE_DISABLE_AUTOUPDATE'] == '1' and prof['env']['OPENCODE_CONFIG'].endswith('opencode.json')


def test_the_model_he_picked_is_one_the_cards_harness_offers_so_the_run_takes_it(here, monkeypatch):
    """Walk 20: on the gateway card the chooser read "HIPAA AI · claude-sonnet-5-5", "you chose it" - and every run took the card's model:
    Codex's session offers only the models of its catalogue, which held the card's two, so the pick was not one it could switch to."""
    monkeypatch.setattr(harness, 'bundled', lambda cmd: {'slug': 'gpt-x'})
    s = MemoryStore(); cid = _card(s)
    seen = []
    real = agents.agent_row
    with mock.patch.object(agents, 'agent_row', side_effect=lambda st, n, m=None: seen.append(m) or real(st, n, m)):
        llm.make_cli_llm(s, f'card-{cid}', 'claude-sonnet-5-5', cli_tools=True, task_id=7)
    assert seen == ['claude-sonnet-5-5'], 'the run hands its pick to the row the harness is started from'
    ms = json.loads((harness.folder(cid) / 'codex' / 'models.json').read_text(encoding='utf-8'))['models']
    assert [m['slug'] for m in ms] == ['hydrogen', 'neon', 'claude-sonnet-5-5']
    oc = _card(s, harness='opencode')
    prof = json.loads(agents.agent_row(s, f'card-{oc}', 'claude-sonnet-5-5@high')['Config'])
    f = json.loads((harness.folder(oc) / 'opencode.json').read_text(encoding='utf-8'))
    assert 'claude-sonnet-5-5-high' in f['provider']['card']['models'] and prof['model'] == 'card/hydrogen'


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
    c = tomllib.loads(harness.codex_config(1, 'AI', 'https://gateway.example/v1', 'hydrogen'))
    p = c['model_providers'][c['model_provider']]
    assert (p['env_key'], p['wire_api'], harness.KEY_ENV) == ('TASKUARY_CARD_KEY', 'responses', 'TASKUARY_CARD_KEY')
    assert c['model_context_window'] == 1_000_000 and c['check_for_update_on_startup'] is False and c['web_search'] == 'disabled'
    assert c['analytics'] == {'enabled': False} and c['feedback'] == {'enabled': False}
    assert all(c['otel'][k] == 'none' for k in ('exporter', 'trace_exporter', 'metrics_exporter'))
    assert all(c['features'][k] is False for k in ('apps', 'plugins', 'remote_plugin'))
    assert c['skills']['bundled']['enabled'] is False          # ...and Codex's own bundled skills never ride a task (the review, 2026-11-23)


def test_a_chat_completions_only_card_defaults_to_opencode_and_its_websearch_is_off(here):
    assert harness.harness_of({}, 'hipaa_ai') == 'codex' and harness.harness_of({}, 'vertex_ai') == 'opencode'
    assert harness.harness_of({'harness': 'codex'}, 'groq') == 'codex'                       # ...his pick stands
    f = harness.opencode_config('AI', 'https://x.example/v1', 'm', '')
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
    from taskuary import agenttools, apiagent
    raw = {t['name']: t['inputSchema'] for t in agenttools.listing()}
    fit = {t['name']: t['inputSchema'] for t in agenttools.listing(portable=True)}
    assert apiagent.portable(raw['propose'])['type'] == 'object' and 'anyOf' not in apiagent.portable(raw['propose'])
    assert all(s['type'] == 'object' and 'anyOf' not in s for s in fit.values())


def test_a_card_session_is_listed_the_core_and_runs_the_rest_by_use_tool():
    """The review, 2026-11-23: an AI card's Codex was sent all ~40 Taskuary schemas (~14k) on every call - no tool search through a gateway.
    It is listed what apiagent offers up front, and any other tool find_tools named runs through use_tool, read back as that tool."""
    import json
    from taskuary import agents, agenttools, apiagent
    whole, card = agenttools.listing(), agenttools.listing(portable=True)
    names = {t['name'] for t in card}
    assert {'find_tools', 'use_tool', 'propose', 'end_turn', 'ask_owner'} <= names and not names & apiagent.LATER
    assert len(json.dumps(card)) < len(json.dumps(whole)) / 2
    assert 'use_tool' not in {t['name'] for t in whole}                           # ...a CLI that defers tools itself gets them all, as before
    ran = []
    call = {'id': 7, 'method': 'tools/call', 'params': {'name': 'use_tool', 'arguments': {'name': 'remind', 'arguments': '{"when": "tomorrow 9am"}'}}}
    got = agenttools.rpc(call, lambda n, a: ran.append((n, a)) or 'set', portable=True)
    assert ran == [('remind', {'when': 'tomorrow 9am'})] and got['result']['isError'] is False
    assert 'error' in agenttools.rpc({**call, 'params': {'name': 'use_tool', 'arguments': {'name': 'remind'}}}, lambda n, a: 'x', skip=('remind',), portable=True)
    # ...and the step reads as the tool it ran, never the wrapper
    c = {'raw': {'server': 'taskuary', 'tool': 'use_tool', 'arguments': {'name': 'propose', 'arguments': {'action': 'pay', 'why': 'due'}}}}
    assert agents.ACPSteps._call(c) == ('mcp__taskuary__propose', {'action': 'pay', 'why': 'due'})


def test_every_act_that_raises_a_card_is_offered_on_every_road(monkeypatch):
    """Walk 10, 2026-11-23: on an AI card's harness propose and hand_over were deferred by apiagent.LATER while agenttools.ALWAYS_LOAD said they
    ride every turn - asked to post, the agent saw no tool that posts and said "I cannot publish directly"."""
    from taskuary import agenttools, apiagent
    acts = {'propose', 'hand_over', 'ask_owner', 'browser_signup', 'show', 'end_turn'}       # ...and the view and the turn's end AGENTS.md names
    assert acts <= set(agenttools.ALWAYS_LOAD) and not acts & apiagent.LATER
    assert acts - {'browser_signup'} <= {t['name'] for t in agenttools.listing(portable=True)}
    listed = [apiagent._fn(t['name'], t['description'], t['inputSchema']) for t in agenttools.listing()]
    monkeypatch.setattr(apiagent, 'taskuary_tools', lambda *a, **k: listed)
    assert acts <= {t['function']['name'] for t in apiagent.tools_for(1, 'acts', browser=True, hands=False)}


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


def test_the_chip_names_the_card_as_he_knows_it_and_keeps_its_harness_apart(here):
    # the owner, 2026-11-24: "HIPAA AI · Codex · gemini-4-hy... - which one?" - the chip is the card and its model; the harness is kept apart
    from taskuary import general
    s = MemoryStore(); cid = _card(s)
    row = next(o for o in general.provider_options(s) if o['pick'] == f'connector:{cid}')
    assert (row['label'], row['model'], row['runs_on']) == ('HIPAA AI', 'hydrogen', 'Codex')


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


def test_a_card_whose_harness_runs_here_takes_a_coding_level_and_says_so(here, monkeypatch):
    """The owner, 2026-11-23: the level picker read "HIPAA AI · Codex - not for coding" for a card whose agent runs on Codex. A card with a
    harness here does coding work on it - the level's coding run goes to that harness CLI; one with none says it has no shell."""
    from taskuary import brainroute
    s = MemoryStore(); cid = _card(s); p = f'connector:{cid}'
    assert next(b for b in brainroute.brains(s) if b['pick'] == p)['coding'] is True
    hands = lambda x: str(x or '').startswith('cli:')
    brainroute.save_by_level(s, {'hard': {'pick': p, 'model': 'neon'}})
    assert brainroute._level(s, 'coding', 'strong', None, None, hands, None) == ((f'cli:card-{cid}', 'neon'), '')
    assert brainroute._said(s, f'cli:card-{cid}') == 'HIPAA AI'
    monkeypatch.setattr(harness, 'ON', False)                    # no harness can run here: the card has no shell for coding
    assert next(b for b in brainroute.brains(s) if b['pick'] == p)['coding'] is False
    assert 'has no shell' in brainroute._level(s, 'coding', 'strong', None, None, hands, None)[1]
