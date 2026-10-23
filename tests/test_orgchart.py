"""The org chart: who is the owner's manager, who reports to them, who owns what (the org-chart gap, 2026-10-22).

A request from the owner's own manager read exactly like anybody's on the To line, and an agent told "send it to whoever runs
payroll" had nobody to name. The directory fills in the manager and the reports where the sign-in may read them; the owner says
the rest through the Assistant; triage, the dossier, the agent's context and the look-ups all read the same chart.
"""
import json
from unittest import mock

import pytest

from taskuary import concierge, context, lookups, orgchart, triage, toolcatalog, operations
from taskuary.store import MemoryStore

ERIN, RAY, GAIL = 'erin.blake@northwind.example', 'ray.colton@northwind.example', 'gail.moreno@northwind.example'


@pytest.fixture
def s():
    v = MemoryStore(); yield v; v.close()


def wrote_in(s, name, email, tid=None):
    return s.add_message({'ExternalId': f'in-{email}-{tid}', 'ConversationId': f'c-{email}-{tid}', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                          'FromName': name, 'FromEmail': email, 'Subject': 'Numbers', 'BodyText': 'Can you send them today?',
                          'SentAt': '2026-10-21 08:00:00', 'Status': 'routed', **({'TaskId': tid} if tid else {})})


# ---- the store -----------------------------------------------------------------------------------------------------------

def test_the_owner_names_their_manager_by_name_and_it_keys_on_the_address(s):
    wrote_in(s, 'Erin Blake', ERIN)
    r = orgchart.relate(s, 'Erin Blake', 'manager')
    assert (r['email'], r['relation'], r['pinned']) == (ERIN, 'manager', True)
    assert orgchart.relation_of(s, ERIN) == 'your manager'
    assert orgchart.relation_of(s, ERIN.upper()) == 'your manager'
    assert orgchart.relation_of(s, 'someone@vendor.example') == ''


def test_someone_who_never_wrote_still_owns_an_area_by_name(s):
    orgchart.relate(s, 'Ray Colton', owns='payroll, benefits')
    assert orgchart.relation_of(s, 'rcolton@northwind.example', 'Ray Colton') == 'owns payroll, benefits'
    orgchart.relate(s, 'Ray Colton', owns=['Payroll', 'expenses'], drops='benefits')         # no duplicate, one taken off
    assert orgchart.find(s, name='Ray Colton')['owns'] == ['payroll', 'expenses']
    assert 'Ray Colton: owns payroll, expenses' in orgchart.block(s)


def test_a_name_that_is_two_people_is_asked_never_picked(s):
    wrote_in(s, 'Gail Moreno', GAIL); wrote_in(s, 'Gail Moreno', 'gail.moreno@vendor.example')
    with pytest.raises(ValueError, match='could be'): orgchart.relate(s, 'Gail Moreno', 'report')
    assert orgchart.chart(s) == []


def test_a_bad_relation_or_nothing_said_is_refused(s):
    with pytest.raises(ValueError, match='manager, report or none'): orgchart.relate(s, ERIN, 'cousin')
    with pytest.raises(ValueError, match='say what'): orgchart.relate(s, ERIN)
    with pytest.raises(ValueError, match='say who'): orgchart.relate(s, '', 'manager')


def test_forget_takes_them_off(s):
    orgchart.relate(s, ERIN, 'manager')
    assert orgchart.relate(s, ERIN, forget=True)['forgotten']
    assert orgchart.chart(s) == [] and orgchart.block(s) == ''


def test_the_block_lists_the_manager_first(s):
    orgchart.relate(s, RAY, 'report'); orgchart.relate(s, ERIN, 'manager', owns='finance')
    assert orgchart.block(s).splitlines()[0] == f'- {ERIN}: your manager; owns finance'


# ---- Microsoft's directory -------------------------------------------------------------------------------------------------

def test_the_directory_fills_the_manager_and_reports(s):
    n = orgchart.merge(s, [{'manager': (ERIN, 'Erin Blake'), 'reports': [(RAY, 'Ray Colton'), (GAIL, 'Gail Moreno')]}])
    assert n == 3
    assert [orgchart.relation_of(s, e) for e in (ERIN, RAY, GAIL)] == ['your manager', 'reports to you', 'reports to you']


def test_the_owners_word_outranks_the_directory(s):
    orgchart.relate(s, ERIN, 'none')                                  # the owner said Erin is not their manager (a dotted line)
    orgchart.merge(s, [{'manager': (ERIN, 'Erin Blake'), 'reports': []}])
    assert orgchart.relation_of(s, ERIN) == ''


def test_a_manager_the_directory_no_longer_gives_goes_but_a_refused_half_wipes_nothing(s):
    orgchart.merge(s, [{'manager': (ERIN, 'Erin Blake'), 'reports': [(RAY, 'Ray Colton')]}])
    orgchart.merge(s, [{'manager': (GAIL, 'Gail Moreno'), 'reports': None}])          # reports refused (scope): Ray stays
    assert orgchart.relation_of(s, ERIN) == '' and orgchart.relation_of(s, GAIL) == 'your manager'
    assert orgchart.relation_of(s, RAY) == 'reports to you'


def test_someone_named_before_the_directory_gets_their_address_on_the_same_row(s):
    orgchart.relate(s, 'Ray Colton', owns='payroll')
    orgchart.merge(s, [{'manager': (), 'reports': [(RAY, 'Ray Colton')]}])
    assert len(orgchart.chart(s)) == 1 and orgchart.relation_of(s, RAY) == 'reports to you; owns payroll'


