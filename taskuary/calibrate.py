"""QUIET UNLESS SURE (the owner, 2026-11-01: "yes - quiet unless sure"; the design, S1). A rule lights its button only where the owner's
own record says that button is what they do in that state. The record is the press log (advice_press): every press keeps the state the
item was in, so for each state there is a count of what the owner chose there - lit or not. A rule's button whose share of the owner's
choices in its state is under BAR, on at least MIN decisions, goes dark; with fewer, the rule stands as it always did (a new home has
no record, and nothing is learned from a light nobody sees).

This counts presses, never words (no hardcoded words: the model reads intent) and never reaches triage (press habits never do)."""
import time
from collections import defaultdict

BAR, MIN, DAYS = 0.8, 5, 30
NOT_ANSWERS = {'back', 'reopen'}                             # moving about, never an answer
TWIN = {'let_go': 'close', 'done': 'close', 'try_again': 'continue', 'remove': 'close'}
TTL = 600
_cache: dict = {}
def _v(v): return TWIN.get(v or '', v or '')


def choices(rows) -> dict:
    """{state: {verb: n}} - the owner's answer on each decision (an item at one revision): its first press that is not Next, else Next."""
    first = {}
    for r in rows:
        p = r.get('Pressed')
        if not r.get('State') or not p or p in NOT_ANSWERS: continue
        k = (r['Key'], r.get('Revision') or '')
        if k not in first or (first[k][1] == 'next' and p != 'next'): first[k] = (r['State'], p)
    out = defaultdict(lambda: defaultdict(int))
    for st, p in first.values(): out[st][_v(p)] += 1
    return out


def share(counts: dict, verb: str):
    """(share, n): how often the owner chose `verb` among their answers in one state."""
    n = sum(counts.values())
    return ((counts.get(_v(verb), 0) / n) if n else None), n


def record(store, workstream: str = None) -> dict:
    key = (id(store), workstream or '')
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL: return hit[1]
    q = ("SELECT p.Key, p.Revision, p.State, p.Pressed FROM advice_press p WHERE p.CreatedAt >= datetime('now', 'localtime', ?) "
         "AND p.State IS NOT NULL")
    a = [f'-{DAYS} days']
    if workstream:
        q += " AND p.TargetKind='task' AND p.TargetId IN (SELECT TaskId FROM task WHERE Workstream=?)"; a.append(workstream)
    try: rows = store._rows(q + ' ORDER BY p.Id', tuple(a))
    except Exception: rows = []
    c = choices(rows)
    _cache[key] = (time.time(), c)
    return c


def trusted(store, state: str, verb: str, workstream: str = None) -> bool:
    """Whether a rule may light `verb` in `state`: the owner chose it at least BAR of the time there, or there is too little record to say.
    With a workstream, its own record decides once it has MIN decisions, else the whole home's."""
    if not state or not verb: return True
    for ws in ([workstream] if workstream else []) + [None]:
        s, n = share(record(store, ws).get(state, {}), verb)
        if n >= MIN: return s >= BAR
    return True


def clear(): _cache.clear()
