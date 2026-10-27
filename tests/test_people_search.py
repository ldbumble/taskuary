"""Finding a person by what the owner remembers of them: a company, a domain, a first name, a fragment - ranked by how much the
owner writes with them, with the model asked only when the plain match finds nobody (peoplesearch.py). Invented people only."""
import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import peoplesearch as ps, server
from taskuary.store import MemoryStore


@pytest.fixture
def s():
    v = MemoryStore(); v.set_setting('owner_email', 'alex@northwind.example', 't'); yield v; v.close()


def sent(s, to, n=1, day=1):
    for i in range(n):
        s.add_message({'ExternalId': f'out-{to}-{i}', 'ConversationId': f'c-{to}-{i}', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                       'FromName': 'You', 'FromEmail': 'alex@northwind.example', 'Subject': 'Numbers', 'BodyText': 'See attached.',
                       'SentAt': f'2026-10-{day:02d} 09:00:00', 'Status': 'context', 'Direction': 'out', 'RecipientsJson': json.dumps({'to': [to]})})


def wrote_in(s, name, email, n=1):
    for i in range(n):
        s.add_message({'ExternalId': f'in-{email}-{i}', 'ConversationId': f'c-in-{email}-{i}', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                       'FromName': name, 'FromEmail': email, 'Subject': 'Hello', 'BodyText': 'Hi', 'SentAt': '2026-10-01 08:00:00', 'Status': 'routed'})


def world(s):
    wrote_in(s, 'Lena Ortiz', 'lortiz@dynamo.example', 2)
    sent(s, 'vhale@dynamo.example', 5)                      # written to most: first among Dynamo's people
    ps.remember(s, [{'email': 'nprice@dynamo.example', 'name': 'Nora Price', 'company': 'Dynamo Freight', 'title': 'Account manager'}])
    wrote_in(s, 'Gail Moreno', 'gmoreno@northwind.example', 3)
    wrote_in(s, 'Ray Colton', 'ray@vendor.example')
    wrote_in(s, 'Murray Jones', 'murray.jones@vendor.example')


def tos(r): return [x['to'] for x in r['data']]


def test_a_company_word_lists_everyone_at_it_most_written_with_first(s):
    world(s)
    assert tos(ps.search(s, 'dynamo')) == ['vhale@dynamo.example', 'lortiz@dynamo.example', 'nprice@dynamo.example']


def test_the_company_name_from_the_directory_matches_and_is_shown(s):
    world(s)
    r = ps.search(s, 'freight')['data']
    assert [x['to'] for x in r] == ['nprice@dynamo.example'] and r[0]['company'] == 'Dynamo Freight' and r[0]['name'] == 'Nora Price'


def test_a_first_name_finds_the_person_and_a_fragment_finds_them_too(s):
    world(s)
    assert tos(ps.search(s, 'gail')) == ['gmoreno@northwind.example']
    assert tos(ps.search(s, 'gmor')) == ['gmoreno@northwind.example']
    assert tos(ps.search(s, 'moreno north')) == ['gmoreno@northwind.example']


def test_a_whole_name_word_outranks_a_fragment_inside_another_address(s):
    world(s)
    assert tos(ps.search(s, 'ray'))[0] == 'ray@vendor.example'
    assert 'murray.jones@vendor.example' in tos(ps.search(s, 'ray'))


def test_the_domain_finds_them_and_the_owner_is_never_offered(s):
    world(s)
    assert set(tos(ps.search(s, 'vendor.example'))) == {'ray@vendor.example', 'murray.jones@vendor.example'}
    assert 'alex@northwind.example' not in tos(ps.search(s, 'northwind'))


def test_nobody_fits_is_empty_and_no_ai_was_asked(s):
    world(s)
    with mock.patch.object(ps, 'ai_pick') as ask:
        assert ps.search(s, 'zebra') == {'data': [], 'ai': False}
    ask.assert_not_called()


