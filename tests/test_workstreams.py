"""WORKSTREAMS (the design 2026-11-01, S2): Alex Doyle runs Northwind finance systems by day, the Ledger app with two friends over a chat
group, and has a personal life on the same phone. Each task, message and idea says which of those it is under; triage is told the list
and names one; the owner moves a task with its picker (or from Wrong here) and the move teaches who belongs where. Invented people only
(CLAUDE.md)."""
from unittest import mock
from fastapi.testclient import TestClient
import pytest
from taskuary import ingest, server, triage, workstreams as W
from taskuary.store import MemoryStore
from taskuary.testing import Factory

ERIN, OMAR, MOM = 'erin@northwind.example', 'omar@ledger.example', 'mom@family.example'
DAYJOB = {'name': 'Northwind finance systems', 'about': 'IT for finance at Northwind', 'domains': ['northwind.example'],
          'mailboxes': ['alex@northwind.example'], 'repos': ['northwind/ledger']}
LEDGER = {'name': 'Ledger app', 'about': 'a product Alex builds with two friends', 'channels': ['whatsapp:ledger crew'], 'people': [OMAR],
          'repos': ['org/app']}
HOME = {'name': 'Personal', 'personal': True, 'people': [MOM]}


@pytest.fixture
def s():
    s = MemoryStore()
    s.set_setting('owner_email', 'alex@northwind.example', 'test')
    W.save(s, [DAYJOB, LEDGER, HOME])
    return s


def test_the_list_is_kept_with_slugs_and_job_md_gets_an_index_and_a_section_per_work_workstream(s):
    assert [w['slug'] for w in W.streams(s)] == ['northwind-finance-systems', 'ledger-app', 'personal']
    assert W.personal(s) == {'personal'}
    job = s.get_doc('job')
    assert W.INDEX_START in job and '- **Ledger app** - a product Alex builds with two friends' in job
    assert '- **Personal** (personal: never learned from)' in job
    assert W.start('ledger-app') in job and W.start('northwind-finance-systems') in job and W.start('personal') not in job
    W.write_section(s, 'ledger-app', '- Omar Keller tests it; his bug reports become coding tasks')
    assert W.section(s, 'ledger-app') == '### Ledger app\n- Omar Keller tests it; his bug reports become coding tasks'
    W.upsert(s, {'name': 'Ledger app', 'people': ['marcus@ledger.example']})      # a machine merge never overwrites a written section
    assert 'Omar Keller tests it' in W.section(s, 'ledger-app') and 'marcus@ledger.example' in W.get(s, 'ledger-app')['people']


def test_an_item_is_placed_by_its_strongest_signal(s):
    xs = W.streams(s)
    group = {'Channel': 'whatsapp', 'SourceName': 'Ledger crew', 'FromEmail': 'someone@else.example'}
    assert W.by_signals(xs, group) == ('ledger-app', 'chat group')
    assert W.by_signals(xs, {'Channel': 'github', 'SourceName': 'org/app'}) == ('ledger-app', 'repository')
    assert W.by_signals(xs, {'Channel': 'whatsapp', 'SourceName': 'Mom', 'FromEmail': MOM}) == ('personal', 'people')
    assert W.by_signals(xs, {'Channel': 'email', 'SourceName': 'alex@northwind.example', 'FromEmail': OMAR}) == ('northwind-finance-systems', 'mailbox')
    assert W.by_signals(xs, {'Channel': 'email', 'SourceName': 'alex@other.example', 'FromEmail': ERIN}) == ('northwind-finance-systems', 'domain')
    # ...the owner's own mail is placed by whom it went to
    out = {'Channel': 'email', 'SourceName': 'alex@other.example', 'Direction': 'out', 'RecipientsJson': f'[{{"email": "{OMAR}"}}]'}
    assert W.by_signals(xs, out) == ('ledger-app', 'people')
    assert W.by_signals(xs, {'Channel': 'email', 'SourceName': 'x', 'FromEmail': 'stranger@nowhere.example'}) == ('', '')


def test_a_mailbox_two_workstreams_share_never_decides(s):
    W.upsert(s, {'name': 'Ledger app', 'mailboxes': ['alex@northwind.example']})
    m = {'Channel': 'email', 'SourceName': 'alex@northwind.example', 'FromEmail': OMAR}
    assert W.by_signals(W.streams(s), m) == ('ledger-app', 'people')


def test_a_message_follows_its_thread_and_a_task_its_messages(s):
    f = Factory(s)
    t = f.task(title='Export button greyed')
    first = f.message(task_id=t, channel='email', from_email=OMAR, conversation_id='email:export')
    W.stamp_message(s, first)
    later = f.message(task_id=t, channel='email', from_email='newtester@elsewhere.example', conversation_id='email:export')
    assert W.of_message(s, s.get_message(later)) == 'ledger-app'
    assert W.of_task(s, t) == 'ledger-app' and s.get_task(t)['Workstream'] == 'ledger-app'


