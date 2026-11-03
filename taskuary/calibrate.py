"""WHAT THE OWNER DID IN THIS STATE (the owner, 2026-11-01: "yes - quiet unless sure"; 2026-11-02: "never ever use hard coded rules,
let the ai see everything"). The record is the press log (advice_press): every press keeps the state the item was in, so for each state
there is a count of what the owner chose there - lit or not. It was an on/off switch on a rule's button (under BAR of the owner's choices,
on MIN or more, the button went dark); now it is EVIDENCE the Advisor's model reads beside the item ("in this state the owner pressed Mark
done 12 of 19 times") and weighs against the item's own facts. Nothing here lights or darkens a button.

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


def evidence(store, state: str, workstream: str = None, label=None) -> str:
    """The owner's answers in `state` over the last DAYS days, as the sentence the Advisor's prompt carries - the workstream's own record
    once it has MIN decisions, else the whole home's; '' with none. `label` names a verb by its button (buttons.label)."""
    if not state: return ''
    for ws in ([workstream] if workstream else []) + [None]:
        c = record(store, ws).get(state) or {}
        n = sum(c.values())
        if not n or (ws and n < MIN): continue
        top = sorted(c.items(), key=lambda x: -x[1])
        said = ', '.join(f"{(label or str)(v)} {k} of {n}" for v, k in top)
        return f"in this state ({state}) over the last {DAYS} days{' in this workstream' if ws else ''}, the owner chose: {said}{habit(top, n, label)}"
    return ''


def habit(top: list, n: int, label=None) -> str:
    """A HABIT (the owner, 2026-11-02: "the same move >=80% of the time over >=5 cases, the Advisor starts lighting that move"): said beside
    the record, with the instruction in advisor.SYSTEM - the model still reads whether this item is the usual one. '' under the bar."""
    v, k = top[0] if top else ('', 0)
    return f"; a HABIT: {(label or str)(v)} ({k} of {n})" if n >= MIN and k / n >= BAR else ''


def clear(): _cache.clear()
