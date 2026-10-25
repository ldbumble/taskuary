"""The strong gear: a third model on each brain, set by the owner, blank by default - and blank means no strong tier.

Nothing is guessed from a model's name (setup never assumes an AI): the router steps up only to a model the owner put in the
"strong model" box of a card.
"""
import ast, json, re
from pathlib import Path
from unittest import mock

from taskuary import agents, aidefaults, brainroute, cli_connections, config, llm
from taskuary.store import MemoryStore

ROOT = Path(__file__).resolve().parents[1] / 'taskuary'


def _cli_store(**gears):
    s = MemoryStore()
    s.upsert_agent('claude', 'coding', 'cli', json.dumps({'cmd': 'claude', **gears}))
    return s


def _ran(s, gear, model=None):
    brain = llm.make_cli_llm(s, 'claude', model, gear=gear)
    with mock.patch.object(agents, 'run_cli', return_value=('ok', 'sid', '')) as run: brain('sys', 'user')
    return run.call_args.args[0].get('model')


def test_the_strong_gear_runs_the_strong_model():
    s = _cli_store(model='sonnet', light_model='haiku', strong_model='opus@high')
    assert (_ran(s, 'light'), _ran(s, 'main'), _ran(s, 'strong')) == ('haiku', 'sonnet', 'opus@high')
    assert _ran(s, 'strong', model='sonnet') == 'sonnet'                 # an explicit per-job model still outranks a gear


def test_a_blank_strong_gear_is_no_strong_tier_and_never_the_light_one():
    s = _cli_store(model='sonnet', light_model='haiku')
    assert _ran(s, 'strong') == 'sonnet'
    assert brainroute.strong_of(s, 'cli:claude', {'cli_connections': {'claude': {'cmd': 'claude', 'model': 'sonnet'}}}) == ''


def test_an_api_card_s_strong_gear_is_swapped_in_for_the_call():
    s = MemoryStore()
    cid = s.get_connector_by_type('anthropic')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-0123456789', 'Active': 1,
                      'ConfigJson': json.dumps({'model': 'claude-sonnet-5', 'strong_model': 'claude-opus-5'})}, 'owner')
    seen = []
    with mock.patch.object(llm, 'make_llm', lambda t, conf, key: seen.append(conf['model']) or (lambda *a, **k: 'ok')):
        llm.build_llm(s, pick=f'connector:{cid}', job='draft')
        llm.build_llm(s, pick=f'connector:{cid}', gear='strong', job='draft')
    assert seen == ['claude-sonnet-5', 'claude-opus-5']
    assert brainroute.strong_of(s, f'connector:{cid}') == 'claude-opus-5'


def test_the_card_saves_the_strong_model_on_the_brain_that_owns_it():
    s = _cli_store(); s.set_setting('triage_ai', 'cli:claude', 'owner'); s.set_setting('default_brain', 'claude', 'owner')
    cfg = {'cli_connections': {'claude': {'cmd': 'claude'}}}
    with mock.patch.object(config, 'save'), mock.patch.object(cli_connections, 'sync'), \
         mock.patch('taskuary.agents.runs_here', lambda profile: True):
        assert aidefaults.resolve(s, cfg, 'triage_ai')['strong_model'] == ''      # blank by default
        r = aidefaults.apply(s, cfg, 'triage_ai', strong='opus')
        assert cfg['cli_connections']['claude']['strong_model'] == 'opus' and r['strong_model'] == 'opus'
        # ...and it is the BRAIN's: the coding card on the same CLI shows the same strong model
        assert aidefaults.resolve(s, cfg, 'default_brain')['strong_model'] == 'opus'
        aidefaults.apply(s, cfg, 'triage_ai', strong='')
        assert 'strong_model' not in cfg['cli_connections']['claude']


def test_an_api_card_keeps_its_strong_model_in_its_own_config():
    s = MemoryStore()
    cid = s.get_connector_by_type('openai')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-0123456789', 'Active': 1, 'ConfigJson': '{}'}, 'owner')
    s.set_setting('triage_ai', f'connector:{cid}', 'owner')
    aidefaults.apply(s, {}, 'triage_ai', strong='gpt-5')
    assert json.loads(s.get_connector(cid)['ConfigJson'])['strong_model'] == 'gpt-5'
    assert aidefaults.resolve(s, {}, 'triage_ai')['strong_model'] == 'gpt-5'


def test_no_model_id_is_typed_into_the_ai_cards():
    """A hand-typed list goes stale (it said Vertex ran a model it did not) and guesses what the owner's key can call. The
    cards' choices are the provider's own list; what a blank box runs is llm.PROVIDER_DEFAULT, the table make_llm reads."""
    tree = ast.parse((ROOT / 'aidefaults.py').read_text(encoding='utf-8'))
    docs = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef))
            and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    shaped = re.compile(r'^(claude|gpt|gemini|muse|llama|meta-llama|openrouter)[-/.]\w', re.I)     # an id, not a regex's prefix
    typed = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
             and id(n) not in docs and shaped.match(n.value)]
    assert not typed, typed


def test_the_provider_list_is_one_cached_read_that_fails_soft():
    s = MemoryStore()
    cid = s.get_connector_by_type('openai')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-0123456789', 'Active': 1}, 'owner')
    llm._models_cache.pop(cid, None)
    with mock.patch.object(llm, 'list_models', return_value=['m-small', 'm-large']) as listed:
        assert llm.connector_models(s, cid) == {'models': ['m-small', 'm-large']}
        assert llm.connector_models(s, cid) == {'models': ['m-small', 'm-large']} and listed.call_count == 1
    llm._models_cache.pop(cid, None)
    with mock.patch.object(llm, 'list_models', side_effect=RuntimeError('openai answered 401')):
        assert llm.connector_models(s, cid)['models'] == [] and '401' in llm.connector_models(s, cid)['error']
    assert llm.connector_models(s, s.get_connector_by_type('github')['ConnectorId'] if s.get_connector_by_type('github') else 99999) is None
