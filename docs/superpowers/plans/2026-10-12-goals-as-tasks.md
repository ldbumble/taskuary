# Goals as tasks (build step 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A goal is a task with a done-when sentence, a due date and checklist boxes that point at child tasks; it is one row on the work rail (a Goals band when it has news, For later when quiet, never gone), its children fold into that row unless they are the owner's move, the New sheet gets a fourth tab that makes one, the task page lists its steps, and an owner's own promise found in sent mail becomes a task with its date.

**Architecture:** Two columns on `task` (`DoneWhen`, `ParentId`) and one optional key on a checklist box (`tid`); every reader derives "is a goal" from `DoneWhen`. The rail builder (`processing_unread.card_for`) turns a goal task into a card of kind `goal` / `goal_slipped` / `goal_fresh` with the fold rule, and `funnel.level_of` + `funnelPile.levelOf` put it in a new `goals` section or in `later`. Steps and child creation are two endpoints beside the checklist ones. The planning of steps reuses the existing model door (`triage.extract_ask`) with a goal sentence added to its prompt: the model writes the steps, code validates.

**Tech Stack:** Python 3.12 / FastAPI / SQLite (`taskuary/`), React + MUI with Vite (`website/src/`), pytest (`tests/`), node:test (`website/test/`).

**Spec:** `docs/superpowers/specs/2026-10-12-goals-outcomes-advisor-design.md` (sections "Goals are tasks", "Mechanics: what touches the rail", build step 1). Steps 2–5 of the spec (outcome ledger, the Advisor's event path, per-person pages, triage's goal kind) are **not** in this plan.

## Global Constraints

- Public repository: no real names, domains or company data anywhere. Stand-ins only: Alex Doyle / `northwind.example`; colleagues Erin Blake, Gail Moreno, Paula Vance, Ray Colton, Marcus Reed, Omar Keller; vendors `vendor.example`, Payworth, Trainly (project CLAUDE.md).
- Code style: concise fast.ai style (global CLAUDE.md); match the surrounding file; no autoformatters.
- Never route on a word match: the model reads, code validates against a vocabulary (the owner, 2026-09-06 and 2026-10-12). The only model door this plan adds is one sentence on `triage.extract_ask`'s prompt.
- One vocabulary: a lane or kind word lives in `taskuary/lanes.json` once; `tests/test_lane_vocabulary.py` and `website/test/funnelPile.test.mjs` pin it on both sides.
- The rail's sections are one rule on both sides: `funnel.level_of` and `funnelPile.levelOf`, pinned by `tests/fixtures/rail_levels.json` from `tests/test_canvas_sections.py` and `website/test/pileLevels.test.mjs`.
- Push only after the full pytest suite from the repo root (`python -m pytest -q`); the one known failure is `tests/test_deps.py::DepsTests::test_the_packaged_exe_installs_beside_the_owners_data` (environmental). UI gates run with Node 22: `cd website && npm exec --yes --package=node@22 -- npm test`, `npm run lint:undef`, `npm run build`; a `docs/site/*.md` edit needs `npm run build:docs` (the built site is committed; CI fails otherwise).
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- A task's checklist box ids are `sha1(text)[:8]` (`store.checklist_id`); `set_task_checklist` keeps a box's state only when its text is unchanged, so a re-plan must merge, never replace, boxes that carry a `tid`.

## Review Focus

1. **A goal with no steps yet** (the owner pressed "Track it" and typed nothing, or the model returned an empty checklist): the row must read "not started", sit in For later with its date, and the task page must still offer Start on nothing without crashing. Pinned in Task 4 (`test_a_goal_with_no_boxes_is_fresh_and_in_later`) and Task 5 (`test_steps_of_a_goal_with_no_checklist_is_empty`).
2. **A child closed by an agent, not the owner**: the parent's box must tick whoever closed it, and a `dropped` child must not tick it. Pinned in Task 1 (`test_closing_a_child_ticks_the_parents_box_and_dropping_does_not`).
3. **A goal whose due date is in the past but every box is done**: it is not slipped, it is ready to close; the row must not say "slipped". Pinned in Task 4 (`test_a_goal_with_every_box_done_is_not_slipped`).
4. **A promise with no date** ("leave it with me"): it becomes a task with no `DueAt` and must not be re-created on the next judging pass, and delivering it must close the task. Pinned in Task 2 (`test_a_promise_becomes_one_task_once_and_delivery_closes_it`).
5. **A re-plan after steps were started**: `set_task_checklist` would drop the `tid` of a box whose text the model rephrased. The plan endpoint must merge by `tid` first, text second. Pinned in Task 5 (`test_replanning_keeps_started_steps`).

---

### Task 1: Two columns and the step helpers on the store

**Files:**
- Modify: `taskuary/store.py:47` (TASK_COLS), `:243-248` (SCHEMA task), `:854-870` (the ALTER block), `:1626-1662` (`update_task`), after `:1756` (`checklist_markdown`)
- Test: `tests/test_goals_store.py` (new)

**Interfaces:**
- Consumes: `SQLiteStore.create_task(fields, actor)`, `task_checklist(tid)`, `_write_checklist(tid, items, actor)`, `update_task(tid, fields, actor)`, `MemoryStore()`.
- Produces: columns `task.DoneWhen TEXT`, `task.ParentId INTEGER`; `TASK_COLS` gains `'DoneWhen', 'ParentId'`; a checklist item may carry `tid: int`; `SQLiteStore.children(tid) -> list[dict]` (child task rows, oldest first); `SQLiteStore.goal_steps(tid) -> list[dict]` (each box as `{id, text, done, tid, child}` where `child` is the child task row or `None`); `SQLiteStore.link_step(tid, item_id, child_tid, actor) -> bool`; `store.is_goal(t: dict) -> bool` (module-level function: `bool((t or {}).get('DoneWhen'))`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_goals_store.py
"""A goal is a task with a done-when sentence; its boxes may point at child tasks (spec 2026-10-12, build step 1)."""
import unittest
from taskuary.store import MemoryStore, is_goal, checklist_id


def goal(s, title='Migrate the census export off the old portal', steps=('Inventory the fields', 'Map the schema', 'Schema sign-off')):
    tid = s.create_task({'Title': title, 'Kind': 'task', 'Status': 'open', 'DoneWhen': 'the nightly census lands in the new ledger',
                         'DueAt': '2026-12-01'}, 'owner')
    s.set_task_checklist(tid, list(steps), 'owner')
    return tid


class ColumnsTests(unittest.TestCase):
    def test_done_when_and_parent_are_written_and_read(self):
        s = MemoryStore()
        g = goal(s)
        c = s.create_task({'Title': 'Map the schema', 'Kind': 'general', 'ParentId': g}, 'owner')
        self.assertEqual(s.get_task(g)['DoneWhen'], 'the nightly census lands in the new ledger')
        self.assertEqual(s.get_task(c)['ParentId'], g)
        self.assertTrue(is_goal(s.get_task(g))); self.assertFalse(is_goal(s.get_task(c))); self.assertFalse(is_goal(None))

    def test_children_come_back_oldest_first(self):
        s = MemoryStore()
        g = goal(s)
        a = s.create_task({'Title': 'first', 'ParentId': g}, 'owner'); b = s.create_task({'Title': 'second', 'ParentId': g}, 'owner')
        self.assertEqual([t['TaskId'] for t in s.children(g)], [a, b])
        self.assertEqual(s.children(b), [])


class StepsTests(unittest.TestCase):
    def test_link_step_puts_the_child_on_the_box_and_the_parent_on_the_child(self):
        s = MemoryStore()
        g = goal(s)
        c = s.create_task({'Title': 'Map the schema', 'Kind': 'general', 'ParentId': g}, 'owner')
        self.assertTrue(s.link_step(g, checklist_id('Map the schema'), c, 'owner'))
        self.assertFalse(s.link_step(g, 'nosuchbox', c, 'owner'))
        steps = s.goal_steps(g)
        self.assertEqual([x['text'] for x in steps], ['Inventory the fields', 'Map the schema', 'Schema sign-off'])
        self.assertEqual(steps[1]['tid'], c); self.assertEqual(steps[1]['child']['TaskId'], c); self.assertIsNone(steps[0]['child'])

    def test_closing_a_child_ticks_the_parents_box_and_dropping_does_not(self):
        s = MemoryStore()
        g = goal(s)
        a = s.create_task({'Title': 'Map the schema', 'ParentId': g}, 'owner'); s.link_step(g, checklist_id('Map the schema'), a, 'owner')
        b = s.create_task({'Title': 'Schema sign-off', 'ParentId': g}, 'owner'); s.link_step(g, checklist_id('Schema sign-off'), b, 'owner')
        s.update_task(a, {'Status': 'done'}, 'agent:coder')          # whoever closes it
        s.update_task(b, {'Status': 'dropped'}, 'owner')
        done = {x['text']: x['done'] for x in s.goal_steps(g)}
        self.assertEqual(done, {'Inventory the fields': False, 'Map the schema': True, 'Schema sign-off': False})
        self.assertEqual(s.get_task(g)['Status'], 'open')             # the parent is never closed for it

    def test_goal_steps_of_a_task_with_no_checklist_is_empty(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'plain', 'DoneWhen': 'it is done'}, 'owner')
        self.assertEqual(s.goal_steps(t), [])
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python -m pytest tests/test_goals_store.py -q`
Expected: FAIL with `ImportError: cannot import name 'is_goal'` (and, once that exists, `AttributeError: ... has no attribute 'children'`).

- [ ] **Step 3: Add the columns**

In `taskuary/store.py:47` change `TASK_COLS` to:

```python
TASK_COLS = ('Title', 'Summary', 'Kind', 'Status', 'Priority', 'Assignee', 'Source', 'SourceRef', 'Tags', 'RemindAt', 'AskedVia', 'DueAt',
             'DoneWhen', 'ParentId')
