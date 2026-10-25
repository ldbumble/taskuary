"""The person seam (the router, 2026-10-25): a rule may name the people a task is with - "drafts to Gail Moreno -> the strong model".
Only the owner adds one; no shipped rule names a person. Who a task is with comes from the people model (people.keys_of_task, the
memory redesign's); while this build has none, a person rule matches nothing rather than guessing at a name."""
import json
from unittest import mock

from taskuary import brainroute, people
from taskuary.store import MemoryStore

GAIL = 'gail@northwind.example'


def _store():
    s = MemoryStore(); cid = s.get_connector_by_type('anthropic')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sk-test-0123456789', 'Active': 1,
                      'ConfigJson': json.dumps({'model': 'claude-sonnet-5', 'strong_model': 'claude-opus-5'})}, 'owner')
    s.set_setting('triage_ai', f'connector:{cid}', 'owner'); s.set_setting('ai_route_mode', 'auto', 'owner')
    brainroute.save_rules(s, [{'id': 'gail-drafts', 'when': {'job': ['draft'], 'person': [GAIL]}, 'use': {'tier': 'strong'}}])
    return s, s.create_task({'Title': 'Budget question', 'Status': 'open'}, 'owner')


def test_no_shipped_rule_names_a_person():
    assert not any('person' in r['when'] for r in brainroute.DEFAULT_RULES)


def test_with_no_people_model_a_person_rule_matches_nothing():
    s, tid = _store()
    assert not hasattr(people, 'keys_of_task')
    r = brainroute.choose(s, 'draft', task=tid)
    assert (r.rule, r.tier) == ('work', 'standard')


def test_with_the_people_model_it_matches_the_people_named():
    s, tid = _store()
    with mock.patch.object(people, 'keys_of_task', lambda store, task: [GAIL], create=True):
        r = brainroute.choose(s, 'draft', task=tid)
        assert (r.rule, r.tier) == ('gail-drafts', 'strong')
    with mock.patch.object(people, 'keys_of_task', lambda store, task: ['ray@northwind.example'], create=True):
        assert brainroute.choose(s, 'draft', task=tid).rule == 'work'
    assert brainroute.sentence(brainroute.rules(s)[0]) == f'Drafts with {GAIL} -> the strong model'


def test_a_people_model_that_fails_matches_nothing():
    s, tid = _store()
    with mock.patch.object(people, 'keys_of_task', mock.Mock(side_effect=RuntimeError('no index')), create=True):
        assert brainroute.choose(s, 'draft', task=tid).rule == 'work'