class _R:
    def __init__(self, code, j=None): self.status_code, self._j = code, j or {}
    def json(self): return self._j


def test_from_directory_reads_me_and_takes_404_as_no_manager_and_403_as_unknown(s):
    def get(url, **kw):
        if url.endswith('/me/manager'): return _R(404)
        return _R(200, {'value': [{'displayName': 'Ray Colton', 'mail': 'Ray.Colton@northwind.example'}]})
    with mock.patch('requests.get', side_effect=get):
        assert orgchart.from_directory(s, 'tok') == {'manager': (), 'reports': [(RAY, 'Ray Colton')]}
    with mock.patch('requests.get', return_value=_R(403)):
        assert orgchart.from_directory(s, 'tok') == {'manager': None, 'reports': None}


def test_the_sync_runs_once_a_day(s):
    with mock.patch.object(orgchart, 'sync', return_value={'changed': 0}) as run:
        orgchart.sync_if_due(s); orgchart.sync_if_due(s)
    assert run.call_count == 1


# ---- who reads it -------------------------------------------------------------------------------------------------------

def test_triage_is_shown_the_relation_with_its_explanation(s):
    seen = {}
    def llm(system, user, **kw):
        seen.update(sys=system, usr=json.loads(user)); return '{"intent": "task", "kind": "task", "why": "x"}'
    triage.classify_intent({'from_email': ERIN, 'subject': 'Numbers', 'body': 'Can you send them today?'}, llm=llm,
                           system='Judge it.', thread={'sender_relation': 'your manager'})
    assert seen['usr']['sender_relation'] == 'your manager'
    assert triage.FIELDS['sender_relation'] in seen['sys']                 # a document that never names it still explains it
    assert 'sender_relation' in triage.INTENT_SYSTEM                       # ...and the shipped guide says how much it counts


def test_ingest_hands_the_relation_to_the_judge(s):
    from taskuary import ingest
    orgchart.relate(s, ERIN, 'manager')
    seen = {}
    def judge(msg, **kw): seen.update(kw.get('thread') or {}); return {'intent': 'fyi', 'why': 'x'}
    with mock.patch.object(ingest, 'classify_intent', side_effect=judge):
        ingest.judge(s, {'from_email': ERIN, 'channel': 'email', 'subject': 'Numbers', 'body': 'b', 'conversation_id': 'n'}, llm=lambda *a, **k: '{}')
    assert seen.get('sender_relation') == 'your manager'


def test_the_dossier_and_the_agents_context_carry_it(s):
    orgchart.relate(s, ERIN, 'manager'); orgchart.relate(s, 'Ray Colton', owns='payroll')
    from taskuary.counsel import dossier
    assert 'WHO THEY ARE TO YOU: your manager' in dossier(s, {'from_email': ERIN, 'subject': 'Numbers'}, calendar=False)
    tid = s.create_task({'Title': 'Send the numbers', 'Kind': 'general', 'Status': 'open'}, 'router')
    wrote_in(s, 'Erin Blake', ERIN, tid)
    with mock.patch('taskuary.origin.of_task', return_value=('owner', '')):
        built = context.build(s, tid)
        assert "## The owner's people" in built and 'Ray Colton: owns payroll' in built
        from taskuary import agents
        assert 'Ray Colton: owns payroll' in agents.task_context(s, tid)
    with mock.patch('taskuary.origin.of_task', return_value=('stranger', '')):
        assert "The owner's people" not in context.build(s, tid)          # who the owner's people are is what a planted line would ask
        assert 'Ray Colton' not in agents.task_context(s, tid)


def test_the_lookups_answer_who_is_my_manager(s):
    wrote_in(s, 'Erin Blake', ERIN); orgchart.relate(s, ERIN, 'manager')
    assert 'to you: your manager' in lookups.sender_read(s, {'who': 'Erin'})
    assert 'your manager' in lookups.memory_list(s, {})


# ---- the Assistant's tool ---------------------------------------------------------------------------------------------------

def test_the_tool_is_offered_and_dispatchable():
    assert 'people.relate' in toolcatalog.PURPOSE and 'people.relate' in operations.KINDS
    assert 'people.relate' in {k for _, _, ks in toolcatalog.BUCKETS for k in ks}
    assert toolcatalog.signature('people.relate') == 'people.relate(who)'
    assert all(f'`{k}`' in toolcatalog.describe('people.relate') for k in ('relation', 'owns', 'drops', 'forget'))
    assert 'runs at once, said' in toolcatalog.describe('people.relate')               # no button to press: it is kept and said


def test_the_assistant_keeps_it_and_says_it_in_one_line(s):
    wrote_in(s, 'Erin Blake', ERIN)
    out = concierge.call_turn(s, 0, {'kind': 'people.relate', 'params': {'who': 'Erin Blake', 'relation': 'my manager'}}, None, 'Erin is my manager')
    assert out['did'] == 'people.relate' and out['say'] == 'Org chart: Erin Blake - your manager.'
    assert orgchart.relation_of(s, ERIN) == 'your manager'
    with pytest.raises(concierge.CallMiss, match='Nothing was changed'):
        concierge.call_turn(s, 0, {'kind': 'people.relate', 'params': {'who': 'Erin Blake', 'relation': 'cousin'}}, None, 'x')
