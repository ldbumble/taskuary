"""The rail re-projects only the roots a write touched (processing_rail), and what it shows never differs
from a cold build. Every dirty table, written through the store AND through a second connection (another
process), must move the right card and leave every other projection the same object."""
import sqlite3
from datetime import datetime, timedelta

import pytest

from taskuary import funnel, terminal, processing_rail
from taskuary.store import SQLiteStore

NOW = datetime(2026, 9, 17, 12, 0, 0)


@pytest.fixture
def db(tmp_path, monkeypatch):
    s = SQLiteStore(str(tmp_path / 'rail.db'))
    s.set_setting('calendar_enabled', '0', 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [])
    s.reconcile_processing_membership()
    s.activate_processing_reads(fixed_now=NOW.isoformat(), live_state=[])
    funnel.invalidate()
    yield s
    funnel.invalidate()
    s.cx.close()


def mail(s, n, *, tid=None, sent=None):
    return s.add_message({'ExternalId': f'rail:{n}', 'ConversationId': f'rail-thread:{n}', 'TaskId': tid,
                          'Channel': 'email', 'SourceName': 'fixture@example.test', 'FromName': f'Person {n}',
                          'FromEmail': f'p{n}@example.test', 'Subject': f'Rail {n}', 'BodyText': f'Body {n}',
                          'Status': 'filed', 'SentAt': sent or (NOW - timedelta(minutes=n)).strftime('%Y-%m-%d %H:%M:%S')})


def read(s, *, days=14, now=NOW):
    s.reconcile_processing_membership()
    return s.processing_inventory_snapshot(fixed_now=now.isoformat(), live_state=[], display_only=True, history_days=days)


def cold(s, *, days=14, now=NOW):
    s._processing_display_cache = {}
    return read(s, days=days, now=now)


def by_member(snapshot, member):
    return next(i for i in snapshot['items'] if member in i['member_ids'])


def projections(snapshot):
    """item_id -> the projection object behind the reader copy (messages list identity stands in for it)"""
    return {i['item_id']: id(i['view']['messages']) for i in snapshot['items']}


def same_except(before, after, *changed):
    b, a = projections(before), projections(after)
    kept = set(b) & set(a) - set(changed)
    assert all(b[k] == a[k] for k in kept), 'an untouched root was re-projected'
    assert all(b[k] != a[k] for k in changed if k in b), 'the touched root was NOT re-projected'


def equal_to_cold(s, snapshot, **kw):
    fresh = cold(s, **kw)
    strip = lambda snap: [{k: v for k, v in i.items() if k != 'item'} for i in snap['items']]
    assert strip(snapshot) == strip(fresh) and snapshot['coverage'] == fresh['coverage']


def other(s):
    """A second connection: what a write from the sync process or the membership worker looks like."""
    cx = sqlite3.connect(s.cx.execute('PRAGMA database_list').fetchone()[2], timeout=5.0)
    cx.row_factory = sqlite3.Row
    return cx


def test_a_receipt_re_projects_one_root_and_the_rest_are_the_same_objects(db):
    mids = [mail(db, n) for n in range(1, 6)]
    first = read(db)
    target = by_member(first, f'message:{mids[2]}')
    funnel.settle(db, 'processing:' + target['item_id'], 'surfaced', read=True)
    second = read(db)
    same_except(first, second, target['item_id'])
    from taskuary.processing_reads import state
    assert state(by_member(second, f'message:{mids[2]}'), NOW)['unread'] is False
    equal_to_cold(db, second)


@pytest.mark.parametrize('write', [
    pytest.param(lambda s, mid, tid, pid: s._exec('UPDATE message SET Subject=? WHERE MessageId=?', ('Rail 3 (edited)', mid)), id='message'),
    pytest.param(lambda s, mid, tid, pid: s.update_task(tid, {'Status': 'in_progress'}, 'fixture'), id='task'),
    pytest.param(lambda s, mid, tid, pid: s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'reply', 'Status': 'pending', 'DraftText': 'D'}), id='review'),
    pytest.param(lambda s, mid, tid, pid: s.add_comment(tid, 'coder', 'agent', 'Finished.'), id='comment'),
    pytest.param(lambda s, mid, tid, pid: s.add_transcript(tid, 'sid-1', 'worked', agent='coder'), id='transcript'),
    pytest.param(lambda s, mid, tid, pid: s.set_funnel_state(f'processing:{pid}', 'surfaced'), id='funnel_state'),
    pytest.param(lambda s, mid, tid, pid: s.tag_task(tid, terminal.INTERRUPTED, True, 'shutdown'), id='task-tag'),
])
def test_each_kind_of_write_moves_its_card_and_only_its_card(db, write):
    mids = [mail(db, n) for n in range(1, 6)]
    tid = db.create_task({'Title': 'Rail task', 'Assignee': 'agent:coder', 'Kind': 'coding'}, 'fixture')
    db._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (tid, mids[2]))
    first = read(db)
    target = by_member(first, f'message:{mids[2]}')
    write(db, mids[2], tid, target['item_id'])
    second = read(db)
    same_except(first, second, target['item_id'])
    equal_to_cold(db, second)


