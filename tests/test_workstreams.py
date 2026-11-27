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


# ── PROFILES (the owner, 2026-11-26): a profile's accounts, the arrival they decide, and the one wall ─────────────────────────────────
# Alex Doyle works at Northwind and runs Harbor Bakery on the side: a mailbox each, tagged to its profile, and one mailbox nobody tagged.
import json
from taskuary import mailsearch, outbound, slots

NW_BOX, HB_BOX, SHARED = 'alex@northwind.example', 'alex@harbor.example', 'alex@home.example'
GAIL, PAULA = 'gail@harbor.example', 'paula@vendor.example'


@pytest.fixture
def two():
    s = MemoryStore()
    s.set_setting('owner_email', NW_BOX, 'test')
    W.save(s, [{'name': 'Northwind'}, {'name': 'Harbor Bakery'}])
    card = lambda t, name, box: s.save_connector({'Type': t, 'Name': name, 'Active': 1, 'ConfigJson': json.dumps({'address': box})}, 't')
    s.nw, s.hb, s.shared = card('outlook', 'Northwind mail', NW_BOX), card('imap', 'Harbor mail', HB_BOX), card('imap', 'Home mail', SHARED)
    W.tag_account(s, 'northwind', connector_id=s.nw); W.tag_account(s, 'harbor-bakery', connector_id=s.hb)
    return s


def test_mail_into_a_tagged_mailbox_is_that_profiles_whatever_its_thread_and_no_model_reads_the_hat(two):
    f = Factory(two)
    t = f.task(title='Flour order')
    first = f.message(task_id=t, from_email=GAIL, source_name=NW_BOX, conversation_id='conv-flour')
    ingest._place(two, first, t)
    assert two.get_message(first)['Workstream'] == 'northwind'
    # ...the same thread, now into Harbor's mailbox: the account decides, never the thread's stamp or triage's word
    later = f.message(from_email=GAIL, source_name=HB_BOX, conversation_id='conv-flour')
    ingest._place(two, later, None, said='northwind')
    assert two.get_message(later)['Workstream'] == 'harbor-bakery'
    seen = []
    def brain(system, user, **kw):
        seen.append("THE OWNER'S WORKSTREAMS" in system)
        return '{"intent": "fyi", "why": "a note", "title": "Flour", "summary": "x", "priority": "regular", "priority_why": "", "sender_class": "person"}'
    msg = {'subject': 'flour', 'body': 'two sacks', 'from_email': GAIL, 'from_name': 'Gail Moreno', 'channel': 'email'}
    for box in (HB_BOX, SHARED): ingest._classify(two, {**msg, 'source_name': box}, brain, {}, None, '', '', 0, (), None)
    assert seen == [False, True]                                  # only mail on an untagged account is put to the model with the list


def test_an_untagged_account_serves_every_profile_and_a_tagged_one_only_its_own(two):
    f = Factory(two)
    nw, hb, none = f.task(title='Northwind close'), f.task(title='Bakery rota'), f.task(title='Unplaced')
    W.set_task(two, nw, 'northwind', 'owner'); W.set_task(two, hb, 'harbor-bakery', 'owner')
    assert W.of_account(two, two.hb) == W.of_account(two, HB_BOX) == 'harbor-bakery' and W.of_account(two, SHARED) == ''
    assert [W.may_use(two, t, two.shared) for t in (nw, hb, none)] == [True, True, True]
    assert [W.may_use(two, t, HB_BOX) for t in (nw, hb, none)] == [False, True, False]
    assert [m['address'] for m in outbound.mailboxes(two, nw)] == [NW_BOX, SHARED]        # what its agent may send from
    assert [m['address'] for m in outbound.mailboxes(two)] == [NW_BOX, HB_BOX, SHARED]    # his own picker: all of them
    with pytest.raises(ValueError): W.tag_account(two, 'no-such-profile', connector_id=two.hb)


# AN EMAIL FROM HIS OTHER PROFILE'S MAILBOX IS ONE CARD, ONE PRESS (the card-tool design, 2026-11-27, the owner's written OK to change locked
# rules 1 and 2): it was a move card, a wake, a new proposal and then Send. The email card carries the From the agent asked for and says
# its press moves the task, and from where; his one press moves it and sends. Nothing goes before that press - the wall still holds
def test_an_email_from_another_profiles_mailbox_is_one_card_whose_one_press_moves_the_task_and_sends(two):
    f = Factory(two)
    t = f.task(title='Northwind close'); W.set_task(two, t, 'northwind', 'owner')
    out = slots.draft(two, t, 'Hi Gail,\n\nThe order is in.', to=GAIL, subject='Order', mailbox=HB_BOX)
    assert out['ok'] and out['from'] == HB_BOX and 'Northwind' in out['moves'] and 'Harbor Bakery' in out['moves'], out
    cards = two._rows("SELECT * FROM review WHERE TaskId=? AND Status='pending'", (t,))
    assert [r['Kind'] for r in cards] == [slots.KIND], 'no move card: the email is the one card'
    rv = two.get_review(out['review_id'])
    assert outbound.shown_from(two, rv) == HB_BOX and W.press_moves(two, rv) == {'from': 'Northwind', 'to': 'Harbor Bakery'}
    assert two.get_task(t)['Workstream'] == 'northwind', 'nothing moves before his press'
    got, boxes = _sent(two, out['review_id'])
    assert got['ok'] and boxes == [HB_BOX] and two.get_task(t)['Workstream'] == 'harbor-bakery', got
    assert W.press_moves(two, two.get_review(out['review_id'])) is None


