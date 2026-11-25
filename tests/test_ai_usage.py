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
    assert got['total'] == {'calls': 3, 'tokens': 97120, 'tokens_in': 93000, 'tokens_out': 4120, 'cached': None, 'seconds': 63.0, 'cost': None}
    top = got['rows'][0]
    assert (top['what'], top['tier'], top['model'], top['tokens'], top['seconds'], top['run']) == ('general work', 'normal', 'claude-sonnet-4-5', 94000, 60.0, True)


def test_an_agent_turn_that_rereads_its_context_from_the_cache_counts_the_cache_apart():
    # a Codex agent's turns of 3 minutes each: every model step re-sends the whole conversation, the provider reads ~96% of it back from
    # its cache - "1.3M tokens" for a turn whose new words were ~40K read as millions spent in ten minutes (2026-11-18)
    s = MemoryStore(); tid = s.create_task({'Title': 'Quarter close', 'Status': 'open', 'Kind': 'general'}, 'owner')
    for i, c, o in ((988243, 947584, 5664), (941470, 921472, 5050), (1340118, 1322624, 5901)):
        rid = brainroute.log(s, brainroute.Route('general', 'standard', 'cli:codex', '', 'light', [], 'fixed', 'x'), tid)
        s.add_brain_usage(rid, 200000, {'in': i, 'cached': c, 'out': o, 'model': 'gpt-5-codex'})
    got = aiusage.for_task(s, tid)
    assert [r['tokens'] for r in got['rows']] == [1340118 - 1322624 + 5901, 941470 - 921472 + 5050, 988243 - 947584 + 5664]
    assert [r['cached'] for r in got['rows']] == [1322624, 921472, 947584]
    assert got['total']['tokens'] == 94766 and got['total']['cached'] == 3191680 and got['total']['tokens_in'] == 3269831


def test_the_dataset_keeps_a_run_whole_and_rolls_the_one_calls_up_per_day():
    s, tid = _usage_store()
    rows = dashboards.DATASETS['ai_usage'][0](s, 90)
    run = next(r for r in rows if r['kind'] == 'agent run')
    one = next(r for r in rows if r['kind'] == 'one call')
    assert (run['task_id'], run['tokens'], run['minutes']) == (tid, 94000, 1.0)
    assert (one['calls'], one['tokens'], one['tier'], one['task_id']) == (2, 3120, 'quick', None)


def test_the_built_in_dashboard_draws_what_the_ai_used_with_its_tokens_in_the_top_row():
    # the owner, 2026-11-07: "I don't see the token count?" - and 2026-11-24, "spend is cost, not tokens": the dollars lead, the tokens under them
    s, _ = _usage_store()
    assert dashboards.validate(dashboards.GLANCE, s) == (True, '')
    data = dashboards.collect(s, dashboards.GLANCE)
    assert not dashboards.problems(dashboards.GLANCE, data)
    top = dashboards.GLANCE['components'][:4]
    assert top[0]['title'] == 'AI spend' and all(c['kind'] == 'stat' for c in top)
    # a Claude Code run is on her plan: no dollars, its tokens said as hers on the plan
    said = dashboards._panel(dashboards.GLANCE, data, top[0], 7)
    assert said == ['AI spend: - (97.1K tokens, 97.1K tokens on your plan)']


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


def _common(a: str, b: str) -> int: return next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))


def _triage_wire(system=None, **kw):
    "What the OpenAI wire carries for one triage call, in its order: the schema (the head of the prompt there), the system, the mail."
    from taskuary.triage import classify_intent
    seen = []
    def brain(system, user, **k): seen.append((system, user, k.get('want'))); return '{"intent": "fyi", "why": "x", "title": "t"}'
    brain.takes_want = True
    classify_intent(llm=brain, system=system, soul='Alex runs operations.', learned='Alex cares about the rota.', **kw)
    sy, us, want = seen[0]
    return json.dumps(want), sy, us


