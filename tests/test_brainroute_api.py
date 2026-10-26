"""The router's part of Settings and of the task page (the router, 2026-10-25): the mode line, the rules as sentences with their
switches, the cap line, the recent routes, the owner's correction of a task's difficulty, and "Run again on the strong model" -
which is a press, and the only way an agent that can act ever steps up."""
import json
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import brainroute, routingmemory, server
from taskuary.store import MemoryStore

c = TestClient(server.app)


def _store():
    s = MemoryStore()
    cid = s.get_connector_by_type('anthropic')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-0123456789', 'Active': 1,
                      'ConfigJson': json.dumps({'model': 'claude-sonnet-5', 'strong_model': 'claude-opus-5'})}, 'owner')
    s.a = f'connector:{cid}'; s.set_setting('triage_ai', s.a, 'owner'); s.set_setting('assistant_ai', s.a, 'owner')
    return s


def test_the_panel_reads_and_writes_the_mode_the_rules_and_the_cap():
    s = _store()
    with mock.patch.object(server, 'store', s):
        p = c.get('/api/ai/route_rules').json()
        assert p['mode'] == 'fixed' and p['cap'] == '' and p['used_today'] == 0
        assert 'Hard drafts, general work and coding -> the strong model' in [r['sentence'] for r in p['rules']]
        rules = [{**r, 'on': r['id'] != 'unsure'} for r in p['rules']]
        p = c.post('/api/ai/route_rules', json={'mode': 'auto', 'rules': rules, 'cap': '5'}).json()
        assert (p['mode'], p['cap']) == ('auto', 5) and not next(r for r in p['rules'] if r['id'] == 'unsure')['on']
        assert c.post('/api/ai/route_rules', json={'cap': 'lots'}).status_code == 422
        assert c.post('/api/ai/route_rules', json={'mode': 'sometimes'}).status_code == 422
        bad = c.post('/api/ai/route_rules', json={'rules': [{'id': 'x', 'when': {'subject': ['invoice']}, 'use': {'tier': 'strong'}}]})
        assert bad.status_code == 422 and 'can only match on' in bad.json()['detail']
        assert c.post('/api/ai/route_rules', json={'cap': ''}).json()['cap'] == ''


def test_recent_routes_name_the_task_and_the_brain():
    s = _store(); tid = s.create_task({'Title': 'Board pack', 'Status': 'open'}, 'owner')
    brainroute.log(s, brainroute.choose(s, 'draft', task=tid), tid)
    with mock.patch.object(server, 'store', s): r = c.get('/api/ai/routes').json()['routes'][0]
    assert (r['ref'], r['brain'], r['Job']) == (f'TQ-{tid:04d}', 'Anthropic API', 'draft')


def test_the_owner_corrects_the_difficulty_and_it_teaches_triage():
    s = _store(); tid = s.create_task({'Title': 'Board pack', 'Status': 'open'}, 'owner')
    s.add_message({'TaskId': tid, 'Channel': 'email', 'FromEmail': 'erin@northwind.example', 'Subject': 'Board pack for Thursday',
                   'BodyText': 'Can you pull the board pack together?', 'Status': 'routed'})
    s.judge_task(tid, {'difficulty': 'quick'}, 'triage')
    with mock.patch.object(server, 'store', s):
        j = c.post(f'/api/tasks/{tid}/judged', json={'difficulty': 'hard'}).json()['judged']
        assert (j['difficulty'], j['by']) == ('hard', 'owner')
        assert c.post(f'/api/tasks/{tid}/judged', json={'difficulty': 'brutal'}).status_code == 422
        assert c.post(f'/api/tasks/{tid}/judged', json={}).status_code == 422
        assert c.get(f'/api/tasks/{tid}').json()['judged']['difficulty'] == 'hard'
    facts = routingmemory.facts_for(s, {'from_email': 'erin@northwind.example', 'subject': 'Board pack for Thursday', 'channel': 'email'})
    assert {'field': 'difficulty', 'value': 'hard'}.items() <= next(f for f in facts if f['field'] == 'difficulty').items()


