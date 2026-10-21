"""NEXT ON AN OPEN TASK IS ONCE PER WALK (the owner, 2026-10-21): "next keeps a task on unless it's closed. It does not have to come
back. once it saw it, unless it starts a new walk it goes on through reports/fyi etc. if it starts over you see same list of tasks
again."

So Next on an open task marks it seen in THIS walk: it stays under Tasks and the walk goes on - the rest of Tasks, then reports and
FYIs. There is no clock bringing it back (it came back after task_return_minutes). When the walk runs out, or a new one starts (a
new chat), every task still open comes up again, from the top, in the rail's order. A closed one does not.
"""
from datetime import datetime, timedelta
from unittest import mock

import pytest

from taskuary import concierge, funnel, lanes
from taskuary.store import SQLiteStore


def ago(minutes=0): return (datetime.now() - timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')


@pytest.fixture
def db(tmp_path):
    store = SQLiteStore(str(tmp_path / 'walk.db'))
    store.set_setting('funnel_hours', '72', 'fixture')
    funnel.invalidate(); funnel.forget_states()
    tids = []
    for title, m in (('Renew the vendor contract', 90), ('Review the portal export', 60)):
        tids.append(store.create_task({'Title': title, 'Kind': 'task', 'Status': 'open'}, 'triage'))
        mail(store, title, m, tids[-1])
    mail(store, 'Office closed Friday', 30, cat='info')
    at = ago(); store.reconcile_processing_membership(fixed_now=at); store.activate_processing_reads(fixed_now=at, live_state=[])
    funnel.invalidate()
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]): yield store, tids
    store.cx.close()


def mail(store, title, minutes, tid=None, cat=None):
    store.add_message({'TaskId': tid, 'ExternalId': f'x:{title}', 'ConversationId': f'c:{title}', 'Channel': 'email', 'Subject': title,
                       'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'SentAt': ago(minutes),
                       'BodyText': 'Please take a look.', 'Status': 'routed', **({'Category': cat} if cat else {})})


def rail(store, now=None):
    funnel.invalidate()
    return funnel.build(store, now=now, live_state=[])['items']


def tasks(store, now=None): return {i['tid']: i for i in rail(store, now) if i.get('tid')}


def walk(store, n):
    """Walk me through my tasks, then Next n-1 times: the keys put on the table, in order. The last stays on the table."""
    out = concierge.surface(store); keys = [out['item'] and out['item']['key']]
    while len(keys) < n and out['item']:
        out = concierge.surface(store, leaving=out['item']['key']); keys.append(out['item'] and out['item']['key'])
    return keys, out


def tid_of(store, key): return next((i.get('tid') for i in rail(store) if i['key'] == key), None)


def test_next_on_two_tasks_goes_on_to_the_fyi_and_both_stay_in_tasks(db):
    store, tids = db
    keys, _ = walk(store, 3)
    assert [tid_of(store, k) for k in keys[:2]] == tids, 'the walk did not start on the tasks, in the rail order'
    assert keys[2].startswith('fyis:'), f'after both tasks the walk did not go on to the FYI: {keys}'
    held = tasks(store)
    assert set(held) == set(tids), 'Next took an open task off the rail'
    assert all(lanes.level_of(held[t]) == 'task' for t in tids), 'a task walked past left Tasks'
    assert not any(held[t]['actionable'] for t in tids), 'the walk would offer a task it already passed in this walk'


def test_no_clock_brings_a_passed_task_back_inside_the_walk(db):
    store, tids = db
    walk(store, 3)
    later = tasks(store, now=datetime.now() + timedelta(hours=5))
    assert not any(later[t]['actionable'] for t in tids), 'the quiet hours brought a task back in the middle of the walk'
    assert not any(later[t].get('back_at') for t in tids), 'a task walked past still promises a time it comes back'


def test_finishing_the_walk_brings_every_open_task_up_again_from_the_top(db):
    store, tids = db
    keys, end = walk(store, 4)
    assert keys[3] is None and end.get('over'), f'the walk did not run out: {keys}'
    again, _ = walk(store, 2)
    assert [tid_of(store, k) for k in again] == tids, 'the next walk did not start again on the open tasks, in rail order'


def test_a_new_walk_brings_every_open_task_up_again(db):
    store, tids = db
    walk(store, 3)                                  # both tasks passed, the FYI on the table: the walk not finished
    funnel.reset_walk(store)                        # a new chat starts a new walk
    again, _ = walk(store, 2)
    assert [tid_of(store, k) for k in again] == tids, 'a new walk did not show the open tasks again'


def test_a_closed_task_does_not_come_up_again(db):
    store, tids = db
    walk(store, 4)
    store.update_task(tids[0], {'Status': 'done'}, 'owner')
    funnel.invalidate()
    again, _ = walk(store, 1)
    assert tid_of(store, again[0]) == tids[1], 'a closed task came back in the next walk'
    assert tids[0] not in tasks(store), 'a closed task is still on the rail'
