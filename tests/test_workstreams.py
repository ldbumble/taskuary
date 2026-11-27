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


def test_an_agent_naming_another_profiles_mailbox_gets_the_one_move_card_and_nothing_is_drafted(two):
    f = Factory(two)
    t = f.task(title='Northwind close'); W.set_task(two, t, 'northwind', 'owner')
    out = slots.draft(two, t, 'Hi Gail,\n\nThe order is in.', to=GAIL, subject='Order', mailbox=HB_BOX)
    assert not out['ok'] and 'Harbor Bakery' in out['why'] and 'nothing was run' in out['why']
    cards = two._rows("SELECT * FROM review WHERE TaskId=? AND Status='pending'", (t,))
    assert [(json.loads(r['DraftText'])['action'], json.loads(r['DraftText'])['profile']) for r in cards] == [('move_profile', 'harbor-bakery')]
    assert cards[0]['NextStep'] == f'email {GAIL} from {HB_BOX}'                           # his press wakes the agent to do what it was doing
    slots.draft(two, t, 'Hi Gail,\n\nAgain.', to=GAIL, subject='Order', mailbox=HB_BOX)
    assert len(two._rows("SELECT 1 AS x FROM review WHERE TaskId=? AND Status='pending'", (t,))) == 1    # one card, however often it asks
    # ...his press is the move the task's own picker makes, and then the mailbox is the task's own
    from taskuary import proposals
    proposals.execute(two, cards[0], 'owner')
    assert two.get_task(t)['Workstream'] == 'harbor-bakery' and W.may_use(two, t, HB_BOX)
    assert slots.draft(two, t, 'Hi Gail,\n\nThe order is in.', to=GAIL, subject='Order', mailbox=HB_BOX)['ok']


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


def _draft_door(s): return lambda tid, text, to, subject, files, cc, mailbox, **kw: slots.draft(s, tid, text, to, subject, cc=cc, mailbox=mailbox, **kw)


def test_an_agent_is_told_only_its_own_profiles_accounts(two):
    """Walk 25: the wall stood at the call alone - Harbor's agent read Northwind's mailbox and its Outlook tools in list_systems as its own,
    and only found out at the call. What it is told it has is what it may use: one list, by the one wall."""
    from taskuary import agenttools, docsync
    two.save_connector({'ConnectorId': two.nw, 'Roles': 'trigger,tool'}, 't')          # Northwind's Outlook card runs tools (its calendar)
    f = Factory(two)
    nw, hb = f.task(title='Northwind close'), f.task(title='Bakery rota')
    W.set_task(two, nw, 'northwind', 'owner'); W.set_task(two, hb, 'harbor-bakery', 'owner')
    mine, theirs, his = docsync.agent_systems(two, tid=nw), docsync.agent_systems(two, tid=hb), docsync.agent_systems(two)
    assert 'Northwind mail' in mine and NW_BOX in mine and SHARED in mine and HB_BOX not in mine
    assert 'Northwind mail' not in theirs and NW_BOX not in theirs and HB_BOX in theirs and SHARED in theirs
    assert NW_BOX in his and HB_BOX in his                                             # a reader with no task (his own page) sees all of it
    said = agenttools.call(two, hb, 'list_systems', {}, {})
    assert NW_BOX not in said and 'Northwind mail' not in said and HB_BOX in said     # ...through the tool the agent asks with
    assert not agenttools.found('northwind', {'list_systems': 'what is connected', 'tick': 'tick a box'}, two, hb)       # ...and its tool search
    W.remove(two, 'harbor-bakery')
    assert NW_BOX in docsync.agent_systems(two, tid=hb)                                # one profile: every account is its own, as before


def test_a_reply_from_another_profiles_mailbox_is_the_same_move_card_never_an_ok_with_the_from_dropped(two):
    """Walk 25, two roads of three: "send the reply from my Northwind address" on Harbor's task - propose (kind reply, `from`) answered ok with
    the field dropped, the card said no From, and the agent told him it went from Northwind. One check for a From, an email's or a reply's."""
    from taskuary import agenttools, card, wrapup
    f = Factory(two)
    t = f.task(title='Flour order')
    f.message(task_id=t, from_email=PAULA, from_name='Paula Vance', source_name=HB_BOX, subject='Flour order', body='20 bags as usual?', channel='email')
    assert W.of_task(two, t) == 'harbor-bakery'
    reply = lambda tid, text, to='', files=(), **who: wrapup.agent_reply(two, tid, text, to=to, **who)
    say = lambda box: json.loads(agenttools.call(two, t, 'propose', {'kind': 'reply', 'text': 'Hi Paula,\n\n20 bags, as usual.', 'from': box}, {'reply': reply}))
    out = say(NW_BOX)
    assert not out['ok'] and 'Northwind' in out['why'] and 'nothing was run' in out['why']
    rows = two._rows("SELECT * FROM review WHERE TaskId=? AND Status='pending'", (t,))
    assert [json.loads(r['DraftText'])['action'] for r in rows if r['Kind'] == 'action'] == ['move_profile'] and card.carries_on(rows[-1], two)
    assert not [r for r in rows if r['Kind'] != 'action' and r['DraftText']]              # no letter was filed behind his back
    # ...a mailbox of his it may use, but not the one this mail came in on: the fact, and the way on - never a From the card would not keep
    out = say(SHARED)
    assert not out['ok'] and HB_BOX in out['why'] and 'kind email' in out['why']
    # ...and the one it does leave from is taken as said
    out = say(HB_BOX)
    assert out['ok'] and out['from'] == HB_BOX
    assert outbound.shown_from(two, two.get_review(out['review_id'])) == HB_BOX          # ...and its card says so, as its agent was told
    two.save_connector({'ConnectorId': two.nw, 'Active': 0}, 't'); two.save_connector({'ConnectorId': two.shared, 'Active': 0}, 't')
    assert outbound.shown_from(two, two.get_review(out['review_id'])) is None            # one mailbox: the card is as it was


def test_the_move_card_keeps_its_next_act_through_the_tool_door_so_his_press_wakes_the_agent(two):
    """Walk 25: the wall's move card carried the refused call as its `then` (slots.draft), and the tool door the call came in by cleared it
    (card.raising: the agent's own propose named none) - his Approve moved the task, woke nobody, and the email stayed owed under "agent done"."""
    from taskuary import agenttools, card
    f = Factory(two)
    t = f.task(title='Northwind close'); W.set_task(two, t, 'northwind', 'owner')
    out = json.loads(agenttools.call(two, t, 'propose', {'kind': 'email', 'to': GAIL, 'subject': 'Order', 'text': 'Hi Gail,\n\nThe order is in.', 'from': HB_BOX},
                                     {'draft': _draft_door(two)}))
    assert not out['ok'] and 'Harbor Bakery' in out['why']
    rv = two._rows("SELECT * FROM review WHERE TaskId=? AND Status='pending'", (t,))[0]
    assert json.loads(rv['DraftText'])['action'] == 'move_profile'
    assert card.then_of(rv) == f'email {GAIL} from {HB_BOX}' and card.carries_on(rv, two)
