"""THREE PRIORITIES (the owner, 2026-10-25, twice: "be careful when updating triage to have 3 categories, important/urgent/regular and
make sure it makes sense"). Urgent keeps its meaning - time-critical, on you now - and everything it did: its shade, its band, the
phone. Important matters for WHO or WHAT, judged by the model with the memory as evidence, said with its reason, and never moves a
row. Regular is everything else. Every old word lands on one of the three, and the one that merges keeps a record. Invented
Northwind people only; the boundary cases themselves are tests/memory_cases.py's."""
import json
from unittest import mock
import pytest
from taskuary import ingest, learned_cut, processing_order as po, triage
from taskuary.store import MemoryStore
from tests import memory_cases as C


def test_three_words_and_every_old_one_lands_on_one():
    assert po.LEVELS == ('regular', 'important', 'urgent')
    assert [po.level(v) for v in ('low', 'normal', 'high', 'urgent', 'IMPORTANT', '', None, 'critical')] == \
           ['regular', 'regular', 'important', 'urgent', 'important', 'regular', 'regular', 'regular']
    assert po.priority_rank('urgent') == 0 and po.priority_rank('high') == po.priority_rank('important') == 1 and po.priority_rank('critical') == 99


def test_a_task_is_stored_in_the_three_words_whatever_its_caller_said():
    s = MemoryStore()
    t = s.create_task({'Title': 'x', 'Priority': 'normal'}, 'owner'); u = s.create_task({'Title': 'y'}, 'owner')
    assert (s.get_task(t)['Priority'], s.get_task(u)['Priority']) == ('regular', 'regular')
    s.update_task(t, {'Priority': 'high'}, 'owner'); assert s.get_task(t)['Priority'] == 'important'


def test_the_rename_loses_nothing():
    s = MemoryStore()
    ids = {p: s.create_task({'Title': p}, 'owner') for p in ('low', 'normal', 'high', 'urgent')}
    for p, t in ids.items(): s._exec('UPDATE task SET Priority=? WHERE TaskId=?', (p, t))      # as a 0.3.9.34 install holds them
    s._exec("UPDATE task SET DueRaised='high' WHERE TaskId=?", (ids['urgent'],))
    assert s.migrate_priorities() == {'low': 1, 'normal': 1, 'high': 1}
    assert {p: s.get_task(t)['Priority'] for p, t in ids.items()} == {'low': 'regular', 'normal': 'regular', 'high': 'important', 'urgent': 'urgent'}
    kept = s._one("SELECT * FROM audit WHERE Action='priority_renamed' AND EntityId=?", (ids['low'],))
    assert json.loads(kept['Detail']) == {'from': 'low', 'to': 'regular'}, 'the one word that merged keeps what it was'
    assert s.get_task(ids['urgent'])['DueRaised'] == 'important' and s.migrate_priorities() == {}


def _mail(s, verdict, who=('Erin Blake', 'erin@northwind.example'), conv='c1', subject='Q4 hiring plan'):
    def llm(system, user, **k): return json.dumps({'intent': 'task', 'kind': 'task', 'why': 'an ask', 'title': subject, 'summary': 's', **verdict})
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': f'{conv}-{len(s.list_tasks())}', 'channel': 'email', 'from_email': who[1], 'from_name': who[0],
                                         'conversation_id': conv, 'subject': subject, 'body': 'Could you look at it before next Thursday?',
                                         'sent_at': '2026-10-20 09:00:00'}, llm=llm)


def test_important_lands_with_its_reason_and_urgent_as_it_always_did():
    s = MemoryStore()
    t = _mail(s, {'priority': 'important', 'priority_why': 'Important: from Erin Blake, your manager'})['task_id']
    assert s.get_task(t)['Priority'] == 'important'
    assert any(c['Body'] == 'Marked important - triage: from Erin Blake, your manager' for c in s.list_comments(t))
    u = _mail(s, {'priority': 'urgent', 'priority_why': 'Urgent: the bank needs it by noon'}, conv='c2', subject='Payroll file')['task_id']
    assert s.get_task(u)['Priority'] == 'urgent'
    old = _mail(s, {'urgent': True}, conv='c3', subject='Old contract')['task_id']
    assert s.get_task(old)['Priority'] == 'urgent', 'an answer to an older document says urgent: true'


