"""An AI per level (the owner, 2026-11-06: "not by default but you can adjust in settings"). In Auto, triage's quick/normal/hard picks
the TIER on the card's AI; the owner may also name the AI itself for a level - for the agents' work only (general, quick work, and
coding on a CLI). Blank is today's routing exactly. Set, it runs there when that AI can take the call, the card's AI behind it, and
otherwise stays on the card and says why. The data rule still wins, and coding never lands on an API card."""
import json
from datetime import datetime, timedelta
from unittest import mock

import pytest

from taskuary import agents, brainroute, config, general
from taskuary.store import MemoryStore

CFG = {'cli_connections': {'claude': {'cmd': 'claude', 'model': 'sonnet', 'strong_model': 'opus'}, 'codex': {'cmd': 'codex'}}}


def _card(s, typ, **conf):
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-0123456789', 'Active': 1, 'ConfigJson': json.dumps(conf)}, 'owner')
    return f'connector:{cid}'


@pytest.fixture
def s():
    s = MemoryStore()
    s.a = _card(s, 'anthropic', model='claude-sonnet-5', strong_model='claude-opus-5', sensitive_ok='1')
    for k, v in (('triage_ai', s.a), ('assistant_ai', s.a), ('default_brain', 'claude'), ('triage_backup_ai', '')): s.set_setting(k, v, 'owner')
    with mock.patch.object(config, 'load', lambda: CFG), mock.patch.object(agents, 'runs_here', lambda prof: bool(prof)), \
         mock.patch.object(agents, 'connection_brains', agents.connection_brains.real): yield s


def _task(s, difficulty='hard', data_class=None):
    tid = s.create_task({'Title': 'Q3 numbers', 'Status': 'open'}, 'owner')
    s.judge_task(tid, {'difficulty': difficulty, **({'data_class': data_class} if data_class else {})}, 'triage')
    return tid


def _set(s, **lv): brainroute.save_by_level(s, {l: {'pick': p, 'model': m} for l, (p, m) in lv.items()})


def test_off_by_default_changes_nothing(s):
    assert MemoryStore().get_setting(brainroute.LEVEL_KEY) == '' and brainroute.by_level(s) == {}
    tid = _task(s)
    before = [brainroute.choose(s, j, task=tid) for j in ('general', 'quick_work', 'coding', 'draft')]
    _set(s, hard=('', ''))                                          # a blank level is the card's AI: nothing is stored
    assert s.get_setting(brainroute.LEVEL_KEY) == '' and [brainroute.choose(s, j, task=tid) for j in ('general', 'quick_work', 'coding', 'draft')] == before
    assert (before[0].pick, before[0].tier, before[0].level) == (s.a, 'strong', '')


def test_set_and_available_routes_there_with_the_card_behind_it(s):
    _set(s, hard=('cli:claude', ''))
    r = brainroute.choose(s, 'general', task=_task(s))
    assert (r.pick, r.tier, r.gear, r.level, r.chain[0]) == ('cli:claude', 'strong', 'strong', 'hard', s.a)
    assert r.why == 'General work judged hard: hard work -> claude (CLI) as set in AI routing (rule hard-work)'
    assert brainroute.choose(s, 'general', task=_task(s, 'standard')).pick == s.a        # normal work keeps the card
    assert brainroute.choose(s, 'draft', task=_task(s)).pick == s.a                       # drafting keeps its own card
    # ...its model when the owner gave one, and a session the level opened carries it back each turn and stays the level's
    _set(s, hard=('cli:claude', 'opus@max'))
    r = brainroute.choose(s, 'general', task=_task(s), want_pick='cli:claude', want_model='sonnet')
    assert (r.pick, r.model, r.level) == ('cli:claude', 'opus@max', 'hard') and 'claude (CLI), opus, max effort as set in AI routing' in r.why
    assert brainroute.choose(s, 'general', task=_task(s), want_pick=s.a).pick == s.a      # an explicit pick still wins


