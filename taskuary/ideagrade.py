"""HOW THE OWNER TOOK EACH ADVISOR IDEA, AND WHICH KINDS HAVE EARNED THEIR PLACE (the design's S0 and S7, 2026-11-01).

An idea is graded by the owner's own acts - no new button:
  taken    they made a task or an agent run of it, adopted its rule, sent a reply on the task it names within a day, or finished the
           task triage made of it
  handled  they put it down with Done
  wrong    they dismissed it (or its whole kind)
  walked   a day went by and they did none of these
  pending  raised less than a day ago with nothing done yet - not graded
  unseen   the app put it down as it was raised, before he could see it - not graded
Useful is taken + handled. A KIND of model idea is QUIET while its useful share over the last DAYS is under BAR on MIN or more graded
(the owner, 2026-11-01: quiet unless sure; precision over 80%) - it raises one line a day, never more (spent_today), so its record can
mend as the window rolls. Read here and by tools/advisor_ideas.py, one grading."""
import json
from datetime import datetime, timedelta

TAKEN, WRONG = ('task', 'agent', 'rule', 'accept'), ('dismiss', 'dismiss_kind')
OWNER = ('owner', 'you', 'human')
GRADES = ('taken', 'handled', 'wrong', 'walked')
BAR, MIN, DAYS = 0.8, 10, 30
UNSEEN_H = 0.1          # put down by the app within six minutes of being raised: inside the run that raised it, before any rail drew it
# the kinds the model raises - the app's own (health, report, connect, rule, workstream, habit) are counted, never thought, and stay
TYPES = ('second_ask', 'pattern', 'decides', 'clash', 'drift', 'promise', 'prep')      # what the model may say a line of its own is
LOOKOUT = ('credit', 'pitch', 'money', 'early_warning', 'leverage')                       # the looking-out-for-you pass's families (lookout.py)
MODEL_KINDS = ('idea',) + TYPES + LOOKOUT


def _later(at, h): return (datetime.fromisoformat(str(at)[:19]) + timedelta(hours=h)).strftime('%Y-%m-%d %H:%M:%S')


def grade(q, i: dict, now: str) -> str:
    """One idea's grade. `q(sql, args)` returns rows as dicts - a store's _rows, or a read-only connection's."""
    verbs = {r['Action'] for r in q("SELECT Action FROM audit WHERE EntityType='idea' AND EntityId=?", (str(i['IdeaId']),))}
    if verbs & set(TAKEN): return 'taken'
    if verbs & set(WRONG) or (i['Status'] == 'dismissed' and i.get('DecidedBy') in OWNER): return 'wrong'
    try: a = json.loads(i.get('ActionJson') or '{}') or {}
    except ValueError: a = {}
    if a.get('tid') and q("SELECT 1 x FROM outcome WHERE Kind='reply.sent' AND TargetKind='task' AND TargetId=? AND At>=? AND At<=? "
                          f"AND Actor IN ({','.join('?' * len(OWNER))}) LIMIT 1", (a['tid'], i['FirstSeen'], _later(i['FirstSeen'], 24), *OWNER)):
        return 'taken'
    if i['Status'] == 'done' and i.get('DecidedBy') in OWNER: return 'handled'
    # ...and one triage made a task of that was then finished: work done from it, never "walked past" (the store puts the idea down
    # with its task, DecidedBy 'task' - 2026-11-12)
    if q("SELECT 1 x FROM task WHERE SourceRef=? AND Status='done' LIMIT 1", (f"assistant:idea:{i['IdeaId']}",)): return 'taken'
    # ...and one the app put down itself as it was raised - the report's judge, the rail, a gate - was never his to see: it says nothing
    # about usefulness and is not graded (decided 2026-11-12). Read and left alone is still walked past
    by, at = i.get('DecidedBy'), i.get('DecidedAt')
    if i['Status'] in ('done', 'dismissed') and by and by not in OWNER and by != 'task' and at and str(at)[:19] <= _later(i['FirstSeen'], UNSEEN_H):
        return 'unseen'
    return 'walked' if _later(i['FirstSeen'], 24) <= now else 'pending'


def tally(gs) -> dict:
    from collections import Counter
    c = Counter(gs)
    useful, graded = c['taken'] + c['handled'], sum(c[g] for g in GRADES)
    return {**{g: c[g] for g in GRADES}, 'pending': c['pending'], 'n': graded, 'pct': round(100 * useful / graded) if graded else None}


def record(store, days: int = DAYS) -> dict:
    """{kind: tally} over the ideas first raised in the last `days`."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    by = {}
    for i in store._rows('SELECT * FROM idea WHERE FirstSeen>=?', (since,)):
        by.setdefault(i.get('Kind') or 'idea', []).append(grade(store._rows, i, now))
    return {k: tally(v) for k, v in by.items()}


SINCE_KEY = 'ideas_checked_since'


def quiet_kinds(store) -> set:
    """The model's kinds of idea that are quiet now: under BAR on MIN or more graded in the window - counting only ideas raised since the
    second look began (SINCE_KEY, set on its first run): graded on the old Advisor's record, an untyped idea was 38% useful on one owner's
    home and every model line would have gone silent at once, the good with the noise (a replay, 2026-11-01)."""
    since = store.get_setting(SINCE_KEY) or ''
    if not since: return set()
    days = max(0.0, min(DAYS, (datetime.now() - datetime.fromisoformat(since[:19])).total_seconds() / 86400))
    return {k for k, t in record(store, days).items() if k in MODEL_KINDS and t['n'] >= MIN and t['pct'] is not None and t['pct'] < BAR * 100}


def spent_today(store, kinds: set) -> set:
    """THE BAR NARROWS, IT NEVER CLOSES: of the quiet `kinds`, those that already raised a line today. A quiet kind held every line for
    the whole window, so its record could not change and nothing it saw reached the owner - the untyped idea went silent on 58% and the
    Advisor with it (2026-11-12). Each quiet kind still raises one line a day, past the second look like any other."""
    if not kinds: return set()
    today = datetime.now().strftime('%Y-%m-%d')
    return set(kinds) & {r['Kind'] for r in store._rows('SELECT DISTINCT Kind FROM idea WHERE FirstSeen>=?', (today,))}
