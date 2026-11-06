"""Auto mode and its rules (the router, 2026-10-25). ON unless the owner chose Fixed (the owner, 2026-11-06); Fixed is the cards,
exactly as before. In Auto each card is its job's STANDARD tier and the rules - plain, ordered, each with its own switch - say when the quick gear or the strong
model runs instead. A rule matches judgement values and ids, never a word from the mail; an explicit pick or model always wins."""
import json
from unittest import mock

import pytest

from taskuary import agents, brainroute, config, llm
from taskuary.store import MemoryStore


def _card(s, typ, **conf):
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-0123456789', 'Active': 1, 'ConfigJson': json.dumps(conf)}, 'owner')
    return f'connector:{cid}'


@pytest.fixture
def s():
    s = MemoryStore()
    s.a = _card(s, 'anthropic', model='claude-sonnet-5', strong_model='claude-opus-5')
    s.o = _card(s, 'openai', model='gpt-5')
    s.set_setting('triage_ai', s.a, 'owner')
    return s


def _task(s, difficulty=None):
    tid = s.create_task({'Title': 'Q3 numbers', 'Status': 'open'}, 'owner')
    if difficulty: s.judge_task(tid, {'difficulty': difficulty}, 'triage')
    return tid


def test_auto_is_on_on_a_fresh_install_and_fixed_is_the_cards(s):
    """The owner, 2026-11-06: "it should be on auto routing by default using triage designation"."""
    assert brainroute.mode(s) == 'auto' and MemoryStore().get_setting('ai_route_mode') == 'auto'
    assert brainroute.choose(s, 'draft', task=_task(s, 'hard')).tier == 'strong'
    s.set_setting('ai_route_mode', 'fixed', 'owner')
    r = brainroute.choose(s, 'draft', task=_task(s, 'hard'))
    assert (r.tier, r.pick, r.gear, r.rule) == ('fixed', s.a, 'light', 'fixed')


def test_an_install_on_the_old_fixed_seed_moves_to_auto_once_and_a_chosen_fixed_stays(tmp_path):
    from taskuary.store import SQLiteStore as Store
    db = str(tmp_path / 'tq.db')
    s = Store(db); s.cx.execute("UPDATE setting SET Value='fixed', UpdatedBy=NULL WHERE Name='ai_route_mode'"); s.cx.commit()
    assert brainroute.mode(Store(db)) == 'auto'                                   # nobody chose the old seed: it moves
    s = Store(db); brainroute.set_panel(s, mode_='fixed')
    assert brainroute.mode(Store(db)) == 'fixed'                                  # the owner's own Fixed is kept, every open


def test_the_rules_pick_the_tier_in_order(s):
    s.set_setting('ai_route_mode', 'auto', 'owner')
    quick, hard, plain = brainroute.choose(s, 'triage'), brainroute.choose(s, 'draft', task=_task(s, 'hard')), brainroute.choose(s, 'draft', task=_task(s))
    assert (quick.tier, quick.gear, quick.rule) == ('light', 'light', 'quick-jobs')
    assert (hard.tier, hard.gear, hard.pick, hard.rule) == ('strong', 'strong', s.a, 'hard-work')
    assert hard.why == 'A draft judged hard -> strong on Anthropic API (rule hard-work)'
    assert (plain.tier, plain.gear, plain.rule) == ('standard', 'main', 'work')
    assert brainroute.choose(s, 'assistant').tier == 'fixed'                    # the Assistant keeps its own model


def test_the_first_matching_rule_wins_and_a_switched_off_one_is_skipped(s):
    s.set_setting('ai_route_mode', 'auto', 'owner')
    brainroute.save_rules(s, [{'id': 'drafts-strong', 'when': {'job': ['draft']}, 'use': {'tier': 'strong'}}])
    assert brainroute.choose(s, 'draft', task=_task(s)).rule == 'drafts-strong'
    rs = [{**r, 'on': False} if r['id'] == 'drafts-strong' else r for r in brainroute.rules(s)]
    brainroute.save_rules(s, rs)
    assert brainroute.choose(s, 'draft', task=_task(s)).rule == 'work'
    assert [r['id'] for r in brainroute.rules(s)] == ['drafts-strong', 'quick-jobs', 'hard-work', 'quick-work', 'work', 'unsure', 'sensitive']