def test_a_follow_up_raises_regular_to_important_never_urgent_down_and_never_over_the_owners_word():
    s = MemoryStore()
    t = _mail(s, {'priority': 'regular'})['task_id']
    _mail(s, {'priority': 'important', 'priority_why': 'Important: from your manager'})
    assert s.get_task(t)['Priority'] == 'important'
    s.update_task(t, {'Priority': 'urgent'}, 'triage'); _mail(s, {'priority': 'important'})
    assert s.get_task(t)['Priority'] == 'urgent', 'urgent is never lowered by important'
    v = _mail(s, {'priority': 'regular'}, conv='c9', subject='Other')['task_id']
    s.audit('task', v, 'priority', 'owner', detail={'from': 'important', 'to': 'regular'})
    _mail(s, {'priority': 'important'}, conv='c9', subject='Other')
    assert s.get_task(v)['Priority'] == 'regular', "the owner's own call stands"


def test_an_fyi_is_regular_whoever_sent_it():
    v = triage.classify_intent({'subject': 'x', 'body': 'y', 'from_email': 'erin@northwind.example'},
                               lambda *a, **k: json.dumps({'intent': 'fyi', 'why': 'x', 'priority': 'important', 'priority_why': 'Important: x'}))
    assert 'priority' not in v and 'urgent' not in v


def test_importance_never_moves_a_row():
    row = {'NeedsYou': 1, 'Channel': 'email', 'TaskId': 1}
    assert po.feed_band({**row, 'Priority': 'important'}) == po.feed_band({**row, 'Priority': 'regular'}) == 2
    assert po.feed_band({**row, 'Priority': 'urgent'}) == 1, "urgent's band is as it was"


def test_triage_reads_the_people_lines_about_this_mail_and_no_one_elses():
    s = C.priority_store(C.PRIORITY_CASES[0])
    doc = s.get_doc('learned').replace('## Your people\n', '## Your people\n' + C.GAIL_LINE + '\n', 1)
    s.save_doc('learned', doc, 'owner')
    got = learned_cut.for_reader(s, 'triage', people={'erin@northwind.example'})
    assert 'Erin Blake (erin@northwind.example)' in got and 'gail@northwind.example' not in got
    assert learned_cut.people_of({'from_email': 'Erin@Northwind.example', 'to': ['alex@northwind.example'], 'cc': ['gail@northwind.example']}) == \
           {'erin@northwind.example', 'alex@northwind.example', 'gail@northwind.example'}


def test_the_evalset_scores_priority_against_the_owners_own_hand():
    """The owner's hand-set priority is the label (evalset._priority_labels), and `evaluate` scores triage's against it - the
    honest yardstick on real mail, beside the invented boundaries (memory_cases)."""
    from taskuary import evalset
    s = MemoryStore()
    t = s.create_task({'Title': 'Q4 plan', 'Kind': 'task'}, 'triage')
    m = s.add_message({'ExternalId': 'q4', 'ConversationId': 'email:q4', 'Channel': 'email', 'Subject': 'Q4 plan', 'FromEmail': 'erin@northwind.example',
                       'FromName': 'Erin Blake', 'BodyText': 'Could you look at the plan?', 'SentAt': '2026-10-01 09:00:00', 'Status': 'routed', 'TaskId': t})
    s.add_route(m, t, 'create', None, 'promoted by the owner', [], 'owner')
    s.audit('task', t, 'priority', 'owner', detail={'from': 'regular', 'to': 'important'})
    cases = [c for c in evalset.build(s) if c['id'] == f'm{m}']
    assert cases and cases[0]['priority_label'] == 'important'
    out = evalset.evaluate(s, cases, lambda *a, **k: json.dumps({'intent': 'task', 'kind': 'task', 'why': 'x', 'title': 't', 'summary': 's',
                                                                 'priority': 'important', 'priority_why': 'Important: your manager'}), verbose=False)
    assert out['priority'] == {'n': 1, 'right': 1, 'confusion': {'important->important': 1}}
    assert set(evalset.MEMORY_ARMS) >= {'today', 'nopeople'}


