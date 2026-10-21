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
    pytest.param(lambda s, mid, tid, pid: s.add_comment(tid, 'coding', 'agent', 'Finished.'), id='comment'),
    pytest.param(lambda s, mid, tid, pid: s.add_transcript(tid, 'sid-1', 'worked', agent='coding'), id='transcript'),
    pytest.param(lambda s, mid, tid, pid: s.set_funnel_state(f'processing:{pid}', 'surfaced'), id='funnel_state'),
    pytest.param(lambda s, mid, tid, pid: s.tag_task(tid, terminal.INTERRUPTED, True, 'shutdown'), id='task-tag'),
])
def test_each_kind_of_write_moves_its_card_and_only_its_card(db, write):
    mids = [mail(db, n) for n in range(1, 6)]
    tid = db.create_task({'Title': 'Rail task', 'Assignee': 'agent:coding', 'Kind': 'coding'}, 'fixture')
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


# ---- the pile cache stays warm through writes nothing on it reads (2026-10-12) -------------------------
def pile(s): return funnel.pile(s, observed=[], quiet=True)
def at(**kw): return (datetime.now() + timedelta(**kw)).isoformat(sep=' ', timespec='seconds')
def stamp(s, cid, col, value): s._exec(f'UPDATE connector SET {col}=? WHERE ConnectorId=?', (value, cid))


def test_a_healthy_connector_check_in_leaves_the_pile_warm(db):
    mail(db, 1)
    cid, first = db.get_connector_by_type('github')['ConnectorId'], pile(db)
    stamp(db, cid, 'LastSyncAt', '2026-01-01 00:00:00')                  # an old stamp, so the check-in below does write
    top = db.rail_top()
    db.touch_connector(cid)
    assert db.get_connector(cid)['LastSyncAt'] != '2026-01-01 00:00:00'
    assert db.rail_top() == top and pile(db) is first


def test_a_connector_that_starts_failing_still_moves_the_pile(db):
    mail(db, 1)
    cid, first = db.get_connector_by_type('github')['ConnectorId'], pile(db)
    db.touch_connector(cid, 'HTTP 404')
    assert pile(db) is not first
    second = pile(db)
    db.touch_connector(cid)                                              # ...and so does it coming back
    assert pile(db) is not second


@pytest.mark.parametrize('column, value', [('Active', 1), ('ConfigJson', '{"bulk": "rank"}'), ('Type', 'gitlab'), ('LastErrorAt', '2026-01-01')])
def test_a_column_the_pile_reads_still_leaves_a_dirty_row(db, column, value):
    cid, top = db.get_connector_by_type('github')['ConnectorId'], db.rail_top()
    stamp(db, cid, column, value)
    assert db.rail_top() > top


def test_a_failing_connectors_stamp_still_leaves_a_dirty_row(db):
    # a broken row's `when` is its LastSyncAt (funnel.broken_connections)
    cid = db.get_connector_by_type('github')['ConnectorId']
    stamp(db, cid, 'LastError', 'HTTP 404'); top = db.rail_top()
    stamp(db, cid, 'LastSyncAt', '2026-01-01 00:00:00')
    assert db.rail_top() > top


def test_the_trigger_names_every_connector_column_but_the_stamp(db):
    cols = {r[1] for r in db.cx.execute('PRAGMA table_info(connector)')}
    assert set(processing_rail.CONNECTOR_COLUMNS) == cols - {'LastSyncAt'}


def test_an_install_made_before_the_when_gets_it(tmp_path):
    path = str(tmp_path / 'old.db')
    s = SQLiteStore(path)
    s.cx.execute('DROP TRIGGER rail_dirty_connector_update')
    s.cx.execute("CREATE TRIGGER rail_dirty_connector_update AFTER UPDATE ON connector BEGIN "
                 "INSERT INTO processing_dirty_row(Kind, LocalId) VALUES ('connector', NEW.ConnectorId); END")
    s.cx.commit(); s.cx.close()
    s = SQLiteStore(path)
    triggers = lambda: {r[0]: r[1] for r in s.cx.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")}
    before = triggers()
    assert ' WHEN ' in before['rail_dirty_connector_update']
    s.cx.close(); s = SQLiteStore(path)                                   # a second open leaves every trigger as it is
    assert triggers() == before
    s.cx.close()


def test_a_check_in_that_changes_nothing_writes_nothing_for_a_while(db):
    cid = db.get_connector_by_type('github')['ConnectorId']
    get = lambda col: db.get_connector(cid)[col]
    stamp(db, cid, 'LastSyncAt', held := at(seconds=-10))
    db.touch_connector(cid); assert get('LastSyncAt') == held             # fresh: skipped
    stamp(db, cid, 'LastSyncAt', at(minutes=-5))
    db.touch_connector(cid); assert get('LastSyncAt') >= at(seconds=-5)   # stale: stamped
    stamp(db, cid, 'LastSyncAt', at(days=1))
    db.touch_connector(cid); assert get('LastSyncAt') < at(minutes=1)     # a stamp from the future does not hold it off
    db.touch_connector(cid, 'HTTP 500')
    stamp(db, cid, 'LastErrorAt', held := at(seconds=-10))
    db.touch_connector(cid, 'HTTP 500'); assert get('LastErrorAt') == held                            # the same error: skipped
    db.touch_connector(cid, 'HTTP 502'); assert (get('LastError'), get('LastErrorAt') > held) == ('HTTP 502', True)
    db.touch_connector(cid); assert get('LastError') is None                                          # recovery: always written


def test_the_assistants_bookkeeping_leaves_the_pile_warm(db):
    mail(db, 1)
    first = pile(db)
    for k in ('assistant_current:7', 'concierge_cli_sid:7', 'assistant_last_undo'): db.set_setting(k, 'x', 'assistant')
    assert pile(db) is first


@pytest.mark.parametrize('name', ['funnel_mutes', 'walk_started_at', 'meeting_grace_minutes'])
def test_a_setting_the_pile_reads_or_might_still_empties_it(db, name):
    mail(db, 1)
    first = pile(db)
    db.set_setting(name, '[]' if name == 'funnel_mutes' else '1', 'owner')
    assert pile(db) is not first


def test_threads_reading_the_rail_at_once_each_get_an_answer(db):
    # sqlite3 shares one cached statement per SQL text on a connection: two threads asking "anything new?" at once
    # reset each other's, and one got no row back - a 500 on the walk's table chip (2026-10-21)
    import threading
    for n in range(3): mail(db, n)
    def rail(): return db.processing_inventory_snapshot(fixed_now=NOW.isoformat(), live_state=[], display_only=True)
    rail()
    errs, go = [], threading.Event()
    def top():
        for _ in range(300): assert db.rail_top() is not None
    def show():
        for _ in range(60): assert rail()['items'] is not None
    def run(f):
        go.wait()
        try: f()
        except Exception as e: errs.append(e)
    def write():
        for n in range(3, 40): mail(db, n)
    ts = [threading.Thread(target=run, args=(f,)) for f in [top, show]*4 + [write]]
    for t in ts: t.start()
    go.set()
    for t in ts: t.join()
    assert not errs, errs[:3]
