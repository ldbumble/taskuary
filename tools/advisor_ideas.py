"""HOW MANY OF THE ADVISOR'S IDEAS WERE WORTH RAISING (the 2026-11-01 design: an idea kind is raised only while it is right 80% of the time
on the owner's own record). Read-only, like tools/advisor_agreement.py: the home's database is opened `mode=ro`.

    python tools/advisor_ideas.py                    # the live home (TASKUARY_HOME, else ~/.taskuary), ideas first raised in the last 14 days
    python tools/advisor_ideas.py --days 30 --home <dir>
    python tools/advisor_ideas.py --line             # one line, for tools/release.sh

Each idea is graded by the owner's own acts - no new button:
  taken    the owner made a task or an agent run of it, adopted its rule, or sent a reply on the task it names within a day of it
  handled  the owner put it down with Done
  wrong    the owner dismissed it (or its whole kind)
  walked   a day went by and the owner did none of these (it is still open, or something else put it down)
  pending  raised less than a day ago with nothing done yet - not graded
Useful is taken + handled; precision is useful / (useful + wrong + walked).
"""
import argparse, json, os, sqlite3, sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

TAKEN, WRONG = ('task', 'agent', 'rule'), ('dismiss', 'dismiss_kind')
OWNER = ('owner', 'you', 'human')
GRADES = ('taken', 'handled', 'wrong', 'walked')


def connect(home) -> sqlite3.Connection:
    p = Path(home, 'taskuary.db').resolve()
    if not p.exists(): raise FileNotFoundError(p)
    cx = sqlite3.connect(p.as_uri() + '?mode=ro', uri=True); cx.row_factory = sqlite3.Row
    return cx
def _later(at, h): return (datetime.fromisoformat(str(at)[:19]) + timedelta(hours=h)).strftime('%Y-%m-%d %H:%M:%S')
def _cols(cx, t): return {r[1] for r in cx.execute(f'PRAGMA table_info({t})')}


def grade(cx, i: dict, now: str) -> str:
    """One idea's grade by what the owner did with it."""
    verbs = {r[0] for r in cx.execute("SELECT Action FROM audit WHERE EntityType='idea' AND EntityId=?", (str(i['IdeaId']),))}
    if verbs & set(TAKEN): return 'taken'
    if verbs & set(WRONG) or (i['Status'] == 'dismissed' and i.get('DecidedBy') in OWNER): return 'wrong'
    try: a = json.loads(i.get('ActionJson') or '{}')
    except ValueError: a = {}
    if a.get('tid') and cx.execute("SELECT 1 FROM outcome WHERE Kind='reply.sent' AND TargetKind='task' AND TargetId=? AND At>=? AND At<=? "
                                   f"AND Actor IN ({','.join('?' * len(OWNER))}) LIMIT 1",
                                   (a['tid'], i['FirstSeen'], _later(i['FirstSeen'], 24), *OWNER)).fetchone(): return 'taken'
    if i['Status'] == 'done' and i.get('DecidedBy') in OWNER: return 'handled'
    return 'walked' if _later(i['FirstSeen'], 24) <= now else 'pending'


def ideas(cx, since: str, until: str = '9999') -> list:
    ws = 'Workstream' in _cols(cx, 'idea')
    rows = [dict(r) for r in cx.execute('SELECT * FROM idea WHERE FirstSeen>=? AND FirstSeen<? ORDER BY IdeaId', (since, until))]
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for i in rows: i['grade'], i['ws'] = grade(cx, i, now), (i.get('Workstream') or '') if ws else ''
    return rows


def tally(xs) -> dict:
    c = Counter(i['grade'] for i in xs)
    useful, graded = c['taken'] + c['handled'], sum(c[g] for g in GRADES)
    return {**{g: c[g] for g in GRADES}, 'pending': c['pending'], 'pct': round(100 * useful / graded) if graded else None}


def line(t, since) -> str:
    pct = f"{t['pct']}%" if t['pct'] is not None else 'n/a'
    return (f"Advisor ideas: {pct} useful ({t['taken']} taken, {t['handled']} handled, {t['wrong']} wrong, {t['walked']} walked past"
            f"{', ' + str(t['pending']) + ' pending' if t['pending'] else ''}) since {since}")


def report(xs, since) -> str:
    out = [line(tally(xs), since)]
    def by(f, title):
        g = defaultdict(list)
        for i in xs: g[f(i)].append(i)
        rows = [title]
        for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
            t = tally(v)
            rows.append(f"  {k or '(none)':<24} {'-' if t['pct'] is None else t['pct']:>4}%  " + '  '.join(f"{t[g]:>3} {g}" for g in GRADES))
        return rows
    out += [''] + by(lambda i: i.get('Kind') or 'idea', 'by kind:')
    if any(i['ws'] for i in xs): out += [''] + by(lambda i: i['ws'], 'by workstream:')
    return '\n'.join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--home', default=os.environ.get('TASKUARY_HOME') or os.path.expanduser('~/.taskuary'))
    ap.add_argument('--days', type=float, default=14)
    ap.add_argument('--since'); ap.add_argument('--until', default='9999')
    ap.add_argument('--line', action='store_true')
    a = ap.parse_args(argv)
    since = a.since or (datetime.now() - timedelta(days=a.days)).strftime('%Y-%m-%d %H:%M:%S')
    xs = ideas(connect(a.home), since, a.until)
    print(line(tally(xs), since) if a.line else report(xs, since))
    return 0


if __name__ == '__main__': sys.exit(main())