def test_a_reply_on_a_thread_and_a_chat_line_share_the_plain_mails_cached_prefix():
    """The OpenAI wire reads the answer's schema first, then the system: a schema that grew same_as / new_job / relationship on a thread's
    reply made the whole cached guide a new prompt for it and for the mail after (the owner's week: 29% of triage read from the cache)."""
    plain = _triage_wire(msg={'from_email': 'erin@northwind.example', 'subject': 'Payworth invoice', 'body': 'Can you approve it by Friday?'})
    task = {'tid': 7, 'ref': 'TQ-0007', 'title': 'Month-end close is short'}
    reply = _triage_wire(msg={'from_email': 'marcus@northwind.example', 'subject': 'Re: Month-end close', 'body': 'Found part of it.'},
                         thread={'thread_task': {**task, 'watching': True}, 'open_work': [task], 'exchange': ['[#3] Marcus: it is short']})
    chat = _triage_wire(msg={'from_name': 'Ruth Bennett', 'subject': '', 'body': 'also the export failed at 2am'},
                        candidates=[{'id': 4, 'who': 'Ruth Bennett', 'when': '09:00', 'text': 'did the import finish?', 'task_id': 7}],
                        thread={'room_tasks': [task], 'filed_notices': [{'mid': 9, 'subject': 'Import report'}]})
    wires = ['\n'.join(w) for w in (plain, reply, chat, plain)]
    assert plain[0] == reply[0] == chat[0], 'one schema for every mail'
    for a, b in zip(wires, wires[1:]): assert _common(a, b) >= 0.8 * max(len(a), len(b)), 'the next mail reads the guide from the cache'
    # ...and a guide that does not explain a key the reply carries is told it in the reply's own part, never in the cached blocks
    doc = 'Judge the mail. ' * 400 + 'Answer JSON with "intent", "why" and "title".'
    a = _triage_wire(system=doc, msg={'from_email': 'erin@northwind.example', 'subject': 's', 'body': 'b'})[1]
    b = _triage_wire(system=doc, msg={'from_email': 'marcus@northwind.example', 'subject': 's', 'body': 'b'}, thread={'exchange': ['[#3] x']})[1]
    assert a.blocks == b.blocks and 'THE PAYLOAD ALSO CARRIES' in b.rest


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


# ── who asked, and about which message (2026-11-11) ───────────────────────────────
# One triage brain is built for a poll and judges every mail in it: its one row said "2 calls" and one sum, for no message and for
# whatever the brain was built for. A row now carries the function that asked and the message it asked about.
def _poll_brain(s, job='triage', answer=None):
    said = json.dumps(answer or {'intent': 'fyi', 'why': 'a notice', 'title': 'A notice', 'summary': 'A notice.', 'sender_class': 'person',
                                 'asks_owner': False, 'difficulty': 'quick', 'sure': True})
    def brain(system, user, **kw):
        aiusage.note('m-1', 1000, 400, 50); return said
    return aiusage.metered(s, brainroute.Lazy(s, brainroute.Route(job, 'light', 'connector:1', '', 'light', [], 'fixed', 'test')), brain)


def _mail(i, **kw):
    return {'external_id': f'u{i}', 'channel': 'email', 'from_email': 'erin@northwind.example', 'from_name': 'Erin Blake',
            'subject': f'Ledger note {i}', 'body': f'The ledger closed for week {i}.', **kw}


def test_two_mails_judged_by_one_brain_are_two_rows_each_with_its_message_and_its_caller():
    from taskuary import ingest
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled'): s.set_setting(k, '0', 't')
    brain = _poll_brain(s)
    mids = [ingest.ingest_message(s, _mail(i), llm=brain)['message_id'] for i in (1, 2)]
    rows = sorted(s.brain_routes(None, limit=50), key=lambda r: r['Id'])
    assert [(r['Caller'], r['MessageId'], r['Calls'], r['TokensIn']) for r in rows] == [('triage.classify', m, 1, 1000) for m in mids], rows
    assert len(set(mids)) == 2


def test_a_report_run_triaged_on_the_reports_brain_is_triages_cost():
    from taskuary import ingest
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled'): s.set_setting(k, '0', 't')
    out = ingest.ingest_message(s, _mail(3, watch_for='Anything over budget.'), llm=_poll_brain(s, 'report'))
    r, = s.brain_routes(None, limit=50)
    assert (r['Job'], r['Caller'], r['MessageId']) == ('report', 'triage.report', out['message_id'])
    assert aiusage.by_caller(s) == {'report': {'triage.report': {'calls': 1, 'in': 1000, 'cached': 400, 'out': 50}}}