def test_the_owner_moving_a_task_moves_its_messages_and_ideas_and_teaches_who_is_where(s):
    f = Factory(s)
    t = f.task(title='Q4 variance file')
    f.message(task_id=t, channel='email', from_email='paula@consultants.example', from_name='Paula Vance')
    s.upsert_idea({'key': 'idea:paula-variance', 'kind': 'idea', 'text': 'Paula asked twice', 'action': {'tid': t}}, '2026-11-01 09:00:00')
    out = W.set_task(s, t, 'northwind-finance-systems', 'owner')
    assert out == {'taskId': t, 'workstream': 'northwind-finance-systems', 'was': ''}
    assert s._one("SELECT Workstream FROM idea WHERE Key='idea:paula-variance'")['Workstream'] == 'northwind-finance-systems'
    assert 'paula@consultants.example' in W.get(s, 'northwind-finance-systems')['people']
    assert 'alex@northwind.example' not in W.get(s, 'northwind-finance-systems')['people']      # never the owner's own address
    W.set_task(s, t, 'ledger-app', 'owner')                          # moved again: the person moves with it
    assert 'paula@consultants.example' not in W.get(s, 'northwind-finance-systems')['people']
    assert 'paula@consultants.example' in W.get(s, 'ledger-app')['people']
    with pytest.raises(ValueError): W.set_task(s, t, 'made-up', 'owner')


def test_an_idea_takes_its_tasks_workstream(s):
    t = Factory(s).task(title='Ledger demo')
    W.set_task(s, t, 'ledger-app', 'owner')
    i = s.upsert_idea({'key': 'idea:demo', 'kind': 'idea', 'text': 'The demo clashes with the board prep', 'action': {'tid': t}}, '2026-11-01 09:00:00')
    assert i['Workstream'] == 'ledger-app'


def test_triage_is_shown_the_list_and_only_a_workstream_it_was_shown_counts(s):
    menu = W.menu(s)
    assert menu.splitlines()[1] == '- ledger-app: Ledger app - a product Alex builds with two friends'
    assert W.from_menu('ledger-app', menu) == 'ledger-app' and W.from_menu('board-seat', menu) == '' and W.from_menu(None, menu) == ''
    seen = {}
    def brain(system, user, **kw):
        seen['system'] = system
        return '{"intent": "task", "why": "a tester found a bug", "title": "Export button greyed", "summary": "Omar: export greyed", "kind": "task", ' \
               '"priority": "regular", "priority_why": "", "sender_class": "person", "workstream": "ledger-app"}'
    msg = {'subject': 'export is greyed', 'body': 'the export button is greyed out', 'from_email': OMAR, 'from_name': 'Omar Keller', 'channel': 'email'}
    v = triage.classify_intent(msg, llm=brain, workstreams=menu)
    assert v['workstream'] == 'ledger-app' and "THE OWNER'S WORKSTREAMS" in seen['system'] and '- personal: Personal (personal)' in seen['system']
    v = triage.classify_intent(msg, llm=lambda system, user, **kw: brain(system, user).replace('ledger-app', 'board-seat'), workstreams=menu)
    assert 'workstream' not in v
    assert 'workstream' not in triage.classify_intent(msg, llm=brain)            # no workstreams, nothing asked


def test_a_landed_message_and_its_task_are_placed_signals_first_then_triages_word(s):
    f = Factory(s)
    t = f.task(title='Lunch?')
    mid = f.message(task_id=t, channel='whatsapp', from_email=MOM, source_name='Mom')
    ingest._place(s, mid, t, said='ledger-app')                    # the people say personal; triage's guess does not override them
    assert (s.get_message(mid)['Workstream'], s.get_task(t)['Workstream']) == ('personal', 'personal')
    t2 = f.task(title='A new hire asks about the portal')
    mid2 = f.message(task_id=t2, channel='email', from_email='new@nowhere.example', source_name='alex@other.example')
    ingest._place(s, mid2, t2, said='northwind-finance-systems')   # nothing in the signals: triage places it
    assert s.get_task(t2)['Workstream'] == 'northwind-finance-systems'


def test_a_rail_task_row_carries_its_tasks_workstream_and_an_idea_keeps_its_own(s):
    from taskuary import funnel
    f = Factory(s)
    t = f.task(title='Export greyed'); W.set_task(s, t, 'ledger-app', 'owner')
    u = f.task(title='Unplaced')
    items = [{'key': f'task:{t}', 'tid': t}, {'key': f'task:{u}', 'tid': u}, {'key': 'idea:1', 'tid': t, 'workstream': 'northwind-finance-systems'}]
    funnel._label_workstreams(s, items)
    assert [i.get('workstream') for i in items] == ['ledger-app', None, 'northwind-finance-systems']


def test_the_api_lists_workstreams_moves_a_task_and_the_task_carries_its_label(s):
    t = Factory(s).task(title='Export button greyed')
    with mock.patch.object(server, 'store', s):
        c = TestClient(server.app)
        assert [w['slug'] for w in c.get('/api/workstreams').json()['data']] == ['northwind-finance-systems', 'ledger-app', 'personal']
        r = c.put(f'/api/tasks/{t}/workstream', json={'workstream': 'ledger-app'})
        assert r.status_code == 200 and r.json()['label'] == {'slug': 'ledger-app', 'name': 'Ledger app', 'personal': False}
        assert c.get(f'/api/tasks/{t}').json()['workstream']['name'] == 'Ledger app'
        assert c.put(f'/api/tasks/{t}/workstream', json={'workstream': 'nope'}).status_code == 422