def test_a_rule_names_only_what_the_router_knows(s):
    for bad in ({'when': {'subject': ['invoice']}, 'use': {'tier': 'strong'}}, {'when': {'job': ['everything']}, 'use': {'tier': 'strong'}},
                {'when': {'job': ['draft']}, 'use': {'tier': 'huge'}}, {'when': {'job': ['draft']}, 'use': {}}):
        with pytest.raises(ValueError): brainroute.save_rules(s, [{'id': 'x', **bad}])


def test_an_explicit_pick_or_model_always_wins(s):
    s.set_setting('ai_route_mode', 'auto', 'owner'); tid = _task(s, 'hard')
    r = brainroute.choose(s, 'draft', task=tid, want_pick=s.o, want_model='gpt-5-mini')
    assert (r.pick, r.model, r.tier, r.rule) == (s.o, 'gpt-5-mini', 'fixed', 'you chose it')
    # a picked brain still gets the tier - on that brain, never another: with no strong model it thinks harder on its own one,
    # and one that cannot do hard work at standard
    r = brainroute.choose(s, 'draft', task=tid, want_pick=s.o)
    assert (r.pick, r.tier, r.model) == (s.o, 'strong', 'gpt-5@high')
    m = _card(s, 'mistral', model='mistral-large')
    r = brainroute.choose(s, 'draft', task=tid, want_pick=m)
    assert (r.pick, r.tier) == (m, 'standard') and 'it has no strong model' in r.why
    assert brainroute.choose(s, 'draft', task=tid, want_pick=s.a).tier == 'strong'


def test_hard_work_moves_to_the_first_backup_with_a_strong_model(s):
    s.set_setting('ai_route_mode', 'auto', 'owner'); s.set_setting('triage_ai', s.o, 'owner'); s.set_setting('triage_backup_ai', s.a, 'owner')
    r = brainroute.choose(s, 'draft', task=_task(s, 'hard'))
    assert (r.pick, r.tier, r.chain) == (s.a, 'strong', [s.o]) and r.why == 'A draft judged hard -> strong on Anthropic API (rule hard-work); OpenAI API has no strong model'


def test_no_strong_model_anywhere_stays_standard_and_says_so(s):
    m = _card(s, 'mistral', model='mistral-large')                     # ...and no effort to raise: mistral takes none here
    s.set_setting('ai_route_mode', 'auto', 'owner'); s.set_setting('triage_ai', m, 'owner'); s.o = m
    r = brainroute.choose(s, 'draft', task=_task(s, 'hard'))
    assert (r.pick, r.tier, r.gear) == (s.o, 'standard', 'main') and 'no brain here has a strong model, so standard' in r.why


def test_the_strong_tier_reaches_the_brain_that_is_built(s):
    s.set_setting('ai_route_mode', 'auto', 'owner'); tid = _task(s, 'hard'); seen = []
    with mock.patch.object(llm, 'make_llm', lambda t, conf, key: seen.append(conf['model']) or (lambda *a, **k: 'ok')):
        llm.build_llm(s, job='draft', task_id=tid); llm.build_llm(s, job='draft', task_id=_task(s))
    assert seen == ['claude-opus-5', 'claude-sonnet-5']
    assert [r['Tier'] for r in s.brain_routes()][::-1] == ['strong', 'standard']


def test_coding_never_routes_to_a_connector_and_the_guide_chat_stays_quick(s):
    s.set_setting('ai_route_mode', 'auto', 'owner')
    with mock.patch('taskuary.agents.resolve_brain', lambda store, role, cli_only=False: ''):
        r = brainroute.choose(s, 'coding', task=_task(s, 'hard'))
    assert r.pick == '' and 'No AI' in r.why or not r.pick.startswith('connector:')
    from taskuary.general import DOCK_TAG
    dock = s.create_task({'Title': 'Guide', 'Status': 'open', 'SourceRef': DOCK_TAG}, 'owner')
    assert brainroute.choose(s, 'general', task=dock, want_pick=s.a, gear='light').gear == 'light'


def test_an_empty_ladder_is_no_ai(s):
    bare = MemoryStore(); bare.set_setting('ai_route_mode', 'auto', 'owner')
    with mock.patch('taskuary.agents.default_pick', lambda store: ''):
        r = brainroute.choose(bare, 'draft')
    assert r.pick == '' and r.why.startswith('No AI is connected')