def test_a_call_nobody_named_is_blank_and_never_put_on_another_callers_row():
    s = MemoryStore(); brain = _poll_brain(s)
    brain('sys', 'one'); brain('sys', 'two')                                     # nobody named these: one row, as before
    with aiusage.asking('triage.title'): brain('sys', 'three')
    brain('sys', 'four')                                                         # ...and after a named one, still the unnamed row
    rows = {r['Caller']: r for r in s.brain_routes(None, limit=50)}
    assert {k: r['Calls'] for k, r in rows.items()} == {None: 3, 'triage.title': 1}
    assert rows[None]['MessageId'] is None and rows['triage.title']['MessageId'] is None
    assert aiusage.by_caller(s)['triage'] == {'': {'calls': 3, 'in': 3000, 'cached': 1200, 'out': 150},
                                              'triage.title': {'calls': 1, 'in': 1000, 'cached': 400, 'out': 50}}
    assert aiusage.today(s)['triage']['calls'] == 4                              # the job's own total is the sum of its callers


def test_a_mark_made_after_the_asker_left_lands_on_its_row_and_opens_no_new_one():
    s = MemoryStore()
    rid = brainroute.Lazy(s, brainroute.Route('triage', 'light', 'connector:1', '', 'light', [], 'fixed', 'test'))
    with aiusage.asking('triage.classify', 41) as a: named = rid()
    brainroute.outcome(s, rid, 'fallback:cli:claude')
    r, = s.brain_routes(None, limit=50)
    assert (r['Id'], r['Caller'], r['MessageId'], r['Outcome']) == (named, 'triage.classify', 41, 'fallback:cli:claude') and a.rids == [named]
    never = brainroute.Lazy(s, brainroute.Route('draft', 'light', 'connector:1', '', 'light', [], 'fixed', 'test'))
    brainroute.outcome(s, never, 'refused:no AI')                                # a build that ends refused still writes its one row
    assert [x['Outcome'] for x in s.brain_routes(None, limit=50) if x['Job'] == 'draft'] == ['refused:no AI'] and never() == never.last()


def test_the_inner_asker_names_the_call_and_a_named_function_names_its_own():
    s = MemoryStore(); brain = _poll_brain(s)
    @aiusage.named('advisor.idea')
    def judge(): return brain('sys', 'is this worth raising?')
    with aiusage.asking('reports.judge'): judge(); brain('sys', 'what came back')
    assert sorted(r['Caller'] for r in s.brain_routes(None, limit=50)) == ['advisor.idea', 'reports.judge']
    assert aiusage.asked() is None and {'advisor.idea', 'reports.judge', 'triage.classify'} <= set(aiusage.CALLERS)


def test_every_name_a_call_site_gives_is_on_the_one_list():
    import re
    from pathlib import Path
    src = {p.name: p.read_text(encoding='utf-8') for p in (Path(aiusage.__file__).parent).glob('*.py')}
    used = {m for t in src.values() for m in re.findall(r"aiusage\.(?:asking|named)\('([^']+)'", t)}
    used |= set(re.findall(r"'(triage\.[a-z]+)'", src['ingest.py'].split('def judge(')[1].split('def _classify(')[0]))   # judge's three, by the arrival
    assert used == set(aiusage.CALLERS), used ^ set(aiusage.CALLERS)


def test_a_row_written_before_the_column_still_reads(tmp_path):
    from taskuary.store import SQLiteStore
    p = str(tmp_path / 'old.db')
    s = SQLiteStore(p); rid = _route(s); aiusage.record(s, rid, 300, {'in': 700, 'out': 20})
    s.cx.execute('ALTER TABLE brainroute DROP COLUMN Caller'); s.cx.commit(); s.close()      # the table as it was before 2026-11-11
    s = SQLiteStore(p)
    old = _row(s, rid)
    assert old['Caller'] is None and old['MessageId'] is None and old['TokensIn'] == 700
    assert aiusage.by_caller(s, str(old['At'])[:10]) == {'triage': {'': {'calls': 1, 'in': 700, 'cached': 0, 'out': 20}}}
    assert aiusage.row(s, old)['tokens'] == 720
    with aiusage.asking('triage.classify', 7): new = _route(s)
    assert (_row(s, new)['Caller'], _row(s, new)['MessageId']) == ('triage.classify', 7)