def test_a_new_general_session_opens_on_the_level_s_ai(s):
    _set(s, quick=('cli:codex', ''))
    tid = _task(s, 'quick')
    assert brainroute.level_pick(s, 'general', tid) == ('cli:codex', '') and general.GeneralSession(s, tid).pick == 'cli:codex'
    assert general.GeneralSession(s, _task(s, 'standard')).pick == s.a
    assert brainroute.choose(s, 'quick_work', task=tid).pick == 'cli:codex'


def test_set_but_unavailable_falls_back_to_the_card_and_says_why(s):
    _set(s, hard=('cli:gemini', ''))
    r = brainroute.choose(s, 'general', task=_task(s))
    assert (r.pick, r.level) == (s.a, '') and r.why.endswith('; hard work is set to gemini (CLI) in AI routing, but it is not connected, so its card')
    _set(s, hard=('cli:codex', ''))
    s.set_setting('cli_tests', json.dumps({'codex': False}), 'owner')
    assert 'but it failed its last test, so its card' in brainroute.choose(s, 'general', task=_task(s)).why
    s.set_setting('cli_tests', '', 'owner')
    brainroute.cool(s, 'cli:codex', datetime.now() + timedelta(hours=1))
    r = brainroute.choose(s, 'general', task=_task(s))
    assert r.pick == s.a and 'but it is limited until' in r.why


def test_the_sensitive_rule_still_wins(s):
    brainroute.save_rules(s, [{**r, 'on': True} if r['id'] == 'sensitive' else r for r in brainroute.rules(s)])
    _set(s, hard=('cli:claude', ''))
    r = brainroute.choose(s, 'general', task=_task(s, data_class='sensitive'))
    assert r.pick == s.a and 'but it is not marked to read sensitive data, so its card' in r.why
    assert brainroute.choose(s, 'general', task=_task(s)).pick == 'cli:claude'           # ordinary data goes where it was set


def test_a_coding_job_never_goes_to_an_api_brain(s):
    _set(s, hard=(s.a, ''))
    r = brainroute.choose(s, 'coding', task=_task(s))
    assert r.pick.startswith('cli:') and 'but it has no shell, and this work needs a CLI' in r.why
    _set(s, hard=('cli:codex', 'gpt-5.5@high'))
    r = brainroute.choose(s, 'coding', task=_task(s))
    assert (r.pick, r.model, r.level, r.chain[0]) == ('cli:codex', 'gpt-5.5@high', 'hard', 'cli:claude')
    with mock.patch.object(brainroute, 'log'): assert brainroute.for_session(s, s.get_task(_task(s))) == ('codex', 'gpt-5.5@high')


def test_fixed_mode_ignores_it(s):
    _set(s, hard=('cli:claude', '')); s.set_setting('ai_route_mode', 'fixed', 'owner')
    assert brainroute.choose(s, 'general', task=_task(s)).pick == s.a


def test_the_panel_saves_it_and_its_lines_say_it(s):
    p = brainroute.set_panel(s, by_level_={'hard': {'pick': 'cli:claude', 'model': ''}})
    assert p['by_level'] == {'hard': {'pick': 'cli:claude', 'model': ''}} and {'cli:claude', 'cli:codex', s.a} <= {b['pick'] for b in p['brains']}
    line = next(l for l in p['levels'] if l['pick'] == s.a)
    # the card also triages, so its own hard model stays said, and the agents' hard work names the AI set for it
    assert line['hard'] == 'claude-opus-5; agents: claude (CLI), opus' and line['normal'] == 'claude-sonnet-5'
    with pytest.raises(ValueError): brainroute.save_by_level(s, {'tricky': {'pick': 'cli:claude'}})
    with pytest.raises(ValueError): brainroute.save_by_level(s, {'hard': {'pick': 'claude'}})
    assert brainroute.set_panel(s, by_level_={})['by_level'] == {} and s.get_setting(brainroute.LEVEL_KEY) == ''
