"""A write that meets "database is locked" leaves nothing open behind it (2026-10-26).

Another process held the database for 5s; one INSERT failed, and the transaction sqlite3 had opened for it stayed open on
the writer. Every BEGIN IMMEDIATE after it failed with "cannot start a transaction within a transaction" until a restart -
the rail's reads with them, and Next said "still refreshing" over and over."""
import os, sqlite3, tempfile
from taskuary.store import SQLiteStore


def _locked_store():
    path = os.path.join(tempfile.mkdtemp(), 't.db')
    s = SQLiteStore(path)
    s.cx.execute('PRAGMA busy_timeout=50')
    other = sqlite3.connect(path, timeout=0.05)
    other.execute('BEGIN IMMEDIATE')                  # another process holds the write lock
    return s, other


def _route(s):
    return s.add_brain_route({'At': '2026-10-26 15:22:23', 'Job': 'triage', 'Pick': 'claude', 'Rule': 'fixed', 'Why': 'test'})


def test_a_locked_bare_write_rolls_back_and_the_next_transaction_starts():
    s, other = _locked_store()
    try: _route(s)
    except sqlite3.OperationalError as e: assert 'locked' in str(e)
    else: raise AssertionError('the write should have met the lock')
    assert not s.cx.in_transaction, 'the failed write left its transaction open'
    other.rollback(); other.close()
    tid = s.create_task({'Title': 'Count the snag list', 'Status': 'open'}, 'router')
    sid = s.save_source({'Channel': 'email', 'Address': 'erin@northwind.example', 'Active': 1}, 'test')
    assert s.patch_source_poll_state(sid, config_set={'cursor': 'a'}) is True     # a BEGIN IMMEDIATE write
    assert s.get_task(tid)['Title'] == 'Count the snag list' and _route(s)


def test_a_transaction_left_open_is_dropped_before_the_next_begin():
    path = os.path.join(tempfile.mkdtemp(), 't.db')
    s = SQLiteStore(path)
    sid = s.save_source({'Channel': 'email', 'Address': 'gail@northwind.example', 'Active': 1}, 'test')
    s.cx.execute("UPDATE source SET Active=1 WHERE SourceId=?", (sid,))            # opened, never committed - a failed write's leftover
    assert s.cx.in_transaction
    assert s.patch_source_poll_state(sid, config_set={'cursor': 'b'}) is True
