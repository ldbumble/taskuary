"""THE OWNER'S RULINGS OF 2026-11-02, EVENING ("never hard-coded rules; let the AI see everything"): an agent that finished and asks to go
further lights nothing on a CODING agent and may light Mark done or Stop and save on a GENERAL one - the model's call, with the agent's kind in
THE STATE and a check that refuses (never swaps) a close over a coding agent's ask; and a HABIT - one move on 80% of 5 or more of the owner's
answers in a state - is said in THE STATE for the model to follow unless this item differs. Invented Northwind data only (CLAUDE.md)."""
import json
from unittest import mock
import pytest
from taskuary import advisor, calibrate, funnel, terminal
from taskuary.store import MemoryStore
from taskuary.testing import Factory
from tests.test_calibrate import _press


@pytest.fixture
def s(monkeypatch):
    s = MemoryStore(); s.set_setting('calendar_enabled', '0', 'test'); s.set_setting('advisor_event_cap', '1000', 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [])
    monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
    calibrate.clear(); funnel.invalidate(); yield s; calibrate.clear(); funnel.invalidate()


def _asking(s, kind):
    t = Factory(s).task(title=f'Reconcile the ledger export ({kind})', kind=kind, status='in_progress')
    return t, {'key': f'agent:{t}', 'kind': 'agent', 'lane': 'blocked', 'asking': True, 'tid': t, 'title': f'Reconcile the ledger export ({kind})'}


def _verbs(*vs): return [{'verb': v, 'label': v} for v in vs]


def _decide(s, item, llm):
    """The decision after the model read the item (item.shown, tier 2) and answered through `llm`."""
    orig = advisor._item
    with mock.patch.object(advisor, '_item', lambda store, tk, ti, key=None: item if key in (None, item['key']) and int(ti) == item['tid'] else orig(store, tk, ti, key)), \
         mock.patch.object(advisor, 'offered', lambda store, it: _verbs('close', 'stop_agent', 'answer_agent')):
        tgt = advisor.target_of(s, item['key'])
        advisor.notice(s, advisor.SHOWN, tgt[0], tgt[1], tier=2, wait=True, llm=llm, key=item['key'])
        with mock.patch.object(advisor, 'notice'): return advisor.decide(s, item['key'], preread=False)


def saying(verb):
    calls = []
    def llm(system, user, **kw): calls.append((system, user)); return json.dumps({'verb': verb, 'line': '', 'evidence': []})
    llm.calls = calls
    return llm


# ── 5. AN AGENT THAT FINISHED AND ASKS TO GO FURTHER ─────────────────────────────────────────────────────────────────────────────────────
def test_the_agents_kind_is_in_the_state_and_the_guidance_is_the_models():
    assert 'CODING agent' in advisor.SYSTEM and 'GENERAL agent' in advisor.SYSTEM and 'deploy now?' in advisor.SYSTEM
    s = MemoryStore()
    for kind, said in (('coding', 'THE AGENT: a CODING agent'), ('general', 'THE AGENT: a GENERAL agent')):
        t, it = _asking(s, kind)
        assert said in advisor.state_line(s, it, _verbs('close', 'stop_agent'), 'task', t)
    t = Factory(s).task(title='Badge access', kind='task')
    assert 'THE AGENT' not in advisor.state_line(s, {'key': f'task:{t}', 'kind': 'asked', 'tid': t}, _verbs('reply'), 'task', t), 'no agent, no kind'


@pytest.mark.parametrize('verb', ['close', 'stop_agent'])
def test_a_close_over_a_coding_agents_ask_is_refused_to_nothing(s, verb):
    t, it = _asking(s, 'coding')
    d = advisor.checked(s, it, _verbs('close', 'stop_agent', 'answer_agent'), {'key': it['key'], 'state': 'agent_asking', 'verb': verb, 'line': 'x', 'evidence': []})
    assert d['verb'] is None and d['checked'] and d['line'] == '', 'refused to nothing - never swapped for another verb'
    # ...the agent's own answer stands, and a coding agent in another state is not this check's
    assert advisor.checked(s, it, _verbs('answer_agent'), {'key': it['key'], 'state': 'agent_asking', 'verb': 'answer_agent', 'line': ''})['verb'] == 'answer_agent'
    assert advisor.checked(s, it, _verbs(verb), {'key': it['key'], 'state': 'agent_done', 'verb': verb, 'line': ''})['verb'] == verb


# ── 6. A HABIT ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_habit_is_one_move_on_eighty_percent_of_five_or_more_answers():
    L = lambda v: {'close': 'Mark done', 'stop_agent': 'Stop and save'}.get(v, v)
    s = MemoryStore()
    for n in range(1, 5): _press(s, n, 'agent_done', 'close')
    assert 'HABIT' not in calibrate.evidence(s, 'agent_done', label=L), 'four answers are not enough'
    _press(s, 5, 'agent_done', 'close'); calibrate.clear()
    assert calibrate.evidence(s, 'agent_done', label=L).endswith('Mark done 5 of 5; a HABIT: Mark done (5 of 5)')
    for n in range(10, 14): _press(s, n, 'stopped', 'close')
    _press(s, 14, 'stopped', 'stop_agent'); _press(s, 15, 'stopped', 'continue'); calibrate.clear()
    assert 'HABIT' not in calibrate.evidence(s, 'stopped', label=L), '4 of 6 is under the bar'
    assert calibrate.habit([('close', 4), ('next', 1)], 5) == '; a HABIT: close (4 of 5)' and calibrate.habit([], 0) == ''
