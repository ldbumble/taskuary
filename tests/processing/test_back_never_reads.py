"""BACK NEVER READS (the owner, 2026-10-29): a report opened from Reports, then Back on the bottom bar, was gone from the rail - putting
it on the table had read it, and a report read leaves the rail. Next reads what it walks away from and moves on; Back, opening, looking
and going elsewhere read nothing. Back is a pull of the row above with no `leaving` (AssistantView.goBack -> surface(key)), so the
report it leaves must still be unread on the rail. Invented people only."""
from datetime import datetime, timedelta
from unittest import mock

import pytest

from taskuary import concierge, funnel, lanes
from taskuary.store import SQLiteStore


def ago(minutes=0): return (datetime.now() - timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')


def mail(store, title, minutes, tid=None, channel='email', cat=None):
    return store.add_message({'TaskId': tid, 'ExternalId': f'x:{title}', 'ConversationId': f'c:{title}', 'Channel': channel,
                              'Subject': title, 'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example', 'SentAt': ago(minutes),
                              'BodyText': 'Have a look when you can.', 'Status': 'routed', **({'Category': cat} if cat else {})})


@pytest.fixture
def db(tmp_path):
    store = SQLiteStore(str(tmp_path / 'back.db'))
    store.set_setting('funnel_hours', '72', 'fixture')
    funnel.invalidate(); funnel.forget_states()
    tid = store.create_task({'Title': 'Renew the vendor contract', 'Kind': 'task', 'Status': 'open'}, 'triage')
    store._exec('UPDATE task SET CreatedAt=? WHERE TaskId=?', (ago(300), tid))
    mail(store, 'Renew the vendor contract', 300, tid)
    mail(store, 'Nightly job check', 120, channel='report')
    mail(store, 'Office closed Friday', 30, cat='info')
    at = ago(); store.reconcile_processing_membership(fixed_now=at); store.activate_processing_reads(fixed_now=at, live_state=[])
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]): yield store
    store.close()


def rail(store):
    funnel.invalidate()
    return [i for i in funnel.build(store, live_state=[])['items'] if i.get('unread') or i.get('deferred')]


def row(store, level): return next(i for i in rail(store) if lanes.level_of(i) == level)
def on_rail(store, key): return any(key in (i['key'], *i.get('aliases', ())) for i in rail(store))


@pytest.mark.parametrize('level', ['reports', 'fyi'])
def test_back_from_a_row_leaves_it_unread_on_the_rail_and_next_reads_it(db, level):
    store, it, task = db, row(db, level), row(db, 'task')
    concierge.surface(store, it['key'])
    assert on_rail(store, it['key']), f'opening the {level} row read it off the rail'
    with mock.patch.object(concierge, 'move_on', wraps=concierge.move_on) as read:
        concierge.surface(store, task['key'])                     # Back: the row above, pulled by key, nothing left behind
    read.assert_not_called()
    left = next((i for i in rail(store) if it['key'] in (i['key'], *i.get('aliases', ()))), None)
    assert left and left.get('unread'), f'Back marked the {level} row read: {left}'
    concierge.surface(store, it['key'])
    concierge.surface(store, leaving=it['key'])                   # Next on it: read, and gone from the rail
    assert not on_rail(store, it['key']), f'Next did not read the {level} row'


def test_a_task_opened_and_left_stays_on_the_rail(db):
    store, task, report = db, row(db, 'task'), row(db, 'reports')
    concierge.surface(store, task['key']); concierge.surface(store, report['key'])
    assert on_rail(store, task['key']) and on_rail(store, report['key'])


def test_only_a_task_is_read_by_being_opened():
    assert concierge.opened_reads({'order_band': 2, 'lane': 'todo'})
    assert not concierge.opened_reads({'order_band': 3, 'lane': 'report', 'kind': 'report'})