# ── which model the call reaches decides the cache marker, and a model that did not answer is said (the HIPAA AI card, 2026-11-15) ──
GW = {'base_url': 'https://ai.northwind.example/v1'}
TOOLS = [{'type': 'function', 'function': {'name': 'file_read', 'description': 'd', 'parameters': {'type': 'object', 'properties': {}}}}]
def _said(model, headers=None, text='ok'):
    "A gateway's 200 as LiteLLM sends it: the model that answered named in the body, its fallbacks counted in a header."
    r = _post({'model': model, 'choices': [{'message': {'role': 'assistant', 'content': text}}], 'usage': {'prompt_tokens': 9, 'completion_tokens': 1}})
    r.headers = {'x-litellm-attempted-fallbacks': '0', **(headers or {})}; return r
def _steps(): return [{'role': 'system', 'content': 'guide ' * 1000}, {'role': 'user', 'content': 'fill the invoice'},
                      {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'c1', 'type': 'function', 'function': {'name': 'file_read', 'arguments': '{}'}}]},
                      {'role': 'tool', 'tool_call_id': 'c1', 'content': 'Date | Units | Amount'}]
def _marks(body) -> int: return json.dumps(body).count('cache_control')


@pytest.mark.parametrize('t,model', [('hipaa_ai', 'claude-sonnet-5-5'), ('hipaa_ai', 'claude-opus-5-5'), ('openrouter', 'anthropic/claude-sonnet-5-5'),
                                     ('openai', 'gpt-5')])
def test_the_model_the_call_reaches_decides_the_marker_not_the_card(t, model):
    "Claude caches only what is marked, behind any gateway; Gemini and OpenAI cache a repeated prefix themselves, and a marker there turns that off."
    llm._NO_CACHE.clear(); llm._ANSWERED.clear()
    with mock.patch.object(llm, 'post_retrying', return_value=_said(model)) as post:
        llm.make_llm(t, {**GW, 'model': model}, 'k').chat(_steps(), TOOLS)
        step = post.call_args.args[2]
        llm.make_llm(t, {**GW, 'model': model}, 'k')(llm.stable('guide ' * 1000, rest='this mail', ttl='1h'), 'the mail')
        one = post.call_args.args[2]
    if 'claude' not in model:
        assert _marks(step) == _marks(one) == 0 and isinstance(step['messages'][0]['content'], str); return
    assert step['messages'][0]['content'][0]['cache_control'] == llm.EPHEMERAL, 'the system: tools and guide read from the cache'
    assert step['messages'][-1]['cache_control'] == llm.EPHEMERAL, 'the conversation so far: each step reads the one before from the cache'
    assert 'cache_control' not in step['messages'][2] and _marks(step) <= 4, "within Claude's four breakpoints"
    assert one['messages'][0]['content'][0]['cache_control'] == {'type': 'ephemeral', 'ttl': '1h'}, "Claude's TTL in its own words, never Gemini's '3600s'"


@pytest.mark.parametrize('model', ['gemini-3.8-flash', 'gemini-2.5-pro', 'hipaa-ai'])
def test_gemini_and_the_alias_on_the_hipaa_card_are_left_to_cache_by_themselves(model):
    llm._NO_CACHE.clear(); llm._ANSWERED.clear()
    with mock.patch.object(llm, 'post_retrying', return_value=_said('gemini-3.8-flash')) as post:
        llm.make_llm('hipaa_ai', {**GW, 'model': model}, 'k').chat(_steps(), TOOLS)
    assert _marks(post.call_args.args[2]) == 0