def test_a_coding_pane_opens_on_the_strong_gear_only_in_auto(s):
    tid = _task(s, 'hard')
    with mock.patch.object(brainroute, 'strong_of', lambda store, p, cfg=None: 'opus@high' if p == 'cli:claude' else ''), \
         mock.patch('taskuary.agents.resolve_brain', lambda store, role, cli_only=False: 'cli:claude'), \
         mock.patch.object(brainroute, 'session_chain', lambda store, brain=None: [brain or 'claude']):
        s.set_setting('ai_route_mode', 'fixed', 'owner')
        assert brainroute.for_session(s, s.get_task(tid), 'claude') == ('claude', None)        # fixed: today's choice
        s.set_setting('ai_route_mode', 'auto', 'owner')
        assert brainroute.for_session(s, s.get_task(tid), 'claude') == ('claude', 'opus@high')
        assert brainroute.for_session(s, s.get_task(_task(s)), 'claude') == ('claude', None)


def test_a_reply_to_a_hard_task_is_written_on_the_strong_model(s):
    from taskuary import responder
    s.set_setting('ai_route_mode', 'auto', 'owner'); tid = _task(s, 'hard'); seen = []
    s.add_message({'TaskId': tid, 'Channel': 'email', 'FromEmail': 'erin@northwind.example', 'FromName': 'Erin Blake',
                   'Subject': 'Board pack', 'BodyText': 'Can you pull the board pack together by Thursday?', 'Status': 'routed'})
    with mock.patch.object(llm, 'make_llm', lambda t, conf, key: seen.append(conf['model']) or (lambda *a, **k: 'Yes - by Thursday.')):
        responder.draft_reply(s, tid)
    assert seen == ['claude-opus-5'] and s.brain_routes(tid, limit=1)[0]['Rule'] == 'hard-work'


def test_general_work_triage_judged_quick_runs_light_in_auto(s):
    """The owner, 2026-11-05: "haiku or sonnet instead of opus for regular agent stuff based off triage complexity" - quick -> light,
    plain -> standard (the card's model), hard -> strong. Fixed mode is the cards, as before."""
    s.set_setting('ai_route_mode', 'fixed', 'owner')
    assert brainroute.choose(s, 'general', task=_task(s, 'quick')).tier == 'fixed'
    s.set_setting('ai_route_mode', 'auto', 'owner')
    q, p, h = (brainroute.choose(s, 'general', task=_task(s, d)) for d in ('quick', None, 'hard'))
    assert (q.tier, q.rule) == ('light', 'quick-work') and (p.tier, p.rule) == ('standard', 'work') and (h.tier, h.rule) == ('strong', 'hard-work')


# ── one model, three steps: effort instead (the owner, 2026-11-06) ─────────────────────────────────────────────────────────────
def _cli(s, cli='claude', **conn):
    cfg = {'cli_connections': {cli: {'cmd': cli, **conn}}}
    s.set_setting('triage_ai', f'cli:{cli}', 'owner')
    return mock.patch.object(config, 'load', lambda: cfg)


def test_a_one_model_cli_does_hard_work_at_high_effort_and_says_so(s):
    with _cli(s, model='sonnet'):
        r = brainroute.choose(s, 'draft', task=_task(s, 'hard'))
        assert (r.pick, r.tier, r.model) == ('cli:claude', 'strong', 'sonnet@high')
        assert r.why == 'A draft judged hard -> strong on claude (CLI), sonnet, high effort (rule hard-work)'
        assert brainroute.choose(s, 'draft', task=_task(s))[2:5] == ('cli:claude', '', 'main')   # normal: the card's own model, as before
    with _cli(s):                                                                    # no model box: the CLI's own model, thinking harder
        assert brainroute.choose(s, 'draft', task=_task(s, 'hard')).model == '@high'
    with _cli(s, model='sonnet', strong_model='opus'):                               # a strong model of its own wins
        r = brainroute.choose(s, 'draft', task=_task(s, 'hard'))
        assert (r.tier, r.model, r.gear) == ('strong', '', 'strong')


def test_the_effort_reaches_the_cli_in_its_own_flag(s):
    assert agents._model_args({'model': 'sonnet@high'}, 'claude') == ['--model', 'sonnet', '--effort', 'high']
    assert agents._model_args({'model': '@high'}, 'codex') == ['-c', 'model_reasoning_effort=high']


