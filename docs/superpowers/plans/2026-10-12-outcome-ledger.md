# Outcome ledger (build step 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One table records, for every action the app took or proposed, what the owner did next and what the world did after; a once-a-day sweep resolves open rows from facts already in the store; reflection reads the resolved rows as evidence so LEARNED.md can hold habits ("green PR from the coder: you merge it, 8 of 8").

**Architecture:** A new module `taskuary/outcomes.py` owns one table (`outcome`), one recorder (`record`), one resolver (`resolve`, run by `sweep_if_due` from the poll's housekeeping), and one reader (`evidence`, lines for reflection). Seven existing doors call `record` in one line each. `learn.gather` appends the ledger's lines to what reflection reads; `learnedgraph` learns the `out` id prefix. No model runs anywhere in this plan except the reflection that already exists: the sweep is bookkeeping, judgment stays the model's.

**Tech Stack:** Python 3.12 / SQLite (`taskuary/`), pytest (`tests/`).

**Spec:** `docs/superpowers/specs/2026-10-12-goals-outcomes-advisor-design.md`, section "The outcome ledger", build step 2.

## Global Constraints

- Public repo: stand-ins only (northwind.example, Alex Doyle, Ray Colton, Gail Moreno, Payworth).
- Concise fast.ai style matching the file; no autoformatters.
- Never route on a word match: the sweep records facts (counts, dates, the owner's words verbatim); what they mean is the model's at reflection. No function in this plan classifies the owner's words.
- Push only after the full pytest suite from the repo root; known failure `tests/test_deps.py::…packaged_exe…`.
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Tables are created in the `SQLiteStore` constructor's migration block, like `operation` (`store.py:918`), never in `SCHEMA`.

## Review Focus

1. **A reply sent, then the sender's auto-reply**: an out-of-office is not a round; the resolver must count only material inbound (reuse `assistant._ooo_row` / `counsel.is_invite` through the store's existing filters). Pinned in Task 2 (`test_an_auto_reply_is_not_a_round`).
2. **A task closed by the owner then reopened by the owner's own hand within a day** (misclick): the resolver says "reopened" only after the 7-day window, from `Status`, never from `ClosedAt` alone. Pinned in Task 2 (`test_a_closed_task_resolves_after_its_window`).
3. **The sweep running twice in one day** (two polls, a restart): the setting `outcomes_swept_on` gates it; a second run resolves nothing twice. Pinned in Task 3 (`test_the_sweep_runs_once_a_day`).
4. **A continue with no words** (Continue session pressed, nothing typed): the row's `NextMove` is `''`, never `None` text or "None". Pinned in Task 4 (`test_a_continue_with_no_words_records_an_empty_move`).
5. **Reflection sees the ledger**: `learn.gather` must include resolved rows and `learnedgraph` must resolve `out123` ids, or the habit line's evidence is "other" and decays wrongly. Pinned in Task 5.

---

### Task 1: The table, the recorder and the reader

**Files:**
- Create: `taskuary/outcomes.py`
- Modify: `taskuary/store.py` (the migration block after the `discussion` table, `:923`)
- Test: `tests/test_outcomes.py` (new)

**Interfaces:**
- Produces: table `outcome (Id INTEGER PK, Kind TEXT, TargetKind TEXT, TargetId INTEGER, Actor TEXT, At TEXT, FactsJson TEXT, NextMove TEXT, NextAt TEXT, Outcome TEXT, ResolvedAt TEXT, Verdict TEXT)`; `outcomes.KINDS = ('reply.sent', 'task.closed', 'agent.stopped', 'agent.continued', 'pr.merged', 'promise.made', 'sender.ignored')`; `outcomes.record(store, kind, target_kind, target_id, actor='owner', facts=None, next_move=None, at=None) -> int` (raises `ValueError` on an unknown kind); `outcomes.rows_for(store, target_kind, target_id) -> list` (newest first); `outcomes.open_rows(store) -> list`; `outcomes.settle(store, row_id, outcome, verdict, now=None)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_outcomes.py
"""The outcome ledger (spec 2026-10-12, build step 2): what the app did, what the owner did next, what came of it."""
import unittest
from datetime import datetime, timedelta
from taskuary import outcomes
from taskuary.store import MemoryStore


def ago(days=0, hours=0): return (datetime.now() - timedelta(days=days, hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


class RecordTests(unittest.TestCase):
    def test_a_row_is_written_and_read_back_newest_first(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'x'}, 'owner')
        a = outcomes.record(s, 'task.closed', 'task', t, 'owner', facts={'how': 'close_from_assistant'})
        b = outcomes.record(s, 'agent.continued', 'task', t, 'owner', next_move='merge it')
        rows = outcomes.rows_for(s, 'task', t)
        self.assertEqual([r['Id'] for r in rows], [b, a])
        self.assertEqual((rows[0]['Kind'], rows[0]['NextMove'], rows[1]['Verdict']), ('agent.continued', 'merge it', None))
        self.assertEqual(rows[1]['FactsJson'], '{"how": "close_from_assistant"}')

    def test_an_unknown_kind_is_refused(self):
        with self.assertRaises(ValueError): outcomes.record(MemoryStore(), 'nonsense', 'task', 1)

    def test_settle_closes_a_row_once(self):
        s = MemoryStore()
        i = outcomes.record(s, 'promise.made', 'task', 1)
        outcomes.settle(s, i, 'delivered 2 days early', 'kept')
        self.assertEqual([r['Id'] for r in outcomes.open_rows(s)], [])
        r = outcomes.rows_for(s, 'task', 1)[0]
        self.assertEqual((r['Outcome'], r['Verdict']), ('delivered 2 days early', 'kept')); self.assertTrue(r['ResolvedAt'])
```

- [ ] **Step 2: Run to see it fail**

Run: `python -m pytest tests/test_outcomes.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'taskuary.outcomes'`.

- [ ] **Step 3: The table**

In `taskuary/store.py`, right after the `discussion` table creation (`:923`):

```python
            # THE OUTCOME LEDGER (spec 2026-10-12, build step 2): what the app did, what the owner did next, what came of
            # it - resolved later by outcomes.resolve from facts already here. Evidence for reflection, never a rule.
            self.cx.execute('CREATE TABLE IF NOT EXISTS outcome (Id INTEGER PRIMARY KEY, Kind TEXT, TargetKind TEXT, TargetId INTEGER, '
                            'Actor TEXT, At TEXT, FactsJson TEXT, NextMove TEXT, NextAt TEXT, Outcome TEXT, ResolvedAt TEXT, Verdict TEXT)')
            self.cx.execute('CREATE INDEX IF NOT EXISTS outcome_target ON outcome(TargetKind, TargetId)')
```

- [ ] **Step 4: The module**

```python
# taskuary/outcomes.py
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
```

(`store._exec` returns the inserted row id: confirm with `grep -n "def _exec" taskuary/store.py`; if it returns the cursor, use `.lastrowid`.)

- [ ] **Step 5: Run to see it pass**

Run: `python -m pytest tests/test_outcomes.py -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add taskuary/outcomes.py taskuary/store.py tests/test_outcomes.py
git commit -m "The outcome ledger: one table, a recorder and a reader

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: The resolver

**Files:**
- Modify: `taskuary/outcomes.py`
- Test: `tests/test_outcomes.py`

**Interfaces:**
- Consumes: `store.get_task`, `store.get_message`, `store.last_inbound_in`, `store.tasks_from_sender(sender, since, limit)`, `store.sent_verdict(mid)`, `assistant._ooo_row(row)`, `counsel.is_invite(row)`.
- Produces: `outcomes.resolve(store, now=None) -> int` (rows resolved this pass); verdict vocabulary per kind: `reply.sent` → `settled` | `unsettled: N more` ; `task.closed` → `held` | `reopened`; `agent.stopped` → `continued` | `closed` | `left`; `pr.merged` → `held`; `promise.made` → `kept` | `kept late` | `late`; `sender.ignored` → `no regret` | `regret`.

- [ ] **Step 1: Write the failing tests**

```python
class ResolveTests(unittest.TestCase):
    def _thread(self, s, cid='c1'):
        s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': 'AP cutover', 'FromEmail': 'erin@northwind.example', 'FromName': 'Erin Blake',
                       'SentAt': ago(days=9), 'BodyText': 'Still Thursday?', 'Status': 'filed'})
        return s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': 'Re: AP cutover', 'FromEmail': 'alex@northwind.example',
                              'FromName': 'Alex Doyle', 'SentAt': ago(days=8), 'BodyText': 'Thursday works.', 'Status': 'context'})

    def test_a_reply_nobody_wrote_back_on_is_settled_after_its_window(self):
        s = MemoryStore(); t = s.create_task({'Title': 'AP cutover', 'Status': 'done'}, 'owner'); mid = self._thread(s)
        i = outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': 'c1', 'mid': mid}, at=ago(days=8))
        self.assertEqual(outcomes.resolve(s), 1)
        self.assertEqual(outcomes.rows_for(s, 'task', t)[0]['Verdict'], 'settled')

    def test_more_rounds_after_a_reply_are_unsettled_and_counted(self):
        s = MemoryStore(); t = s.create_task({'Title': 'Payworth billing'}, 'owner'); mid = self._thread(s, 'c2')
        for d in (6, 4): s.add_message({'ConversationId': 'c2', 'Channel': 'email', 'Subject': 'Re: billing', 'FromEmail': 'billing@vendor.example',
                                       'FromName': 'Payworth', 'SentAt': ago(days=d), 'BodyText': 'And the PO number?', 'Status': 'filed'})
        outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': 'c2', 'mid': mid}, at=ago(days=8))
        outcomes.resolve(s)
        self.assertEqual(outcomes.rows_for(s, 'task', t)[0]['Verdict'], 'unsettled: 2 more')

    def test_an_auto_reply_is_not_a_round(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner'); mid = self._thread(s, 'c3')
        s.add_message({'ConversationId': 'c3', 'Channel': 'email', 'Subject': 'Automatic reply: Re: AP cutover', 'FromEmail': 'erin@northwind.example',
                       'FromName': 'Erin Blake', 'SentAt': ago(days=7), 'BodyText': 'I am out of the office until Monday.', 'Status': 'filed'})
        outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': 'c3', 'mid': mid}, at=ago(days=8))
        outcomes.resolve(s)
        self.assertEqual(outcomes.rows_for(s, 'task', t)[0]['Verdict'], 'settled')

    def test_a_closed_task_resolves_after_its_window(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'done'}, 'owner')
        i = outcomes.record(s, 'task.closed', 'task', t, at=ago(days=3))
        self.assertEqual(outcomes.resolve(s), 0)                                   # inside the window: nothing yet
        s._exec('UPDATE outcome SET At=? WHERE Id=?', (ago(days=8), i))
        outcomes.resolve(s); self.assertEqual(outcomes.rows_for(s, 'task', t)[0]['Verdict'], 'held')
        t2 = s.create_task({'Title': 'y', 'Status': 'open'}, 'owner')
        outcomes.record(s, 'task.closed', 'task', t2, at=ago(days=8)); outcomes.resolve(s)
        self.assertEqual(outcomes.rows_for(s, 'task', t2)[0]['Verdict'], 'reopened')

    def test_a_stop_takes_the_owners_next_move_from_the_later_row(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        i = outcomes.record(s, 'agent.stopped', 'task', t, 'agent:coder', facts={'pr': True}, at=ago(hours=30))
        outcomes.record(s, 'agent.continued', 'task', t, next_move='merge it', at=ago(hours=29))
        outcomes.resolve(s)
        r = s._one('SELECT * FROM outcome WHERE Id=?', (i,))
        self.assertEqual((r['Verdict'], r['NextMove']), ('continued', 'merge it'))
        j = outcomes.record(s, 'agent.stopped', 'task', t, 'agent:coder', at=ago(days=3)); outcomes.resolve(s)
        self.assertEqual(s._one('SELECT Verdict FROM outcome WHERE Id=?', (j,))['Verdict'], 'left')

    def test_a_promise_is_kept_late_or_late(self):
        s = MemoryStore(); t = s.create_task({'Title': 'Send the budget', 'DueAt': (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d'), 'Status': 'done'}, 'owner')
        i = outcomes.record(s, 'promise.made', 'task', t, at=ago(days=9)); s._exec('UPDATE task SET ClosedAt=? WHERE TaskId=?', (ago(days=1), t))
        outcomes.resolve(s); self.assertEqual(s._one('SELECT Verdict FROM outcome WHERE Id=?', (i,))['Verdict'], 'kept late')
        t2 = s.create_task({'Title': 'Send the deck', 'DueAt': (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d'), 'Status': 'open'}, 'owner')
        j = outcomes.record(s, 'promise.made', 'task', t2, at=ago(days=20)); outcomes.resolve(s)
        self.assertEqual(s._one('SELECT Verdict FROM outcome WHERE Id=?', (j,))['Verdict'], 'late')

    def test_an_ignored_sender_who_later_became_a_task_is_regret(self):
        s = MemoryStore()
        i = outcomes.record(s, 'sender.ignored', 'policy', 1, facts={'from': 'news@vendor.example'}, at=ago(days=61))
        outcomes.resolve(s); self.assertEqual(s._one('SELECT Verdict FROM outcome WHERE Id=?', (i,))['Verdict'], 'no regret')
        j = outcomes.record(s, 'sender.ignored', 'policy', 2, facts={'from': 'ray@vendor.example'}, at=ago(days=61))
        t = s.create_task({'Title': 'from ray'}, 'owner')
        s.add_message({'ConversationId': 'c9', 'Channel': 'email', 'Subject': 'Quote', 'FromEmail': 'ray@vendor.example', 'SentAt': ago(days=30), 'BodyText': 'x', 'Status': 'routed', 'TaskId': t})
        outcomes.resolve(s); self.assertEqual(s._one('SELECT Verdict FROM outcome WHERE Id=?', (j,))['Verdict'], 'regret')
```

- [ ] **Step 2: Run to see it fail** → `AttributeError: module 'taskuary.outcomes' has no attribute 'resolve'`.

- [ ] **Step 3: The resolver**

Append to `taskuary/outcomes.py`:

```python
def _material_inbound_after(store, cid: str, at: str) -> list:
    """Their words on the thread after `at`: not the owner's, not an auto-reply, not a calendar response."""
    from .assistant import _ooo_row
    from .counsel import is_invite
    me = str(store.get_setting('owner_email', '') or '').lower()
    rows = store._rows("SELECT * FROM message WHERE ConversationId=? AND SentAt>? AND Status!='context' ORDER BY SentAt", (cid, at))
    return [r for r in rows if str(r.get('FromEmail') or '').lower() != me and not _ooo_row(r) and not is_invite(r)]


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
            before = store._one('SELECT ResolvedAt FROM outcome WHERE Id=?', (r['Id'],))['ResolvedAt']
            _resolve_one(store, r, now)
            if not before and store._one('SELECT ResolvedAt FROM outcome WHERE Id=?', (r['Id'],))['ResolvedAt']: n += 1
        except Exception as e: logger.warning(f'outcome {r["Id"]} not resolved: {e}')
    return n
```

Check `store.tasks_from_sender(sender, since, limit=3)` (`store.py:2235`) matches by `FromEmail` on the task's messages; if it needs a list, pass `[who]`.

- [ ] **Step 4: Run to see it pass** → `python -m pytest tests/test_outcomes.py -q` PASS.

- [ ] **Step 5: Commit** — `git commit -m "The outcome ledger resolves open rows from the store's own facts"` (with the trailer).

---

### Task 3: The once-a-day sweep

**Files:**
- Modify: `taskuary/outcomes.py`, `taskuary/server.py` (the `_poll_reports` housekeeping beside `retention.tick`, `:6976-6981`)
- Test: `tests/test_outcomes.py`

**Interfaces:**
- Produces: `outcomes.sweep_if_due(store, now=None) -> int | None` (None when already swept today; the setting `outcomes_swept_on` holds the date).

- [ ] **Step 1: Failing test**

```python
class SweepTests(unittest.TestCase):
    def test_the_sweep_runs_once_a_day(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'done'}, 'owner')
        outcomes.record(s, 'task.closed', 'task', t, at=ago(days=8))
        self.assertEqual(outcomes.sweep_if_due(s), 1)
        outcomes.record(s, 'task.closed', 'task', t, at=ago(days=8))
        self.assertIsNone(outcomes.sweep_if_due(s))                                 # swept today already
        self.assertEqual(outcomes.sweep_if_due(s, now=datetime.now() + timedelta(days=1)), 1)
```

- [ ] **Step 2: Run** → `AttributeError … sweep_if_due`.

- [ ] **Step 3: Implement**

```python
def sweep_if_due(store, now: datetime = None):
    now = now or datetime.now(); today = now.strftime('%Y-%m-%d')
    if store.get_setting(SWEPT_KEY, '') == today: return None
    n = resolve(store, now)
    store.set_setting(SWEPT_KEY, today, 'outcomes')
    return n
```

In `taskuary/server.py`, inside `_poll_reports`'s housekeeping next to `retention.tick` / `blackboard.roll_daily`:

```python
        try: outcomes.sweep_if_due(store)            # the outcome ledger: resolve what is old enough to judge, once a day
        except Exception as e: logger.warning(f'outcome sweep skipped: {e}')
```

with `from . import outcomes` beside the other local imports there (match the file's style: the block imports `retention` and `blackboard` the same way).

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `"The outcome ledger sweeps once a day from the poll's housekeeping"`.

---

### Task 4: The seven doors record

**Files:**
- Modify: `taskuary/verdicts.py` (after delivery, where `approve`/`edit` is audited, `:231`), `taskuary/concierge.py` (`close_task`, `:2023`), `taskuary/selfclose.py` (`_wrap`, `:212`), `taskuary/server.py` (`continue_session` `:1623-1651`, `continue_work` `:1743/:1763`, `ignore_sender` rule path `:2576-2600`), `taskuary/hooks.py` (the `Stop` branch, `:372-389`), `taskuary/proposals.py` (merge_pr success, `:428`), `taskuary/store.py` (`task_for_promise`, `deliver_promise`)
- Test: `tests/test_outcomes.py` (door tests on MemoryStore where the door is store-level or concierge-level; the hooks and verdicts doors are pinned by patching `outcomes.record` and asserting the call)

**Interfaces:**
- Consumes: `outcomes.record`, `outcomes.settle`, `outcomes.rows_for`.
- Produces: rows with these facts: `reply.sent` → `{'cid', 'mid', 'review', 'verb' ('approve'|'edit'), 'closed': bool}` target task (or `message` when there is no task); `task.closed` → `{'how': 'close_from_assistant'|'self_close'|'agent_done'}`; `agent.stopped` → `{'pr': bool, 'agent'}` actor `agent:<name>`; `agent.continued` → `next_move` = the owner's words (empty string when none), facts `{'door': 'continue-session'|'continue-work'|'continue'}`; `pr.merged` → `{'pr': number}`; `promise.made` → `{'mid', 'due'}`; `sender.ignored` → `{'from', 'rule'}` target policy.

- [ ] **Step 1: Failing tests**

```python
class DoorsTests(unittest.TestCase):
    def test_closing_a_task_from_the_assistant_records_it(self):
        from taskuary import concierge
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        concierge.close_task(s, t, 'owner')
        r = outcomes.rows_for(s, 'task', t)[0]
        self.assertEqual((r['Kind'], r['Actor'], json.loads(r['FactsJson'])['how']), ('task.closed', 'owner', 'close_from_assistant'))

    def test_a_promise_task_records_its_making_and_its_delivery(self):
        s = MemoryStore()
        mid = s.add_message({'ConversationId': 'c1', 'Channel': 'email', 'Subject': 'Budget', 'FromEmail': 'alex@northwind.example', 'SentAt': ago(days=2), 'BodyText': 'x', 'Status': 'context'})
        t = s.task_for_promise(mid, 'send the budget', (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d'))
        self.assertEqual(outcomes.rows_for(s, 'task', t)[0]['Kind'], 'promise.made')
        s.put_sent_verdict(mid, 'c1', False, True, 'send the budget', None, 'test'); s.deliver_promise(mid, mid)
        self.assertEqual(outcomes.rows_for(s, 'task', t)[0]['Verdict'], 'kept')

    def test_a_continue_with_no_words_records_an_empty_move(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        outcomes.record(s, 'agent.continued', 'task', t, next_move=None, facts={'door': 'continue-session'})
        self.assertEqual(outcomes.rows_for(s, 'task', t)[0]['NextMove'], '')
```

Add `import json` at the top of the test file.

- [ ] **Step 2: Run** → the first two fail (no row).

- [ ] **Step 3: Wire the doors** (one line each; the `from . import outcomes` goes beside each file's other local imports):

- `concierge.close_task`, after `store.audit('task', tid, 'close_from_assistant', actor)`:
  `outcomes.record(store, 'task.closed', 'task', tid, actor, facts={'how': 'close_from_assistant'})`
- `selfclose._wrap`, after its `self_close` audit: `outcomes.record(store, 'task.closed', 'task', tid, agent, facts={'how': 'self_close'})`
- `store.task_for_promise`, before `return tid`: `from . import outcomes; outcomes.record(self, 'promise.made', 'task', tid, 'promise', facts={'mid': mid, 'due': due})`
- `store.deliver_promise`, after closing the task: resolve the promise row at once:
  ```python
  from . import outcomes
  for r in outcomes.rows_for(self, 'task', t['TaskId']):
      if r['Kind'] == 'promise.made' and not r['ResolvedAt']: outcomes._resolve_one(self, r, datetime.now())
  ```
  (import `datetime` is already in store.py; confirm with grep.)
- `verdicts.py`, where the `approve`/`edit` audit is written after a real send (`:231`): `outcomes.record(store, 'reply.sent', 'task' if tid else 'message', tid or mid, actor, facts={'cid': cid, 'mid': mid, 'review': rv['ReviewId'], 'verb': verb, 'closed': closed})` — read the surrounding names (`tid`, `mid`, `cid` from the review's message row, `closed` = whether decide closes the task) and use the file's own variables.
- `server.continue_session` (`:1623`), after its audit: `outcomes.record(store, 'agent.continued', 'task', task_id, ACTOR, next_move=(body.instruction if body else None) or '', facts={'door': 'continue-session'})`
- `server.continue_work` (both branches), after the audit: `outcomes.record(store, 'agent.continued', 'task', task_id, ACTOR, next_move=note or '', facts={'door': 'continue-work', 'kind': kind})`
- `server.ignore_sender` rule path, after the policy `create` audit: `outcomes.record(store, 'sender.ignored', 'policy', pid, ACTOR, facts={'from': frm, 'rule': 'skip'})` (use the handler's own variable names for the address and policy id)
- `hooks._events` `Stop` branch, after `turn_end` is recorded: `outcomes.record(store, 'agent.stopped', 'task', tid, f"agent:{t.agent}", facts={'pr': bool(ci.pr_of(store, tid)), 'agent': t.agent})` — `store`, `t` and `tid` are the names the branch already uses; import `ci` beside hooks' other local imports; wrap in `try/except Exception` so a ledger failure never breaks a hook.
- `proposals.execute` merge_pr success (`:428`): `outcomes.record(store, 'pr.merged', 'task', tid, actor, facts={'pr': number})` with the function's own names.

- [ ] **Step 4: Run** `python -m pytest tests/test_outcomes.py tests/test_sentjudge.py tests/test_goals_promises.py tests/test_asks.py tests/test_assistant_reactions.py -q` → PASS (the reactions matrix exercises close_task and continue).

- [ ] **Step 5: Commit** `"Seven doors write the outcome ledger: reply sent, task closed, agent stopped and continued, PR merged, promise made, sender ignored"`.

---

### Task 5: Reflection reads the ledger

**Files:**
- Modify: `taskuary/outcomes.py` (`evidence`), `taskuary/learn.py` (`gather`, `:223`; `REFLECT_SYSTEM` one sentence), `taskuary/learnedgraph.py` (`_EV`, `_resolve`, `:29`, `:126`)
- Test: `tests/test_outcomes.py`, `tests/test_learnedgraph.py`

**Interfaces:**
- Produces: `outcomes.evidence(store, since: str, limit: int = 40) -> list[str]`: one line per resolved row, newest first, `out{id}: {sentence}`; sentences are facts with the owner's words verbatim, e.g. `out12: the coder stopped on TQ-0712 (PR open); you continued 2 min later with "merge it"; the PR held two weeks.`; `learnedgraph._EV` accepts `out`; `learn.gather` ends with a `WHAT CAME OF ACTIONS (the outcome ledger):` block when there are lines.

- [ ] **Step 1: Failing tests**

```python
class EvidenceTests(unittest.TestCase):
    def test_resolved_rows_become_evidence_lines_with_their_ids(self):
        s = MemoryStore(); t = s.create_task({'Title': 'Export job'}, 'owner')
        i = outcomes.record(s, 'agent.stopped', 'task', t, 'agent:coder', facts={'pr': True}, at=ago(hours=30))
        outcomes.record(s, 'agent.continued', 'task', t, next_move='merge it', at=ago(hours=29)); outcomes.resolve(s)
        lines = outcomes.evidence(s, ago(days=30))
        self.assertTrue(lines[0].startswith(f'out{i}: ') or lines[1].startswith(f'out{i}: '))
        self.assertTrue(any('"merge it"' in l and 'coder stopped' in l for l in lines))

    def test_reflection_gathers_the_ledger_and_the_graph_resolves_out_ids(self):
        from taskuary import learn, learnedgraph
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'done'}, 'owner')
        i = outcomes.record(s, 'task.closed', 'task', t, at=ago(days=8)); outcomes.resolve(s)
        self.assertIn('WHAT CAME OF ACTIONS', learn.gather(s, ago(days=30)))
        self.assertIn(f'out{i}', learn.gather(s, ago(days=30)))
        self.assertEqual(learnedgraph._EV.match(f'out{i}').group(1), 'out')
```

- [ ] **Step 2: Run** → fail on `evidence` missing.

- [ ] **Step 3: Implement**

`taskuary/outcomes.py`:

```python
def _sentence(store, r: dict) -> str:
    """The row as one factual sentence with the owner's words verbatim - what happened, never what it means."""
    f = json.loads(r.get('FactsJson') or '{}'); kind = r['Kind']
    ref = f"TQ-{int(r['TargetId']):04d}" if r['TargetKind'] == 'task' and r['TargetId'] else r['TargetKind']
    who = str(r.get('Actor') or '').split(':', 1)[-1]
    nxt = f'; you then {r["NextMove"]!r}' if kind == 'agent.stopped' and r.get('NextMove') and r['Verdict'] == 'continued' else ''
    head = {'reply.sent': f"you sent a reply on {ref} ({f.get('verb', 'approve')}d as drafted)" if f.get('verb') == 'approve' else f"you sent a reply on {ref} (edited first)",
            'task.closed': f"{ref} was closed by {who} ({f.get('how', '')})", 'agent.stopped': f"{who} stopped on {ref}" + (' (PR open)' if f.get('pr') else ''),
            'agent.continued': f"you continued {ref} with {r.get('NextMove')!r}" if r.get('NextMove') else f'you continued {ref} with no words',
            'pr.merged': f"PR #{f.get('pr')} on {ref} was merged", 'promise.made': f"you promised on {ref}" + (f" by {f.get('due')}" if f.get('due') else ''),
            'sender.ignored': f"you ignored {f.get('from')}"}.get(kind, kind)
    return f"{head}{nxt}; outcome: {r.get('Outcome') or ''} [{r.get('Verdict') or ''}]"


def evidence(store, since: str, limit: int = 40) -> list:
    rows = store._rows('SELECT * FROM outcome WHERE ResolvedAt IS NOT NULL AND At>=? ORDER BY Id DESC LIMIT ?', (since, limit))
    return [f"out{r['Id']}: {_sentence(store, r)}" for r in rows]
```

`taskuary/learn.py` `gather(store, since)`: at the end, before returning, add

```python
    from . import outcomes
    out = outcomes.evidence(store, since)
    if out: parts.append('WHAT CAME OF ACTIONS (the outcome ledger - what you did next and what followed; a habit is what you do when nothing corrected it):\n' + '\n'.join(out))
```

using whatever list/string `gather` builds (read it: if it joins a list named differently, use that name). Add one sentence to `REFLECT_SYSTEM`: `'Lines from the outcome ledger (out123) are evidence of HABITS and of what WORKED: a move the owner makes every time an agent stops the same way is a rule about the owner; a reply that always gets more rounds is a fact about what works. Cite their ids like any other.'`

`taskuary/learnedgraph.py`: `_EV = re.compile(r'^(mem|rv|task|out)(\d+)$')`; in `_resolve`, add a branch for `out` returning `{'kind': 'outcome', **row}` from `store._one('SELECT * FROM outcome WHERE Id=?', (n,))`.

- [ ] **Step 4: Run** `python -m pytest tests/test_outcomes.py tests/test_learnedgraph.py tests/test_docs_and_llm.py -q` → PASS.

- [ ] **Step 5: Commit** `"Reflection reads the outcome ledger; out-ids are evidence like mem, rv and task"`.

---

## Self-review

**Spec coverage:** the table and the seven action kinds (T1, T4); resolution from facts without a model (T2); the nightly sweep (T3); distillation into LEARNED.md through the existing reflection with the same grammar (T5). Per-person pages and work facts into playbooks are build step 4 and 5 plans, which read `outcomes.rows_for` / `evidence`.

**Placeholders:** none. Three steps say "use the file's own variable names" where the explorer gave the line but not the names; the implementer reads those lines.

**Type consistency:** `record(store, kind, target_kind, target_id, actor, facts, next_move, at)` everywhere; `rows_for` newest first (T1 test, T4 door tests rely on `[0]`).

**Review Focus:** each line has its test.
