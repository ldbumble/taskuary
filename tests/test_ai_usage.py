"""What each AI call used (the owner, 2026-11-06: "count of tokens per agent ... time it took ... which model it used"): the provider's
own count on that call's route row, per provider and CLI; blank where nothing counts; an agent session's run on its route; the
dashboard's ai_usage dataset and tiles; the task's "AI used" endpoint; and the agent's own ask of a stronger model (no cap)."""
import json
from types import SimpleNamespace as NS
from unittest import mock

import pytest

from taskuary import aiusage, brainroute, dashboards, llm
from taskuary.store import MemoryStore


def _route(s, job='triage', tid=None, tier='light'):
    return brainroute.log(s, brainroute.Route(job, tier, 'connector:1', '', 'light', [], 'fixed', 'test'), tid)


def _row(s, rid): return next(r for r in s.brain_routes(None, limit=50) if r['Id'] == rid)


def _post(body, status=200):
    r = mock.Mock(); r.status_code, r.text = status, json.dumps(body); r.json.return_value = body; return r


# ── per provider ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_anthropic_counts_its_cache_into_what_went_in():
    s = MemoryStore(); rid = _route(s)
    msg = NS(stop_reason='end_turn', model='claude-sonnet-4-5', content=[NS(type='text', text='ok')],
             usage=NS(input_tokens=120, output_tokens=40, cache_read_input_tokens=900, cache_creation_input_tokens=30))
    cli = mock.Mock(); cli.messages.create.return_value = msg
    with mock.patch('anthropic.Anthropic', return_value=cli):
        brain = aiusage.metered(s, rid, llm.make_llm('anthropic', {'model': 'claude-sonnet-4-5'}, 'sk-ant-test'))
        assert brain('sys', 'hi') == 'ok' and brain('sys', 'again') == 'ok'
    r = _row(s, rid)
    assert (r['TokensIn'], r['Cached'], r['TokensOut'], r['Ran'], r['Calls']) == (2 * 1050, 2 * 900, 80, 'claude-sonnet-4-5', 2)
    assert r['Ms'] is not None


@pytest.mark.parametrize('t, cfg', [('openai', {'model': 'gpt-5'}), ('azure_openai', {'endpoint': 'https://x.example', 'deployment': 'd1'}),
                                    ('hipaa_ai', {'base_url': 'https://ai.northwind.example/v1'}), ('openrouter', {})])
def test_chat_completions_usage_lands_on_the_route(t, cfg):
    s = MemoryStore(); rid = _route(s)
    body = {'model': 'gpt-5-2026', 'choices': [{'message': {'content': 'ok'}}],
            'usage': {'prompt_tokens': 500, 'completion_tokens': 60, 'prompt_tokens_details': {'cached_tokens': 200}}}
    with mock.patch('taskuary.llm.requests.post', return_value=_post(body)):
        assert aiusage.metered(s, rid, llm.make_llm(t, cfg, 'key-test'))('s', 'u') == 'ok'
    r = _row(s, rid)
    assert (r['TokensIn'], r['Cached'], r['TokensOut'], r['Ran']) == (500, 200, 60, 'gpt-5-2026')


def test_the_responses_api_web_road_counts_too():
    s = MemoryStore(); rid = _route(s, 'general', tier='standard')
    body = {'model': 'gpt-5', 'output_text': 'found it', 'output': [],
            'usage': {'input_tokens': 3000, 'output_tokens': 400, 'input_tokens_details': {'cached_tokens': 1000}}}
    with mock.patch('taskuary.llm.requests.post', return_value=_post(body)):
        assert aiusage.metered(s, rid, llm.make_llm('openai', {'model': 'gpt-5'}, 'k'))('s', 'u', web=True) == 'found it'
    r = _row(s, rid)
    assert (r['TokensIn'], r['Cached'], r['TokensOut']) == (3000, 1000, 400)


