"""A COPY OF EVERYTHING, KEPT A WEEK (the owner's brief, 2026-11-16): the database is one file, and before this nothing copied it but a one-time
migration (processing_startup). One road now: a consistent copy by SQLite's own backup API (it carries what the WAL holds, never a torn file)
into the home's backups/ folder - once a day while Taskuary runs, and before a new version opens the database, since that is when its schema
changes. The newest KEEP copies are kept. The files the database points at in attachments/ are not in it: they are mirrored beside the
copies, each file once - they never change after they land. The agents' own records (artifacts/) are not copied: they grow while a session
writes, and one session's record copied whole was half a gigabyte (the owner, 2026-11-19: keep three copies, no agent records).

Never in the way: the daily copy runs on its own thread, and any failure is a line in the log, never a start that stops.

Restore (docs/site/troubleshooting.md): quit Taskuary, then copy backups/taskuary-<date>.db over taskuary.db and the mirrored folders back.
"""
import os, shutil, sqlite3, threading, time
from datetime import datetime
from pathlib import Path
from loguru import logger

KEEP = 3                                      # database copies kept, the newest
FILES = ('attachments',)                      # where the database's file rows point, under the home
DROPPED = ('artifacts',)                      # mirrored by an earlier build: taken out of the backups by the next rotation
EVERY = 3600                                  # how often the running app looks whether today's copy is made


def folder(home=None) -> Path:
    from . import config
    return Path(home or config.home()) / 'backups'


def _name(day: str, why: str = '') -> str: return f"taskuary-{day}{'-' + why if why else ''}.db"


def copy_db(src: str, dest: Path) -> Path:
    "A consistent copy of the database at `src`, written beside `dest` first and moved in whole - a copy cut short is never a backup."
    tmp = dest.with_suffix('.partial')
    _gone(tmp)                                # ...one a run cut short left behind is no copy: away before this one
    a, b = sqlite3.connect(src, timeout=30), sqlite3.connect(str(tmp))
    try: a.backup(b)
    finally: a.close(); b.close()             # a `with` only commits: Windows will not move a file still open
    # ...AND MOVED WHEN WINDOWS LETS GO OF IT (the owner's live app, 2026-11-19: WinError 32 on every try - an indexer or a virus scan holds a
    # new file for a moment): tried again for a few seconds, then the half copy is removed and the failure said
    for i in range(20):
        try: os.replace(tmp, dest); return dest
        except PermissionError:
            if i == 19: _gone(tmp); raise
            time.sleep(0.25)
    return dest


def _gone(p: Path) -> None:
    try: p.unlink()
    except FileNotFoundError: pass
    except OSError as e: logger.warning(f'backup: {p.name} could not be removed - {e}')


def mirror(home: Path, to: Path) -> int:
    "The home's file folders into the backup's, each file copied once (new or changed size); returns how many were copied."
    n = 0
    for sub in FILES:
        src = home / sub
        if not src.is_dir(): continue
        for p in src.rglob('*'):
            if not p.is_file(): continue
            q = to / sub / p.relative_to(src)
            if q.is_file() and q.stat().st_size == p.stat().st_size: continue
            q.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, q); n += 1
    return n


def prune(to: Path) -> list:
    "The newest KEEP copies stay and older ones go, and a mirror of what is no longer copied (DROPPED) with them. Each removal is logged."
    dbs = sorted(to.glob('taskuary-*.db'), key=lambda p: (p.stat().st_mtime, p.name))
    gone = dbs[:-KEEP] if len(dbs) > KEEP else []
    for p in gone:
        try: p.unlink(); logger.info(f'backup: {p.name} removed - only the newest {KEEP} copies are kept')
        except OSError as e: logger.warning(f'backup {p.name} not removed: {e}')
    for d in DROPPED:
        if (q := to / d).is_dir():
            n = sum(f.stat().st_size for f in q.rglob('*') if f.is_file())
            shutil.rmtree(q, ignore_errors=True)
            logger.info(f'backup: {d}/ removed from the backups ({n / 1e6:.0f} MB) - agent records are not copied')
            gone.append(q)
    return gone


def make(db: str, home=None, why: str = '', now: datetime = None, files: bool = True) -> Path | None:
    """One copy now: the database, the mirrored files (`files` - the copy before an upgrade leaves them to the daily one, so a first mirror
    of a large home never holds the start), the old copies pruned. None when there is no database yet."""
    if not db or not Path(db).is_file(): return None
    to = folder(home); to.mkdir(parents=True, exist_ok=True)
    out = copy_db(db, to / _name((now or datetime.now()).strftime('%Y-%m-%d'), why))
    if files: mirror(Path(home) if home else Path(db).parent, to)
    prune(to)
    logger.info(f'backup: {out.name} written')
    return out


def due(home=None, now: datetime = None) -> bool:
    "No copy made today yet."
    day = (now or datetime.now()).strftime('%Y-%m-%d')
    return not any(folder(home).glob(f'taskuary-{day}*.db'))


def before_open(db: str, version: str, home=None) -> Path | None:
    """Before this version opens the database: a copy when the version is not the one that last opened it - the schema changes on an upgrade,
    and this is the copy to go back to. Any failure is logged; the start goes on."""
    mark = folder(home) / 'version'
    try:
        if mark.is_file() and mark.read_text(encoding='utf-8').strip() == version: return None
        out = make(db, home, why='before-' + version.replace('/', '-'), files=False)
        mark.parent.mkdir(parents=True, exist_ok=True); mark.write_text(version, encoding='utf-8')
        return out
    except Exception as e:
        logger.warning(f'backup before {version} not made: {e}')
        return None


def start(db: str, home=None, stop: threading.Event = None) -> threading.Thread:
    "The daily copy, on its own thread: made when today has none, looked at every hour."
    def run():
        try: prune(folder(home))              # ...the rotation at every start too, not only with a day's copy
        except Exception as e: logger.warning(f'backup rotation not done: {e}')
        while not (stop and stop.is_set()):
            try:
                if due(home): make(db, home)
            except Exception as e: logger.warning(f'daily backup not made: {e}')
            if stop: stop.wait(EVERY)
            else: time.sleep(EVERY)
    t = threading.Thread(target=run, daemon=True, name='taskuary-backup')
    t.start()
    return t
