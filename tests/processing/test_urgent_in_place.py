"""NO URGENT SECTION, AND REPORTS OLDEST FIRST (the owner, 2026-10-22): "reports should go oldest first like everything else", and
"urgent can skip line. Should we also remove the urgent section and just add quiet shading around it for urgent notice?" - yes.

An urgent row - a meeting inside fifteen minutes, an ask triage called urgent, a sender on the escalate list - sits in its own section
at the place its arrival gives it, and never moves; the page shades it. Next reaches it in its place like any other row (the owner, later that day: "urgent is combined into tasks and
it never moves ... you go through it like all other tasks"), never jumps to it, and a walk starts at the top. Invented people only."""
from datetime import datetime, timedelta
from unittest import mock

import pytest

from taskuary import concierge, funnel, general, lanes
from taskuary import remote_assistant as ra
from taskuary.store import SQLiteStore


def ago(minutes=0): return (datetime.now() - timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')


def mail(store, title, minutes, tid=None, channel='email', cat=None):
    return store.add_message({'TaskId': tid, 'ExternalId': f'x:{title}', 'ConversationId': f'c:{title}', 'Channel': channel,
                              'Subject': title, 'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example', 'SentAt': ago(minutes),
                              'BodyText': 'Please take a look.', 'Status': 'routed', **({'Category': cat} if cat else {})})


# the urgent one arrived LAST: by arrival it is the bottom of Tasks
TASKS = (('Renew the vendor contract', 300, 'normal'), ('Review the portal export', 180, 'normal'),
         ('Investigate the mileage claims', 60, 'normal'), ('Payroll file rejected', 10, 'urgent'))
REPORTS = (('Nightly job check', 240), ('Morning error check', 20))


@pytest.fixture
def db(tmp_path):
    store = SQLiteStore(str(tmp_path / 'urgent.db'))
    store.set_setting('funnel_hours', '72', 'fixture')
    funnel.invalidate(); funnel.forget_states()
    tids = []
    for title, m, pri in TASKS:
        tids.append(store.create_task({'Title': title, 'Kind': 'task', 'Status': 'open', 'Priority': pri}, 'triage'))
        store._exec('UPDATE task SET CreatedAt=? WHERE TaskId=?', (ago(m), tids[-1]))
        mail(store, title, m, tids[-1])
    for title, m in REPORTS: mail(store, title, m, channel='report')
    settle(store)
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]): yield store, tids
    store.cx.close()


def settle(store):
    at = ago(); store.reconcile_processing_membership(fixed_now=at); store.activate_processing_reads(fixed_now=at, live_state=[])
    funnel.invalidate()


def rail(store):
    funnel.invalidate()
    return [i for i in funnel.build(store, live_state=[])['items'] if i.get('unread') or i.get('deferred')]


def keys(items): return [i['key'] for i in items]
def on_table(store): return concierge.current_key(store, general.dock_task(store, 'owner')[0]['TaskId']) or None


def test_reports_are_listed_oldest_first(db):
    store, _ = db
    reports = [i['title'] for i in rail(store) if lanes.level_of(i) == 'reports']
    assert reports == [t for t, _ in REPORTS], f'reports are not oldest first: {reports}'


def test_reports_order_key_is_oldest_first_like_every_section():
    row = lambda key, h: {'key': key, 'lane': 'report', 'kind': 'report', 'order_band': 3, 'arrived_at': ago(h * 60)}
    assert keys(funnel._order([row('report:new', 1), row('report:old', 5)])) == ['report:old', 'report:new']


def test_there_is_no_urgent_section():
    assert 'urgent' not in lanes.LEVEL_ORDER and 'urgent' not in funnel.SECTION_WORDS
    assert lanes.level_of({'lane': 'time', 'order_band': 1}) == 'task'
    assert lanes.level_of({'lane': 'asked', 'urgent_request': True}) == 'task'
    assert lanes.is_urgent({'lane': 'asked', 'urgent_request': True}) and not lanes.is_urgent({'lane': 'asked'})


def test_an_urgent_task_sits_in_tasks_at_its_arrival_and_is_marked_urgent(db):
    store, tids = db
    items = rail(store)
    tasks = [i for i in items if lanes.level_of(i) == 'task']
    assert [i.get('tid') for i in tasks] == tids, 'an urgent task did not take its arrival place in Tasks'
    urgent = next(i for i in tasks if i.get('tid') == tids[-1])
    assert lanes.is_urgent(urgent) and not any(lanes.is_urgent(i) for i in tasks if i is not urgent)
    assert not any(lanes.level_of(i) == 'urgent' for i in items)


def test_next_walks_the_urgent_task_in_its_place_like_any_other(db):
    # the owner, 2026-10-22: "urgent is combined into tasks and it never moves ... you go through it like all other tasks"
    store, tids = db
    items = rail(store)
    row = {i.get('tid'): i['key'] for i in items if i.get('tid')}
    order = [i.get('tid') for i in items if i.get('tid') in tids]
    concierge.surface(store, row[order[0]])                     # the owner opens the top task
    seen, out = [order[0]], concierge.surface(store, leaving=row[order[0]])
    while out.get('item') and out['item'].get('tid') in tids:
        seen.append(out['item']['tid']); out = concierge.surface(store, leaving=out['item']['key'])
    assert seen == order, f"Next did not walk the tasks in rail order, urgent included: {seen} vs {order}"
    assert out['item'] and lanes.level_of(out['item']) == 'reports'

def test_a_walk_starts_at_the_top_not_at_the_urgent_row(db):
    store, tids = db
    order = [i.get('tid') for i in rail(store) if i.get('tid') in tids]
    out = concierge.surface(store)
    assert out['item'] and out['item'].get('tid') == order[0], f"the walk did not start at the top: {out['item'] and out['item'].get('title')}"

def test_below_takes_the_urgent_row_in_its_place():
    from taskuary.funnel_selection import below
    row = lambda key, band, h: {'key': key, 'lane': 'asked', 'kind': 'asked', 'order_band': band, 'arrived_at': ago(h * 60)}
    items = funnel._order([row('task:3', 2, 1), row('urgent:1', 1, 2), row('task:1', 2, 5), row('task:2', 2, 3)])
    assert keys(items) == ['task:1', 'task:2', 'urgent:1', 'task:3'], 'an urgent row is not at its arrival place'
    assert keys(below(items, items, 'task:1')) == ['task:2', 'urgent:1', 'task:3'], 'Next jumped to the urgent row'
    ready = [i for i in items if i['key'] not in ('task:1', 'task:2', 'urgent:1')]
    assert keys(below(items, ready, 'urgent:1')) == ['task:3'], 'after the urgent row Next did not go on below it'

def test_the_phone_summary_still_counts_urgent(db):
    store, tids = db
    said = ra.who_wants_what(rail(store), store)
    assert '1 urgent' in said, said
    assert 'URGENT ·' not in said and 'TASKS · 4' in said, said