def test_the_chatgpt_plan_counts_from_its_completed_event():
    from taskuary import chatgptauth as ca
    s = MemoryStore(); rid = _route(s)
    lines = [f'data: {json.dumps(e)}' for e in ({'type': 'response.output_text.delta', 'delta': 'ok'},
             {'type': 'response.completed', 'response': {'usage': {'input_tokens': 800, 'output_tokens': 20, 'input_tokens_details': {'cached_tokens': 0}}}})]
    r = mock.MagicMock(); r.status_code = 200; r.iter_lines.return_value = iter(lines); r.__enter__.return_value = r
    with mock.patch.object(ca.requests, 'post', return_value=r):
        assert aiusage.metered(s, rid, lambda *a, **k: ca.complete('tok', 'gpt-5', 's', 'u', 100))('s', 'u') == 'ok'
    row = _row(s, rid)
    assert (row['TokensIn'], row['TokensOut'], row['Ran']) == (800, 20, 'gpt-5')


def test_cli_answers_claude_result_and_codex_turns():
    m = {}
    tok = aiusage._METER.set(m)
    try:
        aiusage.claude_result({'type': 'result', 'usage': {'input_tokens': 10, 'output_tokens': 5, 'cache_read_input_tokens': 90},
                               'modelUsage': {'claude-haiku-4-5': {'outputTokens': 1}, 'claude-opus-4-1': {'outputTokens': 5}}})
        aiusage.codex_turn({'input_tokens': 400, 'cached_input_tokens': 300, 'output_tokens': 7})
    finally: aiusage._METER.reset(tok)
    assert m == {'model': 'claude-opus-4-1', 'in': 500, 'cached': 390, 'out': 12}


def test_a_brain_that_counts_nothing_leaves_tokens_blank_but_keeps_its_time():
    s = MemoryStore(); rid = _route(s)
    aiusage.metered(s, rid, lambda *a, **k: 'ok')('s', 'u')
    r = _row(s, rid)
    assert (r['TokensIn'], r['TokensOut'], r['Calls']) == (None, None, 1) and r['Ms'] is not None
    assert aiusage.row(s, r)['tokens'] is None                 # never a guessed 0


def test_build_llm_meters_what_it_hands_out():
    s = MemoryStore(); cid = s.get_connector_by_type('openai')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-0123456789', 'Active': 1, 'ConfigJson': json.dumps({'model': 'gpt-5'})}, 'owner')
    tid = s.create_task({'Title': 'Vendor invoice', 'Status': 'open'}, 'owner')
    body = {'model': 'gpt-5', 'choices': [{'message': {'content': 'ok'}}], 'usage': {'prompt_tokens': 50, 'completion_tokens': 5}}
    with mock.patch('taskuary.llm.requests.post', return_value=_post(body)):
        assert llm.build_llm(s, pick=f'connector:{cid}', task_id=tid, job='summary')('s', 'u') == 'ok'
    r = s.brain_routes(tid, limit=1)[0]
    assert (r['Job'], r['TokensIn'], r['TokensOut'], r['Calls']) == ('summary', 50, 5, 1)


# ── an agent session in a pane ──────────────────────────────────────────────────────────────────────────────────────────────
def test_a_pane_session_lands_once_on_the_route_it_opened_on():
    s = MemoryStore(); tid = s.create_task({'Title': 'Fix the import', 'Status': 'open', 'Kind': 'coding'}, 'owner')
    rid = brainroute.log(s, brainroute.Route('coding', 'strong', 'cli:claude', 'opus', 'strong', [], 't1', 'hard'), tid)
    started = _row(s, rid)['At']
    rec = {'took': 750, 'usage': {'in': 9000, 'cached': 8000, 'out': 300}}
    for _ in range(2): assert aiusage.session(s, tid, 'pane-1', 'claude', started, rec, 'claude-opus-4-1') == rid     # exit AND close
    r = _row(s, rid)
    assert (r['Sid'], r['Ran'], r['TokensIn'], r['TokensOut'], r['Ms'], r['Calls']) == ('pane-1', 'claude-opus-4-1', 9000, 300, 750000, 1)
    other = aiusage.session(s, tid, 'pane-2', 'codex', started, {'took': 60}, '')       # no route of its own left: a row of its own
    assert other != rid and _row(s, other)['Pick'] == 'cli:codex' and _row(s, other)['TokensIn'] is None


