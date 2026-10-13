# The Advisor's event path (build step 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When one item changes, one small model prompt on the light gear says what to do about it (a verb the item already carries, one line, the evidence ids), the answer lands as an `advice` row stamped with the item's revision, the prompt box shows it as ghost text and a pill that presses the card's own button, and the Advisor's notes say what it looked at and dropped. The rail never reads it.

**Architecture:** A new module `taskuary/advisor.py` owns one table (`advice`), the entry point `notice` (gates, then a background thread), the judgement `judge` (prompt, verb validation, habit counts from the outcome ledger), the readers `for_key` / `notes`, and `block` for the chat's system prompt. Eight existing doors call `notice` in one line each. `live.py` gains an `advice` event kind; `server.py` gains `GET /api/advice` and `GET /api/advice/notes`; `AssistantView.jsx` gains the ghost text and the pill. No row the rail builds from is touched: the test that pins it builds the rail with and without the table populated.

**Tech Stack:** Python 3.12 / SQLite / FastAPI (`taskuary/`), pytest (`tests/`), React 18 + Vite (`website/`), node:test for the page.

**Spec:** `docs/superpowers/specs/2026-10-12-goals-outcomes-advisor-design.md`, sections "The Advisor on two clocks", "Surfaces", "Mechanics: what touches the rail", "Seeing the Advisor's thinking"; build step 3.

## Global Constraints

- Public repo: stand-ins only (northwind.example, Alex Doyle, Ray Colton, Gail Moreno, Payworth).
- Concise fast.ai style matching the file; no autoformatters; `website/src` files must stay LF (`test/buildInputs.test.mjs`).
- Always the model, never a word match: the model returns the verb, code validates it against `concierge.chips_for(store, item)`; nothing routes on a hardcoded match. The number beside the pill is read from the outcome ledger, never written by the model.
- Everything runs after the event, off the request path. No button waits on the model; a Next press stays a pile rebuild.
- The rail build does not read `advice`. The table goes in neither `PROCESSING_DIRTY_TABLES` nor `processing_rail.DIRTY_ROWS`.
- One suggestion per item per revision; a per-hour cap; silence when the model has nothing to say; the light gear (`llm.build_llm(store)` with no `pick`, default `gear='light'`).
- Push only after the full pytest suite from the repo root plus `cd website && npm test && npm run lint:undef && npm run build`; the bundle under `taskuary/web` is committed; a `docs/site` or `settings_schema.json` edit needs `npm run build:docs`.
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Review Focus

1. **An event on an item that carries no actions** (an fyi row, a report with no task): no model call, no pill; a `no actions` drop is recorded once. Pinned in Task 2 (`test_an_item_with_no_actions_is_dropped_without_a_call`).
2. **The model names a verb the item cannot carry** ("merge" on a task with no PR): dropped with the verb named, no pill. Pinned in Task 2 (`test_a_verb_the_item_cannot_carry_is_dropped`).
3. **The item changes after the advice landed** (a reply arrives, the agent stops again): `for_key` returns nothing because the revision moved; no cleanup pass. Pinned in Task 4 (`test_advice_vanishes_when_the_item_moves`).
4. **The hour's cap is reached**: a `cap` drop row, no model call, and the next hour runs again. Pinned in Task 2 (`test_the_hourly_cap_drops_without_a_call`).
5. **No brain is set up** (fresh install, demo): `notice` never raises into a hook, a close or a poll; a `no brain` drop is recorded. Pinned in Task 2 (`test_no_brain_is_a_drop_never_an_error`).

---

### Task 1: The table, the revision, the rows, and the rail that never reads them

**Files:**
- Create: `taskuary/advisor.py`
- Modify: `taskuary/store.py` (the migration block, right after the `outcome` index)
- Test: `tests/test_advisor.py` (new)

**Interfaces:**
- Produces: table `advice (Id INTEGER PK, TargetKind TEXT, TargetId INTEGER, Key TEXT, Event TEXT, Revision TEXT, Tier INTEGER, Line TEXT, Verb TEXT, Label TEXT, CountJson TEXT, EvidenceJson TEXT, Model TEXT, Dropped TEXT, CreatedAt TEXT)`, index `advice_target (TargetKind, TargetId)`.
- `advisor.key_of(target_kind, target_id) -> str` (`task:{id}` / `msg:{id}`); `advisor.target_of(store, key) -> (kind, id) | None` (parses `task:`, `agent:`, `wrap:`, `msg:`, `report:`, and `processing:` through `store._processing_read_target`).
- `advisor.revision(store, target_kind, target_id) -> str`: `operations.context_revision` joined with the task's Status, Assignee, DueAt and the newest `worker_event` Id, sha1'd to 16 chars.
- `advisor.row(store, target_kind, target_id, revision) -> dict | None` (the newest row at that revision, highest Tier first); `advisor.rows(store, target_kind, target_id, limit=10) -> list` (newest first); `advisor._write(store, **cols) -> int`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_advisor.py
"""The Advisor's event path (spec 2026-10-12, build step 3): one small judgement per item per revision, a pill that
presses the card's own button, and a rail that never reads any of it."""
import json, unittest
from datetime import datetime
from unittest import mock
import pytest
from taskuary import advisor, funnel, outcomes, processing_unread, terminal
from taskuary.store import MemoryStore


