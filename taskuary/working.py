""""Is it working?" - whether the app's calls stand, counted from what the owner did with them (the owner, 2026-10-22, picked from
the gaps). Three calls, each against the owner's own next move, no model anywhere:

- a DRAFT: sent as drafted, edited first, or redrafted before it went (outcome 'reply.sent' + the review's 'redraft' audit rows)
- a TRIAGE VERDICT: stood, or overturned - the owner's correction against it (the `correction` table, triage-correction-loop)
- an AGENT'S RESULT: accepted (Mark done after it stopped), continued, or still waiting on the owner (outcome 'agent.stopped' and
  the next 'task.closed' / 'agent.continued' on the same task - the ledger's own pairing, outcomes._resolve_one)

Read straight from the rows rather than the outcome sweep's verdicts: the sweep runs once a day, and a number that lags its own
press by a day reads as the press not counting.
"""
import json
from datetime import datetime, timedelta

WINDOWS = (7, 30)


def _since(days: int, now: datetime = None) -> str: return ((now or datetime.now()) - timedelta(days=int(days))).strftime('%Y-%m-%d %H:%M:%S')


def drafts(store, since: str) -> dict:
    "Replies sent since `since`: as drafted, edited first, or redrafted (whatever happened after) - the three add up to `sent`."
    rows = [json.loads(r['f'] or '{}') for r in store._rows("SELECT FactsJson f FROM outcome WHERE Kind='reply.sent' AND At>=?", (since,))]
    rids = {int(f['review']) for f in rows if str(f.get('review') or '').isdigit()}
    redone = {r['EntityId'] for r in store._rows(f"SELECT DISTINCT EntityId FROM audit WHERE EntityType='review' AND Action='redraft' "
                                                  f"AND EntityId IN ({','.join(map(str, rids)) or 'NULL'})")}
    re_ = [f for f in rows if f.get('review') in redone]
    rest = [f for f in rows if f.get('review') not in redone]
    return {'sent': len(rows), 'unedited': sum(f.get('verb') == 'approve' for f in rest), 'edited': sum(f.get('verb') != 'approve' for f in rest),
            'redrafted': len(re_)}


def triage(store, since: str) -> dict:
    "Messages triage judged since `since`, and how many of those the owner overturned (at any time since)."
    q = "SELECT DISTINCT MessageId FROM route WHERE RoutedBy='triage' AND MessageId IS NOT NULL AND CreatedAt>=?"
    n = store._one(f'SELECT COUNT(*) n FROM ({q})', (since,))['n']
    over = store._one(f'SELECT COUNT(DISTINCT MessageId) n FROM correction WHERE MessageId IN ({q})', (since,))['n']
    return {'verdicts': n, 'overturned': over}


def agents(store, since: str) -> dict:
    "Agent results (an agent stopped and handed back) since `since`: what the owner did next on that task."
    out = {'results': 0, 'accepted': 0, 'continued': 0, 'waiting': 0}
    for r in store._rows("SELECT Id, TargetId FROM outcome WHERE Kind='agent.stopped' AND TargetKind='task' AND At>=?", (since,)):
        nxt = store._one("SELECT Kind FROM outcome WHERE TargetKind='task' AND TargetId=? AND Kind IN ('agent.continued','task.closed') AND Id>? "
                         "ORDER BY Id LIMIT 1", (r['TargetId'], r['Id']))
        out['results'] += 1
        out['accepted' if nxt and nxt['Kind'] == 'task.closed' else 'continued' if nxt else 'waiting'] += 1
    return out


def numbers(store, days: int = 7, now: datetime = None) -> dict:
    s = _since(days, now)
    return {'days': int(days), 'drafts': drafts(store, s), 'triage': triage(store, s), 'agents': agents(store, s)}


def windows(store, now: datetime = None) -> list: return [numbers(store, d, now) for d in WINDOWS]