# ── the endpoint, the dataset and the dashboard ────────────────────────────────────────────────────────────────────────────
def _usage_store():
    s = MemoryStore(); tid = s.create_task({'Title': 'Vendor spend', 'Status': 'open', 'Kind': 'general'}, 'owner')
    for job, tier, i, o in (('triage', 'light', 1000, 50), ('triage', 'light', 2000, 70), ('general', 'standard', 90000, 4000)):
        rid = brainroute.log(s, brainroute.Route(job, tier, 'cli:claude', '', 'light', [], 'fixed', 'x'), tid)
        s.add_brain_usage(rid, 60000 if job == 'general' else 1500, {'in': i, 'out': o, 'model': 'claude-sonnet-4-5'})
    return s, tid


def test_the_task_endpoint_lists_every_call_with_its_totals():
    from fastapi.testclient import TestClient
    from taskuary import server
    s, tid = _usage_store()
    with mock.patch.object(server, 'store', s): got = TestClient(server.app).get(f'/api/tasks/{tid}/ai-used').json()
    assert got['total'] == {'calls': 3, 'tokens': 97120, 'tokens_in': 93000, 'tokens_out': 4120, 'cached': None, 'seconds': 63.0}
    top = got['rows'][0]
    assert (top['what'], top['tier'], top['model'], top['tokens'], top['seconds'], top['run']) == ('general work', 'normal', 'claude-sonnet-4-5', 94000, 60.0, True)


def test_the_dataset_keeps_a_run_whole_and_rolls_the_one_calls_up_per_day():
    s, tid = _usage_store()
    rows = dashboards.DATASETS['ai_usage'][0](s, 90)
    run = next(r for r in rows if r['kind'] == 'agent run')
    one = next(r for r in rows if r['kind'] == 'one call')
    assert (run['task_id'], run['tokens'], run['minutes']) == (tid, 94000, 1.0)
    assert (one['calls'], one['tokens'], one['tier'], one['task_id']) == (2, 3120, 'quick', None)


def test_the_built_in_dashboard_draws_the_ai_tiles_and_an_old_copy_gets_them_once():
    s, _ = _usage_store()
    assert dashboards.validate(dashboards.GLANCE, s) == (True, '')
    data = dashboards.collect(s, dashboards.GLANCE)
    assert not dashboards.problems(dashboards.GLANCE, data)
    assert dict(dashboards.headline(dashboards.GLANCE, data))['Tokens per agent run'] == '94.0K'
    # an install seeded before 2026-11-06: its saved copy has no AI source
    old = {**dashboards.GLANCE, 'sources': [x for x in dashboards.GLANCE['sources'] if x['key'] != 'ai'],
           'components': [c for c in dashboards.GLANCE['components'] if c.get('source') != 'ai']}
    row = next(r for r in s.list_sources(active_only=False) if r['Address'] == dashboards.GLANCE['title'])
    s.save_source({'SourceId': row['SourceId'], 'ConfigJson': json.dumps(old)}, 'owner')
    assert dashboards.migrate_ai_tiles(s) == 1 and dashboards.migrate_ai_tiles(s) == 0
    got = dashboards.cfg_of(s.get_source(row['SourceId']))
    assert [c['title'] for c in got['components'][-5:]] == [c['title'] for c in dashboards.AI_TILES] and dashboards.validate(got, s)[0]