def test_a_claude_user_line_is_marked_in_its_content_and_a_refused_marker_comes_off_everywhere_once():
    llm._NO_CACHE.clear(); llm._ANSWERED.clear()
    msgs = _steps()[:2]
    refused, sent = _post({'error': {'message': 'cache_control is not permitted here'}}, 400), []
    answers = iter([refused, _said('claude-sonnet-5-5'), _said('claude-sonnet-5-5')])
    def post(url, headers, body, timeout): sent.append(json.loads(json.dumps(body))); return next(answers)
    with mock.patch.object(llm, 'post_retrying', side_effect=post):
        brain = llm.make_llm('hipaa_ai', {**GW, 'model': 'claude-sonnet-5-5'}, 'k')
        brain.chat(msgs, TOOLS); brain.chat(msgs, TOOLS)
    assert sent[0]['messages'][-1]['content'][-1]['cache_control'] == llm.EPHEMERAL
    assert [_marks(b) for b in sent] == [2, 0, 0], 'asked again with no marker anywhere, and never marked again on this card'


def test_a_claude_name_the_gateway_answered_with_gemini_is_not_marked_from_the_next_call():
    llm._NO_CACHE.clear(); llm._ANSWERED.clear()
    with mock.patch.object(llm, 'post_retrying', return_value=_said('gemini-2.5-pro', {'x-litellm-attempted-fallbacks': '1'})) as post:
        brain = llm.make_llm('hipaa_ai', {**GW, 'model': 'claude-sonnet-5-5'}, 'k')
        brain.chat(_steps(), TOOLS); first = post.call_args.args[2]
        brain.chat(_steps(), TOOLS); second = post.call_args.args[2]
    assert _marks(first) == 2 and _marks(second) == 0, 'a cachedContent on Gemini would turn its own cache off'


def _card(s, model='claude-sonnet-5-5'):
    got = s.save_connector({'Type': 'hipaa_ai', 'Name': 'HIPAA AI', 'Active': 1, 'ConfigJson': json.dumps({**GW, 'model': model})}, 't')
    return got if isinstance(got, int) else got['ConnectorId']


def test_a_fallback_is_said_on_the_card_the_bell_and_the_turn_once_per_episode_until_the_model_asked_for_answers():
    """The owner, 2026-11-15: "it should tell the user as well that the model did not work because of quota so we know what it's doing" -
    every Claude call on the gateway was answered by Gemini 2.5 Pro, and nothing said so."""
    from fastapi.testclient import TestClient
    from taskuary import problems, server
    llm._NO_CACHE.clear(); llm._ANSWERED.clear()
    s = MemoryStore(); cid = _card(s); pick = f'connector:{cid}'
    rid = _route(s, job='general', tid=None)
    fell = _said('gemini-2.5-pro', {'x-litellm-attempted-fallbacks': '1'})
    with mock.patch.object(llm, 'post_retrying', return_value=fell):
        brain = aiusage.Metered(s, rid, llm._Cooling(s, pick, llm.make_llm('hipaa_ai', {**GW, 'model': 'claude-sonnet-5-5'}, 'k')))
        brain('sys', 'one'); brain.chat(_steps(), TOOLS)
    line = 'Asked for Claude Sonnet 5.5 - answered by Gemini 2.5 Pro: the gateway fell back (Claude not available - e.g. its quota)'
    assert llm.fallback_line('claude-sonnet-5-5', 'gemini-2.5-pro') == line
    assert aiusage.row(s, _row(s, rid))['fell_back'] == line, "the task's AI used line for that turn"
    with mock.patch.object(server, 'store', s):
        card = next(c for c in TestClient(server.app).get('/api/connectors').json()['data'] if c['ConnectorId'] == cid)
    assert card['FellBack'] == line
    bell = [p for p in problems.collect(s) if p['key'] == f'fell_back:{pick}']
    assert len(bell) == 1 and bell[0]['title'] == f'HIPAA AI: {line}'
    with mock.patch.object(s, 'set_setting', wraps=s.set_setting) as wrote, mock.patch.object(llm, 'post_retrying', return_value=fell):
        brain('sys', 'two')
    assert not [c for c in wrote.call_args_list if c.args[0] == 'ai_route_fell_back'], 'the same episode is written once'
    with mock.patch.object(llm, 'post_retrying', return_value=_said('claude-sonnet-5-5')): brain('sys', 'three')
    assert not [p for p in problems.collect(s) if p['key'].startswith('fell_back:')]
    assert any('Claude Sonnet 5.5 answers again' in n['title'] for n in problems.news(s)), 'its end is said, as every episode that rang'


