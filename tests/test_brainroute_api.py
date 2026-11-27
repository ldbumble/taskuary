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
        assert p['mode'] == 'auto' and p['cap'] == '' and p['used_today'] == 0
        assert 'Hard redrafts, general work and coding -> the strong model' in [r['sentence'] for r in p['rules']]
        # what each level runs on, per brain, in the words Settings shows: an API card has no quick model of its own
        assert {k: p['levels'][0][k] for k in ('brain', 'quick', 'normal', 'hard')} == \
            {'brain': 'Anthropic API', 'quick': 'claude-sonnet-5, low effort', 'normal': 'claude-sonnet-5', 'hard': 'claude-opus-5'}
        rules = [{**r, 'on': r['id'] != 'unsure'} for r in p['rules']]
        p = c.post('/api/ai/route_rules', json={'mode': 'fixed', 'rules': rules, 'cap': '5'}).json()
        assert (p['mode'], p['cap']) == ('fixed', 5) and not next(r for r in p['rules'] if r['id'] == 'unsure')['on']
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
    s.judge_task(tid, {'difficulty': 'quick'}, 'owner')
    with mock.patch.object(server, 'store', s):
        j = c.post(f'/api/tasks/{tid}/judged', json={'difficulty': 'hard'}).json()['judged']
        assert (j['difficulty'], j['by']) == ('hard', 'owner')
        assert c.post(f'/api/tasks/{tid}/judged', json={'difficulty': 'brutal'}).status_code == 422
        assert c.post(f'/api/tasks/{tid}/judged', json={}).status_code == 422
        assert c.get(f'/api/tasks/{tid}').json()['judged']['difficulty'] == 'hard'
    facts = routingmemory.facts_for(s, {'from_email': 'erin@northwind.example', 'subject': 'Board pack for Thursday', 'channel': 'email'})
    assert {'field': 'difficulty', 'value': 'hard'}.items() <= next(f for f in facts if f['field'] == 'difficulty').items()