def _glance_row(s, spec):
    row = next(r for r in s.list_sources(active_only=False) if r['Address'] == dashboards.GLANCE['title'])
    s.save_source({'SourceId': row['SourceId'], 'ConfigJson': json.dumps(spec)}, 'owner')
    return lambda: dashboards.cfg_of(s.get_source(row['SourceId']))


def test_the_token_total_is_in_the_top_row_and_a_copy_with_the_ai_tiles_last_moves_them_up_once():
    # the owner, 2026-11-07: "I don't see the token count?" - the AI tiles were the last five, below the fold
    top = dashboards.GLANCE['components'][:4]
    assert dashboards.AI_TOKENS in top and all(c['kind'] == 'stat' for c in top)
    assert dict(dashboards.headline(dashboards.GLANCE, dashboards.collect(_usage_store()[0], dashboards.GLANCE)))['AI tokens'] == '97.1K'
    # an unedited copy saved 2026-11-06 (the AI tiles last, the calls bar two wide, the source renamed) becomes today's layout, once
    plain = [c for c in dashboards.GLANCE['components'] if c['source'] != 'ai']
    old = {**dashboards.GLANCE, 'sources': [{**x, 'key': 'ai_used'} if x['key'] == 'ai' else x for x in dashboards.GLANCE['sources']],
           'components': [*plain, *({**c, 'source': 'ai_used', **({'w': 2} if c['kind'] == 'bar' else {})} for c in dashboards.AI_TILES)]}
    s, _ = _usage_store(); got = _glance_row(s, old)
    assert dashboards.migrate_ai_tiles_up(s) == 1
    assert got()['components'] == [{**c, 'source': 'ai_used'} if c['source'] == 'ai' else c for c in dashboards.GLANCE['components']]
    assert dashboards.validate(got(), s)[0]
    # ...and once only: the owner who puts them back at the end keeps them there
    _glance_row(s, old)
    assert dashboards.migrate_ai_tiles_up(s) == 0 and got()['components'] == old['components']
    # an edited copy keeps its own tiles and order: the total after its first three numbers, the AI tiles after the rest of them
    t = {c['title']: c for c in plain}
    order = ['Came in', 'New tasks', 'Open now', 'Median reply time', 'Closed this week', 'Agent time per session', 'How far it got',
             'What came in, by channel', 'Agent sessions, and how they ended', 'Open work by kind', 'Who writes most', 'Waiting longest on you']
    mine = {**old, 'components': [*(t[x] for x in order[:6]), {'kind': 'stat', 'title': 'Mine', 'source': 'mail', 'agg': 'count'},
                                  *(t[x] for x in order[6:]), *old['components'][-5:]]}
    assert dashboards.validate(mine, s)[0]
    titles = [c['title'] for c in dashboards.ai_tiles_up(mine)['components']]
    assert titles[:4] == ['Came in', 'New tasks', 'Open now', 'AI tokens']
    assert titles[4:8] == ['Median reply time', 'Closed this week', 'Agent time per session', 'Mine']
    assert titles[8:13] == [c['title'] for c in dashboards.AI_TILES] and titles[13] == 'How far it got'
    # ...and a copy whose AI tiles the owner already moved, or today's own, is left as it is
    moved = {**old, 'components': [*old['components'][-5:], *plain]}
    assert dashboards.ai_tiles_up(moved) is moved and dashboards.ai_tiles_up(dashboards.GLANCE) is dashboards.GLANCE


def test_retention_keeps_what_was_used_for_ninety_days_and_the_reason_for_thirty():
    from datetime import datetime, timedelta
    s = MemoryStore(); now = datetime(2026, 11, 6, 12)
    for days in (10, 45, 100):
        rid = _route(s); s.set_brain_route(rid, At=(now - timedelta(days=days)).isoformat(sep=' ', timespec='seconds'))
    assert brainroute.trim(s, now) == 1
    left = sorted(s.brain_routes(None, limit=10), key=lambda r: r['At'])
    assert [bool(r['Why']) for r in left] == [False, True]