def test_an_alias_the_gateway_resolves_is_not_a_fallback_but_its_own_count_is():
    assert not llm.fell_back('hipaa-ai', 'gemini-3.8-flash', {'x-litellm-attempted-fallbacks': '0'})
    assert not llm.fell_back('hipaa-ai', 'gemini-3.8-flash'), 'an alias names no family to differ from'
    assert llm.fell_back('hipaa-ai', 'gemini-2.5-pro', {'x-litellm-attempted-fallbacks': '2'})
    assert llm.fell_back('anthropic/claude-sonnet-5-5', 'google/gemini-2.5-pro'), 'a gateway with no count: the families differ'
    assert not llm.fell_back('claude-sonnet-5-5', 'claude-sonnet-5-5@20261001')


def test_a_quota_refusal_is_the_providers_quota_in_plain_words_and_the_card_rests():
    llm._NO_CACHE.clear(); llm._ANSWERED.clear()
    s = MemoryStore(); cid = _card(s); pick = f'connector:{cid}'
    quota = _post({'error': {'message': 'Quota exceeded for online_prediction_requests_per_base_model with base model: '
                                        'anthropic-claude-sonnet. Please submit a quota increase request.', 'code': 429}}, 429)
    brain = llm._Cooling(s, pick, llm.make_llm('hipaa_ai', {**GW, 'model': 'claude-sonnet-5-5'}, 'k'))
    for ask in (lambda: brain('sys', 'one'), lambda: brain.chat(_steps(), TOOLS)):
        from taskuary import brainroute
        brainroute.unspend(s, pick)
        with mock.patch.object(llm, 'post_retrying', return_value=quota), pytest.raises(llm.QuotaSpent) as e: ask()
        assert str(e.value) == ('HIPAA AI: Claude Sonnet 5.5 is over its quota at the provider - raise the quota there, '     # his words, no code
                                'or pick another model on its card')
    assert brainroute.spent(s, pick) == str(e.value), 'it rests: the next call says the same line at once, and a backup takes it'
    with mock.patch.object(llm, 'post_retrying') as post, pytest.raises(llm.BudgetSpent): brain('sys', 'again')
    post.assert_not_called()


# ── what the AI spent, per day and for whom (the owner, 2026-11-24) ─────────────────────────────────────────────────────────────
def _spend_store():
    """A week of invented AI use, in dollars: triage every day but one and the Advisor and the Assistant on two, said by what the gateway
    reported; agent runs on two tasks (one worked twice, the other Claude Code on a plan); a draft at the model's list price; a report's own
    triage; a memory pass on a model with no price; and one call eight days ago, outside the week. Two tasks done, one dropped."""
    from datetime import datetime, timedelta
    s = MemoryStore()
    api = f"connector:{s.get_connector_by_type('anthropic')['ConnectorId']}"
    day = lambda n: (datetime.now() - timedelta(days=n)).strftime('%Y-%m-%d 10:00:00')
    t = [s.create_task({'Title': f'Ask {i}', 'Status': 'open', 'Kind': 'general'}, 'owner') for i in range(3)]
    rows = [(n, 'triage', 'triage.classify', None, 1000, 0, api, 0.01, 'claude-haiku-4-5') for n in (0, 1, 2, 4, 5, 6)] + [
        (1, 'advisor', 'advisor.run', None, 3000, 0, api, 0.30, 'claude-sonnet-4-5'), (3, 'advisor', 'advisor.lookout', None, 2000, 0, api, 0.20, 'claude-sonnet-4-5'),
        (0, 'assistant', None, None, 4000, 0, api, 0.40, 'claude-sonnet-4-5'), (2, 'assistant', None, None, 6000, 0, api, 0.60, 'claude-sonnet-4-5'),
        (1, 'general', None, t[0], 50000, 1, api, 2.0, 'claude-sonnet-4-5'), (4, 'general', None, t[0], 30000, 1, api, 1.0, 'claude-sonnet-4-5'),
        (2, 'coding', None, t[1], 20000, 1, 'cli:claude', None, 'claude-sonnet-4-5'),
        (5, 'draft', 'draft.reply', t[2], 1500, 0, api, None, 'claude-sonnet-4-5'), (3, 'triage', 'reports.judge', None, 700, 0, api, 0.007, 'claude-haiku-4-5'),
        (6, 'memory', 'memory.learn', None, 300, 0, api, None, 'a-model-nobody-prices'), (8, 'triage', 'triage.classify', None, 99000, 0, api, 9.0, 'claude-haiku-4-5')]
    for n, job, caller, tid, tok, run, pick, usd, model in rows:
        s.add_brain_route({'At': day(n), 'Job': job, 'Caller': caller, 'TaskId': tid, 'Pick': pick, 'Tier': 'light', 'Rule': 'x', 'Outcome': 'ok',
                           'Ran': model, 'TokensIn': tok, 'TokensOut': 0, 'Ms': 1000, 'Calls': 1, 'Cost': usd, **({'Sid': f'run-{n}-{tid}'} if run else {})})
    for tid, st, n in ((t[0], 'done', 1), (t[1], 'done', 1), (t[2], 'dropped', 3)):
        s._exec('UPDATE task SET Status=?, ClosedAt=? WHERE TaskId=?', (st, day(n), tid))
    return s, t, day