def test_the_guide_asks_for_the_three_and_binds_them():
    assert 'priority' in triage.verdict_schema()['schema']['required'] and 'urgent' not in triage.verdict_schema()['schema']['properties']
    assert triage.verdict_schema()['schema']['properties']['priority']['enum'] == ['regular', 'important', 'urgent']
    for w in ('"urgent"', '"important"', '"regular"', 'priority_why', 'what a sender says about themselves'): assert w in triage.SHIPPED


# ── the owner's rulings on the three, 2026-10-25 ───────────────────────────────────────────────────────────────────────────
def test_the_phone_card_says_important_the_way_urgent_says_itself():
    from taskuary import remote_assistant as ra
    s = MemoryStore()
    tid = s.create_task({'Title': 'Q4 hiring plan', 'Kind': 'task', 'Status': 'open', 'Priority': 'important'}, 'triage')
    item = {'kind': 'asked', 'lane': 'asked', 'tid': tid, 'ref': 'TQ-0001', 'who': 'Erin Blake', 'channel': 'email', 'priority': 'important'}
    assert '(important)' in ra.story_block(s, item).split('\n')[0]
    assert '(important)' not in ra.story_block(s, {**item, 'priority': 'regular'})
    assert '(important)' in ra.story_block(s, {**item, 'priority': 'high'}).split('\n')[0], 'a task saved as high reads important'


def test_a_saved_dashboard_cuts_on_the_three_and_a_second_run_changes_nothing():
    from taskuary import dashboards as d
    s = MemoryStore()
    spec = {'type': 'dashboard', 'title': 'Mine',
            'sources': [{'key': 't', 'type': 'taskuary_data', 'dataset': 'tasks'}, {'key': 'q', 'type': 'sqlite', 'db': 'x.db', 'query': 'select 1'}],
            'components': [{'kind': 'stat', 'source': 't', 'where': {'priority': 'high', 'state': 'open'}},
                           {'kind': 'bar', 'source': 't', 'x': 'priority', 'order': ['low', 'normal', 'high', 'urgent']},
                           {'kind': 'stat', 'source': 'q', 'where': {'priority': 'high'}}]}
    sid = s.save_source({'Channel': 'report', 'Address': 'Mine', 'ConfigJson': json.dumps(spec)}, 'owner')
    assert d.migrate_priorities(s) == 1
    c = d.cfg_of(s.get_source(sid))['components']
    assert c[0]['where'] == {'priority': 'important', 'state': 'open'}
    assert c[1]['order'] == ['regular', 'important', 'urgent'], 'low and normal both land on regular, once'
    assert c[2]['where'] == {'priority': 'high'}, "another system's priority column keeps its own words"
    assert d.migrate_priorities(s) == 0


def test_a_workflow_step_opens_its_task_in_one_of_the_three():
    from taskuary import flow
    s, ctx = MemoryStore(), flow.context({'title': 'Weekly'}, 'manual', None)
    for said, lands in (('important', 'important'), ('high', 'important'), (None, 'regular')):
        rec = flow.run_step(s, {'id': 's1', 'kind': 'task', 'title': 'Check the bills', **({'priority': said} if said else {})}, ctx, None)
        assert s.get_task(rec['task_id'])['Priority'] == lands
    ok, why = flow.validate(s, [{'id': 's1', 'kind': 'task', 'title': 't', 'priority': 'critical'}])
    assert not ok and 'regular, important, urgent' in why
    from pathlib import Path
    ui = (Path(__file__).resolve().parents[1] / 'website' / 'src' / 'WorkflowSteps.jsx').read_text(encoding='utf-8')
    assert 'PRIORITIES.map((p)' in ui and 'value={level(step.priority)}' in ui
