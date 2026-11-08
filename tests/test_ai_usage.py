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