def test_his_no_on_an_email_from_another_profile_moves_nothing(two):
    f = Factory(two)
    t = f.task(title='Northwind close'); W.set_task(two, t, 'northwind', 'owner')
    out = slots.draft(two, t, 'Hi Gail,\n\nThe order is in.', to=GAIL, subject='Order', mailbox=HB_BOX)
    got, boxes = _sent(two, out['review_id'], 'reject')
    assert got['ok'] and boxes == [] and two.get_task(t)['Workstream'] == 'northwind'


def test_a_reply_leaves_from_the_tasks_own_profile_and_an_agents_search_reads_no_other_profiles_mail(two):
    f = Factory(two)
    t = f.task(title='Supplier question')
    mid = f.message(task_id=t, from_email=GAIL, from_name='Gail Moreno', source_name=NW_BOX, subject='Supplier invoice', body='the invoice for flour')
    f.message(from_email=GAIL, from_name='Gail Moreno', source_name=HB_BOX, subject='Bakery invoice', body='the invoice for ovens')
    W.set_task(two, t, 'harbor-bakery', 'owner')                  # he moves it: its answer is Harbor's now, from Harbor's mailbox
    assert outbound.sending_mailbox(two, {'TaskId': t}, two.get_message(mid)) == HB_BOX
    other = f.task(title='Northwind audit'); W.set_task(two, other, 'northwind', 'owner')
    assert {h['subject'] for h in mailsearch.search(two, words='invoice')} == {'Supplier invoice', 'Bakery invoice'}       # his own search
    assert [h['subject'] for h in mailsearch.search(two, words='invoice', tid=other)] == ['Supplier invoice']       # ...and a Northwind agent's: the mail in Northwind's mailbox


def test_with_one_profile_nothing_is_labelled_picked_or_walled(two):
    f = Factory(two)
    t = f.task(title='Bakery rota'); W.set_task(two, t, 'northwind', 'owner')
    assert W.label(two, 'northwind') and len(W.shown(two)) == 2
    W.remove(two, 'harbor-bakery')
    assert W.shown(two) == [] and W.label(two, 'northwind') is None            # no label by a title, no picker on a card or a task
    assert W.of_account(two, HB_BOX) == '' and W.may_use(two, t, HB_BOX)       # ...and every account is the one profile's
    with mock.patch.object(server, 'store', two):
        c = TestClient(server.app)
        assert c.get('/api/workstreams').json()['data'] == [] and c.get(f'/api/tasks/{t}').json()['workstream'] is None
    from taskuary import funnel
    items = [{'key': f'task:{t}', 'tid': t}]
    funnel._label_workstreams(two, items)
    assert 'workstream' not in items[0]


def test_a_removed_profile_leaves_no_stamp_behind(two):
    f = Factory(two)
    t = f.task(title='Bakery rota'); W.set_task(two, t, 'harbor-bakery', 'owner')
    W.upsert(two, {'name': 'Ledger app'})                         # a third, so two are still kept after the removal
    W.remove(two, 'harbor-bakery')
    assert two.get_task(t)['Workstream'] == '' and two.get_connector(two.hb)['Workstream'] == ''
    assert W.may_use(two, f.task(title='Northwind close'), HB_BOX)


def test_the_card_picker_tags_an_account_through_the_api(two):
    with mock.patch.object(server, 'store', two):
        c = TestClient(server.app)
        assert c.put(f'/api/connectors/{two.shared}/workstream', json={'workstream': 'harbor-bakery'}).json() == {'workstream': 'harbor-bakery'}
        assert next(x for x in c.get('/api/connectors').json()['data'] if x['ConnectorId'] == two.shared)['Workstream'] == 'harbor-bakery'
        assert c.put(f'/api/connectors/{two.shared}/workstream', json={'workstream': ''}).status_code == 200 and W.of_account(two, SHARED) == ''
        assert c.put(f'/api/connectors/{two.shared}/workstream', json={'workstream': 'nope'}).status_code == 422


def test_about_you_adds_a_profile_by_name_with_one_kept_too(two):
    "The owner's yes, 2026-11-26: the second profile is made by naming it on About you - there was no way to one but the mail's own grouping."
    W.remove(two, 'harbor-bakery')
    with mock.patch.object(server, 'store', two):
        c = TestClient(server.app)
        r = c.post('/api/about/workstreams', json={'name': '  Harbor   Bakery '})
        assert r.status_code == 200 and [x['name'] for x in json.loads(r.json()['text'])] == ['Northwind', 'Harbor Bakery']
        assert [w['slug'] for w in W.shown(two)] == ['northwind', 'harbor-bakery'] and W.start('harbor-bakery') in two.get_doc('job')
        assert c.post('/api/about/workstreams', json={'name': 'harbor bakery'}).status_code == 422       # one name, one profile
        assert c.post('/api/about/workstreams', json={'name': '  '}).status_code == 422
        # ...one he unticked is put by, not gone: with one profile left nothing is picked or walled, and naming it again brings it back
        W.tag_account(two, 'harbor-bakery', connector_id=two.hb)
        c.put('/api/about/workstreams', json={'items': [{'slug': 'harbor-bakery', 'keep': False}]})
        assert W.shown(two) == [] and W.may_use(two, Factory(two).task(title='Northwind close'), HB_BOX)
        r = c.post('/api/about/workstreams', json={'name': 'Harbor Bakery'})
        assert r.status_code == 200 and [w['slug'] for w in W.shown(two)] == ['northwind', 'harbor-bakery']
        assert W.of_account(two, HB_BOX) == 'harbor-bakery'                    # ...its accounts still its own