def test_a_brain_without_an_effort_setting_keeps_today_s_answer(s):
    s.set_setting('triage_ai', _card(s, 'groq', model='llama-3.3-70b-versatile'), 'owner')    # an API card whose provider takes none
    r = brainroute.choose(s, 'draft', task=_task(s, 'hard'))
    assert (r.tier, r.model) == ('standard', '') and 'no brain here has a strong model' in r.why
    assert brainroute.choose(s, 'triage').model == ''
    with _cli(s, 'gemini', model='gemini-2.5-pro'):                                  # a CLI whose effort flag we cannot spell
        assert brainroute.choose(s, 'draft', task=_task(s, 'hard')).tier == 'standard'
    with _cli(s, model='sonnet@max'):                                                # already past high: no step to take
        assert brainroute.choose(s, 'draft', task=_task(s, 'hard')).tier == 'standard'


def test_light_on_one_model_is_low_effort_where_the_cli_ships_no_quick_gear(s):
    with _cli(s, model='sonnet'), mock.patch.dict(llm.LIGHT_DEFAULT, {'claude': ''}):
        r = brainroute.choose(s, 'triage')
        assert (r.tier, r.model) == ('light', 'sonnet@low') and 'sonnet, low effort' in r.why
    with _cli(s, model='sonnet'):                                                    # claude's own quick gear (haiku) stands
        assert brainroute.choose(s, 'triage').model == ''


def test_settings_says_what_each_level_runs_on_in_plain_words(s):
    with _cli(s, model='sonnet'):
        lv = brainroute.levels(s)
    assert {k: lv[0][k] for k in ('brain', 'quick', 'normal', 'hard')} == \
        {'brain': 'claude (CLI)', 'quick': 'haiku', 'normal': 'sonnet', 'hard': 'same model, high effort'}
    with _cli(s, 'codex'):
        assert {k: brainroute.levels(s)[0][k] for k in ('quick', 'normal', 'hard')} == \
            {'quick': 'same model, low effort', 'normal': 'its default model', 'hard': 'same model, high effort'}
    s.set_setting('triage_ai', s.a, 'owner')
    assert brainroute.levels(s)[0]['hard'] == 'claude-opus-5' and brainroute.levels(s)[0]['quick'] == 'same model, low effort'
    s.set_setting('triage_ai', s.o, 'owner')                                          # one model on an API card: effort both ways
    assert {k: brainroute.levels(s)[0][k] for k in ('quick', 'normal', 'hard')} == \
        {'quick': 'same model, low effort', 'normal': 'gpt-5', 'hard': 'same model, high effort'}
    s.set_setting('triage_ai', _card(s, 'groq'), 'owner')
    assert {k: brainroute.levels(s)[0][k] for k in ('quick', 'hard')} == {'quick': 'same model', 'hard': 'same model'}
    words = ' '.join(' '.join(str(v) for v in l.values()) for l in brainroute.panel(s)['levels'])
    assert not any(w in words.lower() for w in ('tier', 'gear'))


def test_the_panel_tells_a_person_how_auto_picks():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / 'website' / 'src' / 'RouteRules.jsx').read_text(encoding='utf-8')
    assert 'Triage judges each task quick, normal or hard and picks the model for it' in src
    assert 'quick: ${l.quick} · normal: ${l.normal} · hard: ${l.hard}' in src
    said = [m for m in __import__('re').findall(r'"([^"]*)"', src) if ' ' in m]
    assert not [m for m in said if __import__('re').search(r'\b(tier|gear)s?\b', m, __import__('re').I)], said


# ── effort on an API card: sent where the provider takes it, dropped once where the model does not (mocked HTTP, no live calls) ──
class _R:
    def __init__(self, code, data=None, text=''): self.status_code, self._d, self.text = code, data, text or json.dumps(data or {})
    def json(self): return self._d


OK = {'choices': [{'message': {'content': 'ok'}, 'finish_reason': 'stop'}]}


@pytest.fixture
def fresh():
    llm._NO_EFFORT.clear(); yield; llm._NO_EFFORT.clear()


