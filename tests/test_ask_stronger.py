"""The agent asks a stronger model itself when it is stuck (the owner, 2026-11-06: "don't like cap. if it needs it, it calls it"):
one call on the strong gear of its brain, no daily cap, logged as a route with what it used."""
import json
from unittest import mock

from taskuary import aiusage, askstronger, brainroute
from taskuary.store import MemoryStore


def _post(body, status=200):
    r = mock.Mock(); r.status_code, r.text = status, json.dumps(body); r.json.return_value = body; return r


def test_ask_stronger_runs_once_on_the_strong_gear_with_no_cap_and_is_on_the_fold():
    s = MemoryStore(); cid = s.get_connector_by_type('openai')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-0123456789', 'Active': 1,
                      'ConfigJson': json.dumps({'model': 'gpt-5-mini', 'strong_model': 'gpt-5-pro'})}, 'owner')
    s.set_setting('assistant_ai', f'connector:{cid}', 'owner')
    s.set_setting(brainroute.CAP_KEY, '0', 'owner')                     # the day's cap is spent: the agent's own ask is not under it
    tid = s.create_task({'Title': 'Which contract wins', 'Status': 'open', 'Kind': 'general'}, 'owner')
    sent = []
    def post(url, headers=None, json=None, timeout=None):
        sent.append(json['model'])
        return _post({'model': json['model'], 'choices': [{'message': {'content': 'Contract B.'}}], 'usage': {'prompt_tokens': 700, 'completion_tokens': 90}})
    with mock.patch('taskuary.llm.requests.post', side_effect=post):
        out = askstronger.ask(s, tid, 'Which renewal is cheaper over 3 years?', 'A: $4,860/yr flat. B: $4,200 rising 5%.')
    assert out['ok'] and out['answer'] == 'Contract B.' and sent == ['gpt-5-pro']
    r = s.brain_routes(tid, limit=1)[0]
    assert (r['Rule'], r['Tier'], r['TokensIn'], r['TokensOut']) == ('agent asked', 'strong', 700, 90)
    assert aiusage.for_task(s, tid)['rows'][0]['what'] == 'a question the agent asked a stronger model'


def test_ask_stronger_with_nothing_stronger_says_so_and_the_tool_is_listed():
    from taskuary import agenttools
    s = MemoryStore(); cid = s.get_connector_by_type('mistral')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-0123456789', 'Active': 1, 'ConfigJson': json.dumps({'model': 'mistral-large'})}, 'owner')
    s.set_setting('assistant_ai', f'connector:{cid}', 'owner')
    tid = s.create_task({'Title': 'Hard call', 'Status': 'open', 'Kind': 'general'}, 'owner')
    out = askstronger.ask(s, tid, 'Which one?')
    assert not out['ok'] and 'no brain here has a stronger model' in out['says']
    assert 'ask_stronger' in {t['name'] for t in agenttools.listing()}
    assert agenttools.call(s, tid, 'ask_stronger', {'question': 'q'}, {'ask_stronger': lambda t, q, c: {'ok': True, 'answer': 'A'}}) == 'A'
    from taskuary import general
    assert 'ask_stronger tool' in general._ACTION and 'Never for routine steps' in general._ACTION     # the agent is told it may
