"""The Advisor on the event (spec 2026-10-12, build step 3).

The clock pass (assistant.py) finds what only a window shows and files rows. This is the other entry point into the same
brain: when ONE item changes, one small prompt on the light gear says what to do about it - a verb the item already
carries, one line, the evidence ids - or nothing. The answer lands as an `advice` row stamped with the item's revision;
the prompt box reads it as ghost text and a pill that presses the card's own button; the rail never reads it.

Gates are on WHEN the model runs, never on whether: only on a state change (the revision), once per item per revision,
a per-hour cap, the light gear, a small prompt, the bigger read only for the item on the table, silence when nothing.
"""
import hashlib, json, re, threading
from datetime import datetime, timedelta
from loguru import logger

ON_KEY, CAP_KEY, CAP_DEFAULT = 'advisor_events', 'advisor_event_cap', 30
def _now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def key_of(target_kind: str, target_id) -> str: return f"{'task' if target_kind == 'task' else 'msg'}:{int(target_id)}"
def target_of(store, key: str):
    """A rail key -> (target kind, id), or None for a key with nothing to advise on (a connection, a meeting, a batch)."""
    m = re.match(r'^(task|agent|wrap|msg|report):(\d+)$', str(key or ''))
    if m: return ('task' if m.group(1) in ('task', 'agent', 'wrap') else 'message', int(m.group(2)))
    if str(key or '').startswith('processing:'):
        try:
            with store._processing_read() as cur: hit = store._processing_read_target(cur, key)
        except Exception: hit = None
        if hit and hit[1] in ('task', 'message'): return (hit[1], int(hit[2]))
    return None


def revision(store, target_kind: str, target_id) -> str:
    """The stamp advice is pinned to: the proposal's own context revision (messages and status) joined with what that
    revision leaves out and an event changes - the task's state and the newest word its agent said."""
    from .operations import context_revision
    base = context_revision(store, target_kind, target_id)
    if target_kind == 'task':
        t = store.get_task(target_id) or {}
        ev = store._one('SELECT MAX(Id) AS Id FROM worker_event WHERE TaskId=?', (int(target_id),)) or {}
        base += f"|{t.get('Status')}|{t.get('Assignee')}|{t.get('DueAt')}|{ev.get('Id')}"
    return hashlib.sha1(base.encode()).hexdigest()[:16]


def _write(store, *, target_kind, target_id, key, event, revision, tier=1, line='', verb=None, label=None, count=(0, 0),
           evidence=(), model=None, dropped=None) -> int:
    return store._exec('INSERT INTO advice (TargetKind,TargetId,Key,Event,Revision,Tier,Line,Verb,Label,CountJson,EvidenceJson,Model,Dropped,CreatedAt) '
                       'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (target_kind, int(target_id), key, event, revision, int(tier), line or '', verb, label, json.dumps(list(count)),
                        json.dumps(list(evidence)), model, dropped, _now()))
def row(store, target_kind: str, target_id, revision: str):
    return store._one('SELECT * FROM advice WHERE TargetKind=? AND TargetId=? AND Revision=? ORDER BY Tier DESC, Id DESC LIMIT 1',
                      (target_kind, int(target_id), revision))
def rows(store, target_kind: str, target_id, limit: int = 10) -> list:
    return store._rows('SELECT * FROM advice WHERE TargetKind=? AND TargetId=? ORDER BY Id DESC LIMIT ?', (target_kind, int(target_id), limit))
