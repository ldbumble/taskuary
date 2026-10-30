"""How many recent general tasks would take the quick path, and why the rest go deep: `python tools/quick_replay.py --db PATH [--days 14] [--ask 0]`.

Reads a COPY of PATH (a read such as origin.of_task writes a cache) with TASKUARY_HOME pointed at a fresh temp dir, so the real home is never opened.
There is no default for --db. Prints `key: count` lines - never a title, a name or any text. With --ask N it also makes the quick call on up to N
would-be-quick tasks, and counts what came back; nothing is filed."""
import argparse, os, shutil, sys, tempfile
from datetime import datetime, timedelta
from pathlib import Path


def replay(store, days: int = 14, now: datetime = None, ask: int = 0) -> dict:
    "Counts for the general tasks created in the last `days`: how many would be quick, and the reason for each deep one."
    from taskuary import general, ingest, quickwork
    since = (now or datetime.now()) - timedelta(days=days)
    def recent(t):
        try: return datetime.fromisoformat(str(t.get('CreatedAt') or '')[:19]) >= since
        except ValueError: return False
    ts = [t for t in store.list_tasks() if general.handles(t) and not general.is_dock(t) and recent(t)]
    out = {'general': len(ts), 'quick': 0, **{f'deep:{w}': 0 for w in quickwork.DEEP_WHY}}
    quick = []
    for t in ts:
        w = quickwork.why_deep(store, t['TaskId'])
        if w: out[f'deep:{w}'] += 1
        else: out['quick'] += 1; quick.append(t['TaskId'])
    if ask > 0:
        out.update(asked=0, escalated=0, unreadable=0, failed=0)
        for tid in quick[:ask]:
            out['asked'] += 1
            try: a = quickwork.ask(store, tid, ingest.first_ask(store, tid))
            except Exception: out['failed'] += 1; continue
            if a is None: out['unreadable'] += 1
            elif a.escalate: out['escalated'] += 1
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', required=True); p.add_argument('--days', type=int, default=14); p.add_argument('--ask', type=int, default=0)
    a = p.parse_args(argv)
    tmp = Path(tempfile.mkdtemp(prefix='quick-replay-')); db = tmp / 'taskuary.db'
    shutil.copy(a.db, db)
    os.environ['TASKUARY_HOME'] = str(tmp / 'home')          # before any taskuary import: nothing may open the real home
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from loguru import logger; logger.remove(); logger.add(sys.stderr, level='WARNING')
    from taskuary.store import SQLiteStore
    try:
        for k, v in replay(SQLiteStore(db), a.days, ask=a.ask).items(): print(f'{k}: {v}')
    finally: shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == '__main__': sys.exit(main())
