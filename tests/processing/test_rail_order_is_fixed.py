"""THE RAIL IS ONE FIXED ORDER, AND NEXT WALKS DOWN IT (the owner, 2026-10-22): "They should be set by time, oldest to newest and then
never move." "On the table should never move them." "If you hit Next it jumps all over the place instead of moving down the line. If I
click on the bottom one then hit Next it should go to Reports, not jump back to Tasks. It should always be in order."

The rail showed 19h, 17h, 11h, <30m - and then 1h, the task on the table with its coding agent working: a row's place came from its
NEWEST activity (the last message on its thread, its agent's start or question), so a reply or an agent moved it. And Next took the
first walkable row of the whole rail, so from a clicked bottom task it went back up to a task the owner had not reached yet.

A row's place is the time it ARRIVED (its task's creation, else its first message), and Next takes the row directly below the one on
the table - the rest of Tasks, then Reports, then FYI - never one above it. Invented people only."""
from datetime import datetime, timedelta
from unittest import mock

import pytest

from taskuary import concierge, funnel, general, lanes
from taskuary import remote_assistant as ra
from taskuary.store import SQLiteStore


def ago(minutes=0): return (datetime.now() - timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')


def mail(store, title, minutes, tid=None, channel='email', cat=None, n=''):
    return store.add_message({'TaskId': tid, 'ExternalId': f'x:{title}{n}', 'ConversationId': f'c:{title}', 'Channel': channel,
                              'Subject': title, 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'SentAt': ago(minutes),
                              'BodyText': 'Please take a look.', 'Status': 'routed', **({'Category': cat} if cat else {})})


TASKS = (('Renew the vendor contract', 300), ('Review the portal export', 180), ('Investigate the mileage claims', 60))


@pytest.fixture
def db(tmp_path):
    store = SQLiteStore(str(tmp_path / 'order.db'))
    store.set_setting('funnel_hours', '72', 'fixture')
    funnel.invalidate(); funnel.forget_states()
    tids = []
    for title, m in TASKS:
        tids.append(store.create_task({'Title': title, 'Kind': 'task', 'Status': 'open'}, 'triage'))
        store._exec('UPDATE task SET CreatedAt=? WHERE TaskId=?', (ago(m), tids[-1]))
        mail(store, title, m, tids[-1])
    mail(store, 'Nightly job check', 120, channel='report')
    mail(store, 'Office closed Friday', 30, cat='info')
    settle(store)
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]): yield store, tids
    store.cx.close()


def settle(store):
    at = ago(); store.reconcile_processing_membership(fixed_now=at); store.activate_processing_reads(fixed_now=at, live_state=[])
    funnel.invalidate()


def rail(store, live=()):
    funnel.invalidate()
    return [i for i in funnel.build(store, live_state=list(live))['items'] if i.get('unread') or i.get('deferred')]


def keys(items): return [i['key'] for i in items]
def task_rows(store, live=()): return [i.get('tid') for i in rail(store, live) if lanes.level_of(i) == 'task']
def on_table(store): return concierge.current_key(store, general.dock_task(store, 'owner')[0]['TaskId']) or None


def test_the_rail_is_oldest_first_by_arrival_and_a_reply_does_not_move_a_row(db):
    store, tids = db
    assert task_rows(store) == tids, 'the tasks are not drawn oldest first'
    mail(store, TASKS[0][0], 1, tids[0], n=':again')           # a sender writes again on the OLDEST task
    settle(store)
    assert task_rows(store) == tids, 'a reply on a task moved its row'


def test_an_agent_starting_or_asking_does_not_move_its_row(db):
    store, tids = db
    working = {'taskId': tids[0], 'sid': 's1', 'agent': 'coding', 'started': ago(1), 'waiting': False, 'tail': []}
    assert task_rows(store, [working]) == tids, 'an agent at work moved its row'
    asking = working | {'waiting': True, 'state': 'asking', 'request': {'at': ago(0), 'kind': 'input_needed', 'text': 'Which file?'}}
    assert task_rows(store, [asking]) == tids, 'an agent asking moved its row'


def test_going_on_the_table_does_not_move_a_row(db):
    store, tids = db
    before = keys(rail(store))
    bottom = next(i for i in rail(store) if i.get('tid') == tids[-1])
    concierge.surface(store, bottom['key'])                    # the owner clicks the bottom task
    assert on_table(store) == bottom['key']
    assert keys(rail(store)) == before, 'putting a row on the table moved the rail'