def test_every_step_of_an_agents_loop_is_counted_and_todays_totals_say_by_job():
    """The owner, 2026-11-10: "they spent 25 dollars in one day?" - an AI card agent's steps (brain.chat) went past the meter: a turn of
    many calls read as one row with no tokens. Each step is a call on the route row now, and today() totals the day by job."""
    from taskuary import apiagent
    s = MemoryStore(); rid = brainroute.Lazy(s, brainroute.Route('general', 'standard', 'connector:1', '', 'main', [], 'fixed', 'test'))
    body = {'model': 'flash', 'choices': [{'message': {'content': 'ok'}}], 'usage': {'prompt_tokens': 9000, 'completion_tokens': 50,
                                                                                     'prompt_tokens_details': {'cached_tokens': 8000}}}
    brain = llm._Scrubbed(aiusage.metered(s, rid, llm.make_llm('hipaa_ai', {'base_url': 'https://ai.northwind.example/v1'}, 'k')))
    assert apiagent.can(brain)
    with mock.patch('taskuary.llm.requests.post', return_value=_post(body)):
        for _ in range(3): brain.chat([{'role': 'user', 'content': 'go'}], [])
    r = _row(s, rid())
    assert (r['Calls'], r['TokensIn'], r['Cached'], r['TokensOut']) == (3, 27000, 24000, 150)
    assert aiusage.today(s, str(r['At'])[:10])['general'] == {'calls': 3, 'in': 27000, 'cached': 24000, 'out': 150}
    assert not apiagent.can(aiusage.metered(s, rid, lambda system, user, **kw: 'ok')), 'a brain with no loop gains none from the meter'


def test_an_anthropic_card_marks_the_stable_part_of_each_call_for_the_prompt_cache():
    "The guide, the tools and the conversation so far are the same bytes call after call: marked, the provider bills them as cache reads."
    msg = NS(stop_reason='end_turn', model='claude-sonnet-4-5', content=[NS(type='text', text='ok')], usage=None)
    cli = mock.Mock(); cli.messages.create.return_value = msg
    tools = [{'type': 'function', 'function': {'name': n, 'description': 'd', 'parameters': {'type': 'object', 'properties': {}}}} for n in 'ab']
    with mock.patch('anthropic.Anthropic', return_value=cli):
        brain = llm.make_llm('anthropic', {'model': 'claude-sonnet-4-5'}, 'sk-ant-test')
        brain.chat([{'role': 'system', 'content': 'guide ' * 1000}, {'role': 'user', 'content': 'go'}], tools)
        brain('guide ' * 1000, 'one mail'); brain('short', 'one mail')
    (_, step), (_, one), (_, small) = cli.messages.create.call_args_list
    assert step['system'][0]['cache_control'] == llm.EPHEMERAL and step['tools'][-1]['cache_control'] == llm.EPHEMERAL
    assert 'cache_control' not in step['tools'][0] and step['messages'][-1]['content'][-1]['cache_control'] == llm.EPHEMERAL
    assert one['system'][0]['text'] == 'guide ' * 1000 and small['system'] == 'short'


def _triage_system(learned='Alex cares about the rota.', who='erin@northwind.example'):
    from taskuary.triage import classify_intent
    seen = []
    def brain(system, user, **kw): seen.append(system); return '{"intent": "fyi", "why": "x"}'
    classify_intent({'from_email': who, 'subject': 's', 'body': 'b'}, llm=brain, notes=[f'{who}: rota changes are tasks'], learned=learned,
                    playbooks='- rota: when a rota changes', workflows='- invoices: when an invoice arrives', soul='Alex runs operations.')
    return seen[0]


