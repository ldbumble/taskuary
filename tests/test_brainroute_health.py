"""Health and the day's cap (the router, 2026-10-25), Auto mode only. A CLI refused on its usage allowance says when it comes back,
and until then its calls go to the next brain; the reason names the reset. Past the owner's cap on strong calls (blank = none),
hard work runs standard and an unsure answer is not asked again - each said in the route's reason."""
import json
from datetime import datetime, timedelta
from unittest import mock

import pytest

from taskuary import agents, brainroute, llm
from taskuary.store import MemoryStore


def _card(s, typ, **conf):
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-0123456789', 'Active': 1, 'ConfigJson': json.dumps(conf)}, 'owner')
    return f'connector:{cid}'


@pytest.fixture
def s():
    s = MemoryStore(); s.set_setting('ai_route_mode', 'auto', 'owner')
    return s


def test_a_resting_claude_hands_the_call_to_codex_and_says_until_when(s):
    s.set_setting('triage_ai', 'cli:claude', 'owner'); s.set_setting('triage_backup_ai', 'cli:codex', 'owner')
    at = datetime.now().replace(second=0, microsecond=0) + timedelta(hours=2)
    brainroute.cool(s, 'cli:claude', at)
    r = brainroute.choose(s, 'triage')
    assert (r.pick, r.chain) == ('cli:codex', ['cli:claude'])
    assert f"claude (CLI) is limited until {at.strftime('%H:%M')}, so codex (CLI)" in r.why
    s.set_setting('ai_route_mode', 'fixed', 'owner')
    assert brainroute.choose(s, 'triage').pick == 'cli:claude'                  # Fixed: the cards stand, as before
    s.set_setting('ai_route_mode', 'auto', 'owner')
    assert brainroute.choose(s, 'triage').pick == 'cli:codex'
    with mock.patch.object(brainroute, 'datetime', mock.Mock(now=lambda: at + timedelta(minutes=1), fromisoformat=datetime.fromisoformat)):
        assert brainroute.cooldowns(s) == {}                                     # the reset passed: it is back


def test_a_refusal_with_a_reset_time_rests_the_brain(s):
    reset = int((datetime.now() + timedelta(hours=3)).timestamp())
    def refuse(*a, **k):
        raise agents.RateLimited('claude has reached its five-hour usage limit, so it did not run.', {'resetsAt': reset, 'status': 'rejected'})
    brain = llm._Cooling(s, 'cli:claude', refuse)
    with pytest.raises(agents.RateLimited): brain('sys', 'user')
    assert brainroute.cooldowns(s)['cli:claude'].strftime('%H:%M') == datetime.fromtimestamp(reset).strftime('%H:%M')
    assert agents.availability_failure(agents.RateLimited('claude has reached its usage limit'))      # still a failover, as before


def test_a_rest_is_never_longer_than_a_week(s):
    brainroute.cool(s, 'cli:claude', datetime.now() + timedelta(days=400))
    assert brainroute.cooldowns(s)['cli:claude'] < datetime.now() + timedelta(days=8)


def test_past_the_cap_hard_work_runs_standard_and_says_so(s):
    a = _card(s, 'anthropic', model='claude-sonnet-5', strong_model='claude-opus-5'); s.set_setting('triage_ai', a, 'owner')
    tid = s.create_task({'Title': 'Board pack', 'Status': 'open'}, 'owner'); s.judge_task(tid, {'difficulty': 'hard'}, 'triage')
    assert brainroute.cap(s) is None and brainroute.choose(s, 'draft', task=tid).tier == 'strong'   # blank: no cap
    s.set_setting('ai_route_strong_cap', '2', 'owner')
    for _ in range(2): brainroute.log(s, brainroute.choose(s, 'draft', task=tid), tid)
    r = brainroute.choose(s, 'draft', task=tid)
    assert (r.tier, r.gear) == ('standard', 'main') and "today's 2 strong calls are spent, so standard" in r.why
    assert brainroute.strong_today(s) == 2


def test_the_cap_blocks_a_second_step_up(s):
    a = _card(s, 'anthropic', model='claude-sonnet-5', strong_model='claude-opus-5'); s.set_setting('triage_ai', a, 'owner')
    s.set_setting('ai_route_strong_cap', '1', 'owner')
    good = json.dumps({'title': 'Q3 numbers', 'summary': 'Erin Blake wants the Q3 numbers.'})
    calls = []
    def make(t, conf, key):
        return lambda system, user, **kw: calls.append(conf['model']) or (good if conf['model'] == 'claude-opus-5' else 'junk')
    with mock.patch.object(llm, 'make_llm', make):
        first = llm.ask_json(llm.build_llm(s, job='triage'), 'sys', 'user', need=('title',))
        second = llm.ask_json(llm.build_llm(s, job='triage'), 'sys', 'user', need=('title',))
    assert first.data['title'] == 'Q3 numbers' and second.data is None and calls.count('claude-opus-5') == 1