def test_an_agent_is_told_only_its_own_profiles_accounts(two):
    """Walk 25: the wall stood at the call alone - Harbor's agent read Northwind's mailbox and its Outlook tools in list_systems as its own,
    and only found out at the call. What it is told it has is what it may use: one list, by the one wall."""
    from taskuary import agenttools, docsync
    two.save_connector({'ConnectorId': two.nw, 'Roles': 'trigger,tool'}, 't')          # Northwind's Outlook card runs tools (its calendar)
    f = Factory(two)
    nw, hb = f.task(title='Northwind close'), f.task(title='Bakery rota')
    W.set_task(two, nw, 'northwind', 'owner'); W.set_task(two, hb, 'harbor-bakery', 'owner')
    OTHER = 'CONNECTED UNDER HIS OTHER PROFILES'
    usable = lambda t: t.split(OTHER)[0]                                               # ...what it may use: everything above that one line
    mine, theirs, his = docsync.agent_systems(two, tid=nw), docsync.agent_systems(two, tid=hb), docsync.agent_systems(two)
    assert 'Northwind mail' in usable(mine) and NW_BOX in usable(mine) and SHARED in usable(mine) and HB_BOX not in usable(mine)
    assert 'Northwind mail' not in usable(theirs) and NW_BOX not in usable(theirs) and HB_BOX in usable(theirs) and SHARED in usable(theirs)
    assert NW_BOX in his and HB_BOX in his and OTHER not in his                        # a reader with no task (his own page) sees all of it
    said = agenttools.call(two, hb, 'list_systems', {}, {})
    assert NW_BOX not in usable(said) and 'Northwind mail' not in usable(said) and HB_BOX in usable(said)     # ...through the tool the agent asks with
    W.remove(two, 'harbor-bakery')
    assert NW_BOX in docsync.agent_systems(two, tid=hb) and OTHER not in docsync.agent_systems(two, tid=hb)   # one profile: every account is its own, as before


def test_the_wall_says_what_is_connected_under_the_other_profile_and_nothing_of_what_it_holds(two):
    """Walk 26, the real Codex CLI on a Harbor task asked to answer from his Northwind address: told Harbor's accounts alone, it said "Taskuary
    has only your Harbor mailbox connected. Can you connect alex@northwind.example?" - a mailbox that was connected, under his other profile.
    The wall hides what an account holds, never that it is there: the other profile's accounts are named beside the list, with what a call
    on one comes to."""
    from taskuary import agenttools, docsync
    f, hb, nw, mine, theirs = _both(two)
    said = agenttools.call(two, hb, 'list_systems', {}, {})
    line = next(l for l in said.splitlines() if l.startswith('CONNECTED UNDER HIS OTHER PROFILES'))
    assert 'this task is under Harbor Bakery' in line and f'Northwind - {NW_BOX}' in line and 'Northwind mail' in line and 'whose press moves this task there' in line
    assert HB_BOX not in line and SHARED not in line and 'Payroll invoice' not in said and GAIL not in said      # its own and the shared are no other's; no mail of theirs
    assert f'Harbor Bakery - {HB_BOX}' in next(l for l in docsync.agent_systems(two, tid=nw).splitlines() if l.startswith('CONNECTED UNDER'))
    free = f.task(title='Payroll form for the accountant')                             # under no profile: both are another's, and it is told so
    assert 'this task is under no profile' in docsync.agent_systems(two, tid=free) and NW_BOX in docsync.agent_systems(two, tid=free)
    assert agenttools.found('northwind', {'list_systems': 'what is connected', 'tick': 'tick a box'}, two, hb)   # ...and a search for it finds where it is