def test_every_call_lands_on_who_it_was_for_by_its_asker_else_its_job():
    assert [aiusage.who(j, c) for j, c in (('triage', 'triage.classify'), ('triage', 'reports.judge'), ('judge', 'sent.judge'), ('advisor', None),
                                           ('general', 'advisor.idea'), ('assistant', ''), ('coding', None), ('draft', 'draft.reply'),
                                           ('memory', 'memory.learn'), (None, None))] == \
        ['Triage', 'Other', 'Triage', 'Advisor', 'Advisor', 'Assistant', 'Tasks', 'Tasks', 'Other', 'Triage']


def test_the_built_in_dashboard_says_the_weeks_spend_per_day_for_whom_per_task_and_what_got_done():
    s, t, day = _spend_store()
    spec = dashboards.GLANCE
    assert dashboards.validate(spec, s) == (True, '')
    data = dashboards.collect(s, spec)
    assert not dashboards.problems(spec, data)
    panel = lambda title: dashboards._panel(spec, data, next(c for c in spec['components'] if c['title'] == title), 7)
    # the week's dollars for each, in the owner's order - the call eight days ago is not in them; the draft at its list price (1,500 x $3/M)
    assert panel('AI spend by who')[1:] == ['Triage: $0.06', 'Advisor: $0.50', 'Tasks: $3.00', 'Assistant: $1', 'Other: $0.01']
    # ...per day, split by who (a day with no call of the Advisor's has no Advisor part)
    days = dict(x.split(': ', 1) for x in panel('AI spend per day')[1:])
    assert len(days) == 7 and days[day(3)[:10]] == 'Advisor $0.20, Other $0.01' and days[day(1)[:10]] == 'Tasks $2, Advisor $0.30, Triage $0.01'
    # the total, and under it its tokens: the plan's said apart, and the one with no price
    assert panel('AI spend') == ['AI spend: $4.57 (123.5K tokens, 20.0K tokens on your plan, 300 tokens with no price)']
    # one task's agent work, on average: $2 + $1 on one task; the other ran on a plan, so it has no dollars to average
    assert panel('Cost per task') == ['Cost per task: $3 (50.0K tokens a task)']
    # ...and what got done: two tasks done, one dropped, per day apart
    assert panel('Tasks completed') == ['Tasks completed: 2']
    assert panel('Tasks closed per day')[1:] == [f'{day(3)[:10]}: dropped 1', f'{day(1)[:10]}: done 2']