def test_the_model_picks_from_the_known_people_when_the_words_describe_someone(s):
    world(s)
    seen = {}
    def brain(system, user, **kw):
        seen['user'] = user
        n = next(l.split('.')[0] for l in user.splitlines() if 'lortiz@' in l)
        return json.dumps({'picks': [int(n), 999]})            # 999 is nobody: dropped, never invented
    r = ps.search(s, 'the dynamo billing person', ai=True, brain=brain)
    assert r == {'data': r['data'], 'ai': True} and tos(r) == ['lortiz@dynamo.example']
    assert 'the dynamo billing person' in seen['user'] and 'Dynamo Freight' in seen['user']


def test_the_model_is_not_asked_when_a_plain_name_already_matched(s):
    world(s)
    brain = mock.Mock()
    assert tos(ps.search(s, 'gail', ai=True, brain=brain)) == ['gmoreno@northwind.example']
    brain.assert_not_called()


def test_no_ai_connected_is_plain_matching_only(s):
    world(s)
    with mock.patch('taskuary.llm.build_llm', return_value=None):
        assert ps.search(s, 'someone who does billing', ai=True) == {'data': [], 'ai': False}


def test_a_model_that_answers_nonsense_is_plain_matching(s):
    world(s)
    assert ps.search(s, 'the billing one', ai=True, brain=lambda *a, **k: 'sure, Lena!') == {'data': [], 'ai': False}


def test_a_directory_answer_is_remembered_and_found_offline(s):
    c = s.get_connector_by_type('outlook')
    s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Secret': 'rt', 'ConfigJson': json.dumps({'auth': 'user'})}, 'o')
    ps._DIR_HELD.clear()
    hit = [{'email': 'pvance@dynamo.example', 'name': 'Paula Vance', 'company': 'Dynamo Freight', 'title': ''}]
    with mock.patch('taskuary.channels.graph_token', return_value='tok'), mock.patch.object(ps, 'graph_people', return_value=hit) as g:
        assert tos(ps.search(s, 'paula')) == ['pvance@dynamo.example']
    g.assert_called_once_with('tok', 'paula', True)
    ps._DIR_HELD.clear()
    with mock.patch.object(ps, 'graph_people', side_effect=RuntimeError('offline')):
        assert tos(ps.search(s, 'dynamo')) == ['pvance@dynamo.example']


def test_graph_people_reads_both_halves_and_keeps_the_company():
    def get(url, headers=None, params=None, timeout=None):
        if url.endswith('/me/people'):
            return mock.Mock(status_code=200, json=lambda: {'value': [{'displayName': 'Lena Ortiz', 'companyName': 'Dynamo Freight',
                                                                       'scoredEmailAddresses': [{'address': 'lortiz@dynamo.example'}]}]})
        assert headers.get('ConsistencyLevel') == 'eventual'
        return mock.Mock(status_code=403, json=lambda: {})       # a sign-in that cannot read users: nothing, not an error
    with mock.patch('requests.get', side_effect=get):
        assert ps.graph_people('t', 'dynamo', True) == [{'email': 'lortiz@dynamo.example', 'name': 'Lena Ortiz', 'company': 'Dynamo Freight', 'title': None}]


def test_a_chat_channel_offers_its_chats_by_name(s):
    s.add_message({'ExternalId': 'w1', 'ConversationId': 'teams:19:ops@thread.v2', 'Channel': 'teams', 'FromName': 'Erin Blake',
                   'Subject': '', 'BodyText': 'hi', 'SentAt': '2026-10-02 08:00:00', 'Status': 'routed'})
    assert [(x['to'], x['name']) for x in ps.search(s, 'erin', 'teams')['data']] == [('19:ops@thread.v2', 'Erin Blake')]


def test_the_endpoint_answers_the_search():
    with mock.patch.object(ps, 'search', return_value={'data': [{'to': 'lortiz@dynamo.example'}], 'ai': False}) as f:
        r = TestClient(server.app).get('/api/people/search', params={'q': 'dynamo', 'channel': 'email', 'ai': 1})
    assert r.status_code == 200 and r.json()['data'][0]['to'] == 'lortiz@dynamo.example'
    assert f.call_args.args[1:] == ('dynamo', 'email') and f.call_args.kwargs == {'ai': True}
