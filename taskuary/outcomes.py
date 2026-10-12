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


def _material_inbound_after(store, cid: str, at: str) -> list:
    """Their words on the thread after `at`: not the owner's, not an auto-reply, not a calendar response."""
    from .autoreply import is_auto
    from .counsel import is_invite
    me = str(store.get_setting('owner_email', '') or '').lower()
    rows = store._rows("SELECT * FROM message WHERE ConversationId=? AND SentAt>? AND Status!='context' ORDER BY SentAt", (cid, at))
    return [r for r in rows if str(r.get('FromEmail') or '').lower() != me and not is_auto(r) and not is_invite(r)]


def _resolve_one(store, r: dict, now: datetime):
    kind, at, facts = r['Kind'], _dt(r['At']), json.loads(r.get('FactsJson') or '{}')
    if not at: return settle(store, r['Id'], 'no stamp', 'unknown')
    age = (now - at).days
    t = store.get_task(r['TargetId']) if r['TargetKind'] == 'task' else None
    if kind == 'reply.sent':
        if age < WINDOW[kind]: return
        later = _material_inbound_after(store, facts.get('cid') or '', r['At'])
        reopened = t and t.get('Status') not in ('done', 'dropped') and facts.get('closed')
        if later or reopened: return settle(store, r['Id'], f"{len(later)} more from them" + ('; the task reopened' if reopened else ''), f'unsettled: {len(later)} more')
        return settle(store, r['Id'], 'nothing more from them in the window; the task stayed as it was', 'settled')
    if kind == 'task.closed':
        if age < WINDOW[kind]: return
        back = t and t.get('Status') not in ('done', 'dropped')
        return settle(store, r['Id'], 'open again' if back else 'stayed closed', 'reopened' if back else 'held')
    if kind == 'agent.stopped':
        nxt = store._one("SELECT * FROM outcome WHERE TargetKind='task' AND TargetId=? AND Kind IN ('agent.continued','task.closed') AND Id>? ORDER BY Id LIMIT 1",
                         (r['TargetId'], r['Id']))
        if nxt:
            verdict = 'continued' if nxt['Kind'] == 'agent.continued' else 'closed'
            mins = max(0, int(((_dt(nxt['At']) or now) - at).total_seconds() // 60))
            store._exec('UPDATE outcome SET NextMove=?, NextAt=? WHERE Id=?', (nxt.get('NextMove') or verdict, nxt['At'], r['Id']))
            return settle(store, r['Id'], f'{verdict} {mins} min later', verdict)
        if age >= WINDOW[kind]: return settle(store, r['Id'], 'nothing for two days', 'left')
        return
    if kind == 'agent.continued': return settle(store, r['Id'], 'the owner continued it', 'continued')
    if kind == 'pr.merged':
        if age >= WINDOW[kind]: return settle(store, r['Id'], 'still merged after two weeks', 'held')
        return
    if kind == 'promise.made':
        due = _dt(f"{str((t or {}).get('DueAt') or '')[:10]} 00:00:00")
        if t and t.get('Status') == 'done':
            closed = _dt(t.get('ClosedAt')) or now
            late = due and closed.date() > due.date()
            return settle(store, r['Id'], f"delivered {closed:%Y-%m-%d}" + (f", due {due:%Y-%m-%d}" if due else ''), 'kept late' if late else 'kept')
        if due and (now - due).days >= WINDOW[kind]: return settle(store, r['Id'], f'not delivered a week past {due:%Y-%m-%d}', 'late')
        return
    if kind == 'sender.ignored':
        if age < WINDOW[kind]: return
        who = str(facts.get('from') or '').lower()
        tasks = store.tasks_from_sender(who, r['At']) if who else []
        return settle(store, r['Id'], f'{len(tasks)} task(s) from them since' if tasks else 'nothing from them became work', 'regret' if tasks else 'no regret')


def resolve(store, now: datetime = None) -> int:
    """The sweep: every open row old enough to judge, judged from the store's own facts. Bookkeeping, no model."""
    now, n = now or datetime.now(), 0
    for r in open_rows(store):
        try:
            _resolve_one(store, r, now)
            if store._one('SELECT ResolvedAt FROM outcome WHERE Id=?', (r['Id'],))['ResolvedAt']: n += 1
        except Exception as e: logger.warning(f'outcome {r["Id"]} not resolved: {e}')
    return n