def test_a_write_from_another_process_is_seen_the_same_way(db):
    mids = [mail(db, n) for n in range(1, 6)]
    first = read(db)
    target = by_member(first, f'message:{mids[1]}')
    cx = other(db)
    cx.execute('UPDATE message SET Subject=? WHERE MessageId=?', ('Rail 2 (from the sync)', mids[1])); cx.commit(); cx.close()
    second = read(db)
    same_except(first, second, target['item_id'])
    assert by_member(second, f'message:{mids[1]}')['view']['messages'][0]['Subject'] == 'Rail 2 (from the sync)'
    equal_to_cold(db, second)


def test_nothing_written_means_nothing_re_projected_and_a_reconcile_pass_writes_nothing(db):
    [mail(db, n) for n in range(1, 4)]
    first = read(db)
    db.reconcile_processing_membership()          # a no-op pass: the census has nothing to file
    second = db.processing_inventory_snapshot(fixed_now=NOW.isoformat(), live_state=[], display_only=True, history_days=14)
    same_except(first, second)
    assert first['snapshot_revision'] == second['snapshot_revision']


def test_a_root_leaves_the_window_and_a_new_one_enters(db):
    old = mail(db, 1, sent='2020-01-01 09:00:00')
    db._exec('UPDATE message SET CreatedAt=? WHERE MessageId=?', ('2020-01-01 09:00:00', old))
    first = read(db)
    assert all(f'message:{old}' not in i['member_ids'] for i in first['items'])
    new = mail(db, 2)
    db._exec('UPDATE message SET CreatedAt=? WHERE MessageId=?', (NOW.strftime('%Y-%m-%d %H:%M:%S'), new))
    second = read(db)
    assert by_member(second, f'message:{new}')
    same_except(first, second)
    equal_to_cold(db, second)
    # ...and the window itself moving (a later day) rebuilds against the new cutoff
    later = read(db, now=NOW + timedelta(days=15))
    assert later['items'] == []


def test_a_trimmed_dirty_log_rebuilds_in_full_and_matches_a_cold_build(db):
    mids = [mail(db, n) for n in range(1, 4)]
    first = read(db)
    db._exec('UPDATE message SET Subject=? WHERE MessageId=?', ('Rail 1 (edited)', mids[0]))
    # the rows between the rail's mark and now vanish (what an ancient rail sees after a trim)
    db._exec('DELETE FROM processing_dirty_row WHERE Id > (SELECT MAX(Id) FROM processing_dirty_row) - 1')
    db._exec("INSERT INTO processing_dirty_row(Id, Kind, LocalId) VALUES ((SELECT MAX(Id) FROM processing_dirty_row) + 5, 'message', '999')")
    second = read(db)
    assert by_member(second, f'message:{mids[0]}')['view']['messages'][0]['Subject'] == 'Rail 1 (edited)'
    equal_to_cold(db, second)


def test_a_cache_hit_does_not_take_the_writer_lock(db):
    import threading
    mail(db, 1)
    read(db)
    done = threading.Event()
    with db.lock:
        threading.Thread(target=lambda: (db.processing_inventory_snapshot(
            fixed_now=NOW.isoformat(), live_state=[], display_only=True, history_days=14), done.set())).start()
        assert done.wait(0.5), 'a read with nothing new waited on the lock'


def test_a_setting_every_projection_reads_rebuilds_everything(db):
    [mail(db, n) for n in range(1, 4)]
    first = read(db)
    db.set_setting('funnel_hours', '48', 'fixture')
    second = read(db)
    b, a = projections(first), projections(second)
    assert all(b[k] != a[k] for k in b)


def test_dirty_rows_say_which_row_and_an_update_names_its_key_once(db):
    mid = mail(db, 1)
    db._exec('DELETE FROM processing_dirty_row')
    db._exec('UPDATE message SET Subject=? WHERE MessageId=?', ('once', mid))
    assert [tuple(r) for r in db.cx.execute('SELECT Kind, LocalId FROM processing_dirty_row')] == [('message', str(mid))]
    assert processing_rail.dirty_since(db.cx.cursor(), 0)[1] == [('message', str(mid))]