def test_next_from_the_clicked_bottom_task_goes_to_the_first_report(db):
    store, tids = db
    items = rail(store)
    bottom = next(i for i in items if i.get('tid') == tids[-1])
    report = next(i for i in items if lanes.level_of(i) == 'reports')
    concierge.surface(store, bottom['key'])                    # clicked, never walked: the two tasks above are unseen
    out = concierge.surface(store, leaving=bottom['key'])
    assert out['item'] and out['item']['key'] == report['key'], f"Next went to {out['item'] and out['item'].get('title')}, not the report"


def test_next_never_moves_up(db):
    store, tids = db
    order = keys(rail(store))
    middle = next(i['key'] for i in rail(store) if i.get('tid') == tids[1])
    out = concierge.surface(store, middle)                     # start the walk from the middle task
    seen = [middle]
    while out['item']:
        out = concierge.surface(store, leaving=out['item']['key'])
        if out['item']: seen.append(out['item']['key'])
    at = [order.index(next(k for k in order if k in (key, *key[5:].split(',')))) for key in seen]
    assert at == sorted(at) and len(set(at)) == len(at), f'Next went back up: {seen} over {order}'
    assert not any(k for k in seen if next((i for i in rail(store) if i['key'] == k and i.get('tid') == tids[0]), None)), \
        'Next went back to a task above the one it started from'


def test_a_close_takes_the_walk_on_below_not_back_to_the_top(db):
    store, tids = db
    items = rail(store)
    middle = next(i for i in items if i.get('tid') == tids[1])
    concierge.surface(store, middle['key'])
    store.update_task(tids[1], {'Status': 'done'}, 'owner')    # Mark done: the row leaves the rail, the table is emptied
    funnel.settle(store, middle['key'], 'done', 'owner')
    concierge.set_current(store, general.dock_task(store, 'owner')[0]['TaskId'], None, 'owner')
    funnel.invalidate()
    out = concierge.surface(store)                             # the walk goes on after the close
    assert out['item'] and out['item'].get('tid') == tids[2], f"after the close the walk took {out['item'] and out['item'].get('title')}"


def test_the_phone_next_follows_the_same_order(db):
    store, tids = db
    items = rail(store)
    bottom = next(i for i in items if i.get('tid') == tids[-1])
    report = next(i for i in items if lanes.level_of(i) == 'reports')
    with concierge.delivering(concierge.PHONE):
        concierge.surface(store, bottom['key'])
        ra.run_act(store, {'t': 'next'}, bottom, 'owner')
    assert on_table(store) == report['key'], 'the phone Next did not go on from the bottom task to the first report'


def test_the_bottom_ends_the_walk_names_what_was_skipped_and_the_next_walk_starts_at_the_top(db):
    store, tids = db
    bottom = next(i for i in rail(store) if i.get('tid') == tids[-1])
    out = concierge.surface(store, bottom['key'])
    while out['item']: out = concierge.surface(store, leaving=out['item']['key'])
    assert out.get('over'), 'the walk did not end at the bottom'
    assert 'TQ-0001' in out['say'] and 'TQ-0002' in out['say'], f"the end line did not name the tasks skipped above: {out['say']}"
    assert out['chips'][0]['verb'] == 'walk' and [c['key'] for c in out['chips'][1:]][:2] == [i['key'] for i in rail(store) if i.get('tid') in tids[:2]]
    again = concierge.surface(store)
    assert again['item'] and again['item'].get('tid') == tids[0], 'the next walk did not start at the top'


def test_urgent_is_walked_in_its_place():
    """The owner, 2026-10-22: urgent sits in Tasks, never moves, and Next reaches it like every other row - "a meeting in 4 hours -
    once you hit Next on the item before it, it opens up, then you hit Next it goes to next, no jumping around"."""
    from taskuary.funnel_selection import below
    row = lambda key, band, h: {'key': key, 'lane': 'asked', 'kind': 'asked', 'order_band': band, 'arrived_at': ago(h * 60)}
    items = funnel._order([row('task:3', 2, 1), row('urgent:1', 1, 0), row('task:1', 2, 5), row('task:2', 2, 3)])
    assert keys(items) == ['task:1', 'task:2', 'task:3', 'urgent:1']
    assert keys(below(items, items, 'task:2')) == ['task:3', 'urgent:1']
    assert below(items, items, None) is None, 'a walk with nothing on the table and no place starts at the top'
