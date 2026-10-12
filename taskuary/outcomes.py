"""The outcome ledger (spec 2026-10-12, build step 2).

Every store that remembers is written from the owner's click at the moment of the click. Nothing recorded what the
owner did NEXT (Continue session, "merge it") or what the world did AFTER (the thread died, the task reopened, the PR
held, Ray delivered on day 9). This table does: one row per action, filled in two halves - the action when it happens
(record), the outcome days later by a sweep that reads facts already in the store (resolve). No model runs here:
what the facts MEAN is reflection's (learn.gather reads evidence()), and the Advisor's (build step 3).
"""
import json
from datetime import datetime, timedelta
from loguru import logger

KINDS = ('reply.sent', 'task.closed', 'agent.stopped', 'agent.continued', 'pr.merged', 'promise.made', 'sender.ignored')
WINDOW = {'reply.sent': 7, 'task.closed': 7, 'agent.stopped': 2, 'pr.merged': 14, 'sender.ignored': 60, 'promise.made': 7}
SWEPT_KEY = 'outcomes_swept_on'
def _now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def _dt(s):
    try: return datetime.strptime(str(s)[:19].replace('T', ' '), '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError): return None


def record(store, kind: str, target_kind: str, target_id, actor: str = 'owner', facts: dict = None, next_move: str = None, at: str = None) -> int:
    if kind not in KINDS: raise ValueError(f'not an outcome kind: {kind}')
    return store._exec('INSERT INTO outcome (Kind,TargetKind,TargetId,Actor,At,FactsJson,NextMove,NextAt) VALUES (?,?,?,?,?,?,?,?)',
                       (kind, target_kind, int(target_id or 0), actor, at or _now(), json.dumps(facts or {}),
                        '' if next_move is None else str(next_move)[:300], _now() if next_move is not None else None))


def rows_for(store, target_kind: str, target_id) -> list:
    return store._rows('SELECT * FROM outcome WHERE TargetKind=? AND TargetId=? ORDER BY Id DESC', (target_kind, int(target_id)))
def open_rows(store) -> list: return store._rows('SELECT * FROM outcome WHERE ResolvedAt IS NULL ORDER BY Id')
def settle(store, row_id: int, outcome: str, verdict: str, now: str = None):
    store._exec('UPDATE outcome SET Outcome=?, Verdict=?, ResolvedAt=? WHERE Id=? AND ResolvedAt IS NULL', (outcome, verdict, now or _now(), row_id))