def test_an_agents_memory_lookup_reads_no_other_profiles_people(two):
    """Walk 26: `owner_memory` on a Harbor task listed Northwind's people - every address on record, whatever was asked about. A person all of
    whose mail is in another profile's accounts is that profile's (the one wall); a lookup that names nobody answers with nobody's addresses."""
    from taskuary import agenttools, ledger, memory
    f, hb, nw, mine, theirs = _both(two)
    for who in (GAIL, PAULA): ledger.write(two, 'address', who, '', 'mailed', f'rv-{who}')
    memory.remember(two, 'Gail signs off payroll before it runs.', subject='payroll sign-off', about=GAIL)
    memory.remember(two, 'Paula delivers flour on Tuesdays.', subject='flour delivery', about=PAULA)
    memory.remember(two, 'Never write before 8 am.', subject='hours')
    his, harbor, northwind = memory.lookup(two), agenttools.call(two, hb, 'owner_memory', {}, {}), agenttools.call(two, nw, 'owner_memory', {}, {})
    assert GAIL in his and PAULA in his and 'payroll' in his and 'flour' in his        # his own read, and the Assistant's: all of it
    assert GAIL not in harbor and 'payroll' not in harbor and PAULA in harbor and 'Paula delivers flour' in harbor and 'Never write before 8 am' in harbor
    assert PAULA not in northwind and 'flour' not in northwind and GAIL in northwind and 'Gail signs off payroll' in northwind and 'Never write before 8 am' in northwind
    # ...asked about a subject, which names no one, it lists nobody's addresses (it listed every one on record)
    about = agenttools.call(two, hb, 'owner_memory', {'about': 'Harbor Bakery flour order holiday'}, {})
    assert GAIL not in about and PAULA not in about and 'holds nothing about' in about
    # ...and asked about someone of the other profile it says where they are known from, never "nothing"
    gail = agenttools.call(two, hb, 'owner_memory', {'about': GAIL}, {})
    assert 'another of his profiles' in gail and 'payroll' not in gail
    assert 'Paula delivers flour' in agenttools.call(two, hb, 'owner_memory', {'about': PAULA}, {})
    W.remove(two, 'harbor-bakery')                                                      # one profile: as before
    assert GAIL in agenttools.call(two, hb, 'owner_memory', {}, {}) and 'Gail signs off payroll' in agenttools.call(two, hb, 'owner_memory', {'about': GAIL}, {})


def test_a_reply_from_another_profiles_mailbox_is_one_card_whose_press_moves_the_task_and_sends_from_it(two):
    """Walk 25, two roads of three: "send the reply from my Northwind address" on Harbor's task - propose (kind reply, `from`) answered ok with
    the field dropped, the card said no From, and the agent told him it went from Northwind. One check for a From, an email's or a reply's -
    and the card carries it (the owner's OK, 2026-11-27): his one press moves the task to Northwind and sends from there."""
    from taskuary import agenttools, wrapup
    f = Factory(two)
    t = f.task(title='Flour order')
    f.message(task_id=t, from_email=PAULA, from_name='Paula Vance', source_name=HB_BOX, subject='Flour order', body='20 bags as usual?', channel='email')
    assert W.of_task(two, t) == 'harbor-bakery'
    reply = lambda tid, text, to='', files=(), **who: wrapup.agent_reply(two, tid, text, to=to, **who)
    say = lambda box: json.loads(agenttools.call(two, t, 'propose', {'kind': 'reply', 'text': 'Hi Paula,\n\n20 bags, as usual.', 'from': box}, {'reply': reply}))
    out = say(NW_BOX)
    assert out['ok'] and out['from'] == NW_BOX and 'Northwind' in out['moves'], out
    rows = two._rows("SELECT * FROM review WHERE TaskId=? AND Status='pending'", (t,))
    assert [r['Kind'] for r in rows] == ['draft_reply'] and W.press_moves(two, rows[0]) == {'from': 'Harbor Bakery', 'to': 'Northwind'}
    assert outbound.shown_from(two, rows[0]) == NW_BOX
    got, boxes = _sent(two, rows[0]['ReviewId'])
    assert got['ok'] and boxes == [NW_BOX] and W.of_task(two, t) == 'northwind', (got, boxes)


def test_a_reply_from_its_own_mailbox_and_a_shared_one(two):
    from taskuary import agenttools, wrapup
    f = Factory(two)
    t = f.task(title='Flour order')
    f.message(task_id=t, from_email=PAULA, from_name='Paula Vance', source_name=HB_BOX, subject='Flour order', body='20 bags as usual?', channel='email')
    reply = lambda tid, text, to='', files=(), **who: wrapup.agent_reply(two, tid, text, to=to, **who)
    say = lambda box: json.loads(agenttools.call(two, t, 'propose', {'kind': 'reply', 'text': 'Hi Paula,\n\n20 bags, as usual.', 'from': box}, {'reply': reply}))
    # ...a mailbox of his it may use, but not the one this mail came in on: the fact, and the way on - never a From the card would not keep
    out = say(SHARED)
    assert not out['ok'] and HB_BOX in out['why'] and 'kind email' in out['why']
    # ...and the one it does leave from is taken as said
    out = say(HB_BOX)
    assert out['ok'] and out['from'] == HB_BOX
    assert outbound.shown_from(two, two.get_review(out['review_id'])) == HB_BOX          # ...and its card says so, as its agent was told
    two.save_connector({'ConnectorId': two.nw, 'Active': 0}, 't'); two.save_connector({'ConnectorId': two.shared, 'Active': 0}, 't')
    assert outbound.shown_from(two, two.get_review(out['review_id'])) is None            # one mailbox: the card is as it was


# ── THE WALL ON WHAT AN AGENT READS, AND ON A NEW EMAIL'S FROM (the red team, round 6) ───────────────────────────────────────────────────
def _both(two):
    "A Harbor task and a Northwind one, each profile with mail of its own on one thread."
    f = Factory(two)
    hb, nw = f.task(title='Bakery rota'), f.task(title='Northwind close')
    W.set_task(two, hb, 'harbor-bakery', 'owner'); W.set_task(two, nw, 'northwind', 'owner')
    theirs = f.message(from_email=GAIL, from_name='Gail Moreno', source_name=NW_BOX, subject='Payroll invoice', body='the payroll invoice, salaries in it',
                       conversation_id='conv-inv')
    mine = f.message(from_email=PAULA, from_name='Paula Vance', source_name=HB_BOX, subject='Flour invoice', body='the invoice for flour', conversation_id='conv-inv')
    return f, hb, nw, mine, theirs