def test_triage_is_the_cached_context_then_the_new_mail_and_a_learned_line_rebills_only_its_own_block():
    """The owner, 2026-11-10: "keep the triage context cached and then just the new info should query it". The guide and documents, the
    menus and the memory are three cached blocks, least often changing first; what is this mail's own follows them."""
    a, b, c = _triage_system(), _triage_system(who='gail@northwind.example'), _triage_system(learned='Alex cares about the rota. And invoices.')
    assert isinstance(a, llm.Stable) and len(a.blocks) == 3 and a.ttl == '1h'
    assert a.blocks == b.blocks and a.rest != b.rest, 'another mail: the same cached blocks, only its own part differs'
    assert c.blocks[:2] == a.blocks[:2] and c.blocks[2] != a.blocks[2], 'a learned line: only the memory block changes'
    assert 'rota changes are tasks' in a.rest and 'rota changes are tasks' not in ''.join(a.blocks)
    assert sum(map(len, a.blocks)) > 20 * len(a.rest), 'nearly all of it is cached'


def test_each_card_type_carries_the_cache_the_way_its_provider_takes_it_and_a_refused_marker_is_dropped_once():
    system = _triage_system()
    msg = NS(stop_reason='end_turn', model='claude-sonnet-4-5', content=[NS(type='text', text='{}')], usage=None)
    cli = mock.Mock(); cli.messages.create.return_value = msg
    with mock.patch('anthropic.Anthropic', return_value=cli): llm.make_llm('anthropic', {'model': 'claude-sonnet-4-5'}, 'k')(system, 'the mail')
    sent = cli.messages.create.call_args.kwargs['system']
    assert [x.get('cache_control') for x in sent[:3]] == [{'type': 'ephemeral', 'ttl': '1h'}] * 3 and 'cache_control' not in sent[-1]
    assert ''.join(x['text'] for x in sent) == system
    ok = {'choices': [{'message': {'content': '{}'}}], 'usage': {'prompt_tokens': 9, 'completion_tokens': 1}}
    gw = {'base_url': 'https://ai.northwind.example/v1'}
    with mock.patch('taskuary.llm.requests.post', return_value=_post(ok)) as post:
        llm.make_llm('hipaa_ai', gw, 'k')(system, 'the mail')                      # implicit caching: the order alone, no marker
        assert isinstance(post.call_args.kwargs['json']['messages'][0]['content'], str)
        llm.make_llm('hipaa_ai', {**gw, 'cache': 'explicit'}, 'k')(system, 'the mail')
        first = post.call_args.kwargs['json']['messages'][0]['content']
        assert first[0]['cache_control'] == {'type': 'ephemeral', 'ttl': '3600s'}
    refused = _post({'error': {'message': 'cache_control is not supported for this model'}}, 400)
    llm._NO_CACHE.clear()
    answers, kinds = iter([refused, _post(ok), _post(ok)]), []
    def post(url, json=None, **kw): kinds.append(type(json['messages'][0]['content']).__name__); return next(answers)
    with mock.patch('taskuary.llm.requests.post', side_effect=post):
        brain = llm.make_llm('hipaa_ai', {**gw, 'model': 'flash-x', 'cache': 'explicit'}, 'k')
        assert brain(system, 'the mail') == '{}' and brain(system, 'the next mail') == '{}'
    assert kinds == ['list', 'str', 'str'], 'asked again without the marker, and never marked again on this card'


def test_the_settings_page_reads_what_the_ai_did_today_and_the_ceiling():
    from fastapi.testclient import TestClient
    from taskuary import server
    s = MemoryStore(); rid = brainroute.Lazy(s, brainroute.Route('triage', 'light', 'connector:1', '', 'light', [], 'fixed', 'test'))
    aiusage.record(s, rid(), 900, {'in': 16000, 'cached': 15000, 'out': 200})
    with mock.patch.object(server, 'store', s):
        got = TestClient(server.app).get('/api/ai/today').json()
    assert got['jobs']['triage'] == {'calls': 1, 'in': 16000, 'cached': 15000, 'out': 200}
    assert (got['calls'], got['ceiling'], got['held']) == (1, brainroute.AUTO_CAP, '')