```

In the `SCHEMA` string at `:248`, change the last line of the `task` table to:

```sql
  AskedWatchAt TEXT, AskedNudgedAt TEXT, DueAt TEXT, DueSaid TEXT, DueRaised TEXT, DoneWhen TEXT, ParentId INTEGER);
```

In the ALTER block, right after the `for col in ('AskedWatchAt', ...)` loop (`:869-870`), add:

```python
            # a GOAL is a task with a done-when sentence and a date; its boxes may point at child tasks, which carry the
            # parent (spec 2026-10-12, goals as tasks). Derived everywhere from DoneWhen - no kind, no second object.
            if 'DoneWhen' not in tcols: self.cx.execute('ALTER TABLE task ADD COLUMN DoneWhen TEXT')
            if 'ParentId' not in tcols: self.cx.execute('ALTER TABLE task ADD COLUMN ParentId INTEGER')
```

- [ ] **Step 4: Add `is_goal`, `children`, `goal_steps`, `link_step`, and the tick-on-close**

Module level, right after `def task_ref(task_id)` (`:148`):

```python
def is_goal(t) -> bool: return bool((t or {}).get('DoneWhen'))
```

Inside `SQLiteStore`, right after `checklist_markdown` (`:1756-1762`):

```python
    # ── goals: a task whose boxes are tasks (spec 2026-10-12) ─────────────────────────────────
    def children(self, task_id) -> list:
        return self._rows('SELECT * FROM task WHERE ParentId=? ORDER BY TaskId', (task_id,))
    def goal_steps(self, task_id) -> list:
        """Every box of the goal with the child task behind it, in the goal's own order."""
        kids = {t['TaskId']: t for t in self.children(task_id)}
        return [{'id': i['id'], 'text': i['text'], 'done': bool(i.get('done')), 'tid': i.get('tid'), 'child': kids.get(i.get('tid'))}
                for i in self.task_checklist(task_id)]
    def link_step(self, task_id, item_id: str, child_tid: int, actor: str) -> bool:
        items = self.task_checklist(task_id)
        hit = [i for i in items if i['id'] == item_id]
        if not hit: return False
        hit[0]['tid'] = int(child_tid)
        self._write_checklist(task_id, items, actor)
        self._exec('UPDATE task SET ParentId=? WHERE TaskId=?', (task_id, int(child_tid)))
        return True
    def _tick_parent_step(self, child_tid, actor: str):
        """A child closed `done` ticks the parent's box that points at it; the parent itself is never closed for it."""
        row = self._one('SELECT ParentId FROM task WHERE TaskId=?', (child_tid,))
        if not row or not row.get('ParentId'): return
        items = self.task_checklist(row['ParentId'])
        hit = [i for i in items if i.get('tid') == child_tid and not i.get('done')]
        if not hit: return
        hit[0]['done'] = True
        self._write_checklist(row['ParentId'], items, actor)
