"""One thing, one place, over a real home: `python tools/rail_dupes.py <home> [--threads] [--ids]`.

Reads a COPY - the home's taskuary.db is backed up into a temp folder first (sqlite's backup API, so a running app is never
touched), and the rail is built there exactly as /api/funnel/pile builds it, then again with read rows kept. Prints counts by
shape (lanes, kinds, entity kinds) and, with --ids, the row keys - never a subject, a name or an address."""
import os, sys, json, shutil, sqlite3, tempfile
from pathlib import Path


def main(argv):
    if not argv or argv[0] in ('-h', '--help'): print(__doc__); return 2
    src = Path(argv[0]).expanduser() / 'taskuary.db'
    tmp = Path(tempfile.mkdtemp(prefix='rail-dupes-'))
    s, d = sqlite3.connect(f'file:{src.as_posix()}?mode=ro', uri=True), sqlite3.connect(tmp / 'taskuary.db')
    s.backup(d); d.close(); s.close()
    os.environ['TASKUARY_HOME'] = str(tmp)                 # before any taskuary import: nothing may open the real home
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))     # this checkout's code, not whichever one is installed
    from loguru import logger; logger.remove(); logger.add(sys.stderr, level='WARNING')
    from taskuary import config, funnel, railcheck
    from taskuary.store import SQLiteStore
    assert Path(config.db_path()).parent == tmp, config.db_path()
    st = SQLiteStore(config.db_path())
    from taskuary.processing_all import MEMBERSHIP_RULES          # this checkout's grouping, as the app's loop stamps it at start
    if st.get_setting('processing_membership_rules') != MEMBERSHIP_RULES: st.set_setting('processing_membership_rules', MEMBERSHIP_RULES, 'system')
    if st.processing_reads_active(): st.reconcile_processing_membership()
    p = funnel.pile(st, force=True, quiet=True)
    full = funnel.full_items(st) or p['items']
    for name, items, lanes in (('rail', p['items'], p.get('lanes')), ('with read rows', full, None)):
        found = railcheck.collisions(items, st, lanes=lanes, threads='--threads' in argv, ideas=lanes is not None)
        print(f'{name}: {len(items)} rows, {len(found)} collision(s)')
        print(json.dumps(railcheck.summary(found), indent=1))
        if '--ids' in argv:
            for c in found: print(' ', c['check'], c['shape'], c['ids'], c['keys'])
    st.cx.close(); shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == '__main__': sys.exit(main(sys.argv[1:]))
