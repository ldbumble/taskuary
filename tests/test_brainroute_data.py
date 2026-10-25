"""The data-type seam (the router, 2026-10-25). Triage judges whether a task carries sensitive data; each AI card carries the owner's
own "may read sensitive data" mark, off by default and set by no code. With the rule off nothing changes. Turned on, a sensitive
task reaches only a marked AI - over an explicit pick, through a failover, into a coding pane - and with none it WAITS and says
why. It never falls back to an AI the rule keeps out. Triage reads everything first, so Settings warns when its brain is unmarked."""
import json
from unittest import mock

import pytest

from taskuary import aidefaults, brainroute, llm, terminal, triage
from taskuary.store import MemoryStore

MSG = {'subject': 'Leave request', 'body': 'My doctor says I need two weeks off for surgery.', 'from_email': 'erin@northwind.example',
       'from_name': 'Erin Blake', 'channel': 'email'}


def _card(s, typ, **conf):
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-0123456789', 'Active': 1, 'ConfigJson': json.dumps(conf)}, 'owner')
    return f'connector:{cid}'


@pytest.fixture
def s():
    s = MemoryStore()
    s.a, s.o = _card(s, 'anthropic', model='claude-sonnet-5'), _card(s, 'openai', model='gpt-5', sensitive_ok='1')
    s.set_setting('triage_ai', s.a, 'owner'); s.set_setting('triage_backup_ai', s.o, 'owner')
    return s


def _task(s, data_class='sensitive'):
    tid = s.create_task({'Title': 'Leave request', 'Status': 'open'}, 'owner')
    s.add_route(None, tid, 'create', None, 'triage: task', [], 'triage', verdict={'intent': 'task', 'data_class': data_class})
    return tid


def _rule_on(s):
    brainroute.save_rules(s, [{**r, 'on': True} if r['id'] == 'sensitive' else r for r in brainroute.rules(s)])


def test_triage_judges_it_and_the_most_restricted_reading_wins(s):
    v = triage.classify_intent(MSG, llm=lambda sy, u, **k: json.dumps({'intent': 'task', 'why': 'w', 'title': 't', 'summary': 's',
                                                                         'data_class': 'sensitive'}))
    assert v['data_class'] == 'sensitive' and triage.verdict_schema()['schema']['properties']['data_class']['enum'] == ['ordinary', 'sensitive', None]
    assert '- **data_class** - for every verdict' in triage.INTENT_SYSTEM
    tid = _task(s)
    s.add_route(None, tid, 'attach', None, 'triage: more', [], 'triage', verdict={'intent': 'task', 'data_class': 'ordinary'})
    assert brainroute.judged(s, tid)['data_class'] == 'sensitive'            # a later ordinary message does not lower it
    s.judge_task(tid, {'data_class': 'ordinary'}, 'owner')
    assert brainroute.judged(s, tid)['data_class'] == 'ordinary'             # ...only the owner does


def test_with_the_rule_off_nothing_changes(s):
    r = brainroute.choose(s, 'draft', task=_task(s))
    assert (r.pick, r.chain) == (s.a, [s.o]) and not next(x for x in brainroute.rules(s) if x['id'] == 'sensitive')['on']


def test_on_a_sensitive_task_reaches_only_a_marked_ai_even_over_an_explicit_pick(s):
    _rule_on(s); tid = _task(s)
    r = brainroute.choose(s, 'draft', task=tid)
    assert (r.pick, r.chain) == (s.o, []) and 'only an AI marked for sensitive data may read it (rule sensitive)' in r.why
    assert brainroute.choose(s, 'general', task=tid, want_pick=s.a).pick == s.o
    assert brainroute.choose(s, 'draft', task=_task(s, 'ordinary')).pick == s.a        # an ordinary task is untouched


def test_with_no_marked_ai_it_waits_and_says_why_and_nothing_is_built(s):
    _rule_on(s); tid = _task(s)
    s.save_connector({'ConnectorId': int(s.o[10:]), 'ConfigJson': json.dumps({'model': 'gpt-5'})}, 'owner')
    r = brainroute.choose(s, 'draft', task=tid)
    assert (r.pick, r.chain, r.tier, r.rule) == ('', [], 'held', 'sensitive')
    assert r.why == 'No AI here may read sensitive data; mark one on its card in Settings, so a draft waits'
    with mock.patch.object(llm, 'make_llm', side_effect=AssertionError('built a brain the rule keeps out')):
        assert llm.build_llm(s, job='draft', task_id=tid) is None
    assert s.brain_routes(tid, limit=1)[0]['Outcome'] == 'refused:sensitive'


def test_a_failover_never_crosses_to_an_unmarked_ai(s):
    _rule_on(s); tid = _task(s); third = _card(s, 'mistral', model='mistral-large')
    s.set_setting('triage_backup_ai', f'{s.o},{third}', 'owner')
    assert brainroute.choose(s, 'draft', task=tid).chain == []


def test_a_coding_pane_opens_only_on_a_marked_cli(s):
    tid = _task(s); t = s.get_task(tid)
    with mock.patch.object(brainroute, 'may_read_sensitive', lambda store, p, cfg=None: p == 'cli:codex'):
        assert brainroute.session_allowed(s, t, ['claude', 'codex']) == (['claude', 'codex'], '')     # rule off: as it was
        _rule_on(s)
        assert brainroute.session_allowed(s, t, ['claude', 'codex']) == (['codex'], '')
        chain, why = brainroute.session_allowed(s, t, ['claude'])
    assert chain == [] and why.startswith('No AI here may read sensitive data')


def test_triage_coverage_is_warned_once_the_rule_is_on(s):
    assert brainroute.coverage_warning(s) == ''
    _rule_on(s)
    assert 'Anthropic API is not marked to read sensitive data' in brainroute.coverage_warning(s)
    s.set_setting('triage_ai', s.o, 'owner')
    assert brainroute.coverage_warning(s) == ''


def test_the_mark_is_off_by_default_and_saved_on_the_brain(s):
    fresh = MemoryStore(); a = _card(fresh, 'anthropic', model='claude-sonnet-5'); fresh.set_setting('triage_ai', a, 'owner')
    assert aidefaults.resolve(fresh, {}, 'triage_ai')['sensitive_ok'] is False
    aidefaults.apply(fresh, {}, 'triage_ai', sensitive=True)
    assert brainroute.may_read_sensitive(fresh, a) and aidefaults.resolve(fresh, {}, 'triage_ai')['sensitive_ok'] is True
    aidefaults.apply(fresh, {}, 'triage_ai', sensitive=False)
    assert not brainroute.may_read_sensitive(fresh, a)
    # no card is marked by code: every connector the store ships starts unmarked
    assert not any(brainroute.may_read_sensitive(MemoryStore(), f"connector:{c['ConnectorId']}") for c in MemoryStore().list_connectors())