def _calendars(two):
    "A calendar each: Northwind's Outlook card reads its mailbox's, and Harbor has an Outlook card of its own. Returns Harbor's (card, mailbox)."
    cid, box = two.save_connector({'Type': 'outlook', 'Name': 'Harbor calendar', 'Active': 1, 'ConfigJson': '{}'}, 't'), 'shop@harbor.example'
    W.tag_account(two, 'harbor-bakery', connector_id=cid)
    for c, a in ((two.nw, NW_BOX), (cid, box)): two.save_source({'Name': a, 'Address': a, 'Channel': 'email', 'ConnectorId': c, 'Active': 1}, 't')
    return cid, box


def test_an_agents_own_tools_read_no_other_profiles_mail_thread_or_file(two, tmp_path):
    """The red team, round 6: the wall stood at the shell's search alone. The agent's own tools - search_messages, read_message by any id,
    the thread a message of its own is on, read_attachment by any id - read another profile's mailbox. One check for a mail read
    (mailsearch.mine), asked by every door."""
    from taskuary import agenttools, general
    f, hb, nw, mine, theirs = _both(two)
    note = tmp_path / 'payroll.txt'; note.write_text('salaries: 1 2 3')
    aid = two.add_attachment({'MessageId': theirs, 'Name': 'payroll.txt', 'ContentType': 'text/plain', 'Path': str(note)})
    said = agenttools.call(two, hb, 'search_messages', {'words': 'invoice'}, {})
    assert 'Flour invoice' in said and 'Payroll' not in said
    for name, args in (('read_message', {'id': theirs}), ('read_attachment', {'id': aid})):
        with pytest.raises(ValueError) as e: agenttools.call(two, hb, name, args, {})
        assert 'Northwind' in str(e.value) and 'nothing was run' in str(e.value) and 'salaries' not in str(e.value)
    cards = two._rows("SELECT * FROM review WHERE TaskId=? AND Status='pending'", (hb,))
    assert [json.loads(r['DraftText'])['action'] for r in cards] == ['move_profile']             # never a flat no: the one card, however often
    read = agenttools.call(two, hb, 'read_message', {'id': mine}, {})
    assert 'the invoice for flour' in read and 'Payroll' not in read                              # ...its own, without the other mailbox's part of the thread
    assert [h['subject'] for h in mailsearch.message(two, mine, hb)['messages']] == ['Flour invoice']
    assert len(mailsearch.message(two, mine)['messages']) == 2                                    # his own read: the whole thread
    # ...Northwind's own agent reads its file, and a task reads its own mail whichever mailbox it came in on (he moved it: its brief shows it)
    assert 'salaries' in agenttools.call(two, nw, 'read_attachment', {'id': aid}, {})
    two._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (hb, theirs))
    assert 'salaries in it' in agenttools.call(two, hb, 'read_message', {'id': theirs}, {})
    # ...and the Assistant on the rail is his, across every profile
    dock = general.dock_task(two)[0]['TaskId']
    assert W.may_use(two, dock, NW_BOX) and W.may_use(two, dock, HB_BOX)


def test_an_agents_calendar_tool_reads_only_its_own_profiles_calendars(two):
    "Round 6: the calendar tool an agent calls read every calendar the cards reach - the shell's door alone handed it the task."
    from datetime import timedelta
    from taskuary import agenttools, calendar
    _, box = _calendars(two)
    hb = Factory(two).task(title='Bakery rota'); W.set_task(two, hb, 'harbor-bakery', 'owner')
    day = lambda cfg, sec, boxes, start, end, tz: [{'start': f'{start + timedelta(days=1):%Y-%m-%d} 10:00', 'end': f'{start + timedelta(days=1):%Y-%m-%d} 11:00',
                                                    'who': [], 'all_day': False, 'status': 'busy', 'where': '', 'subject': f'Standup of {boxes[0]}'}]
    with mock.patch.object(calendar, 'outlook_events', day):
        said = agenttools.call(two, hb, 'calendar', {'days': 7}, {})
        assert f'Standup of {box}' in said and NW_BOX not in said
        W.remove(two, 'harbor-bakery')                                                # one profile: every calendar is read, as before
        said = agenttools.call(two, hb, 'calendar', {'days': 7}, {})
        assert f'Standup of {box}' in said and f'Standup of {NW_BOX}' in said