def test_a_calls_cost_is_what_the_provider_said_else_its_list_price_else_none_and_a_plan_is_no_cost():
    s = MemoryStore()
    cid = lambda t: f"connector:{s.get_connector_by_type(t)['ConnectorId']}"
    row = lambda **kw: {'Pick': cid('anthropic'), 'Ran': 'claude-sonnet-4-5', 'TokensIn': 1_000_000, 'Cached': 400_000, 'TokensOut': 100_000, **kw}
    # 600K new at $3, 400K read from the cache at $0.30, 100K out at $15 - LiteLLM's list price
    assert aiusage.cost(s, row()) == (pytest.approx(1.8 + 0.12 + 1.5), 'priced')
    assert aiusage.cost(s, row(Cost=0.42)) == (0.42, 'reported'), "what the provider said beats a list price"
    assert aiusage.cost(s, row(Ran='anthropic/claude-sonnet-4-5@high'))[1] == 'priced', "a gateway's prefix and an effort are not the model"
    assert aiusage.cost(s, row(Ran='a-model-nobody-prices')) == (None, 'unknown'), "never a guessed price"
    assert aiusage.cost(s, row(Pick='cli:claude')) == (None, 'plan')
    assert aiusage.cost(s, row(Pick=cid('chatgpt'))) == (None, 'plan')
    assert aiusage.cost(s, row(Pick=cid('ollama'))) == (None, 'local')
    assert aiusage.price_of('claude-haiku-4-5') == [1.0, 5.0, 0.1] and aiusage.price_of('') is None


def test_the_gateways_own_cost_lands_on_the_route():
    # the HIPAA AI card is a LiteLLM gateway: it says what each answer cost in a header, and that is what is kept
    s = MemoryStore(); rid = _route(s)
    body = {'model': 'gemini-4-hydrogen', 'choices': [{'message': {'content': 'ok'}}], 'usage': {'prompt_tokens': 500, 'completion_tokens': 60}}
    r = _post(body); r.headers = {'x-litellm-response-cost': '0.00123'}
    with mock.patch('taskuary.llm.requests.post', return_value=r):
        brain = aiusage.metered(s, rid, llm.make_llm('hipaa_ai', {'base_url': 'https://ai.northwind.example/v1'}, 'key-test'))
        assert brain('s', 'u') == 'ok' and brain('s', 'again') == 'ok'
    assert _row(s, rid)['Cost'] == pytest.approx(0.00246)
    # ...and OpenRouter in the usage itself
    r = _post({**body, 'usage': {**body['usage'], 'cost': 0.5}}); rid = _route(s)
    with mock.patch('taskuary.llm.requests.post', return_value=r):
        assert aiusage.metered(s, rid, llm.make_llm('openrouter', {}, 'k'))('s', 'u') == 'ok'
    assert _row(s, rid)['Cost'] == 0.5


def test_per_averages_each_values_own_number_and_leaves_the_blank_out():
    rows = [{'t': 1, 'v': 10}, {'t': 1, 'v': 30}, {'t': 2, 'v': 20}, {'t': None, 'v': 999}, {'t': '', 'v': 999}]
    assert dashboards.aggregate(rows, 'sum', 'v', 't') == 30 and dashboards.aggregate(rows, 'count', None, 't') == 1.5
    assert dashboards.aggregate([], 'sum', 'v', 't') is None
    assert dashboards.validate({'title': 'x', 'sources': [{'key': 'a', 'type': 'taskuary_data', 'dataset': 'tasks'}],
                                'components': [{'kind': 'stat', 'source': 'a', 'per': 3}]})[0] is False


def test_an_unedited_built_in_becomes_todays_and_an_edited_one_keeps_its_own():
    s, _, _ = _spend_store()
    was = [c for c in dashboards.GLANCE['components'] if c not in dashboards.SPEND_TILES]
    row = next(r for r in s.list_sources(active_only=False) if r['Address'] == dashboards.GLANCE['title'])
    cfg = lambda: dashboards.cfg_of(s.get_source(row['SourceId']))
    s.save_source({'SourceId': row['SourceId'], 'ConfigJson': json.dumps({**dashboards.GLANCE, 'components': was, 'daily_at': '06:30'})}, 'owner')
    with mock.patch.object(dashboards, 'GLANCE_WAS', (dashboards.glance_print(was),)):
        assert dashboards.migrate_glance(s) == 1 and dashboards.migrate_glance(s) == 0
        assert cfg()['components'] == dashboards.GLANCE['components'] and cfg()['daily_at'] == '06:30'
        mine = [*was[:3], {'kind': 'stat', 'title': 'Mine', 'source': 'mail', 'agg': 'count'}]
        s.save_source({'SourceId': row['SourceId'], 'ConfigJson': json.dumps({**dashboards.GLANCE, 'components': mine})}, 'owner')
        assert dashboards.migrate_glance(s) == 0 and cfg()['components'] == mine
