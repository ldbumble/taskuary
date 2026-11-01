"""DOES WRITING PER WORKSTREAM HELP? (the owner, 2026-11-01: STYLE per workstream - "try it", measured and easily reverted; stylews.py).
Read-only, like tools/advisor_agreement.py: the home's database is opened `mode=ro`.

    python tools/style_by_workstream.py                  # the live home (TASKUARY_HOME, else ~/.taskuary), drafts decided in the last 30 days
    python tools/style_by_workstream.py --days 60 --home <dir>

Every draft the owner decided is one of two: it read its workstream's own style lines (an audit row `style_ws` on its task before it was
decided) or only the shared style. For each, how often the owner sent it as written (approved) and how often they edited it first:
  edit rate  edited / (edited + approved)
Lower with the workstream's lines than without, on enough drafts, says it helps; higher says switch it off (setting style_by_workstream 0).
"""
import argparse, os, sqlite3, sys
from datetime import datetime, timedelta
from pathlib import Path


def connect(home) -> sqlite3.Connection:
    p = Path(home, 'taskuary.db').resolve()
    if not p.exists(): raise FileNotFoundError(p)
    cx = sqlite3.connect(p.as_uri() + '?mode=ro', uri=True); cx.row_factory = sqlite3.Row
    return cx


def measure(cx, since: str) -> dict:
    """{'with': {sent, edited, rate}, 'without': {...}} over the owner's decided drafts since `since`."""
    out = {k: {'sent': 0, 'edited': 0} for k in ('with', 'without')}
    for r in cx.execute("SELECT ReviewId, TaskId, Status, IFNULL(DecidedAt, CreatedAt) at FROM review WHERE DecidedBy='owner' "
                        "AND Status IN ('approved','edited') AND IFNULL(DecidedAt, CreatedAt)>=?", (since,)):
        used = r['TaskId'] and cx.execute("SELECT 1 FROM audit WHERE EntityType='task' AND EntityId=? AND Action='style_ws' AND CreatedAt<=? LIMIT 1",
                                          (str(r['TaskId']), r['at'])).fetchone()
        b = out['with' if used else 'without']
        b['sent' if r['Status'] == 'approved' else 'edited'] += 1
    for b in out.values():
        n = b['sent'] + b['edited']
        b['rate'] = round(100 * b['edited'] / n) if n else None
    return out


def line(m: dict) -> str:
    f = lambda b: f"{'n/a' if b['rate'] is None else str(b['rate']) + '%'} edited of {b['sent'] + b['edited']}"
    return f"Style per workstream: {f(m['with'])} with its lines, {f(m['without'])} with the shared style only"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--home', default=os.environ.get('TASKUARY_HOME') or os.path.expanduser('~/.taskuary'))
    ap.add_argument('--days', type=float, default=30)
    a = ap.parse_args(argv)
    print(line(measure(connect(a.home), (datetime.now() - timedelta(days=a.days)).strftime('%Y-%m-%d %H:%M:%S'))))
    return 0


if __name__ == '__main__': sys.exit(main())