def test_openai_and_azure_get_reasoning_effort_and_the_bare_model(fresh):
    sent = []
    with mock.patch.object(llm.requests, 'post', lambda url, headers, json, timeout: sent.append(json) or _R(200, OK)):
        assert llm.make_llm('openai', {'model': 'gpt-5@high'}, 'sk-test')('sys', 'user') == 'ok'
        llm.make_llm('azure_openai', {'endpoint': 'https://res.example', 'deployment': 'gpt5', 'model': '@low'}, 'k')('sys', 'user')
        llm.make_llm('openai', {'model': 'gpt-5'}, 'sk-test')('sys', 'user')
    assert (sent[0]['model'], sent[0]['reasoning_effort']) == ('gpt-5', 'high')
    assert sent[1]['model'] == 'gpt5' and sent[1]['reasoning_effort'] == 'low'
    assert 'reasoning_effort' not in sent[2]                                         # no effort asked, none sent


def test_a_model_that_refuses_the_effort_is_asked_once_more_without_it_and_not_again(fresh):
    sent = []
    no = _R(400, text='{"error": {"message": "Unsupported parameter: \'reasoning_effort\' is not supported with this model."}}')
    def post(url, headers, json, timeout):
        sent.append(dict(json)); return no if 'reasoning_effort' in json else _R(200, OK)
    with mock.patch.object(llm.requests, 'post', post):
        brain = llm.make_llm('openai', {'model': 'gpt-4o-mini@high'}, 'sk-test')
        assert brain('sys', 'user') == 'ok' and brain('sys', 'again') == 'ok'
    assert ['reasoning_effort' in b for b in sent] == [True, False, False]


def test_another_400_is_not_read_as_a_refused_effort(fresh):
    with mock.patch.object(llm.requests, 'post', lambda url, headers, json, timeout: _R(400, text='{"error": "bad key"}')):
        with pytest.raises(RuntimeError, match='openai error 400'): llm.make_llm('openai', {'model': 'gpt-5@high'}, 'sk-test')('sys', 'u')
    assert not llm._NO_EFFORT


def test_anthropic_gets_output_config_effort_and_drops_it_when_refused(fresh):
    import anthropic, httpx2
    seen = []
    def create(**kw):
        seen.append(kw)
        if kw.get('output_config') and kw['model'] == 'claude-old':
            raise anthropic.BadRequestError('output_config.effort: this model does not support effort', body=None,
                                            response=httpx2.Response(400, request=httpx2.Request('POST', 'https://api.anthropic.example')))
        return mock.Mock(stop_reason='end_turn', content=[mock.Mock(type='text', text='ok')])
    client = mock.Mock(); client.messages.create = create
    with mock.patch.object(anthropic, 'Anthropic', lambda api_key: client):
        assert llm.make_llm('anthropic', {'model': 'claude-sonnet-5@high'}, 'sk-test')('sys', 'user') == 'ok'
        assert llm.make_llm('anthropic', {'model': 'claude-old@low'}, 'sk-test')('sys', 'user') == 'ok'
    assert (seen[0]['model'], seen[0]['output_config']) == ('claude-sonnet-5', {'effort': 'high'})
    assert seen[1]['output_config'] == {'effort': 'low'} and 'output_config' not in seen[2] and seen[2]['model'] == 'claude-old'


def test_a_provider_without_effort_never_sees_it_and_a_dated_id_stays_whole(fresh):
    sent = []
    with mock.patch.object(llm.requests, 'post', lambda url, headers, json, timeout: sent.append(json) or _R(200, OK)):
        llm.make_llm('groq', {'model': 'llama-3.3-70b-versatile@high'}, 'k')('sys', 'user')
    assert sent[0]['model'] == 'llama-3.3-70b-versatile' and 'reasoning_effort' not in sent[0]
    assert llm.split_effort('claude-x@20251101') == ('claude-x@20251101', '') and llm.split_effort('@low') == ('', 'low')


def test_the_router_s_effort_reaches_the_api_call(s, fresh):
    s.set_setting('triage_ai', s.o, 'owner'); tid = _task(s, 'hard'); sent = []
    with mock.patch.object(llm.requests, 'post', lambda url, headers, json, timeout: sent.append(json) or _R(200, OK)):
        llm.build_llm(s, job='draft', task_id=tid)('sys', 'user')
    assert (sent[0]['model'], sent[0]['reasoning_effort']) == ('gpt-5', 'high')
    assert 'gpt-5, high effort' in s.brain_routes(tid, limit=1)[0]['Why']


def test_a_rule_sentence_never_repeats_its_job():
    from taskuary import brainroute
    assert brainroute.sentence({'when': {'job': ['general', 'quick_work'], 'difficulty': ['quick']}, 'use': {'tier': 'light'}}) == \
        'Quick general work -> the quick model'