def test_run_again_on_the_strong_model_is_a_press_on_a_brain_that_has_one():
    s = _store(); tid = s.create_task({'Title': 'Research the vendor', 'Status': 'open', 'Kind': 'general'}, 'owner')
    s.judge_task(tid, {'sure': False}, 'triage')                                       # the reader was unsure: the ▾ offers it
    sent, told = [], []
    class Session:
        def send_prompt(self, text, **kw): sent.append(kw); told.append(text)
    with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.start_session', lambda store, tid, actor='owner': Session()), \
         mock.patch('threading.Thread', lambda target, **kw: type('T', (), {'start': lambda self: target()})()):
        d = c.get(f'/api/tasks/{tid}').json()
        assert d['strongAgain'] == {'pick': s.a, 'brain': 'Anthropic API', 'model': 'claude-opus-5'}
        out = c.post(f'/api/tasks/{tid}/strong-again').json()
    assert (out['kind'], out['model']) == ('general', 'claude-opus-5') and sent == [{'pick': s.a, 'model': 'claude-opus-5', 'as_owner': False}]
    # ...and the agent is told what was pressed: a re-run on a stronger model, not a Resume nobody pressed (2026-10-26)
    assert 'Run again on the strong model' in told[0] and 'chose Resume' not in told[0]
    from taskuary import buttons
    assert 'fresh start' not in buttons.hint('strong_again') and 'saved work' in buttons.hint('strong_again'), 'the hover says what it does'
    r = s.brain_routes(tid, limit=1)[0]
    assert (r['Tier'], r['Rule']) == ('strong', 'you chose it') and 'as you pressed' in r['Why']


def test_no_strong_model_anywhere_offers_nothing_and_refuses_with_where_to_set_one():
    s = MemoryStore(); cid = s.get_connector_by_type('openai')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-0123456789', 'Active': 1, 'ConfigJson': json.dumps({'model': 'gpt-5'})}, 'owner')
    s.set_setting('assistant_ai', f'connector:{cid}', 'owner')
    tid = s.create_task({'Title': 'Research the vendor', 'Status': 'open', 'Kind': 'general'}, 'owner')
    with mock.patch.object(server, 'store', s):
        assert c.get(f'/api/tasks/{tid}').json()['strongAgain'] is None
        r = c.post(f'/api/tasks/{tid}/strong-again')
    assert r.status_code == 422 and 'strong model box on its card' in r.json()['detail']


def test_opening_a_task_asks_the_router_only_when_the_strong_rerun_can_be_offered():
    """Opening a task paid ~11 ms for the strong model's brain on every task, 2.7x 0.3.9.34's open (2026-10-26): only an open task whose
    agent failed or whose reader was unsure draws the button, so only that one asks."""
    s = _store()
    plain = s.create_task({'Title': 'Research the vendor', 'Status': 'open', 'Kind': 'general'}, 'owner')
    unsure = s.create_task({'Title': 'Research the supplier', 'Status': 'open', 'Kind': 'general'}, 'owner')
    shut = s.create_task({'Title': 'Research the venue', 'Status': 'done', 'Kind': 'general'}, 'owner')
    for t in (unsure, shut): s.judge_task(t, {'sure': False}, 'triage')
    with mock.patch.object(server, 'store', s), mock.patch.object(brainroute, 'strong_for', wraps=brainroute.strong_for) as asked:
        assert c.get(f'/api/tasks/{plain}').json()['strongAgain'] is None
        assert c.get(f'/api/tasks/{shut}').json()['strongAgain'] is None
        assert not asked.called, 'nothing on these tasks can show the button'
        assert c.get(f'/api/tasks/{unsure}').json()['strongAgain']['model'] == 'claude-opus-5'
        assert asked.call_count == 1


def test_the_strong_rerun_reads_config_toml_once():
    from taskuary import config
    s = _store(); tid = s.create_task({'Title': 'Research the vendor', 'Status': 'open', 'Kind': 'general'}, 'owner')
    with mock.patch.object(server, 'store', s), mock.patch.object(config, '_read', wraps=config._read) as rd:
        server._strong_again_of(s.get_task(tid))
    assert rd.call_count <= 1, f'config.toml parsed {rd.call_count} times for one button'