def test_a_meeting_an_agent_sets_up_goes_on_a_calendar_its_task_may_use(two):
    "Round 6, the same class: the invite an agent set up went on the first Outlook card's calendar, whoever's task it was."
    from taskuary import calwrite
    cid, box = _calendars(two)
    f = Factory(two)
    hb, none = f.task(title='Bakery rota'), f.task(title='Unplaced')
    W.set_task(two, hb, 'harbor-bakery', 'owner')
    assert calwrite.account(two)['mailbox'] == NW_BOX                                  # his own New -> Meeting: the first card, as before
    assert calwrite.account(two, tid=hb)['mailbox'] == box and not calwrite.can_book(two, none)
    board = [{'start': '2030-01-07 10:00', 'end': '2030-01-07 11:00', 'subject': 'Northwind board', 'who': []}]
    with mock.patch.object(calwrite, 'busy', lambda s, days=14, sure=False, tid=None: [] if tid else board), mock.patch.object(calwrite, 'require_write'):
        out = calwrite.meeting(two, hb, [GAIL], 'Rota', start='2030-01-07 10:00', end='2030-01-07 10:30')
    env = calwrite.env_of(two.get_review(out['review']))
    assert env['mailbox'] == box and env['connector_id'] == cid
    assert 'clashes with another meeting' in out['says'] and 'Northwind board' not in out['says']     # the time is his; whose meeting is not said


def test_an_agents_search_across_tasks_shows_its_own_profiles_work(two):
    "Round 6, the same class: search_tasks answered with the other profile's tasks and its mail, by another door than the mail search."
    from taskuary import agenttools, people
    f, hb, nw, mine, theirs = _both(two)
    two._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (nw, theirs))
    free = f.task(title='Payroll form for the accountant')                             # under no profile: everyone's
    said = agenttools.call(two, hb, 'search_tasks', {'words': 'payroll'}, {})
    assert 'accountant' in said and 'Payroll invoice' not in said and 'Northwind close' not in said
    said = agenttools.call(two, nw, 'search_tasks', {'words': 'payroll'}, {})
    assert 'accountant' in said and 'Payroll invoice' in said
    assert not people.tasks_of(two, GAIL, skip=hb) and [t['title'] for t in people.tasks_of(two, GAIL, skip=free)] == []
    assert [t['title'] for t in people.tasks_of(two, GAIL)] == ['Northwind close']       # his own read
    W.remove(two, 'harbor-bakery')                                                      # one profile: as before
    assert 'Payroll invoice' in agenttools.call(two, hb, 'search_tasks', {'words': 'payroll'}, {})
    assert [t['title'] for t in people.tasks_of(two, GAIL, skip=hb)] == ['Northwind close']


def test_with_a_card_for_each_profile_an_agents_call_runs_on_its_own(two):
    "A tool card for each profile was 'say which with connector_id' to an agent that may use one of them: the task's own is picked by code."
    from taskuary import reports
    books = lambda name: two.save_connector({'Type': 'quickbooks', 'Name': name, 'Active': 1, 'Roles': 'tool', 'ConfigJson': '{}'}, 't')
    nwb, hbb = books('Northwind books'), books('Harbor books')
    W.tag_account(two, 'northwind', connector_id=nwb); W.tag_account(two, 'harbor-bakery', connector_id=hbb)
    f = Factory(two)
    hb = f.task(title='Bakery rota'); W.set_task(two, hb, 'harbor-bakery', 'owner')
    t = next(k for k in reports.REGISTRY if reports.card_of(k) == 'quickbooks')
    assert reports.tool_card(two, t, tid=hb)['ConnectorId'] == hbb
    with pytest.raises(ValueError): reports.tool_card(two, t)                           # with no task to go by, he is asked which
    with pytest.raises(ValueError): reports.tool_card(two, t, tid=f.task(title='Unplaced'))
    W.remove(two, 'harbor-bakery')
    with pytest.raises(ValueError): reports.tool_card(two, t, tid=hb)                   # one profile: two cards are two cards, as before


def _sent(two, rid, verb='approve'):
    "Press Send on card `rid` with the provider stood in: (what the press answered, the mailbox each send left from)."
    from taskuary import verdicts
    with mock.patch.object(outbound, 'send_out', return_value={'channel': 'email', 'to': [GAIL]}) as send:
        out = verdicts.decide(two, two.get_review(rid), verb)
    return out, [c.kwargs.get('mailbox') for c in send.call_args_list]


def test_a_new_email_with_no_from_leaves_from_its_tasks_own_profile_never_the_first_card(two):
    """Round 6: a new email on a task no mail came in on named no From, and left from the first Outlook card - Northwind's, on Harbor's task.
    It leaves from its task's own profile's mailbox, else one every profile shares; with neither it is refused with the fact and the place
    a mailbox is connected - at the draft for its agent, and at the press for a card that already stood."""
    f = Factory(two)
    hb = f.task(title='Bakery rota'); W.set_task(two, hb, 'harbor-bakery', 'owner')
    letter = lambda t, **kw: slots.draft(two, t, 'Hi Gail,\n\nThe rota is up.', to=GAIL, subject='Rota', **kw)
    out = letter(hb)
    assert out['ok'] and out['from'] == HB_BOX == outbound.new_from(two, hb)          # its agent is told where it goes from, and its card says so
    assert _sent(two, out['review_id'])[1] == [HB_BOX]
    # ...Harbor's mailbox gone: the one nobody tagged serves every profile
    two.save_connector({'ConnectorId': two.hb, 'Active': 0}, 't')
    out = letter(hb, slot='new')
    assert out['ok'] and out['from'] == SHARED
    # ...and that one gone too: only Northwind's is left. The card that stood is not sent from it - the failure stays on it, with its fix
    two.save_connector({'ConnectorId': two.shared, 'Active': 0}, 't')
    res, boxes = _sent(two, out['review_id'])
    assert boxes == [] and not res['ok'] and 'Harbor Bakery' in res['send_error'] and res['send_fix'] == {'label': outbound.MAIL[0], 'href': outbound.MAIL[1]}
    assert two.get_review(out['review_id'])['Status'] == 'pending'
    no = letter(hb, slot='new')
    assert not no['ok'] and 'Harbor Bakery' in no['why'] and 'Nothing was drafted' in no['why'] and outbound.MAIL[1] in no['why']
    # ...a task under no profile is kept from every profile's own mailbox the same way; naming one in From is its move card, as before
    assert not letter(f.task(title='Unplaced'), slot='new')['ok']