class RowTests(unittest.TestCase):
    def test_a_row_is_keyed_by_target_and_revision_and_read_back(self):
        s = MemoryStore(); t = s.create_task({'Title': 'Export job'}, 'owner')
        rev = advisor.revision(s, 'task', t)
        self.assertEqual(len(rev), 16)
        i = advisor._write(s, target_kind='task', target_id=t, key='task:%d' % t, event='agent.stopped', revision=rev, tier=1,
                           line='You usually merge it here.', verb='continue', label='Continue session', count=(8, 8), evidence=['out3'], model='haiku')
        r = advisor.row(s, 'task', t, rev)
        self.assertEqual((r['Id'], r['Verb'], json.loads(r['CountJson']), json.loads(r['EvidenceJson'])), (i, 'continue', [8, 8], ['out3']))
        self.assertIsNone(advisor.row(s, 'task', t, 'other'))
        self.assertEqual([x['Id'] for x in advisor.rows(s, 'task', t)], [i])

    def test_the_revision_moves_with_the_task_and_its_agent_events(self):
        from taskuary import workerstate as ws
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'open'}, 'owner')
        a = advisor.revision(s, 'task', t)
        s.update_task(t, {'Status': 'in_progress'}, 'owner'); b = advisor.revision(s, 'task', t)
        ws.record(s, t, 'run1', 'turn_end', text='done'); c = advisor.revision(s, 'task', t)
        self.assertEqual(len({a, b, c}), 3)
        self.assertEqual(c, advisor.revision(s, 'task', t))                             # stable while nothing changes

    def test_keys_round_trip(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        self.assertEqual(advisor.key_of('task', t), f'task:{t}')
        self.assertEqual(advisor.target_of(s, f'task:{t}'), ('task', t))
        self.assertEqual(advisor.target_of(s, 'agent:7'), ('task', 7))
        self.assertEqual(advisor.target_of(s, 'msg:9'), ('message', 9))
        self.assertIsNone(advisor.target_of(s, 'conn:3'))


@pytest.fixture
def rail(monkeypatch):
    s = MemoryStore()
    s.set_setting('calendar_enabled', '0', 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [])
    monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
    for n in range(5):
        t = s.create_task({'Title': f'Arrival {n}', 'Status': 'open'}, 'owner')
        s.add_message({'ConversationId': f'c{n}', 'Channel': 'email', 'Subject': f'Arrival {n}', 'FromEmail': f'p{n}@vendor.example',
                       'SentAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'BodyText': 'x', 'Status': 'routed', 'TaskId': t})
    s.reconcile_processing_membership()
    s.activate_processing_reads(fixed_now=datetime.now().isoformat(), live_state=[])
    funnel.invalidate(); yield s; funnel.invalidate(); s.cx.close()


def order(s):
    s.reconcile_processing_membership(); funnel.invalidate()
    return [c['key'] for c in processing_unread.build(s, live_state=[], include_read=True)['items']]


def test_the_rail_is_the_same_with_and_without_advice(rail):
    before = order(rail)
    assert len(before) >= 5
    for t in rail._rows('SELECT TaskId FROM task'):
        advisor._write(rail, target_kind='task', target_id=t['TaskId'], key=f"task:{t['TaskId']}", event='task.closed',
                       revision=advisor.revision(rail, 'task', t['TaskId']), tier=1, line='Close it.', verb='close', label='Mark done',
                       count=(3, 3), evidence=[], model='haiku')
    assert order(rail) == before
```

- [ ] **Step 2: Run to see it fail**

Run: `python -m pytest tests/test_advisor.py -q`
Expected: FAIL `ImportError: cannot import name 'advisor' from 'taskuary'`.

- [ ] **Step 3: The table**

In `taskuary/store.py`, right after `self.cx.execute('CREATE INDEX IF NOT EXISTS outcome_target ON outcome(TargetKind, TargetId)')`:

```python
            # THE ADVISOR'S ADVICE (spec 2026-10-12, build step 3): one row per item per revision - the line, the verb, the
            # evidence ids, what was dropped. The rail never reads it (test_the_rail_is_the_same_with_and_without_advice).
            self.cx.execute('CREATE TABLE IF NOT EXISTS advice (Id INTEGER PRIMARY KEY, TargetKind TEXT, TargetId INTEGER, Key TEXT, Event TEXT, '
                            'Revision TEXT, Tier INTEGER, Line TEXT, Verb TEXT, Label TEXT, CountJson TEXT, EvidenceJson TEXT, Model TEXT, '
                            'Dropped TEXT, CreatedAt TEXT)')
            self.cx.execute('CREATE INDEX IF NOT EXISTS advice_target ON advice(TargetKind, TargetId)')
```

- [ ] **Step 4: The module**

```python
# taskuary/advisor.py
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
```

- [ ] **Step 5: Run to see it pass** → `python -m pytest tests/test_advisor.py -q` PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add taskuary/advisor.py taskuary/store.py tests/test_advisor.py
git commit -m "The Advisor's advice table: one row per item per revision, and a rail that never reads it

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: The judgement: gates, the small prompt, the verb the item carries, the ledger's number

**Files:**
- Modify: `taskuary/advisor.py`
- Test: `tests/test_advisor.py`

**Interfaces:**
- Consumes: `concierge.chips_for(store, item) -> [{verb, label, hint?}]`, `funnel.next_item(store, key, include_surfaced=True)`, `funnel.item_for_key(store, key)`, `learn.injectable(text)`, `outcomes.rows_for`, `outcomes._sentence`, `outcomes.evidence`, `counsel.dossier(store, msg)`, `ci.pr_of(store, tid)`, `llm.build_llm(store)`, `llm.ask_json(brain, system, user, want=, need=)`.
- Produces: `advisor.notice(store, event, target_kind, target_id, *, tier=1, wait=False, llm=None) -> int | None` (the row id when one was written inline, None when skipped or backgrounded); `advisor.judge(store, event, target_kind, target_id, rev, tier=1, llm=None) -> int`; `advisor.habit(store, verb, item) -> (n, m)`; `advisor.pill(label, count) -> str`; `advisor.VERB_PROMPT`.

- [ ] **Step 1: Write the failing tests**

```python
def brain_saying(answer: dict):
    """A light brain that answers one JSON object, and counts its calls."""
    calls = []
    def llm(system, user, max_tokens=400, images=None, want=None, **kw):
        calls.append((system, user)); return json.dumps(answer)
    llm.takes_want = False; llm.calls = calls
    return llm


class JudgeTests(unittest.TestCase):
    def _stopped_task(self, s):
        t = s.create_task({'Title': 'Export job', 'Status': 'in_progress', 'Kind': 'code'}, 'owner')
        s.add_message({'ConversationId': 'c1', 'Channel': 'email', 'Subject': 'Export job', 'FromEmail': 'gail@northwind.example', 'FromName': 'Gail Moreno',
                       'SentAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'BodyText': 'Please move the export.', 'Status': 'routed', 'TaskId': t})
        return t

    def test_a_verb_the_item_carries_lands_with_the_ledgers_number(self):
        s = MemoryStore(); t = self._stopped_task(s)
        for _ in range(3):
            i = outcomes.record(s, 'agent.stopped', 'task', t, 'agent:coder', facts={'pr': False}); outcomes.settle(s, i, 'continued 2 min later', 'continued')
        llm = brain_saying({'verb': 'continue', 'line': 'You usually continue it here.', 'evidence': ['out1']})
        rid = advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=llm)
        r = s._one('SELECT * FROM advice WHERE Id=?', (rid,))
        self.assertEqual((r['Verb'], r['Line'], json.loads(r['CountJson']), r['Dropped']), ('continue', 'You usually continue it here.', [3, 3], None))
        self.assertIn('CONTINUE', llm.calls[0][1].upper()); self.assertIn('out1', llm.calls[0][1])
        self.assertEqual(advisor.pill(r['Label'], json.loads(r['CountJson'])), f"{r['Label']} · 3 of 3 times")

    def test_the_same_revision_is_judged_once(self):
        s = MemoryStore(); t = self._stopped_task(s)
        llm = brain_saying({'verb': 'continue', 'line': 'x', 'evidence': []})
        advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=llm)
        self.assertIsNone(advisor.notice(s, 'agent.asked', 'task', t, wait=True, llm=llm))
        self.assertEqual(len(llm.calls), 1)

    def test_silence_is_a_row_with_no_verb_and_no_pill(self):
        s = MemoryStore(); t = self._stopped_task(s)
        rid = advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=brain_saying({'verb': None, 'line': '', 'evidence': []}))
        r = s._one('SELECT * FROM advice WHERE Id=?', (rid,))
        self.assertEqual((r['Verb'], r['Dropped']), (None, 'nothing to say'))

    def test_a_verb_the_item_cannot_carry_is_dropped(self):
        s = MemoryStore(); t = self._stopped_task(s)
        rid = advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=brain_saying({'verb': 'approve', 'line': 'Send it.', 'evidence': []}))
        r = s._one('SELECT * FROM advice WHERE Id=?', (rid,))
        self.assertEqual(r['Verb'], None); self.assertIn('approve', r['Dropped'])

    def test_an_item_with_no_actions_is_dropped_without_a_call(self):
        s = MemoryStore()
        mid = s.add_message({'ConversationId': 'c2', 'Channel': 'email', 'Subject': 'Newsletter', 'FromEmail': 'news@vendor.example',
                             'SentAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'BodyText': 'x', 'Status': 'filed'})
        llm = brain_saying({'verb': 'close', 'line': 'x', 'evidence': []})
        with mock.patch.object(advisor.concierge, 'chips_for', return_value=[{'verb': 'next', 'label': 'Next'}]):
            rid = advisor.notice(s, 'report.landed', 'message', mid, wait=True, llm=llm)
        self.assertEqual(s._one('SELECT Dropped FROM advice WHERE Id=?', (rid,))['Dropped'], 'no actions'); self.assertEqual(llm.calls, [])

    def test_the_hourly_cap_drops_without_a_call(self):
        s = MemoryStore(); s.set_setting(advisor.CAP_KEY, '1', 'test'); t = self._stopped_task(s); t2 = self._stopped_task(s)
        llm = brain_saying({'verb': 'continue', 'line': 'x', 'evidence': []})
        advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=llm)
        rid = advisor.notice(s, 'agent.stopped', 'task', t2, wait=True, llm=llm)
        self.assertEqual(s._one('SELECT Dropped FROM advice WHERE Id=?', (rid,))['Dropped'], 'cap'); self.assertEqual(len(llm.calls), 1)
        s._exec("UPDATE advice SET CreatedAt=?", ((datetime.now() - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S'),))
        t3 = self._stopped_task(s); advisor.notice(s, 'agent.stopped', 'task', t3, wait=True, llm=llm)
        self.assertEqual(len(llm.calls), 2)

    def test_no_brain_is_a_drop_never_an_error(self):
        s = MemoryStore(); t = self._stopped_task(s)
        with mock.patch.object(advisor, 'build_llm', return_value=None):
            rid = advisor.notice(s, 'agent.stopped', 'task', t, wait=True)
        self.assertEqual(s._one('SELECT Dropped FROM advice WHERE Id=?', (rid,))['Dropped'], 'no brain')

    def test_the_switch_off_runs_nothing(self):
        s = MemoryStore(); s.set_setting(advisor.ON_KEY, '0', 'test'); t = self._stopped_task(s)
        llm = brain_saying({'verb': 'continue', 'line': 'x', 'evidence': []})
        self.assertIsNone(advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=llm)); self.assertEqual(llm.calls, [])

    def test_habit_counts_come_from_the_ledger(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        for v in ('held', 'held', 'reopened'):
            i = outcomes.record(s, 'task.closed', 'task', t); outcomes.settle(s, i, v, v)
        self.assertEqual(advisor.habit(s, 'close', {'tid': t}), (2, 3))
        for v in ('approve', 'edit', 'approve'):
            i = outcomes.record(s, 'reply.sent', 'task', t, facts={'verb': v}); outcomes.settle(s, i, 'settled', 'settled')
        self.assertEqual(advisor.habit(s, 'approve', {'tid': t}), (2, 3))
        self.assertEqual(advisor.habit(s, 'defer', {'tid': t}), (0, 0))
```

Add `from datetime import datetime, timedelta` at the top of the test file (replace the `datetime` import).

- [ ] **Step 2: Run to see it fail** → `AttributeError: module 'taskuary.advisor' has no attribute 'notice'`.

- [ ] **Step 3: The judgement**

Append to `taskuary/advisor.py` (and add `from . import concierge` and `from .llm import build_llm, ask_json` to its imports; `concierge` is imported at module level so tests can patch `advisor.concierge.chips_for`):

```python
SYSTEM = (
    "You are the Advisor inside Taskuary, speaking as the owner's own assistant. ONE item just changed. Say what the owner should do "
    "with it now, as ONE of the VERBS OFFERED (exactly as written) and one short sentence in the second person that says why, naming "
    "the habit or the fact it rests on - or say nothing. Say nothing unless the owner's own habits (LEARNED), the outcome ledger or "
    "the item's own facts point at one verb. Never invent a number: the numbers in the ledger lines are the only ones you may use, "
    "and you cite their ids. Answer with JSON only: {\"verb\": \"<one of the verbs>\" or null, \"line\": \"<sentence>\" or \"\", "
    "\"evidence\": [\"<ids from the lines below>\"]}.")
WANT = {'type': 'object', 'properties': {'verb': {'type': ['string', 'null']}, 'line': {'type': 'string'},
                                         'evidence': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['verb', 'line', 'evidence']}
_EV = re.compile(r'^(out|mem|rv|task)\d+$')


def _item(store, target_kind, target_id):
    key = key_of(target_kind, target_id)
    from . import funnel
    try: it = funnel.next_item(store, key, include_surfaced=True)
    except Exception: it = None
    return it or funnel.item_for_key(store, key)


def habit(store, verb: str, item: dict) -> tuple:
    """(n, m): how often the owner's next move after THIS kind of moment was this verb - read from the ledger, never from the model.
    continue: stops that ended in a continue, over every stop that resolved; approve: replies sent as drafted, over every reply;
    close: closes that held, over every close that resolved. Any other verb has no count yet."""
    q = {'continue': ("SELECT Verdict AS v FROM outcome WHERE Kind='agent.stopped' AND ResolvedAt IS NOT NULL", lambda r: r['v'] == 'continued'),
         'approve': ("SELECT FactsJson AS f FROM outcome WHERE Kind='reply.sent' AND ResolvedAt IS NOT NULL", lambda r: json.loads(r['f'] or '{}').get('verb') == 'approve'),
         'close': ("SELECT Verdict AS v FROM outcome WHERE Kind='task.closed' AND ResolvedAt IS NOT NULL", lambda r: r['v'] == 'held')}.get(verb)
    if not q: return (0, 0)
    rs = store._rows(q[0]); return (sum(1 for r in rs if q[1](r)), len(rs))
def pill(label: str, count) -> str:
    n, m = (list(count) + [0, 0])[:2]
    return f'{label} · {n} of {m} times' if m >= 2 else str(label or '')


def _prompt(store, event, item, verbs, tier, target_kind, target_id) -> str:
    from .learn import injectable
    from . import outcomes
    facts = {k: item.get(k) for k in ('ref', 'kind', 'lane', 'title', 'who', 'when', 'why', 'channel') if item.get(k)}
    lines = [f'EVENT: {event}', 'THE ITEM: ' + json.dumps(facts), f"PREVIEW: {str(item.get('preview') or '')[:300]}",
             'VERBS OFFERED: ' + ', '.join(f"{v['verb']} ({v['label']})" for v in verbs)]
    lrn = injectable(store.doc('learned') or '')
    if lrn.strip(): lines.append('LEARNED (the owner, from their own verdicts):\n' + lrn[:2000])
    led = [f"out{r['Id']}: {outcomes._sentence(store, r)}" for r in outcomes.rows_for(store, target_kind, target_id) if r.get('ResolvedAt')][:5]
    led += [f"{v['verb']}: this move {n} of {m} times" for v in verbs for n, m in [habit(store, v['verb'], item)] if m >= 2]
    if led: lines.append('THE OUTCOME LEDGER (what came of actions like this):\n' + '\n'.join(led))
    if tier >= 2:                                         # the bigger read, only for the item on the table
        from .counsel import dossier
        m = store.get_message(item.get('mid')) if item.get('mid') else None
        try: dos = dossier(store, {'from_email': (m or {}).get('FromEmail', ''), 'from_name': (m or {}).get('FromName', ''), 'subject': (m or {}).get('Subject', '')}, calendar=False) if m else ''
        except Exception: dos = ''
        if dos: lines.append('WHAT THE HUB KNOWS:\n' + dos[:1500])
        more = outcomes.evidence(store, (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'), limit=15)
        if more: lines.append('RECENT OUTCOMES:\n' + '\n'.join(more))
    return '\n\n'.join(lines)


def judge(store, event: str, target_kind: str, target_id, rev: str, tier: int = 1, llm=None) -> int:
    key = key_of(target_kind, target_id); W = lambda **kw: _write(store, target_kind=target_kind, target_id=target_id, key=key, event=event, revision=rev, tier=tier, **kw)
    item = _item(store, target_kind, target_id)
    if not item: return W(dropped='no item')
    verbs = [c for c in concierge.chips_for(store, item) if c.get('verb') != 'next']
    if not verbs: return W(dropped='no actions')
    brain = llm or build_llm(store)
    if not brain: return W(dropped='no brain')
    model = getattr(brain, 'last_pick', None) or getattr(brain, 'model', None) or 'light'
    ans = ask_json(brain, SYSTEM, _prompt(store, event, item, verbs, tier, target_kind, target_id), want=WANT, need=('verb', 'line'), max_tokens=200)
    d = ans.data or {}
    if ans.error and not d: return W(dropped=f'no answer: {ans.error}'[:200], model=model)
    verb, line = d.get('verb'), ' '.join(str(d.get('line') or '').split())[:200]
    ev = [e for e in (d.get('evidence') or []) if isinstance(e, str) and _EV.match(e)][:6]
    if not verb or not line: return W(dropped='nothing to say', model=model, evidence=ev)
    hit = next((v for v in verbs if v['verb'] == verb), None)
    if not hit: return W(dropped=f'verb not offered: {verb}'[:120], model=model, line=line, evidence=ev)
    rid = W(line=line, verb=verb, label=hit['label'], count=habit(store, verb, item), evidence=ev, model=model)
    try:
        from . import live
        live.emit(live.ADVICE, key=key, target_kind=target_kind, target_id=int(target_id))
    except Exception: pass
    return rid


def _capped(store) -> bool:
    cap = int(store.get_setting(CAP_KEY, CAP_DEFAULT) or CAP_DEFAULT)
    since = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
    n = (store._one("SELECT COUNT(*) AS n FROM advice WHERE CreatedAt>=? AND Dropped IS NOT 'cap'", (since,)) or {}).get('n') or 0
    return n >= cap


def notice(store, event: str, target_kind: str, target_id, *, tier: int = 1, wait: bool = False, llm=None):
    """The one door every event calls. Never raises: a hook, a close or a poll must not fail for advice.
    Returns the row id when judged inline (tests, `wait=True`), None when skipped or sent to the background."""
    try:
        if str(store.get_setting(ON_KEY, '1') or '1') != '1' or not target_id: return None
        rev = revision(store, target_kind, target_id)
        have = row(store, target_kind, target_id, rev)
        if have and int(have.get('Tier') or 1) >= tier: return None             # judged at this revision already
        if _capped(store): return _write(store, target_kind=target_kind, target_id=target_id, key=key_of(target_kind, target_id), event=event, revision=rev, tier=tier, dropped='cap')
        if wait: return judge(store, event, target_kind, target_id, rev, tier, llm)
        def go():
            try: judge(store, event, target_kind, target_id, rev, tier, llm)
            except Exception as e: logger.warning(f'advisor: {event} on {target_kind} {target_id} not judged - {e}')
        threading.Thread(target=go, daemon=True, name=f'advise-{target_kind}-{target_id}').start()
    except Exception as e: logger.warning(f'advisor: {event} on {target_kind} {target_id} skipped - {e}')
    return None
```

`live.ADVICE` is added in Task 4; until then the `try/except` around the emit keeps the tests green. If `ask_json` has no `max_tokens` passthrough, drop that keyword (check `grep -n "def ask_json" taskuary/llm.py`).

- [ ] **Step 4: Run to see it pass** → `python -m pytest tests/test_advisor.py -q` PASS.

- [ ] **Step 5: Commit** `"The Advisor judges one changed item on the light gear: a verb the item carries, one line, the ledger's number"`.

---

### Task 3: The eight doors

**Files:**
- Modify: `taskuary/hooks.py` (the Stop branch, beside `outcomes.stopped`), `taskuary/workerstate.py` (`record`, after the insert), `taskuary/ci.py` (`open_for_task`, after the `pr_opened` audit), `taskuary/asks.py` (`_reply`, after `AskedSeenMid` is written), `taskuary/ingest.py` (the routed exit at `store.add_route(...)`, when `r['decision'] == 'attach'`), `taskuary/store.py` (`update_task`, beside the `task.closed` outcome row), `taskuary/remind.py` (`deadlines`, when `s == 'late'`), `taskuary/reports.py` (`_run_report_source`, after `store.audit('message', mid, 'report', ...)`)
- Test: `tests/test_advisor.py`

**Interfaces:**
- Consumes: `advisor.notice(store, event, target_kind, target_id)`.
- Produces: events `agent.stopped` (once per stretch: only when `outcomes.stopped` returned a new row id), `agent.asked` (a worker event in `workerstate.REQUESTS`), `pr.opened`, `reply.arrived`, `message.attached`, `task.closed`, `due.late`, `report.landed`.

- [ ] **Step 1: Failing tests**

```python
class DoorTests(unittest.TestCase):
    def _session(self, s, tid):
        from types import SimpleNamespace
        return SimpleNamespace(sid='run1', alive=True, task_id=tid, cwd='C:/x', agent='coder', label='coder', argv=['claude'], last=1.0,
                               ext_id='', started='2026-10-12 09:00:00', typed=[], files=lambda: [], tail=lambda n=3: [], idle=lambda: 0.0,
                               witness=SimpleNamespace(note=lambda n: None), store=s, bg={})

    def test_a_stop_notices_once_per_stretch_and_an_ask_notices(self):
        from taskuary import hooks, workerstate as ws
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner'); sess = self._session(s, t)
        with mock.patch.object(advisor, 'notice') as n:
            for _ in range(3): hooks._events(sess, {'hook_event_name': 'Stop', 'last_assistant_message': ''})
            self.assertEqual([c.args[1] for c in n.call_args_list], ['agent.stopped'])
            ws.record(s, t, 'run1', 'input_needed', text='Open the PR?')
            self.assertEqual([c.args[1] for c in n.call_args_list], ['agent.stopped', 'agent.asked'])

    def test_a_close_notices_through_the_one_door(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        with mock.patch.object(advisor, 'notice') as n:
            s.update_task(t, {'Status': 'done'}, 'owner')
        self.assertEqual(n.call_args.args[1:], ('task.closed', 'task', t))

    def test_a_late_due_notices_once(self):
        from taskuary import remind
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'open', 'DueAt': '2026-01-01'}, 'owner')
        with mock.patch.object(advisor, 'notice') as n:
            remind.deadlines(s, datetime(2026, 1, 9, 9)); remind.deadlines(s, datetime(2026, 1, 10, 9))
        self.assertEqual([c.args[1:] for c in n.call_args_list], [('due.late', 'task', t)])
```

- [ ] **Step 2: Run** → the three fail (no call recorded).

- [ ] **Step 3: Wire the doors** (one line each; `from . import advisor` local to the function in every file except store.py, which imports inside the branch like `outcomes`):

- `hooks.py` Stop branch: `outcomes.stopped(...)` returns the new row id or 0; change it to `if outcomes.stopped(st, tid, f'agent:{agent}', facts={...}): advisor.notice(st, 'agent.stopped', 'task', tid)` inside the same try.
- `workerstate.record`, after `store.add_worker_event(...)` and before the `_poke`: `if kind in REQUESTS: advisor.notice(store, 'agent.asked', 'task', tid)` (wrapped `try/except Exception: pass` like the poke).
- `ci.open_for_task`, after `store.audit('task', task_id, 'pr_opened', ...)`: `advisor.notice(store, 'pr.opened', 'task', task_id)`.
- `asks._reply`, after `store._exec('UPDATE task SET AskedSeenMid=? ...')`: `advisor.notice(store, 'reply.arrived', 'task', t['TaskId'])`.
- `ingest.ingest_message`, right before the routed `return {'status': 'attached' if r['decision'] == 'attach' else 'created', ...}`: `if r['decision'] == 'attach': advisor.notice(store, 'message.attached', 'task', tid)`.
- `store.update_task`, inside the `task.closed` branch after `outcomes.record(...)`: `from . import advisor; advisor.notice(self, 'task.closed', 'task', task_id)`.
- `remind.deadlines`, beside `store._exec('UPDATE task SET DueSaid=? WHERE TaskId=?', (s, t['TaskId']))`: `if s == 'late': advisor.notice(store, 'due.late', 'task', t['TaskId'])`.
- `reports._run_report_source`, after `store.audit('message', mid, 'report', ...)`: `advisor.notice(store, 'report.landed', 'task' if out.get('task_id') else 'message', out.get('task_id') or mid)`.

`notice` never raises, so no door needs its own guard beyond the ones already there.

- [ ] **Step 4: Run** `python -m pytest tests/test_advisor.py tests/test_outcomes.py tests/test_hooks_events.py tests/test_asks.py tests/test_remind.py -q` → PASS (use `ls tests | grep -i remind` for the file's real name).

- [ ] **Step 5: Commit** `"Eight doors tell the Advisor an item changed: a stop, an ask, a PR, a reply, an attached mail, a close, a late day, a report"`.

---

### Task 4: The live kind, the two endpoints, the chat's block

**Files:**
- Modify: `taskuary/live.py` (`ADVICE`, `KINDS`, `_DELAY`), `taskuary/server.py` (two routes beside `GET /api/concierge/chips`), `taskuary/advisor.py` (`for_key`, `notes`, `block`), `taskuary/concierge.py` (`_say`: the system prompt, after `table_actions(store, item)` is folded in)
- Test: `tests/test_advisor.py`, `tests/test_live.py` (if one exists; else the advisor file)

**Interfaces:**
- Produces: `live.ADVICE = 'advice'`; `GET /api/advice?key=` → `{} | {key, line, verb, label, pill, count, evidence, revision, tier, at}`; `GET /api/advice/notes?key=` → `{rows: [{at, event, tier, line, verb, label, pill, dropped, model, evidence: [{id, kind, label}]}]}`; `advisor.for_key(store, key) -> dict`; `advisor.notes(store, key, limit=10) -> list`; `advisor.block(store, item) -> str` (empty when nothing).
- `for_key` kicks tier 2 in the background once per revision when a tier-1 row is on the table (`notice(..., tier=2)`).

- [ ] **Step 1: Failing tests**

```python
class ReadTests(unittest.TestCase):
    def _advised(self):
        s = MemoryStore(); t = s.create_task({'Title': 'Export job', 'Status': 'in_progress'}, 'owner')
        s.add_message({'ConversationId': 'c1', 'Channel': 'email', 'Subject': 'Export job', 'FromEmail': 'gail@northwind.example',
                       'SentAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'BodyText': 'x', 'Status': 'routed', 'TaskId': t})
        rid = advisor.notice(s, 'agent.stopped', 'task', t, wait=True, llm=brain_saying({'verb': 'continue', 'line': 'You usually continue it.', 'evidence': []}))
        return s, t, rid

    def test_for_key_reads_the_rows_line_and_pill(self):
        s, t, rid = self._advised()
        with mock.patch.object(advisor, 'notice') as n:
            d = advisor.for_key(s, f'task:{t}')
        self.assertEqual((d['verb'], d['line'], d['pill']), ('continue', 'You usually continue it.', d['label']))
        self.assertEqual(n.call_args.kwargs.get('tier'), 2)                         # the item on the table earns the bigger read, once

    def test_advice_vanishes_when_the_item_moves(self):
        s, t, rid = self._advised()
        s.update_task(t, {'Status': 'waiting'}, 'owner')
        with mock.patch.object(advisor, 'notice'): self.assertEqual(advisor.for_key(s, f'task:{t}'), {})

    def test_notes_say_what_was_decided_and_dropped(self):
        s, t, rid = self._advised()
        advisor.notice(s, 'agent.asked', 'task', t, wait=True, llm=brain_saying({'verb': 'approve', 'line': 'x', 'evidence': []}))   # same revision: skipped, no row
        s.update_task(t, {'Status': 'waiting'}, 'owner')
        advisor.notice(s, 'agent.asked', 'task', t, wait=True, llm=brain_saying({'verb': 'approve', 'line': 'Send it.', 'evidence': []}))
        ns = advisor.notes(s, f'task:{t}')
        self.assertEqual([(n['verb'], bool(n['dropped'])) for n in ns], [(None, True), ('continue', False)])
        self.assertIn('approve', ns[0]['dropped'])

    def test_the_chat_block_carries_the_line_for_why(self):
        s, t, rid = self._advised()
        self.assertIn('You usually continue it.', advisor.block(s, {'key': f'task:{t}', 'tid': t}))
        self.assertEqual(advisor.block(s, {'key': 'conn:1'}), '')


class ApiTests(unittest.TestCase):
    def test_the_routes_answer(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'in_progress'}, 'owner')
        with mock.patch.object(server, 'store', s), mock.patch.object(advisor, 'notice'):
            c = TestClient(server.app)
            self.assertEqual(c.get(f'/api/advice?key=task:{t}').json(), {})
            self.assertEqual(c.get(f'/api/advice/notes?key=task:{t}').json(), {'rows': []})
            self.assertEqual(c.get('/api/advice?key=conn:1').json(), {})
```

Read `tests/conftest.py` first: it defaults the owner token onto every TestClient, and other API tests patch `server.store` the same way (`grep -n "patch.object(server, 'store'" tests/*.py | head -3`); copy that idiom if it differs.

- [ ] **Step 2: Run** → fail on `for_key` missing.

- [ ] **Step 3: Implement**

`taskuary/live.py`: `ADVICE = 'advice'`, add it to `KINDS` and `_DELAY[ADVICE] = 0.05` with the comment `# the Advisor's line landed on an item: the prompt box fills, nothing moves`.

`taskuary/advisor.py`:

```python
def _payload(r: dict) -> dict:
    count = json.loads(r.get('CountJson') or '[0,0]')
    return {'key': r['Key'], 'line': r['Line'], 'verb': r['Verb'], 'label': r['Label'], 'pill': pill(r['Label'], count), 'count': count,
            'evidence': json.loads(r.get('EvidenceJson') or '[]'), 'revision': r['Revision'], 'tier': r['Tier'], 'at': r['CreatedAt']}


def for_key(store, key: str) -> dict:
    """What the prompt box shows for the item on the table: the row at the item's CURRENT revision, or nothing. A changed
    item drops its old pill by this one comparison - no cleanup pass. The item on the table earns the bigger read, once."""
    tgt = target_of(store, key)
    if not tgt: return {}
    rev = revision(store, *tgt); r = row(store, tgt[0], tgt[1], rev)
    if r and int(r.get('Tier') or 1) < 2: notice(store, r['Event'], tgt[0], tgt[1], tier=2)
    return _payload(r) if r and r.get('Verb') else {}


def notes(store, key: str, limit: int = 10) -> list:
    """The receipt: what it decided and what it dropped, per revision, with the evidence resolved to labels."""
    from .learnedgraph import _resolve
    tgt = target_of(store, key)
    if not tgt: return []
    out = []
    for r in rows(store, tgt[0], tgt[1], limit):
        ev = [{'id': e, **{k: v for k, v in _resolve(store, e).items() if k in ('kind', 'label')}} for e in json.loads(r.get('EvidenceJson') or '[]')]
        out.append({'at': r['CreatedAt'], 'event': r['Event'], 'tier': r['Tier'], 'line': r['Line'], 'verb': r['Verb'], 'label': r['Label'],
                    'pill': pill(r['Label'], json.loads(r.get('CountJson') or '[0,0]')) if r.get('Verb') else '', 'dropped': r['Dropped'],
                    'model': r['Model'], 'evidence': ev})
    return out


def block(store, item: dict) -> str:
    """The Advisor's line for the chat's system prompt, so 'why?' is answered from its evidence - a lookup, not a think."""
    d = for_key(store, (item or {}).get('key') or '') if item else {}
    if not d: return ''
    ev = ', '.join(d['evidence']) or 'the item itself'
    return (f"THE ADVISOR'S LINE on this item (if the owner asks why, this is the answer; the numbers are the ledger's): "
            f"\"{d['line']}\" - the pill offers {d['pill']} (verb {d['verb']}); evidence: {ev}.")
```

`taskuary/server.py`, beside `GET /api/concierge/chips`:

```python
@app.get('/api/advice')
def advice_for(key: str):
    """The Advisor's line and pill for the item on the table, at its current revision - or nothing (advisor.py)."""
    from . import advisor
    return advisor.for_key(store, key)


@app.get('/api/advice/notes')
def advice_notes(key: str, limit: int = 10):
    from . import advisor
    return {'rows': advisor.notes(store, key, limit)}
```

`taskuary/concierge.py` `_say`: find where `table_actions(store, item)` is joined into the system prompt and append `advisor.block(store, item)` as its own paragraph when non-empty (`from . import advisor` beside the function's other local imports). Read the surrounding lines first; the block goes AFTER the actions so the model has the verbs before the line.

- [ ] **Step 4: Run** `python -m pytest tests/test_advisor.py tests/test_assistant_reactions.py -q` → PASS.

- [ ] **Step 5: Commit** `"The Advisor's line reaches the page: an advice event, two routes, and the chat answers why from it"`.

---

### Task 5: The prompt box: ghost text and the pill

**Files:**
- Modify: `website/src/AssistantView.jsx` (state, fetch on `current`, the `advice` live event, the textarea placeholder, the send button), `website/src/assistantView.css` (`.tq-pill`)
- Test: `website/test/advicePill.test.mjs` (new; the repo's unit tests read the source and assert on it)
- Build: `cd website && npm test && npm run lint:undef && npm run build` (the bundle under `taskuary/web` is committed)

**Interfaces:**
- Consumes: `GET /api/advice?key=`, live kind `advice` with `{key}`, `runChip(c)` (`c = {verb, label}`), `current`, `text`, `pics.imgs`.
- Produces: the placeholder reads `${advice.line} Tell me what to do with it, or press…` while the box is empty and advice is on; a `button.tq-pill` with `advice.pill` replaces `button.tq-send` while the box is empty; typing anything brings the arrow back; the pill calls `runChip({verb: advice.verb, label: advice.label})`.

- [ ] **Step 1: Failing test**

```js
// website/test/advicePill.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const src = fs.readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("../src/assistantView.css", import.meta.url), "utf8");

test("the Advisor's line is the ghost text while the box is empty, and the pill sits where the arrow does", () => {
  assert.match(src, /const \[advice, setAdvice\] = useState\(null\)/);
  assert.match(src, /api\.get\("\/api\/advice", \{ params: \{ key/);
  assert.match(src, /onLive\("advice"/);
  assert.match(src, /advice\?\.line && !text\.trim\(\)/);                       // ghost text only while empty
  assert.match(src, /Tell me what to do with it, or press…/);
  assert.match(src, /className="tq-pill"/);
  assert.match(src, /runChip\(\{ verb: advice\.verb, label: advice\.label \}\)/);   // the card's own button, same path
  assert.match(css, /\.tq-pill \{/);
});

test("the pill never shows beside a typed line or a picture", () => {
  assert.match(src, /advice\?\.verb && !text\.trim\(\) && !pics\.imgs\.length\s*\?\s*\(\s*<button type="button" className="tq-pill"/);
});
```

- [ ] **Step 2: Run** `cd website && node --test test/advicePill.test.mjs` → FAIL.

- [ ] **Step 3: Implement**

In `AssistantView.jsx`:

State, beside `const [text, setText] = useState("")`:
```jsx
  const [advice, setAdvice] = useState(null);     // the Advisor's line for the key on the table (advisor.py), or null
```

A fetch, beside the other `useEffect`s that follow `current` (after `loadState`'s effects):
```jsx
  // the Advisor's line for the item on the table: read when the table changes and when its event lands; a changed
  // item answers {} and the pill goes with it - nothing on the rail moves for it (spec 2026-10-12, mechanics 3-5)
  const readAdvice = useCallback(async (key) => {
    if (!key) { setAdvice(null); return; }
    try { const { data } = await api.get("/api/advice", { params: { key } }); setAdvice(data && data.verb ? data : null); }
    catch { setAdvice(null); }
  }, []);
  useEffect(() => { readAdvice(current); }, [current, readAdvice]);
  useEffect(() => onLive("advice", (ev) => { if (ev?.key && currentRef.current && (ev.key === currentRef.current || (currentItem?.aliases || []).includes(ev.key))) readAdvice(currentRef.current); }), [readAdvice, currentItem]);
```
(`useCallback` is imported already if other callbacks use it; `onLive` is imported from `./live`; confirm both with `grep -n "useCallback\|from \"./live\"" website/src/AssistantView.jsx`.)

The textarea placeholder (replace the whole `placeholder={...}` expression):
```jsx
              placeholder={advice?.line && !text.trim() ? `${advice.line} Tell me what to do with it, or press…`
                : phone ? (current ? "Ask about this one…" : "Ask Taskuary anything…")
                : current ? "Ask about this one, tell me what to do with it, or name something else…" : "Ask Taskuary anything — a name or a subject pulls it in…"}
```

The send button (replace the `<button ... className="tq-send" ...>` line):
```jsx
            {advice?.verb && !text.trim() && !pics.imgs.length ? (
              <button type="button" className="tq-pill" title={advice.line} disabled={busy || resetting}
                onClick={() => runChip({ verb: advice.verb, label: advice.label })}>{advice.pill}</button>
            ) : (
              <button type="button" className="tq-send" aria-label="Send" disabled={busy || resetting || pics.busy || !(text.trim() || pics.imgs.length)} onClick={() => send()}><SendIcon fontSize="small" /></button>
            )}
```
`runChip` is defined above the JSX in the same component (confirm with `grep -n "const runChip" website/src/AssistantView.jsx`).

CSS, after `.tq-send:disabled`:
```css
.tq-pill { height: 34px; flex: 0 0 auto; max-width: 46%; padding: 0 12px; border: 0; border-radius: 17px; cursor: pointer; color: white; background: #738275; font: 600 12.5px/34px 'IBM Plex Sans', system-ui, sans-serif; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tq-pill:disabled { opacity: .4; cursor: default; }
```

Then check the source-reading tests that pin the composer: `node --test test/assistantEmoji.test.mjs test/canvasItem.test.mjs test/setupWalk.test.mjs test/actionRow.test.mjs` - their regexes match `ref={composeRef}`, the ActionRow line and the compose div, none of which move.

- [ ] **Step 4: Run** `cd website && npm test && npm run lint:undef && npm run build` → all green; the bundle under `taskuary/web/assets` changes.

- [ ] **Step 5: Commit** (the bundle rides along) `"The prompt box carries the Advisor's line as ghost text and its verb as a pill where the arrow sits"`.

---

### Task 6: Settings, the Advisor's notes in the clock menu, and the docs

**Files:**
- Modify: `taskuary/settings_schema.json` (two knobs in group `Advisor`), `website/src/AssistantView.jsx` (the Past chats menu gains an "Advisor's notes" entry for the item on the table), `docs/site/advisor.md`, `docs/site/how-it-works.md`, `docs/site/settings.md` is generated
- Test: `tests/test_settings_schema*.py` (whatever exists: `ls tests | grep -i schema`), `website/test/advicePill.test.mjs`
- Build: `cd website && npm run build:docs && npm run build`

**Interfaces:**
- Produces: knobs `advisor_events` (type `bool`, default on) and `advisor_event_cap` (type `number`, 30) in group `Advisor`; a menu entry that opens `GET /api/advice/notes?key=<current>` in the same read-only panel the past chats use.

- [ ] **Step 1: Failing tests**

Append to `tests/test_advisor.py`:
```python
class SchemaTests(unittest.TestCase):
    def test_the_two_knobs_are_in_the_advisor_group(self):
        import json, pathlib
        d = json.loads(pathlib.Path('taskuary/settings_schema.json').read_text(encoding='utf-8'))
        self.assertEqual(d['knobs']['advisor_events']['group'], 'Advisor')
        self.assertEqual(d['knobs']['advisor_event_cap']['group'], 'Advisor')
```
Append to `website/test/advicePill.test.mjs`:
```js
test("the clock menu offers the Advisor's notes for the item on the table", () => {
  assert.match(src, /Advisor's notes/);
  assert.match(src, /api\.get\("\/api\/advice\/notes", \{ params: \{ key/);
});
```

- [ ] **Step 2: Run** → both fail.

- [ ] **Step 3: Implement**

`settings_schema.json`, in `knobs` after `assistant_producers` (copy the sibling's shape; read one `bool` knob first for its exact `type` spelling: `grep -n '"type": "bool' taskuary/settings_schema.json | head -2`):
```json
    "advisor_events": {"group": "Advisor", "label": "Advise on the item that changed", "type": "bool",
      "desc": "When an agent stops or asks, a reply arrives, a pull request opens, a task closes, a day is missed or a report lands, the Advisor runs one small prompt on the light model and leaves one line and one verb on that item: the ghost text in the prompt box and the pill where the send arrow sits. On by default.",
      "help": "Never a row and never a change to the rail's order: the line attaches to the item and shows when the walk reaches it. The verb is one the item already carries; the number beside it is read from the outcome ledger. Off, the Advisor still runs on its schedule."},
    "advisor_event_cap": {"group": "Advisor", "label": "Event judgements per hour, at most", "type": "number",
      "desc": "The small prompt runs once per item per change and never more than this many times an hour; past it, the change is noted as dropped and the item simply has no pill. 30 by default.",
      "help": "The Advisor's notes on an item (the clock menu) say when a judgement was dropped for the cap."},
```

`AssistantView.jsx`: in the Past chats list (the `openChats` panel, drawn near the `HistoryIcon` button), add one entry at the top when `current` is set: a row labelled **Advisor's notes** that fetches `api.get("/api/advice/notes", { params: { key: current } })` and shows `rows` as lines: `at · event · (pill or "dropped: " + dropped) · line`, with each evidence label under it. Reuse the read-only panel the past chats use (`openOld`'s banner states) and give the list `className="tq-advisor-notes"`. Keep it to one component `AdvisorNotes({ keyOnTable })` defined above `AssistantView` in the same file.

Docs: in `docs/site/advisor.md`, under "Two clocks", change "This is designed and not yet built." to say it is built, name the two settings and the eight events; under "What is built, and what is next", move the event path into Built and leave "a receipt of what it looked at and dropped" as built too (the clock menu). In `how-it-works.md`'s three-brains table, the Advisor's "When" cell adds "and on the event: an agent stop or ask, a reply, a PR, a close, a missed day, a report". Then `cd website && npm run build:docs`.

- [ ] **Step 4: Run** `python -m pytest tests/test_advisor.py -q` and `cd website && npm test && npm run lint:undef && npm run build && npm run build:docs` → green; then the full suite from the repo root.

- [ ] **Step 5: Commit** `"The Advisor's two knobs, its notes in the clock menu, and the docs say the event path is built"`.

---

## Self-review

**Spec coverage:** the event entry point with the small prompt, the verb vocabulary validated by code, the advice sidecar with revision/model/dropped (T1, T2); the triggers (T3: the hooks and asks, a PR, a reply, a close, a slipped step via the late day, a report; the owner's presses reach it through the doors they call - a Next press changes no fact, by the spec's own gate); the live push, the stage join at one lookup, the stale-revision rule (T4); the ghost text and pill through the card's own path, empty Enter unchanged (T5); the Advisor's notes receipt from the clock menu and "why?" from the block (T4, T6); the rail test (T1); the cost gates (T2: revision, cap, light gear, tier 2 only on the table). Not in this plan: the By the way strip (removed from the desktop on 2026-09-23 - the spec is out of date there) and earned autonomy (out of scope by the spec).

**Placeholders:** none; two steps ask the implementer to confirm a name by grep before using it (`ask_json`'s max_tokens, `useCallback`/`onLive` imports, the bool type spelling), each with the grep given.

**Type consistency:** `notice(store, event, target_kind, target_id, *, tier, wait, llm)` everywhere; `for_key` returns `{}` for nothing, a dict with `verb` otherwise; `pill(label, count)` takes the list the row stores; `target_of` returns `('task'|'message', int)`.

**Review Focus:** each line has its test (T2 x4, T4 x1).