```

In `update_task`, inside the existing `if fields.get('Status') == 'done':` block (after the checklist tick at `:1655-1657`), add one line:

```python
            self._tick_parent_step(task_id, actor)
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `python -m pytest tests/test_goals_store.py tests/test_task_checklist.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add taskuary/store.py tests/test_goals_store.py
git commit -m "A goal is a task: DoneWhen and ParentId on the task, a box may point at a child, and a child's close ticks it

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: An owner's promise in sent mail becomes a task

**Files:**
- Modify: `taskuary/sentjudge.py:82-113` (`judge`), `taskuary/store.py` after `deliver_promise` (`:2094`), `taskuary/assistant.py:222-240` (`followups`)
- Test: `tests/test_goals_promises.py` (new)

**Interfaces:**
- Consumes: `store.put_sent_verdict(mid, cid, asks, promise, what, due, by, delivered_by=None)`, `store.deliver_promise(mid, by)`, `store.open_promises(since, before, cid=None)`, `store.create_task`, `store.update_task`.
- Produces: `SQLiteStore.task_for_promise(mid: int, what: str, due: str | None) -> int` (creates once; returns the existing task id on a second call), `SQLiteStore.promise_task(mid) -> dict | None`; a promise task has `Source='promise'`, `SourceRef=f'promise:{mid}'`, `Status='open'`, `Assignee='owner'`, `Kind='task'`, `DueAt=due`; `deliver_promise` closes it with actor `'promise'`.

Scope note: only the owner's **promises** become tasks here (the spec's "when you said it"). What the owner asked *others* for stays an Advisor follow-up line until build step 4 (the per-person chase ladder); turning every sent question into a row would fill On you.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_goals_promises.py
"""The owner's own promise, judged from sent mail, is a task on them with its date (spec 2026-10-12)."""
import json, unittest
from unittest import mock
from taskuary import sentjudge, assistant
from taskuary.store import MemoryStore


def sent(s, mid_body, cid='email:budget', at='2026-10-10 09:00:00'):
    return s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': 'Revised budget', 'BodyText': mid_body,
                          'FromEmail': 'alex@northwind.example', 'FromName': 'Alex Doyle', 'ToEmail': 'gail@northwind.example',
                          'SentAt': at, 'Direction': 'out', 'Status': 'context'}, 'test')


def verdicts(*vs):
    return lambda system, user: json.dumps({'verdicts': list(vs)})


class PromiseTaskTests(unittest.TestCase):
    def test_a_promise_becomes_one_task_once_and_delivery_closes_it(self):
        s = MemoryStore()
        m1 = sent(s, "I'll send the revised budget Friday")
        sentjudge.judge(s, llm=verdicts({'id': f'm{m1}', 'asks_them': False, 'promise': True, 'what': 'send the revised budget',
                                         'due': '2026-10-16', 'delivered': False, 'delivers': []}))
        t = s.promise_task(m1)
        self.assertEqual((t['Title'], t['Status'], t['Assignee'], t['DueAt'], t['Source'], t['SourceRef']),
                         ('Send the revised budget', 'open', 'owner', '2026-10-16', 'promise', f'promise:{m1}'))
        self.assertEqual(s.task_for_promise(m1, 'send the revised budget', '2026-10-16'), t['TaskId'])   # once
        m2 = sent(s, 'Here is the revised budget, attached.', at='2026-10-15 10:00:00')
        sentjudge.judge(s, llm=verdicts({'id': f'm{m2}', 'asks_them': False, 'promise': False, 'what': '', 'due': None,
                                         'delivered': False, 'delivers': [f'm{m1}']}))
        self.assertEqual(s.get_task(t['TaskId'])['Status'], 'done')

    def test_a_promise_with_no_date_has_no_due_and_still_one_task(self):
        s = MemoryStore()
        m1 = sent(s, 'Leave it with me')
        for _ in range(2):
            sentjudge.judge(s, llm=verdicts({'id': f'm{m1}', 'asks_them': False, 'promise': True, 'what': 'sort the refund',
                                             'due': None, 'delivered': False, 'delivers': []}))
        tasks = [t for t in s.list_tasks() if t.get('Source') == 'promise']
        self.assertEqual(len(tasks), 1); self.assertIsNone(tasks[0]['DueAt'])

    def test_the_advisor_does_not_raise_a_promise_that_is_already_a_task(self):
        s = MemoryStore()
        m1 = sent(s, "I'll send the revised budget Friday", at='2026-09-01 09:00:00')
        s.add_message({'ConversationId': 'email:budget', 'Channel': 'email', 'Subject': 'Revised budget', 'BodyText': 'Can I have it?',
                       'FromEmail': 'gail@northwind.example', 'FromName': 'Gail Moreno', 'SentAt': '2026-08-31 09:00:00', 'Direction': 'in'}, 'test')
        s.put_sent_verdict(m1, 'email:budget', False, True, 'send the revised budget', '2026-09-05', 'test')
        with mock.patch.object(assistant, '_since', return_value='2026-08-01 00:00:00'):
            self.assertEqual([c['kind'] for c in assistant.followups(s, 0, want=('promise',))], ['promise'])
            s.task_for_promise(m1, 'send the revised budget', '2026-09-05')
            self.assertEqual(assistant.followups(s, 0, want=('promise',)), [])
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python -m pytest tests/test_goals_promises.py -q`
Expected: FAIL with `AttributeError: 'SQLiteStore' object has no attribute 'promise_task'`. (If `add_message` or `list_tasks` has a different name in `store.py`, use the store's own: `grep -n "def add_message\|def list_tasks" taskuary/store.py` and adjust the test, not the store.)

- [ ] **Step 3: Add the store door**

In `taskuary/store.py`, right after `deliver_promise` (`:2094`), replace that one-liner and add:

```python
    def deliver_promise(self, mid, by):
        self._exec('UPDATE sent_verdict SET DeliveredBy=? WHERE MessageId=?', (by, mid))
        t = self.promise_task(mid)
        if t and t.get('Status') not in ('done', 'dropped'): self.update_task(t['TaskId'], {'Status': 'done'}, 'promise')
    def promise_task(self, mid):
        return self._one("SELECT * FROM task WHERE SourceRef=?", (f'promise:{mid}',))
    def task_for_promise(self, mid: int, what: str, due) -> int:
        """The owner's own promise as a task on them (spec 2026-10-12): made once per sent message, dated when it was."""
        t = self.promise_task(mid)
        if t: return t['TaskId']
        what = ' '.join(str(what or '').split())[:120] or 'what you promised'
        return self.create_task({'Title': what[:1].upper() + what[1:], 'Kind': 'task', 'Status': 'open', 'Assignee': 'owner',
                                 'Source': 'promise', 'SourceRef': f'promise:{mid}', 'DueAt': due or None}, 'promise')
```

(Keep whatever `deliver_promise` did before in its first line; the explorer saw it as the single `UPDATE` shown.)

- [ ] **Step 4: Make the judge create it, and the Advisor skip it**

In `taskuary/sentjudge.py:107-110`, after `store.put_sent_verdict(...)`, add:

```python
            if promise and not done:                                  # the owner's own word is their task, with its day
                store.task_for_promise(m['MessageId'], ' '.join(str(v.get('what') or '').split())[:160], _date(v.get('due')))
```

In `taskuary/assistant.py:232`, change the promise rows line to skip promises that are already a task:

```python
    if 'promise' in want: rows += [('promise', r) for r in store.open_promises(_since(DAYS), cut) if not store.promise_task(r['MessageId'])]
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `python -m pytest tests/test_goals_promises.py tests/test_sentjudge.py tests/test_assistant.py -q` (the last two: whichever of those files exist; `ls tests | grep -i "sentjudge\|assistant"`).
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add taskuary/store.py taskuary/sentjudge.py taskuary/assistant.py tests/test_goals_promises.py
git commit -m "The owner's own promise is a task on them with its day; the Advisor stops raising one that is

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: The vocabulary and the Goals section, on both sides

**Files:**
- Modify: `taskuary/lanes.json` (`kinds`), `taskuary/funnel.py:911-931` (`SECTION_WORDS`, `level_of`), `website/src/funnelPile.js:389-404` and `:539` (`LEVEL_META`, `LEVEL_ORDER`, `levelOf`, `SECTION_WORDS`), `website/src/theme.jsx:24-28`, `website/src/assistantView.css:42-47`, `tests/fixtures/rail_levels.json`, `tests/test_canvas_sections.py:30-33`, `website/test/pileLevels.test.mjs:10-30`
- Test: the two level tests above plus `tests/test_lane_vocabulary.py` and `website/test/funnelPile.test.mjs` (unchanged, must stay green)

**Interfaces:**
- Produces: kinds `goal` ("on track", 🎯, role `info`), `goal_slipped` ("slipped", 🎯, role `bad`), `goal_fresh` ("not started", 🎯, role `info`); section `goals` ("Goals") between `task` and `agents` in `LEVEL_ORDER`; the rule in both `level_of`s: a card whose kind starts with `goal` is in `goals` when `news` is true and it is unread, else `later`.

- [ ] **Step 1: Add fixture rows and update the section lists in the tests (failing first)**

Append to the list in `tests/fixtures/rail_levels.json` (it is a JSON list of `[item, level]` pairs):

```json
[{"kind": "goal_slipped", "lane": "yours", "order_band": 2, "news": true, "unread": true}, "goals"],
[{"kind": "goal", "lane": "yours", "order_band": 2, "news": true, "unread": true}, "goals"],
[{"kind": "goal", "lane": "yours", "order_band": 2, "news": true, "unread": false}, "later"],
[{"kind": "goal", "lane": "yours", "order_band": 2, "news": false, "unread": true}, "later"],
[{"kind": "goal_fresh", "lane": "yours", "order_band": 2, "unread": true}, "later"]
```

In `tests/test_canvas_sections.py:31-32` change the expected list to `['urgent', 'task', 'goals', 'agents', 'later', 'reports', 'ideas', 'fyi']` and add `self.assertEqual(funnel.SECTION_WORDS['goals'], 'Goals')`.

In `website/test/pileLevels.test.mjs:12` change the `LEVEL_ORDER` assertion to `["urgent", "task", "goals", "agents", "later", "reports", "ideas", "fyi"]`, and add to the "no level name merges two things" test: `assert.equal(levelLabel("goals"), "goals");`.

- [ ] **Step 2: Run both sides to see them fail**

Run: `python -m pytest tests/test_canvas_sections.py -q` and `cd website && npm exec --yes --package=node@22 -- node --test test/pileLevels.test.mjs`
Expected: both FAIL on the section list and the fixture rows.

- [ ] **Step 3: The vocabulary**

In `taskuary/lanes.json`, in the `"kinds"` list after the `wrapup` entry, add:

```json
    {
      "key": "goal",
      "word": "on track",
      "role": "info",
      "mark": "🎯",
      "hint": "a goal with a date: its steps are tasks, and it stays on the rail until it is done"
    },
    {
      "key": "goal_slipped",
      "word": "slipped",
      "role": "bad",
      "mark": "🎯",
      "hint": "a goal past its date, or a step somebody owes past theirs"
    },
    {
      "key": "goal_fresh",
      "word": "not started",
      "role": "info",
      "mark": "🎯",
      "hint": "a goal nothing has moved on yet"
    }
```

- [ ] **Step 4: The server side**

In `taskuary/funnel.py:911-912` change `SECTION_WORDS` to:

```python
SECTION_WORDS = {'urgent': 'Urgent', 'task': 'On you', 'goals': 'Goals', 'agents': 'Agents working', 'later': 'For later',
                 'reports': 'Reports', 'ideas': 'Advisor ideas', 'fyi': 'FYI'}
```

In `level_of` (`:919`), before the `put_down` line, add:

```python
    # A GOAL is one row and never gone: Goals while it has news you have not read, For later otherwise (spec 2026-10-12)
    if str(item.get('kind') or '').startswith('goal'): return 'goals' if item.get('news') and item.get('unread') else 'later'
```

- [ ] **Step 5: The page side**

In `website/src/funnelPile.js`, `LEVEL_META` (`:389`) gains, after `task`:

```js
  goals: { word: "goals", hint: "an outcome with a date, its steps tasks of their own - here while it has news, in For later while it is quiet" },
```

`LEVEL_ORDER` (`:403`) becomes `["urgent", "task", "goals", "agents", "later", "reports", "ideas", "fyi"]`.

`levelOf` (`:418`) gains, as its first line after `const band = ...`:

```js
  if (String(item?.kind || "").startsWith("goal")) return item?.news && item?.unread ? "goals" : "later";
```

`PLACEMENT` (`:405`) gains `"news"` so the page keeps the server's flag when it merges a row with a card: `export const PLACEMENT = ["lane", "order_band", "surfaced", "surfaced_at", "put_down", "unread", "kind", "working", "state", "news"];`

`SECTION_WORDS` (`:539`) becomes `{ urgent: "Urgent", task: "On you", goals: "Goals", agents: "Agents working", later: "For later", reports: "Reports", ideas: "Advisor ideas", fyi: "FYI" }`.

In `website/src/theme.jsx:24-28` add `goals: PALETTE.slate` to `LEVEL_COLOR` and `goals: "#e6ebef"` to `LEVEL_TINT`.

In `website/src/assistantView.css` after the `.lvl-agents` rule (`:47`) add:

```css
.tq-pile-head span.lvl-goals, .tq-sum-head span.lvl-goals { color: #fff; background: #55697a; border: 1px solid #55697a; }   /* a goal is slate, like the project mark it wears */
```

- [ ] **Step 6: Run both sides to see them pass**

Run: `python -m pytest tests/test_canvas_sections.py tests/test_lane_vocabulary.py -q` and `cd website && npm exec --yes --package=node@22 -- npm test`
Expected: all pass (the lane test asserts `funnel.KIND_MARKS` keys equal the file's kinds; both read the same file).

- [ ] **Step 7: Commit**

```bash
git add taskuary/lanes.json taskuary/funnel.py website/src/funnelPile.js website/src/theme.jsx website/src/assistantView.css tests/fixtures/rail_levels.json tests/test_canvas_sections.py website/test/pileLevels.test.mjs
git commit -m "A Goals section on the rail, and three goal kinds in the one vocabulary

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: The goal row on the rail, and its children folded into it

**Files:**
- Modify: `taskuary/processing_unread.py:66` (constants), `:290` (after the `theirs` line), `:473-476` (`on_rail`)
- Test: `tests/test_goals_rail.py` (new)

**Interfaces:**
- Consumes: `store.goal_steps`, `store.children`, `store.is_goal`, `funnel.LANE_WORDS`, `task_ref`.
- Produces: on a goal's card: `kind` in `goal | goal_slipped | goal_fresh`, `news: bool`, `due: 'YYYY-MM-DD' | None`, `back_at` (the due day at 08:00, for For later's countdown), `steps_done: int`, `steps: int`, `why` (the sub line); on a child's card: `folded: bool` and `goal: 'TQ-nnnn'`; `on_rail` keeps a goal card and drops a folded one. `FOLD_LANES = ('working', 'queued', 'theirs', 'fyi')`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_goals_rail.py
"""One row per goal: Goals when it has news, For later when quiet, never gone; children fold into it unless they are the
owner's move (spec 2026-10-12)."""
import unittest
from datetime import datetime, timedelta
from unittest import mock
from taskuary import funnel, processing_unread
from taskuary.store import checklist_id
from test_funnel import ago, store


def settled():
    s = store()
    def settle():
        s.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()
    return s, settle


def rail(s, **kw):
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        return processing_unread.build(s, live_state=[], **kw)['items']


def day(n): return (datetime.now() + timedelta(days=n)).strftime('%Y-%m-%d')


def goal(s, due=None, steps=('Inventory the fields', 'Map the schema', 'Schema sign-off')):
    g = s.create_task({'Title': 'Migrate the census export off the old portal', 'Kind': 'task', 'Status': 'open',
                       'DoneWhen': 'the nightly census lands in the new ledger', 'DueAt': due or day(50)}, 'owner')
    if steps: s.set_task_checklist(g, list(steps), 'owner')
    return g


def card(s, tid): return next(i for i in rail(s, include_read=True) if i.get('tid') == tid)


class GoalRowTests(unittest.TestCase):
    def test_a_goal_with_no_boxes_is_fresh_and_in_later(self):
        s, settle = settled(); g = goal(s, steps=()); settle()
        c = card(s, g)
        self.assertEqual((c['kind'], c['steps'], c['steps_done'], c['due']), ('goal_fresh', 0, 0, day(50)))
        self.assertEqual(funnel.level_of(c), 'later'); self.assertTrue(c['back_at'].startswith(day(50)))

    def test_a_quiet_goal_on_track_sits_in_later_with_its_count(self):
        s, settle = settled(); g = goal(s)
        s.tick_checklist_item(g, checklist_id('Inventory the fields'), True, 'owner'); settle()
        c = card(s, g)
        self.assertEqual(c['kind'], 'goal'); self.assertEqual(funnel.level_of(c), 'later')
        self.assertTrue(c['why'].startswith('1 of 3'), c['why'])

    def test_a_goal_past_its_date_is_slipped_and_in_goals(self):
        s, settle = settled(); g = goal(s, due=day(-4)); settle()
        c = card(s, g)
        self.assertEqual((c['kind'], c['news']), ('goal_slipped', True)); self.assertEqual(funnel.level_of(c), 'goals')
        self.assertIn('slipped 4d', c['why'])

    def test_a_goal_with_every_box_done_is_not_slipped(self):
        s, settle = settled(); g = goal(s, due=day(-4), steps=('Only step',))
        s.tick_checklist_item(g, checklist_id('Only step'), True, 'owner'); settle()
        self.assertEqual(card(s, g)['kind'], 'goal')

    def test_a_step_closed_today_is_news(self):
        s, settle = settled(); g = goal(s)
        c = s.create_task({'Title': 'Map the schema', 'Kind': 'general', 'ParentId': g}, 'owner'); s.link_step(g, checklist_id('Map the schema'), c, 'owner')
        s.update_task(c, {'Status': 'done'}, 'agent:coder'); settle()
        k = card(s, g)
        self.assertTrue(k['news']); self.assertEqual(funnel.level_of(k), 'goals')


class FoldTests(unittest.TestCase):
    def test_a_child_waiting_on_them_folds_into_the_goal_and_names_who(self):
        s, settle = settled(); g = goal(s)
        c = s.create_task({'Title': 'Schema sign-off', 'Kind': 'task', 'Status': 'waiting', 'Assignee': 'person:ray@northwind.example', 'ParentId': g}, 'owner')
        s.link_step(g, checklist_id('Schema sign-off'), c, 'owner'); settle()
        items = rail(s, include_read=True)
        self.assertNotIn(c, [i.get('tid') for i in items])                      # folded: not a row of its own
        self.assertIn('ray owes step 3', card(s, g)['why'])

    def test_a_child_that_is_the_owners_move_stays_a_row_and_names_its_goal(self):
        s, settle = settled(); g = goal(s)
        c = s.create_task({'Title': 'Tell the sites the cutover date', 'Kind': 'task', 'Status': 'open', 'ParentId': g}, 'owner')
        s.link_step(g, checklist_id('Map the schema'), c, 'owner'); settle()
        k = card(s, c)
        self.assertEqual((k['lane'], k['folded'], k['goal']), ('yours', False, funnel.task_ref(g)))
        self.assertIn('step 2 is on you', card(s, g)['why'])

    def test_a_closed_goal_leaves_the_rail(self):
        s, settle = settled(); g = goal(s); settle()
        s.update_task(g, {'Status': 'done'}, 'owner'); settle()
        self.assertNotIn(g, [i.get('tid') for i in rail(s, include_read=True)])
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python -m pytest tests/test_goals_rail.py -q`
Expected: FAIL with `KeyError: 'steps'` (the card has no goal fields yet).

- [ ] **Step 3: The constants**

In `taskuary/processing_unread.py` after `OWNER_LANES` (`:66`) add:

```python
# a goal's CHILD in one of these lanes is told by the goal's row ("coder on step 5 · Ray owes step 4"), not by a row of its
# own; in any other lane it is the owner's move and stays a row (spec 2026-10-12, "many steps, one row")
FOLD_LANES = ('working', 'queued', 'theirs', 'fyi')
```

- [ ] **Step 4: The goal card and the fold, in `card_for`**

Right after the `theirs` line (`:290`), add:

```python
    # A GOAL IS ONE ROW (spec 2026-10-12): its kind says its state, its sub line says the count and who is holding it, its
    # date sits where the age goes, and it is never gone while open. Its children fold into it unless they are your move.
    from .store import is_goal
    if is_goal(task) and active and not review and not worker:
        card.update(**goal_facts(store, task, tid, now))
    elif task.get('ParentId') and active:
        card.update(goal=funnel.task_ref(task['ParentId']), folded=card['lane'] in FOLD_LANES)
```

And add the helper at module level (above `card_for`):

```python
def goal_facts(store, task, tid, now) -> dict:
    """What the goal's row says: kind (slipped / on track / not started), news, the count, who holds it, its date."""
    from . import funnel
    steps = store.goal_steps(tid)
    done, n = sum(1 for x in steps if x['done']), len(steps)
    today = now.strftime('%Y-%m-%d')
    due = str(task.get('DueAt') or '')[:10] or None
    kids = [x for x in steps if x['child']]
    late_kid = next((x for x in kids if x['child'].get('Status') == 'waiting' and str(x['child'].get('DueAt') or '')[:10] and str(x['child'].get('DueAt'))[:10] < today), None)
    slipped = (due and due < today and done < n) or bool(late_kid)
    started = done or any(x['child'].get('Status') != 'open' or x['child'].get('Assignee') for x in kids)
    kind = 'goal_slipped' if slipped else 'goal_fresh' if not started else 'goal'
    recent = (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    news = slipped or any(str(x['child'].get('ClosedAt') or '') >= recent for x in kids)
    bits = [f'{done} of {n}' if n else 'no steps yet']
    for k, x in enumerate(steps, 1):
        c = x['child']
        if not c or c.get('Status') in ('done', 'dropped'): continue
        who = str(c.get('Assignee') or '')
        if who.startswith('agent:'): bits.append(f"{who.split(':', 1)[1]} on step {k}")
        elif who.startswith('person:'): bits.append(f"{who.split(':', 1)[1].split('@')[0]} owes step {k}")
        elif c.get('Status') == 'open': bits.append(f'step {k} is on you')
    if slipped and due and due < today: bits.append(f"slipped {(now - datetime.strptime(due, '%Y-%m-%d')).days}d")
    return {'kind': kind, 'news': bool(news), 'due': due, 'steps': n, 'steps_done': done, 'why': ' · '.join(bits),
            'back_at': f'{due} 08:00:00' if due else None, 'folded': False}
```

Add `from datetime import datetime, timedelta` to the module's imports if not already there (check the top of the file).

- [ ] **Step 5: Keep goals on the rail and drop folded children**

Replace `on_rail` (`:473-476`) with:

```python
def on_rail(card) -> bool:
    """What the rail holds: the unread, a task put away with Remind me (still open work, in For later with its day), and a
    goal - never gone while open (spec 2026-10-12). A goal's child folded into its row is not a row. ONE rule for the
    builder and for funnel.pile."""
    if card.get('folded'): return False
    if str(card.get('kind') or '').startswith('goal') and card.get('tid') and not card.get('closed'): return True
    return bool(card.get('unread') or (card.get('deferred') and card.get('tid') and not card.get('closed')))
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `python -m pytest tests/test_goals_rail.py tests/test_rail_decisions.py tests/test_canvas_sections.py tests/processing -q`
Expected: all pass. If `test_a_child_waiting_on_them_folds...` fails because the child never reaches lane `theirs`, check `card_for:290`: it requires `not row.get('MessageId')`, which holds for a task with no message; the fold line must come *after* that line, as placed.

- [ ] **Step 7: Commit**

```bash
git add taskuary/processing_unread.py tests/test_goals_rail.py
git commit -m "One row per goal on the rail: slipped, on track or not started, with its count and who holds it; children fold in

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: The API: a goal's steps, starting one, planning them

**Files:**
- Modify: `taskuary/server.py:309-312` (`TaskBody`), `:623-642` (`_read_hand_task`, `read_hand_task`), after `:731` (`edit_checklist`), `taskuary/triage.py:400-440` (`ASK_SYSTEM`, `extract_ask`)
- Test: `tests/test_goals_api.py` (new)

**Interfaces:**
- Consumes: `store.goal_steps`, `store.link_step`, `store.create_task`, `store.task_checklist`, `store.merge_task_checklist(tid, texts, actor)`, `selfclose.claim(store, tid, actor)`, `concierge.brain(store, fast=True)`, `task_ref`.
- Produces: `TaskBody` gains `DoneWhen: str | None`, `DueAt: str | None`, `ParentId: int | None`; `GET /api/tasks/{id}/steps -> {steps: [{id, text, done, tid, ref, status, who, state}]}`; `POST /api/tasks/{id}/steps/{item_id}/start -> {taskId, ref}` (creates the child, links it, claims it as the owner's); `POST /api/tasks/{id}/read-ask` takes an optional body `ReadAskBody(goal: bool = False)`; `triage.extract_ask(msg, llm=None, goal=False)` adds `GOAL_SYSTEM` to the prompt when `goal`; `triage.GOAL_SYSTEM` (the one added sentence); `server.plan_goal(tid, text)` merges by tid first, text second.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_goals_api.py
"""The goal's doors: its steps, starting one, planning them (spec 2026-10-12)."""
import json, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import server, triage
from taskuary.store import checklist_id


def client():
    server.store = server.MemoryStore() if hasattr(server, 'MemoryStore') else server.store
    return TestClient(server.app)


class StepsTests(unittest.TestCase):
    def setUp(self):
        from taskuary.store import MemoryStore
        server.store = MemoryStore(); self.c = TestClient(server.app)
        self.g = self.c.post('/api/tasks', json={'Title': 'Migrate the census export', 'Kind': 'task', 'DoneWhen': 'the nightly census lands',
                                                 'DueAt': '2026-12-01'}).json()['taskId']

    def test_a_goal_is_created_with_its_sentence_and_date(self):
        t = server.store.get_task(self.g)
        self.assertEqual((t['DoneWhen'], t['DueAt']), ('the nightly census lands', '2026-12-01'))

    def test_steps_of_a_goal_with_no_checklist_is_empty(self):
        self.assertEqual(self.c.get(f'/api/tasks/{self.g}/steps').json(), {'steps': []})

    def test_starting_a_step_makes_a_child_and_links_it(self):
        server.store.set_task_checklist(self.g, ['Inventory the fields', 'Map the schema'], 'owner')
        r = self.c.post(f'/api/tasks/{self.g}/steps/{checklist_id("Map the schema")}/start').json()
        child = server.store.get_task(r['taskId'])
        self.assertEqual((child['ParentId'], child['Title'], child['Kind']), (self.g, 'Map the schema', 'general'))
        self.assertIn('Done when: the nightly census lands', child['Summary'])
        steps = self.c.get(f'/api/tasks/{self.g}/steps').json()['steps']
        self.assertEqual((steps[1]['tid'], steps[1]['ref'], steps[1]['status'], steps[0]['tid']), (r['taskId'], r['ref'], 'open', None))
        self.assertEqual(self.c.post(f'/api/tasks/{self.g}/steps/{checklist_id("Map the schema")}/start').json()['taskId'], r['taskId'])  # once

    def test_starting_a_step_that_is_not_there_is_404(self):
        self.assertEqual(self.c.post(f'/api/tasks/{self.g}/steps/nosuch/start').status_code, 404)

    def test_replanning_keeps_started_steps(self):
        server.store.set_task_checklist(self.g, ['Inventory the fields', 'Map the schema'], 'owner')
        child = self.c.post(f'/api/tasks/{self.g}/steps/{checklist_id("Map the schema")}/start').json()['taskId']
        ask = {'summary': 'x', 'checklist': ['Inventory the fields', 'Map them onto the ledger schema', 'Schema sign-off'], 'outputs': []}
        with mock.patch.object(triage, 'extract_ask', return_value=ask):
            server.plan_goal(self.g, 'anything')
        steps = server.store.goal_steps(self.g)
        self.assertEqual([x['text'] for x in steps], ['Inventory the fields', 'Map them onto the ledger schema', 'Schema sign-off'])
        self.assertEqual(steps[1]['tid'], child)                      # the rephrased box kept its child


class PromptTests(unittest.TestCase):
    def test_a_goal_adds_the_goal_sentence_and_nothing_else(self):
        seen = {}
        def llm(system, user): seen['system'] = system; return json.dumps({'summary': 's', 'checklist': ['a', 'b'], 'outputs': []})
        triage.extract_ask({'body': 'Migrate the census export. Done when: it lands. Involved: Ray, the coder'}, llm, goal=True)
        self.assertTrue(seen['system'].startswith(triage.ASK_SYSTEM)); self.assertTrue(seen['system'].endswith(triage.GOAL_SYSTEM))
        triage.extract_ask({'body': 'plain'}, llm)
        self.assertEqual(seen['system'], triage.ASK_SYSTEM)
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python -m pytest tests/test_goals_api.py -q`
Expected: FAIL: the `DoneWhen` field is dropped by `TaskBody` (first test) and `/steps` is 404. (See `tests/test_api.py` for how it swaps `server.store`; if it uses a helper, use that helper instead of assigning `server.store` directly.)

- [ ] **Step 3: The body and the prompt**

`taskuary/server.py:309-312`:

```python
class TaskBody(BaseModel):
    Title: str | None = None; Summary: str | None = None; Kind: str | None = None
    Priority: str | None = None; Status: str | None = None; Tags: str | None = None
    Assignee: str | None = None; DoneWhen: str | None = None; DueAt: str | None = None; ParentId: int | None = None
class ReadAskBody(BaseModel): goal: bool = False
```

`taskuary/triage.py`, after `ASK_SYSTEM` (`:409`):

```python
# ...and for a GOAL (spec 2026-10-12): the boxes are the ordered steps to the outcome, each naming who does it. The model
# writes them; code only keeps the ones it returns.
GOAL_SYSTEM = (' This message is a GOAL with a date, not one ask: the checklist is the ORDERED steps that reach the outcome it '
               'describes, three to nine of them, each one step a person or an agent can finish, named for who does it when '
               'the message says ("Ray: schema sign-off"). The summary restates what done looks like.')
```

`extract_ask` signature and the one call (`:412`, `:431`):

```python
def extract_ask(msg: dict, llm=None, goal: bool = False) -> dict:
    ...
        raw = llm(ASK_SYSTEM + (GOAL_SYSTEM if goal else ''), f'Subject: {subject}\n\n{body[:6000]}')
```

- [ ] **Step 4: The planner and the read-ask body**

`taskuary/server.py`, replace `_read_hand_task` and `read_hand_task` (`:623-642`):

```python
def _read_hand_task(tid: int, text: str, goal: bool = False):
    """A task typed into + New skips triage, so it had no checklist - one block of words with no boxes (the owner, 2026-10-09:
    "when i create task the task list looks weird?? (no checkboxes?)"). The same reading a promoted message gets
    (triage.extract_ask), off the request: each distinct thing asked becomes a box, an email it asks for becomes one of the
    task's emails. The owner's own words stay the summary. A brain that fails leaves the task as typed. A goal's boxes are its
    steps (plan_goal)."""
    if goal: return plan_goal(tid, text)
    try:
        from . import concierge, slots, triage
        ask = triage.extract_ask({'body': text}, concierge.brain(store, fast=True))
        if ask.get('checklist') and not store.task_checklist(tid): store.set_task_checklist(tid, ask['checklist'], 'triage')
        if ask.get('outputs'): slots.add(store, tid, ask['outputs'], 'triage')
    except Exception as e: logger.info(f'could not read the checklist of {task_ref(tid)}: {e}')


def plan_goal(tid: int, text: str):
    """The model writes the goal's steps; a step already started keeps its child whatever the new words are: matched by tid
    first (same position, or the one box with that tid), by text second (spec 2026-10-12, Review Focus 5)."""
    try:
        from . import concierge, triage
        ask = triage.extract_ask({'body': text}, concierge.brain(store, fast=True), goal=True)
        texts = [x for x in ask.get('checklist') or [] if x]
        if not texts: return
        old = store.task_checklist(tid)
        started = [i for i in old if i.get('tid')]
        store.set_task_checklist(tid, texts, 'triage')
        new = store.task_checklist(tid)
        for i in started:                                       # same words: set_task_checklist kept it; else the same slot
            if any(n.get('tid') == i['tid'] for n in new): continue
            slot = next((n for n in new if n['text'] == i['text']), None) or (new[old.index(i)] if old.index(i) < len(new) else None)
            if slot and not slot.get('tid'): store.link_step(tid, slot['id'], i['tid'], 'triage')
    except Exception as e: logger.info(f'could not plan {task_ref(tid)}: {e}')


@app.post('/api/tasks/{task_id}/read-ask')
def read_hand_task(task_id: int, background: BackgroundTasks, body: ReadAskBody = None):
    """+ New asks for its task to be read once it exists (_read_hand_task) - answered at once, read behind it."""
    t = store.get_task(task_id)
    if not t: raise HTTPException(404, 'task not found')
    goal = bool(body and body.goal) or bool(t.get('DoneWhen'))
    words = t.get('Summary') or t.get('Title') or ''
    if goal: words = f"{t.get('Title') or ''}\nDone when: {t.get('DoneWhen') or ''}\n{words}"
    background.add_task(_read_hand_task, task_id, words, goal)
    return {'ok': True}
```

Check `set_task_checklist` keeps a box's `tid` when its text is unchanged: it keeps the box's *state*; read `store.py:1699-1722` and, if it rebuilds items from texts, make it carry over `tid` the same way it carries `done` (one extra key in the dict it builds). Pin that with the existing `test_task_checklist.py` style if you touch it.

- [ ] **Step 5: The two step endpoints**

After `edit_checklist` (`:727-731`):

```python
@app.get('/api/tasks/{task_id}/steps')
def goal_steps(task_id: int):
    """A goal's boxes with the child task behind each (store.goal_steps), as the task page lists them."""
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    from . import taskstate
    out = []
    for x in store.goal_steps(task_id):
        c = x.pop('child')
        who = str((c or {}).get('Assignee') or '')
        out.append({**x, 'ref': task_ref(c['TaskId']) if c else None, 'status': (c or {}).get('Status'),
                    'who': who.split(':', 1)[1] if ':' in who else who, 'state': taskstate.state(store, c) if c else None})
    return {'steps': out}


@app.post('/api/tasks/{task_id}/steps/{item_id}/start')
def start_step(task_id: int, item_id: str):
    """One box becomes a task of its own, the goal's child: made once, claimed as the owner's like any + New task."""
    g = store.get_task(task_id)
    if not g: raise HTTPException(404, 'task not found')
    box = next((i for i in store.task_checklist(task_id) if i['id'] == item_id), None)
    if not box: raise HTTPException(404, 'no such step')
    if box.get('tid') and store.get_task(box['tid']): return {'taskId': box['tid'], 'ref': task_ref(box['tid'])}
    k = [i['id'] for i in store.task_checklist(task_id)].index(item_id) + 1
    tid = store.create_task({'Title': box['text'][:300], 'Kind': 'general', 'ParentId': task_id, 'Source': 'goal', 'SourceRef': f'goal:{task_id}:{item_id}',
                             'Summary': f"Step {k} of {task_ref(task_id)} \"{g.get('Title') or ''}\". Done when: {g.get('DoneWhen') or ''}", 'AskedVia': 'desktop'}, ACTOR)
    store.link_step(task_id, item_id, tid, ACTOR)
    from . import selfclose
    selfclose.claim(store, tid, ACTOR)
    store.audit('task', tid, 'create', ACTOR, detail={'goal': task_id, 'step': item_id})
    return {'taskId': tid, 'ref': task_ref(tid)}
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `python -m pytest tests/test_goals_api.py tests/test_api.py tests/test_task_checklist.py -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add taskuary/server.py taskuary/triage.py tests/test_goals_api.py
git commit -m "A goal's doors: its steps with the child behind each, Start on a step, and the model plans the steps

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: The page: the fourth tab, the goal row's mark and date, the steps on the task page

**Files:**
- Modify: `website/src/NewSheet.jsx:29-33` (KINDS), `:151` (state), `:169-217` (submit), `:220-221` (verb), `:254-380` (the per-kind blocks); `website/src/assistantCards.jsx:48-70` (`SourceMark`, `sourceColor`); `website/src/AssistantView.jsx:443-446` (the gutter); `website/src/TaskPage.jsx:1259` (before the checklist block), `:892` (`rowVerbs`)
- Test: `website/test/goalRow.test.mjs` (new) for the pure helpers; `npm run lint:undef`; `npm run build`

**Interfaces:**
- Consumes: `POST /api/tasks` with `DoneWhen`, `DueAt`; `POST /api/tasks/{id}/read-ask` with `{goal: true}`; `GET /api/tasks/{id}/steps`; `POST /api/tasks/{id}/steps/{item_id}/start`; `PATCH /api/tasks/{id}` with `{DueAt}`.
- Produces: `funnelPile.dueWord(iso) -> "Dec 1"` (exported, for the gutter); a `goal` tab on the sheet; `GoalSteps` component inside `TaskPage.jsx`.

- [ ] **Step 1: Write the failing node test for the helper**

```js
// website/test/goalRow.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { dueWord, levelOf } from "../src/funnelPile.js";

test("a goal's gutter says its date, short", () => {
  assert.equal(dueWord("2026-12-01"), "Dec 1");
  assert.equal(dueWord("2026-12-01 08:00:00"), "Dec 1");
  assert.equal(dueWord(""), "");
  assert.equal(dueWord(null), "");
});

test("a goal is in Goals only while it has unread news", () => {
  assert.equal(levelOf({ kind: "goal_slipped", order_band: 2, news: true, unread: true }), "goals");
  assert.equal(levelOf({ kind: "goal", order_band: 2, news: false, unread: true }), "later");
});
```

Run: `cd website && npm exec --yes --package=node@22 -- node --test test/goalRow.test.mjs` → FAIL (`dueWord` is not exported).

- [ ] **Step 2: The helper and the gutter**

In `website/src/funnelPile.js`, next to `railBack` (`:430`):

```js
// a GOAL's gutter is its date, not its age: for a goal the date is the clock (spec 2026-10-12)
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const dueWord = (iso) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
  return m ? `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}` : "";
};
```

In `website/src/AssistantView.jsx:445-446` (the `<span className="when">` contents), make the goal's gutter its date:

```jsx
                      {String(i.kind || "").startsWith("goal") ? dueWord(i.due)
                        : level === "later" ? railBack(backAt(i)) : railAge(i.kind === "meeting" ? i.when : (i.since || i.when))}</span>
```

and add `dueWord` to the `funnelPile.js` import at the top of `AssistantView.jsx`.

- [ ] **Step 3: The mark**

`website/src/assistantCards.jsx`: import `OutlinedFlagIcon from "@mui/icons-material/OutlinedFlag"` beside the other icon imports, and add as the second branch of both `SourceMark` and `sourceColor` (after the `meeting` line):

```jsx
  if (String(item.kind || "").startsWith("goal")) return <OutlinedFlagIcon sx={{ fontSize: size, color: "#55697a" }} />;   // a goal has no source: it wears the project mark
```

```js
  if (String(item.kind || "").startsWith("goal")) return "#55697a";
```

- [ ] **Step 4: The fourth tab**

`website/src/NewSheet.jsx:29-33`, add to `KINDS`:

```js
  { key: "goal", mark: "🎯", label: "Set a goal", hint: "an outcome with a date and steps - the steps are tasks, and it stays on your rail until it is done" },
```

State, next to `const [when, setWhen] = useState("");` (`:151`):

```js
  const [by, setBy] = useState(""); const [who, setWho] = useState(""); const [plan, setPlan] = useState(true);
```

In `submit`, before the final `} else {` (the note branch), add a branch:

```js
      } else if (kind === "goal") {
        const title = about.split(/[.\n]/)[0].trim().slice(0, 120) || about.slice(0, 120);
        const { data } = await api.post("/api/tasks", { Title: title, Summary: who ? `${about}\nInvolved: ${who}` : about,
          DoneWhen: about.slice(0, 1000), DueAt: by || null, Kind: "task", Tags: "goal" });
        // the model writes the steps (server.plan_goal); "Track it" leaves the boxes to you
        if (plan) api.post(`/api/tasks/${data.taskId}/read-ask`, { goal: true }).catch(() => null);
        setOk(`${data.ref} — ${plan ? "planning the steps; they land on the task in a moment." : "on your rail; add the steps on the task."}`);
        aboutRef.current?.clear(); setHasAbout(false); setBy(""); setWho(""); onDone?.(); onOpenTask?.(data.taskId);
```

and add `by, who, plan` to the `useCallback` dependency list. The `verb` line (`:220-221`) becomes:

```js
  const verb = kind === "send" ? (mode === "task" ? "Send an agent" : "Draft it")
    : kind === "agent" ? (how === "chat" ? "Ask the assistant" : "Start the session") : kind === "goal" ? (plan ? "Plan it" : "Track it") : "Note it";
```

The about-field label (`:347-348`) gains `: kind === "goal" ? "What does done look like"`, and its placeholder (`:101-103`) gains `: kind === "goal" ? "the nightly census lands in the new ledger for all three sites, and the old portal's export is switched off"`.

Add the goal block after the `{kind === "agent" && (...)}` block (`:312-345`), using the sheet's own `Label` and `Fork` components:

```jsx
        {kind === "goal" && (
          <>
            <Box>
              <Label>By</Label>
              <TextField type="date" size="small" value={by} onChange={(e) => setBy(e.target.value)} sx={{ "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7" } }} />
              <Typography sx={{ fontSize: 11, color: FAINT, mt: 0.5 }}>The date is the goal's clock: it sits where the age goes on your rail.</Typography>
            </Box>
            <Box>
              <Label>Who is involved</Label>
              <TextField fullWidth size="small" value={who} onChange={(e) => setWho(e.target.value)} placeholder="Ray Colton, Payworth (Marcus), the coder"
                sx={{ "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7" } }} />
              <Typography sx={{ fontSize: 11, color: FAINT, mt: 0.5 }}>People it may chase and systems it may touch. Anyone else is a question to you first.</Typography>
            </Box>
            <Box>
              <Label>And then</Label>
              <Box sx={{ display: "flex", gap: 1 }}>
                <Fork on={plan} onClick={() => setPlan(true)} title="Plan it and show me"
                  hint="the AI proposes the steps from your words; you cut or add, then start the first one. It lands on the rail as a goal." />
                <Fork on={!plan} onClick={() => setPlan(false)} title="Track it, I have the plan"
                  hint="type the steps yourself on the task; it chases the people on them and reports against the date." />
              </Box>
            </Box>
          </>
        )}
```

- [ ] **Step 5: The steps on the task page**

In `website/src/TaskPage.jsx`, add a component above `export default function TaskPage` (or wherever the page's top-level function begins; find it with `grep -n "^export default function\|^function TaskPage" website/src/TaskPage.jsx`):

```jsx
// A GOAL'S STEPS (spec 2026-10-12): the checklist, each box with the task behind it. Start makes a box a task of its own;
// a box with a task shows its ref and state and opens it. The parent's box ticks itself when the child closes (store).
function GoalSteps({ task, onOpenTask, onChanged }) {
  const [steps, setSteps] = useState([]);
  const load = useCallback(() => api.get(`/api/tasks/${task.TaskId}/steps`).then((r) => setSteps(r.data.steps || [])).catch(() => setSteps([])), [task.TaskId]);
  useEffect(() => { load(); }, [load, task.UpdatedAt]);
  const start = async (s) => { const { data } = await api.post(`/api/tasks/${task.TaskId}/steps/${s.id}/start`); load(); onChanged?.(); onOpenTask?.(data.taskId); };
  const moveDate = async (e) => { await api.patch(`/api/tasks/${task.TaskId}`, { DueAt: e.target.value || null }); onChanged?.(); };
  const done = steps.filter((s) => s.done).length;
  return (
    <Box sx={{ mt: 0.85, maxWidth: 900 }}>
      <Typography sx={{ ...label, display: "block", mb: 0.25 }}>Done when</Typography>
      <Typography variant="body2" sx={{ color: INK, lineHeight: 1.55 }}>{task.DoneWhen}</Typography>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mt: 0.6, flexWrap: "wrap" }}>
        <Typography variant="caption" sx={{ color: FAINT }}>{steps.length ? `${done} of ${steps.length} steps done` : "no steps yet"}</Typography>
        <Typography variant="caption" sx={{ color: FAINT }}>by</Typography>
        <TextField type="date" size="small" defaultValue={String(task.DueAt || "").slice(0, 10)} onBlur={moveDate}
          inputProps={{ "aria-label": "Move the date" }} sx={{ "& .MuiInputBase-root": { fontSize: 12, height: 26 } }} />
      </Box>
      {steps.map((s, k) => (
        <Box key={s.id} sx={{ display: "flex", alignItems: "center", gap: 0.8, py: 0.35, borderBottom: `1px solid ${BORDER}` }}>
          <Typography variant="caption" sx={{ color: FAINT, width: 16, fontVariantNumeric: "tabular-nums" }}>{k + 1}</Typography>
          <Typography variant="body2" sx={{ flex: 1, color: s.done ? FAINT : INK, textDecoration: s.done ? "line-through" : "none" }}>{s.text}</Typography>
          {s.who && <Typography variant="caption" sx={{ color: FAINT }}>{s.who}</Typography>}
          {s.ref
            ? <Button size="small" variant="text" onClick={() => onOpenTask?.(s.tid)} sx={{ fontSize: 11, textTransform: "none" }}>{s.ref} · {s.state || s.status}</Button>
            : !s.done && <Button size="small" variant="outlined" onClick={() => start(s)} sx={{ fontSize: 11, textTransform: "none" }}>Start</Button>}
        </Box>
      ))}
    </Box>
  );
}
```

Then in the Task step, right before the `{(detail?.checklist || []).length > 0 && (` block (`:1259`), render it for a goal and skip the plain checklist for one:

```jsx
                        {t?.DoneWhen && <GoalSteps task={t} onOpenTask={onOpenTask} onChanged={() => { loadDetail(t.TaskId); loadTasks(); onChanged?.(); }} />}
                        {!t?.DoneWhen && (detail?.checklist || []).length > 0 && (
```

(`onOpenTask`, `loadDetail`, `loadTasks`, `onChanged`, `label`, `INK`, `FAINT`, `BORDER`, `Button`, `TextField`, `useState`, `useEffect`, `useCallback`, `api` are what the file already uses; confirm each with `grep -n` and import any that is missing.)

- [ ] **Step 6: Gates**

Run (from `website/`): `npm exec --yes --package=node@22 -- npm test`, then `npm exec --yes --package=node@22 -- npm run lint:undef`, then `npm exec --yes --package=node@22 -- npm run build`.
Expected: tests pass, 0 undefined, the bundle builds. Commit the rebuilt bundle with the source (the repo commits it; see `git status` for the bundle path).

- [ ] **Step 7: Look at it once**

Run `taskuary --demo --port 7901` and open the Assistant tab: press New, pick Set a goal, type a done-when sentence, a date and "Ray Colton, the coder", press Plan it. Expect the goal row under For later (or Goals once a step is news), with a flag mark and its date in the gutter; open it and see Done when, the count, the steps and Start. Then stop the server.

- [ ] **Step 8: Commit**

```bash
git add website/src/NewSheet.jsx website/src/assistantCards.jsx website/src/AssistantView.jsx website/src/TaskPage.jsx website/src/funnelPile.js website/test/goalRow.test.mjs taskuary/web
git commit -m "Set a goal on the New sheet; the goal row wears a flag and its date; the task page lists its steps with Start

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

(`taskuary/web` is where the built bundle lands; if the path differs, add whatever `git status` shows as the rebuilt bundle.)

---

### Task 7: The demo world, the docs and the walk

**Files:**
- Modify: `taskuary/demo.py` (after the GL task at `:330-337`), `docs/site/tasks-and-agents.md:250-258` (the rail table), `docs/site/how-it-works.md:16`, `README.md:41-42`, `taskuary/walk.py:106-118` (the Tasks stop)
- Test: `tests/test_demo.py` (existing: `test_nobody_real_is_in_it`, `test_the_seed_builds_a_morning_worth_looking_at`), plus one new assertion in `tests/test_goals_rail.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_goals_rail.py`:

```python
class DemoTests(unittest.TestCase):
    def test_the_demo_world_has_one_goal_with_a_started_step(self):
        from taskuary import demo
        from taskuary.store import MemoryStore, is_goal
        s = MemoryStore(); demo.seed(s)
        goals = [t for t in s.list_tasks() if is_goal(t) and t.get('Status') == 'open']
        self.assertEqual(len(goals), 1)
        steps = s.goal_steps(goals[0]['TaskId'])
        self.assertGreaterEqual(len(steps), 4); self.assertTrue(any(x['child'] for x in steps))
```

Run: `python -m pytest tests/test_goals_rail.py -k demo -q` → FAIL (no goal in the seed).

- [ ] **Step 2: Seed it**

In `taskuary/demo.py`, after `refs['gl'] = gl` (`:337`):

```python
    # ONE GOAL (spec 2026-10-12): an outcome with a date, its steps tasks of their own - one done by the coder, one waiting on
    # a person, the rest not started. Dana's census migration, like the owner's.
    g = f.task(title='Migrate the census export off the old portal', status='open', kind='task',
               DoneWhen='the nightly census lands in the new ledger for all three sites, and the old portal\'s export is switched off',
               DueAt=(datetime.now() + timedelta(days=45)).strftime('%Y-%m-%d'))
    store.set_task_checklist(g, ['Inventory the fields the old export carries', 'Map them onto the ledger schema',
                                 'Ray: schema sign-off', 'Export job on the new schema', 'Tell the sites the cutover date'], 'owner')
    from .store import checklist_id
    done = f.task(title='Inventory the fields the old export carries', status='done', kind='general', ParentId=g)
    store.link_step(g, checklist_id('Inventory the fields the old export carries'), done, 'owner')
    waiting = f.task(title='Ray: schema sign-off', status='waiting', kind='task', ParentId=g, Assignee='person:ray@northwind.example',
                     DueAt=(datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d'))
    store.link_step(g, checklist_id('Ray: schema sign-off'), waiting, 'owner')
    refs['goal'] = g
```

Add `from datetime import datetime, timedelta` to the module imports if missing. (`Factory.task` passes `**kw` straight into `create_task`, so `DoneWhen`, `DueAt`, `ParentId`, `Assignee` ride through.)

- [ ] **Step 3: The docs**

`docs/site/tasks-and-agents.md`, in the rail table (`:252-258`), add a row after **On you**:

```markdown
| **Goals** | A goal - an outcome with a date whose steps are tasks - while it has news: it slipped, a step finished, somebody it is waiting on is late. One row per goal; its steps fold into the row ("3 of 7 · coder on step 5 · Ray owes step 4") unless one is your move, which is a row of its own under On you | For later while it is quiet, with its date in the time column; never gone until it is done |
```

Under `## The work rail`, after the second table, add a short section:

```markdown
### Goals

**+ New → Set a goal** asks three things: what done looks like, by when, who is involved. Plan it and the AI proposes the
steps; Track it and you type them. Each step is a box on the goal; **Start** on a box makes it a task of its own (the
goal's child), and when that task closes the box ticks itself. A promise you made in your own mail ("I'll send it
Friday") is a goal's smaller cousin: it becomes a task on you with its day, so the Advisor stops raising it as a line.
```

`docs/site/how-it-works.md:16`: in the list of headings, add "Goals" after "On you" (match the sentence's existing shape).

`README.md:41-42`: add **Goals** to the bold list between **On you** and **For later**.

Then `cd website && npm exec --yes --package=node@22 -- npm run build:docs`.

- [ ] **Step 4: The walk**

`taskuary/walk.py`, in the Tasks stop's `_can` list (`:106-118`), add:

```python
            _can('set a goal with a date and let the AI plan its steps', 'Tasks'),
```

- [ ] **Step 5: Run the gates**

Run: `python -m pytest tests/test_goals_rail.py tests/test_demo.py tests/test_walk.py -q` (`test_walk.py` if it exists), then the full suite `python -m pytest -q` from the repo root.
Expected: all pass except the known `test_deps` case.

- [ ] **Step 6: Commit and push**

```bash
git add taskuary/demo.py docs/site/tasks-and-agents.md docs/site/how-it-works.md README.md taskuary/walk.py website/docs-dist
git commit -m "The demo world has a goal; the docs, the README and the walk say what one is

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git fetch origin && git rebase origin/master && git push origin master
```

(`website/docs-dist` stands for whatever `build:docs` writes; add the paths `git status` shows.)

---

## Self-review

**Spec coverage (build step 1):** `DueAt`/`DoneWhen` (Task 1, 5, 6); a box pointing at a task and ticking on close (Task 1); a person as assignee (Task 1 stores it; Task 4 reads `person:` for "owes"; the UI's `assigneeLabel` splits on the colon already); promises as tasks (Task 2, owner's promises only, the asks-them half deferred to step 4 and said so); the Goals and Later rules and the fold (Task 3, 4); the fourth tab (Task 6); the goal card with its opening steps (Task 6, as a steps list with Start; the per-step receipts and the stuck line the spec draws need the outcome ledger and the Advisor, steps 2 and 3). Not in this plan, by the spec's own build order: triage's goal kind, "which step does this serve", chat's "make this a goal", the pill in the prompt box.

**Placeholders:** none; every code step shows the code. Two steps tell the implementer to confirm a name with `grep` before relying on it (the store's message/task listing names in Task 2, the page's imports in Task 6), because the explorer did not read those lines.

**Type consistency:** `goal_steps` returns `{id, text, done, tid, child}` in Task 1 and the endpoint in Task 5 pops `child` and adds `ref, status, who, state`; `GoalSteps` in Task 6 reads exactly those. `link_step(tid, item_id, child_tid, actor)` is called with that order in Tasks 1, 4, 5, 7. `is_goal` is a module-level function in `taskuary/store.py` and imported as such everywhere.

**Review Focus:** each of the five lines names its test and task above.
