"""A COPY OF EVERYTHING, KEPT A WEEK (backups.py): the database by SQLite's own backup API - what the WAL holds included - once a day and
before a new version opens it, seven days kept, the files it points at mirrored once each, and nothing that can stop a start."""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from taskuary import backups


def _home(tmp_path):
    db = tmp_path / 'taskuary.db'
    cx = sqlite3.connect(db); cx.execute('PRAGMA journal_mode=WAL'); cx.execute('CREATE TABLE task (Title TEXT)')
    cx.execute("INSERT INTO task VALUES ('Send Erin the Q3 numbers')"); cx.commit()     # committed, still in the WAL: the copy must carry it
    (tmp_path / 'attachments' / '12').mkdir(parents=True); (tmp_path / 'attachments' / '12' / 'budget.xlsx').write_bytes(b'x' * 10)
    return db, cx


def test_a_copy_holds_what_the_wal_holds_and_the_files_beside_it(tmp_path):
    db, cx = _home(tmp_path)
    out = backups.make(str(db), tmp_path, now=datetime(2026, 11, 16))
    r = sqlite3.connect(out)
    assert out.name == 'taskuary-2026-11-16.db' and not list(out.parent.glob('*.partial'))
    assert r.execute('SELECT Title FROM task').fetchall() == [('Send Erin the Q3 numbers',)]; r.close()
    assert (tmp_path / 'backups' / 'attachments' / '12' / 'budget.xlsx').read_bytes() == b'x' * 10
    assert backups.mirror(tmp_path, tmp_path / 'backups') == 0, 'a file already mirrored is not copied again'
    cx.close()


def test_a_week_is_kept_and_the_newest_always(tmp_path):
    db, cx = _home(tmp_path)
    day0 = datetime(2026, 11, 1)
    for i in range(10): backups.make(str(db), tmp_path, now=day0 + timedelta(days=i))
    kept = sorted(p.name for p in (tmp_path / 'backups').glob('taskuary-*.db'))
    assert kept == [f'taskuary-2026-11-{d:02d}.db' for d in range(3, 11)]
    assert backups.prune(tmp_path / 'backups', now=datetime(2027, 1, 1)) and len(list((tmp_path / 'backups').glob('taskuary-*.db'))) == 1
    assert not backups.due(tmp_path, now=datetime(2026, 11, 10, 18)) and backups.due(tmp_path, now=datetime(2026, 11, 11))
    cx.close()


def test_a_new_version_copies_before_it_opens_and_only_once(tmp_path):
    db, cx = _home(tmp_path)
    first = backups.before_open(str(db), '0.4.0.11', tmp_path)
    assert first and 'before-0.4.0.11' in first.name
    assert not (tmp_path / 'backups' / 'attachments').exists(), 'the files are the daily copy\'s - an upgrade never waits on a first mirror'
    assert backups.before_open(str(db), '0.4.0.11', tmp_path) is None
    assert backups.before_open(str(tmp_path / 'none.db'), '0.4.0.12', tmp_path) is None, 'a fresh install has nothing to copy'
    cx.close()


def test_a_copy_that_fails_never_stops_the_start(tmp_path, monkeypatch):
    db, cx = _home(tmp_path)
    monkeypatch.setattr(backups, 'copy_db', lambda *a: (_ for _ in ()).throw(OSError('disk full')))
    assert backups.before_open(str(db), '0.4.0.11', tmp_path) is None
    cx.close()