def test_with_one_profile_a_new_email_and_every_read_are_as_they_were(two):
    "One profile, or none: nothing is walled - a new email with no From names none and the sender's own first card decides, as before."
    from taskuary import agenttools
    f, hb, nw, mine, theirs = _both(two)
    W.remove(two, 'harbor-bakery')
    for t in (hb, nw, f.task(title='Unplaced')):
        assert outbound.new_from(two, t) is None and [m['address'] for m in outbound.mailboxes(two, t)] == [NW_BOX, HB_BOX, SHARED]
        said = agenttools.call(two, t, 'search_messages', {'words': 'invoice'}, {})
        assert 'Flour invoice' in said and 'Payroll invoice' in said
        assert 'salaries in it' in agenttools.call(two, t, 'read_message', {'id': theirs}, {})
        assert len(mailsearch.message(two, mine, t)['messages']) == 2
    out = slots.draft(two, hb, 'Hi Gail,\n\nThe rota is up.', to=GAIL, subject='Rota')
    assert out['ok'] and 'from' not in out
    assert _sent(two, out['review_id'])[1] == [None]
    W.save(two, [])                                                                    # ...and with no profile at all
    assert outbound.new_from(two, hb) is None and W.may_use(two, hb, NW_BOX)


# ── A PROFILE HOLDS SEVERAL MAILBOXES, AND A MOVED TASK ANSWERS FROM ITS NEW PROFILE'S (the owner, 2026-11-27) ─────────────────────────
# Northwind has two mailboxes (Alex's own and the accounts desk he also reads), Harbor Bakery one. A mailbox is not a profile.
AP_BOX = 'accounts@northwind.example'


@pytest.fixture
def hats():
    s = MemoryStore()
    s.set_setting('owner_email', NW_BOX, 'test')
    W.save(s, [{'name': 'Northwind'}, {'name': 'Harbor Bakery'}])
    def card(t, name, box, ws):
        c = s.save_connector({'Type': t, 'Name': name, 'Active': 1, 'ConfigJson': json.dumps({'address': box})}, 't')
        W.tag_account(s, ws, connector_id=c)
        return c
    s.nw, s.ap, s.hb = card('outlook', 'Northwind mail', NW_BOX, 'northwind'), card('imap', 'Accounts desk', AP_BOX, 'northwind'), card('imap', 'Harbor mail', HB_BOX, 'harbor-bakery')
    return s


def _asked(hats, box, ws):
    "Gail's mail into mailbox `box`, its task under profile `ws`, and the reply card that waits on it: (task, mail, card)."
    f = Factory(hats)
    t = f.task(title='Flour order')
    mid = f.message(task_id=t, from_email=GAIL, from_name='Gail Moreno', source_name=box, subject='Flour order', body='Twenty sacks as usual?\nGail')
    W.set_task(hats, t, ws, 'owner')
    return t, mid, f.review(t, mid, kind='draft_reply', draft='Hi Gail,\n\nTwenty, as usual.')


def _press(hats, rid):
    "Press Send on card `rid` with both providers stood in: (the answer, the replies in a thread, the new emails)."
    from taskuary import verdicts
    with mock.patch.object(outbound, 'reply_to_message', return_value={'channel': 'email', 'to': [GAIL]}) as reply, \
         mock.patch.object(outbound, 'send_out', return_value={'channel': 'email', 'to': [GAIL]}) as new, \
         mock.patch.object(outbound, 'send_block', return_value=''), mock.patch('taskuary.learning.learn_from'):
        out = verdicts.decide(hats, hats.get_review(rid), 'approve')
    return out, reply.call_args_list, new.call_args_list


