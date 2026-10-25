"""One-shot escalation (the router, 2026-10-25). In Auto mode, a job that only reads and writes - triage, a draft, a summary, the
Advisor, ranking, memory, a judgement - whose answer comes back unreadable after its own retry, or that its model says it is not
sure of, is asked ONCE of a strong model. An agent that can act (general, coding) never is: it may have done half its work, and
the owner re-runs it with a press. Nothing is ever sent by any of this."""
import json
from unittest import mock

import pytest

from taskuary import brainroute, llm
from taskuary.store import MemoryStore

GOOD = json.dumps({'intent': 'task', 'title': 'Q3 numbers', 'summary': 'Erin Blake wants the Q3 numbers.', 'sure': True})


def _card(s, typ, **conf):
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-0123456789', 'Active': 1, 'ConfigJson': json.dumps(conf)}, 'owner')
    return f'connector:{cid}'


@pytest.fixture
def s():
    s = MemoryStore()
    s.a = _card(s, 'anthropic', model='claude-sonnet-5', strong_model='claude-opus-5')
    s.set_setting('triage_ai', s.a, 'owner'); s.set_setting('ai_route_mode', 'auto', 'owner')
    return s


def _brains(weak):
    "make_llm for the fakes: the light/standard model answers `weak`, the strong one answers GOOD - and every call is counted."
    calls = []
    def make(t, conf, key):
        def brain(system, user, **kw): calls.append(conf['model']); return GOOD if conf['model'] == 'claude-opus-5' else weak
        return brain
    return make, calls


def _ask(s, job='triage', task_id=None):
    return llm.ask_json(llm.build_llm(s, job=job, task_id=task_id), 'sys', 'user', need=('title', 'summary'))


def test_junk_twice_is_answered_by_the_strong_brain_once_and_logged(s):
    make, calls = _brains('not json at all')
    with mock.patch.object(llm, 'make_llm', make): a = _ask(s)
    assert a.data['title'] == 'Q3 numbers' and calls == ['claude-sonnet-5', 'claude-sonnet-5', 'claude-opus-5']
    first, up = s.brain_routes()[::-1]
    assert (first['Outcome'], up['EscalatedFrom'], up['Tier'], up['Rule']) == ('escalated', first['Id'], 'strong', 'unsure')
    assert 'came back unreadable' in up['Why'] and "Anthropic API's strong model" in up['Why']


def test_an_unsure_answer_steps_up_and_a_sure_one_does_not(s):
    unsure = json.dumps({**json.loads(GOOD), 'title': 'Maybe numbers', 'sure': False})
    make, calls = _brains(unsure)
    with mock.patch.object(llm, 'make_llm', make): a = _ask(s)
    assert a.data['title'] == 'Q3 numbers' and calls[-1] == 'claude-opus-5' and 'came back unsure' in s.brain_routes()[0]['Why']
    make, calls = _brains(json.dumps({**json.loads(GOOD), 'title': 'Sure numbers'}))
    with mock.patch.object(llm, 'make_llm', make): a = _ask(s)
    assert a.data['title'] == 'Sure numbers' and calls == ['claude-sonnet-5']


def test_once_per_item_per_job(s):
    tid = s.create_task({'Title': 'Q3 numbers', 'Status': 'open'}, 'owner')
    make, calls = _brains('junk')
    with mock.patch.object(llm, 'make_llm', make):
        _ask(s, task_id=tid); n = len(calls); b = _ask(s, task_id=tid)
    assert b.data is None and 'claude-opus-5' not in calls[n:]
    assert sum(1 for r in s.brain_routes() if r['EscalatedFrom']) == 1


def test_fixed_mode_never_steps_up_nor_does_a_brain_with_no_strong_model(s):
    make, calls = _brains('junk')
    s.set_setting('ai_route_mode', 'fixed', 'owner')
    with mock.patch.object(llm, 'make_llm', make): assert _ask(s).data is None
    s.set_setting('ai_route_mode', 'auto', 'owner'); o = _card(s, 'openai', model='gpt-5'); s.set_setting('triage_ai', o, 'owner')
    with mock.patch.object(llm, 'make_llm', make): assert _ask(s).data is None
    assert 'claude-opus-5' not in calls and not any(r['EscalatedFrom'] for r in s.brain_routes())


def test_the_owner_can_switch_the_rule_off(s):
    brainroute.save_rules(s, [{**r, 'on': False} if r['id'] == 'unsure' else r for r in brainroute.rules(s)])
    make, calls = _brains('junk')
    with mock.patch.object(llm, 'make_llm', make): assert _ask(s).data is None
    assert 'claude-opus-5' not in calls


def test_agents_that_can_act_never_step_up(s):
    tid = s.create_task({'Title': 'Q3 numbers', 'Status': 'open'}, 'owner')
    for job in ('general', 'coding', 'assistant', 'report'):
        assert brainroute.choose(s, job, task=tid, want_pick=s.a).escalate == '', job
    assert brainroute.choose(s, 'triage').escalate == 'strong'


def test_a_stepped_up_draft_is_still_only_a_draft(s):
    from taskuary import responder
    tid = s.create_task({'Title': 'Meeting time', 'Status': 'open'}, 'owner')
    s.add_message({'TaskId': tid, 'Channel': 'email', 'FromEmail': 'erin@northwind.example', 'FromName': 'Erin Blake',
                   'Subject': 'Thursday?', 'BodyText': 'Does Thursday at 2 work?', 'Status': 'routed'})
    make, _calls = _brains('Thursday at 2 works.')
    with mock.patch.object(llm, 'make_llm', make), mock.patch('taskuary.outbound.send_out', side_effect=AssertionError('sent')) as send:
        responder.draft_reply(s, tid)
    assert not send.called and not [m for m in s.list_messages(tid) if m.get('Direction') == 'out' and m.get('Status') == 'sent']
