"""Drafting has its own card (the owner, 2026-10-25). Blank is the triage brain, exactly as before; once set, every reply, message
and subject line is written on it. Nothing is sent without the owner's press either way - this chooses who writes, never who sends.
"""
import json
from unittest import mock

from taskuary import aidefaults, brainroute, cli_connections, config, llm, responder
from taskuary.store import MemoryStore


def _keyed(s, typ):
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-0123456789', 'Active': 1}, 'owner')
    return cid


def test_blank_drafting_is_the_triage_brain_exactly():
    s = MemoryStore(); a = _keyed(s, 'anthropic'); s.set_setting('triage_ai', f'connector:{a}', 'owner')
    d, t = brainroute.choose(s, 'draft'), brainroute.choose(s, 'triage')
    assert (d.pick, d.model, d.gear, d.chain) == (t.pick, t.model, t.gear, t.chain) == (f'connector:{a}', '', 'light', [])


def test_once_set_the_drafts_are_written_on_it_and_triage_is_untouched():
    s = MemoryStore(); a, o = _keyed(s, 'anthropic'), _keyed(s, 'openai')
    s.set_setting('triage_ai', f'connector:{a}', 'owner'); s.set_setting('draft_ai', f'connector:{o}', 'owner')
    s.set_setting('draft_model', 'gpt-5', 'owner')
    built = []
    with mock.patch.object(llm, 'make_llm', lambda t, conf, key: built.append((t, conf.get('model'))) or (lambda *a, **k: 'Thanks, Thursday works.')):
        tid = s.create_task({'Title': 'Meeting time', 'Status': 'open'}, 'owner')
        s.add_message({'TaskId': tid, 'Channel': 'email', 'FromEmail': 'erin@northwind.example', 'FromName': 'Erin Blake',
                       'Subject': 'Thursday?', 'BodyText': 'Does Thursday at 2 work?', 'Status': 'routed'})
        responder.draft_reply(s, tid)
        llm.build_llm(s, job='triage')
    assert built[0] == ('openai', 'gpt-5') and built[-1] == ('anthropic', None)
    assert [r['Job'] for r in s.brain_routes()][::-1] == ['draft', 'triage']


def test_the_drafting_card_blank_says_it_is_the_triage_brain():
    s = MemoryStore(); a = _keyed(s, 'anthropic'); s.set_setting('triage_ai', f'connector:{a}', 'owner')
    r = aidefaults.resolve(s, {}, 'draft_ai')
    assert (r['value'], r['default'], r['label']) == (f'connector:{a}', True, 'Drafting')
    assert 'the triage brain' in r['note']
    assert [x['key'] for x in aidefaults.state(s, {})['slots']][:2] == ['triage_ai', 'draft_ai']


def test_the_drafting_model_is_its_own_never_the_light_gear_triage_rides():
    s = MemoryStore(); s.upsert_agent('claude', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
    s.set_setting('triage_ai', 'cli:claude', 'owner'); s.set_setting('draft_ai', 'cli:claude', 'owner')
    cfg = {'cli_connections': {'claude': {'cmd': 'claude', 'light_model': 'haiku'}}}
    with mock.patch.object(config, 'save'), mock.patch.object(cli_connections, 'sync'), \
         mock.patch('taskuary.agents.runs_here', lambda profile: True), mock.patch('taskuary.agents.ready_brains', lambda store: ['claude']):
        assert aidefaults.resolve(s, cfg, 'draft_ai')['default_hint'].startswith('haiku')     # blank = the light gear, as before
        aidefaults.apply(s, cfg, 'draft_ai', model='sonnet', effort='medium')
        assert cfg['cli_connections']['claude']['light_model'] == 'haiku'                    # triage's gear untouched
        assert s.get_setting('draft_model') == 'sonnet@medium'
        assert (brainroute.choose(s, 'draft').model, brainroute.choose(s, 'triage').model) == ('sonnet@medium', '')
        assert aidefaults.resolve(s, cfg, 'draft_ai')[('model')] == 'sonnet'


def test_an_explicit_pick_still_wins_over_the_drafting_card():
    s = MemoryStore(); o = _keyed(s, 'openai'); s.set_setting('draft_ai', 'cli:claude', 'owner')
    assert brainroute.choose(s, 'draft', want_pick=f'connector:{o}').pick == f'connector:{o}'


def test_the_drafting_model_waits_for_a_drafting_brain():
    # the owner, 2026-10-25: blank Drafting is the triage brain on its own model, so the drafting model box is shut until a brain is chosen
    s = MemoryStore(); a, o = _keyed(s, 'anthropic'), _keyed(s, 'openai'); s.set_setting('triage_ai', f'connector:{a}', 'owner')
    try: aidefaults.apply(s, {}, 'draft_ai', model='gpt-5'); assert False, 'a model saved on a blank Drafting card'
    except ValueError as e: assert 'choose a drafting brain first' in str(e)
    aidefaults.apply(s, {}, 'draft_ai', value=f'connector:{o}'); aidefaults.apply(s, {}, 'draft_ai', model='gpt-5')
    assert brainroute.choose(s, 'draft').model == 'gpt-5'
    aidefaults.apply(s, {}, 'draft_ai', value='')                  # back to blank: the triage brain, and no drafting model left riding it
    assert (s.get_setting('draft_model'), brainroute.choose(s, 'draft').model) == ('', '')