def test_a_moved_tasks_reply_leaves_from_its_new_profiles_mailbox_as_a_new_email_on_the_same_subject(hats):
    """His ruling: "if you change profile of a item it should go out from the new profile if it's connected to email". The thread lives in the
    old mailbox, so it is a new email - same people, Re: its subject, the mail it answers quoted - and the card raised before the move says
    the new From before his press."""
    t, mid, rid = _asked(hats, HB_BOX, 'harbor-bakery')
    assert outbound.shown_from(hats, hats.get_review(rid)) == HB_BOX
    W.set_task(hats, t, 'northwind', 'owner')
    # ...Northwind has two; the thread came in on neither, so its first - on the card, in what its agent is told, under its signature
    rv = hats.get_review(rid)
    assert outbound.shown_from(hats, rv) == outbound.leaves_from(hats, rv) == outbound.sending_mailbox(hats, rv, hats.get_message(mid)) == NW_BOX
    out, replies, new = _press(hats, rid)
    assert out['ok'] and not replies and len(new) == 1                     # never a reply in Harbor's thread, from Harbor's mailbox
    (_, ch, to, subject, body), kw = new[0].args, new[0].kwargs
    assert (ch, to, subject, kw['mailbox']) == ('email', [GAIL], 'Re: Flour order', NW_BOX)
    assert body.startswith('Hi Gail,\n\nTwenty, as usual.') and 'Gail Moreno' in body and '> Twenty sacks as usual?' in body
    went = [m for m in hats.list_messages(t) if m.get('Direction') == 'out']
    assert [(m['SourceName'], m['BodyText']) for m in went] == [(NW_BOX, 'Hi Gail,\n\nTwenty, as usual.')]      # kept as he approved it, from where it left


def test_a_task_moved_back_answers_in_its_thread_from_the_mailbox_it_came_in_on_not_the_profiles_first(hats):
    "Several mailboxes in the new profile, and one is where the thread came in: that one is kept, and it is a reply in its thread."
    t, mid, rid = _asked(hats, AP_BOX, 'northwind')
    W.set_task(hats, t, 'harbor-bakery', 'owner')
    assert outbound.leaves_from(hats, hats.get_review(rid)) == HB_BOX
    W.set_task(hats, t, 'northwind', 'owner')
    assert outbound.shown_from(hats, hats.get_review(rid)) == AP_BOX and [m['address'] for m in outbound.mailboxes(hats, t)] == [NW_BOX, AP_BOX]
    out, replies, new = _press(hats, rid)
    assert out['ok'] and not new and [c.args[1]['MessageId'] for c in replies] == [mid]


def test_a_task_moved_to_a_profile_with_no_mailbox_says_so_on_its_card_and_never_sends_from_the_old_one(hats):
    "No mailbox under the new profile: the card says it before the press, with the way past it (connect one, or move back); a press sends nothing."
    t, mid, rid = _asked(hats, NW_BOX, 'northwind')
    hats.save_connector({'ConnectorId': hats.hb, 'Active': 0}, 't')
    assert not outbound.review_connect(hats, hats.get_review(rid))
    W.set_task(hats, t, 'harbor-bakery', 'owner')
    fix = outbound.review_connect(hats, hats.get_review(rid))
    assert 'Harbor Bakery' in fix['says'] and 'back to Northwind' in fix['says'] and (fix['label'], fix['href']) == outbound.MAIL
    assert outbound.leaves_from(hats, hats.get_review(rid)) is None
    out, replies, new = _press(hats, rid)
    assert not out['sent'] and not replies and not new and 'Harbor Bakery' in out['send_error'] and out['send_fix'] == {'label': outbound.MAIL[0], 'href': outbound.MAIL[1]}
    assert hats.get_review(rid)['Status'] == 'pending' and hats.get_review(rid)['DeliveryState'] == 'failed'
    W.set_task(hats, t, 'northwind', 'owner')                              # ...moved back: the reply it was, in its thread
    assert not outbound.review_connect(hats, hats.get_review(rid))
    out, replies, new = _press(hats, rid)
    assert out['ok'] and len(replies) == 1 and not new


def test_a_press_on_a_card_drawn_before_the_move_sends_nothing_until_it_is_read_again(hats):
    "Locked rule 2: a page still showing From Harbor's mailbox presses after the move - nothing runs, and the card is shown as it stands."
    from taskuary import proposals
    t, mid, rid = _asked(hats, HB_BOX, 'harbor-bakery')
    drawn = lambda: {'to': None, 'cc': None, 'subject': None, 'mailbox': None, 'attachments': [], 'from': outbound.shown_from(hats, hats.get_review(rid))}
    old = drawn()
    assert old['from'] == HB_BOX and proposals.unlike_shown(hats.get_review(rid), old, 'approve', hats) is None
    W.set_task(hats, t, 'northwind', 'owner')
    with mock.patch.object(outbound, 'reply_to_message') as reply, mock.patch.object(outbound, 'send_out') as new:
        out = server.press_review(hats, rid, server.DecideBody(verb='approve', shown=old))
    assert out['changed'] and out['send_error'] == proposals.CHANGED and not reply.called and not new.called
    assert proposals.unlike_shown(hats.get_review(rid), drawn(), 'approve', hats) is None                 # read again, it goes
    assert proposals.unlike_shown(hats.get_review(rid), {'to': None}, 'approve', hats) is None            # a page that drew no From is held to none


def test_an_agents_reply_on_a_moved_task_is_told_the_from_its_card_shows(hats):
    "What the agent is told and what a `from` is checked against are the card's own From: the new profile's mailbox, once moved."
    from taskuary import wrapup
    t, mid, rid = _asked(hats, HB_BOX, 'harbor-bakery')
    W.set_task(hats, t, 'northwind', 'owner')
    out = wrapup.agent_reply(hats, t, 'Hi Gail,\n\nTwenty, as usual.', mailbox=NW_BOX)
    assert out['ok'] and out['from'] == NW_BOX == outbound.shown_from(hats, hats.get_review(out['review_id']))
