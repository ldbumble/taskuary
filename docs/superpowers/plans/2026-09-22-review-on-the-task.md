# Review Happens On The Task — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fold the Review tab into the task page — every decision (drafted reply, proposed playbook or action) is made on the task that owns it — and retire the tab.

**Architecture:** The decision block is extracted from `ReviewView.jsx` into a `ReviewDecision.jsx` that stage 3 of the task page mounts; `ReviewView.jsx` is deleted rather than kept as a second caller. Every review gets a task at `store.add_review` so nothing is stranded. The Tasks rail stops inventing state words and reads the lane `funnel.py` already assigns, via `lanes.json`.

**Tech Stack:** React 18 + MUI (Vite, JSX), FastAPI + SQLite (Python), `node --test` for JS, pytest for Python.

**Spec:** `docs/superpowers/specs/2026-09-22-review-on-the-task-design.md`

## Global Constraints

- **`lanes.json` is not edited.** It is THE vocabulary; four surfaces build their tables from it.
- **`taskFilter.js` imports nothing.** `stateOf` and `asUtc` live in `ui.jsx`, which is JSX; `node --test` cannot parse it. New predicates there take plain values.
- **`/api/reviews` and the `review` table keep their names.** Internal; renaming churns ~80 correct test references.
- **Copy rule:** "in Review" → "on the task". The capital-R place disappears; lowercase review survives as the act.
- **Never run an autoformatter** on this code — the repo is deliberately dense.
- Style: Jeremy Howard / fast.ai density, matching the surrounding file.
- **Gates before any push:** full `pytest` from the repo root (a "no tests ran" is a failure), `npm test`, `npm run lint:undef`, and a bundle rebuild — esbuild syntax-checks JSX that pytest never loads.
- **Commit via a temp index.** Concurrent agents share one git index in this checkout.

---

### Task 1: The today-cut moves from the pill to the row (spec §6)

Independent of everything else. Lands first — it is the bug currently on screen.

**Files:**
- Modify: `website/src/taskFilter.js` (add `cutAway`)
- Modify: `website/src/TasksView.jsx:504-514` (`bucket` / `cut` / `shown` / `countIn`)
- Test: `website/test/taskFilter.test.mjs`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `cutAway(stateKey: string, touchedToday: boolean, older: boolean) => boolean` — true when the row should be hidden behind "show older". Plain values only, no imports.

- [ ] **Step 1: Write the failing test**

```js
// website/test/taskFilter.test.mjs — append
import { cutAway } from "../src/taskFilter.js";

test("live work shows at any age; finished work stops at today", () => {
  assert.equal(cutAway("needs_you", false, false), false);   // live, last touched yesterday - still live
  assert.equal(cutAway("working",   false, false), false);
  assert.equal(cutAway("queued",    false, false), false);
  assert.equal(cutAway("done",      false, false), true);    // finished and not today - behind "show older"
  assert.equal(cutAway("dropped",   false, false), true);
  assert.equal(cutAway("done",      true,  false), false);   // finished today - shown
});

test("show older lifts the cut off everything", () => {
  assert.equal(cutAway("done",    false, true), false);
  assert.equal(cutAway("dropped", false, true), false);
});

// the defect this fixes: all(5) under in-progress(4) + done(2). A live row untouched today
// counted for the in-progress pill and not for all, so `all` was not a superset of its parts.
test("all is a superset of its own buckets", () => {
  const rows = [
    { key: "needs_you", today: false },   // TQ-0667 - waiting, 2026-09-21 23:30
    { key: "needs_you", today: false },   // TQ-0664 - waiting, 2026-09-21 23:27
    { key: "needs_you", today: true },
    { key: "done",      today: true },
    { key: "done",      today: false },   // yesterday's - behind "show older" in every bucket
  ];
  const shown = (pred) => rows.filter((r) => !cutAway(r.key, r.today, false)).filter(pred).length;
  const all  = shown(() => true);
  const live = shown((r) => !["done", "dropped"].includes(r.key));
  const done = shown((r) => r.key === "done");
  assert.equal(live, 3);
  assert.equal(done, 1);
  assert.equal(all, live + done);      // 4 - the arithmetic closes
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd website && npm test`
Expected: FAIL — `cutAway is not a function` / `SyntaxError: The requested module does not provide an export named 'cutAway'`.

- [ ] **Step 3: Add the predicate**

```js
// website/src/taskFilter.js — append
// The cut is about HISTORY, not about which pill you are on. Live work has no age - it is live
// whether it arrived this morning or last night - so cutting it per pill made `in progress` count
// a wider window than `all`, and "all 5" sat under "in progress 4 · done 2" (2026-09-22).
export const cutAway = (stateKey, touchedToday, older) =>
  !older && ["done", "dropped"].includes(stateKey) && !touchedToday;
```

- [ ] **Step 4: Run it and watch it pass**

Run: `cd website && npm test`
Expected: PASS, and every pre-existing `taskFilter.test.mjs` test still passes.

- [ ] **Step 5: Use it in both places that were disagreeing**

`TasksView.jsx`, replacing the `cut` / `shown` / `countIn` block at 504-514. Both the list and
the pills now apply the same per-row predicate, so a pill cannot count a window its list does not show.

```jsx
  const bucket = (tasks || []).filter((x) => search ? taskMatchesQuery(x, search) : (!filter || inBucket(x, filter)));
  const keep = (x) => search || !cutAway(stateOf(x).key, touchedToday(x), older);
  const shown = bucket.filter(keep);
  const nOlder = bucket.length - shown.length;
  // Each pill counts what clicking it would SHOW - the same rows, by the same rule. A count that
  // outruns the rows beneath it reads as a bug, and one that undercounts its own parts is one.
  const countIn = (key) => (tasks || []).filter((x) => (!key || inBucket(x, key)) && keep(x)).length;
```

Add `cutAway` to the existing `./taskFilter.js` import at the top of the file.

- [ ] **Step 6: Verify the gates**

Run: `cd website && npm test && npm run lint:undef`
Expected: PASS. Then rebuild the bundle and confirm the pills add up in the running app: `all` must equal `in progress` + `done` whenever nothing is dropped.

- [ ] **Step 7: Commit**

```bash
git add website/src/taskFilter.js website/src/TasksView.jsx website/test/taskFilter.test.mjs
git commit -m "fix: the today-cut belongs to the row, not to the pill you are standing on"
```

---

### Task 2: Every review has a task (spec §3)

Backend, independent of the UI work. Must land before Task 6 deletes the tab, or the three
task-less paths lose their only surface.

**Files:**
- Modify: `taskuary/store.py:3501` (`add_review`)
- Modify: `taskuary/concierge.py:1560`, `taskuary/invoice_workflow.py:175`, `taskuary/reports.py:2140`
- Modify: `taskuary/store.py` schema/migration block
- Test: `tests/test_review_task.py` (new)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `store.add_review(fields)` guarantees a non-null `TaskId` on the returned row. Callers may pass `_task_title: str` and `_task_kind: str` (stripped before the INSERT) to name the task they cause.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_review_task.py
def test_a_review_with_no_task_gets_one(store):
    rid = store.add_review({'Kind': 'action', 'Status': 'pending', 'DraftText': '{"action":"settings"}',
                            '_task_title': 'Setting · where general work runs'})
    rv = store.get_review(rid)
    assert rv['TaskId'], 'a review with nowhere to be decided is a review nobody can answer'
    assert store.get_task(rv['TaskId'])['Title'] == 'Setting · where general work runs'

def test_a_review_that_names_its_task_is_left_alone(store):
    tid = store.add_task({'Title': 'already mine'})
    rid = store.add_review({'TaskId': tid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'hi'})
    assert store.get_review(rid)['TaskId'] == tid
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m pytest tests/test_review_task.py -v`
Expected: FAIL — `assert None` on `rv['TaskId']`.

- [ ] **Step 3: Make `add_review` the chokepoint**

One place, so no call site added later can strand a decision by forgetting.

```python
    def add_review(self, fields):
        # A review IS the ask for a decision, and every decision is made on a task. Three callers
        # used to file one with no task (a setting proposed in chat, an invoice, a report) and the
        # Review tab was the only place they could be answered - so the tab could not be retired
        # until this was true (2026-09-22).
        f = dict(fields)
        title, kind = f.pop('_task_title', None), f.pop('_task_kind', None)
        if not f.get('TaskId'):
            f['TaskId'] = self.add_task({'Title': title or (f.get('Reason') or 'Waiting on you')[:140],
                                         'Kind': kind or 'task', 'Status': 'open', 'Source': 'review'})
        ...existing insert, using f...
```

- [ ] **Step 4: Run it and watch it pass**

Run: `python -m pytest tests/test_review_task.py -v`
Expected: PASS.

- [ ] **Step 5: Let the three callers name their own task**

Generic titles would be whatever those callers wrote for a different purpose. Each passes its own words:

```python
# concierge.py:1560 - propose_switch
rid = store.add_review({'Kind': 'action', 'Status': 'pending', 'DraftText': json.dumps(p),
                        'Reason': f'you asked for this setting: {says}',
                        '_task_title': f'Setting · {says}'[:140], '_task_kind': 'task'})

# invoice_workflow.py:175
rid = store.add_review({'MessageId': mid, 'Kind': 'outbound', 'Status': 'pending', 'DraftText': body,
                        'Reason': ...,  # unchanged
                        '_task_title': f"Invoice · {item['CustomerName']} · {batch['Period']}"[:140],
                        '_task_kind': 'task', 'Deliver': json.dumps(deliver)})

# reports.py:2140
store.add_review({'MessageId': mid, 'Kind': 'outbound', 'Status': 'pending', 'DraftText': body,
                  'Reason': f'{cfg.get("title") or "report"} → {who}. Approve to send it.',
                  '_task_title': f'Report · {cfg.get("title") or "report"} → {who}'[:140],
                  '_task_kind': 'task', 'Deliver': json.dumps({...})})
```

- [ ] **Step 6: Backfill the rows already in live databases**

A migration in the schema block, guarded so it runs once and cannot run on an empty table:

```python
# a review with no task predates the rule in add_review; without one it has no surface at all
# once the Review tab is gone
for rv in self.cx.execute("SELECT ReviewId, Reason FROM review WHERE TaskId IS NULL").fetchall():
    tid = self.add_task({'Title': (rv['Reason'] or 'Waiting on you')[:140], 'Kind': 'task',
                         'Status': 'open', 'Source': 'review'})
    self.cx.execute('UPDATE review SET TaskId=? WHERE ReviewId=?', (tid, rv['ReviewId']))
```

Add a test that the migration leaves zero `TaskId IS NULL` rows behind.

- [ ] **Step 7: Run the full Python suite**

Run: `python -m pytest` from the repo root.
Expected: PASS. "No tests ran" is a failure.

- [ ] **Step 8: Commit**

```bash
git add taskuary/store.py taskuary/concierge.py taskuary/invoice_workflow.py taskuary/reports.py tests/test_review_task.py
git commit -m "fix: a review with nowhere to be decided is one nobody can answer"
```

---

### Task 3: The rail reads the lane (spec §2)

**Files:**
- Modify: `taskuary/server.py` (`/api/tasks` returns the row's lane)
- Modify: `website/src/ui.jsx:997-1032` (`TASK_STATES`, `stateOf`, `StateChip`)
- Test: `website/test/funnelPile.test.mjs`, `tests/test_server.py`

**Interfaces:**
- Consumes: `cutAway` from Task 1 (`stateOf(x).key` must keep returning `done`/`dropped`).
- Produces: task rows carry `Lane: string|null`; `StateChip` renders `rowMeta(lane).word` + `.mark` when a lane is present.

- [ ] **Step 1: Write the failing test**

```js
// website/test/funnelPile.test.mjs — append
import { rowMeta } from "../src/funnelPile.js";

test("the rail's words are the Work rail's words", () => {
  assert.equal(rowMeta({ lane: "approve" }).word, "reply ready");
  assert.equal(rowMeta({ lane: "blocked" }).word, "agent waving");
  // the defect: both of these wore the same red "needs you" chip on the Tasks rail
  assert.notEqual(rowMeta({ lane: "approve" }).word, rowMeta({ lane: "blocked" }).word);
});
```

- [ ] **Step 2: Run it and watch it pass or fail**

Run: `cd website && npm test`
Expected: PASS already — `rowMeta` exists. This test is the *guard*: it pins the two words apart so a later edit cannot re-merge them. Keep it.

- [ ] **Step 3: Return the lane from the server**

`/api/tasks` joins the lane `funnel.py` already assigns. **Do not derive a second one client-side** — two derivations drift, and this whole task exists because they did.

- [ ] **Step 4: Replace only the fall-through**

`lanes.json` names live work and has no word for done or dropped, so those rungs stay:

```js
export const stateOf = (t) => {
  if (!t) return ST.queued;
  if (t.Status === "dropped") return ST.dropped;
  if (t.Status === "done")    return ST.done;
  return t.Lane ? laneState(t.Lane) : (busyNow(t) ? ST.working : ST.needs_you);
};
```

`laneState(lane)` builds a `TASK_STATES`-shaped object from `rowMeta(lane)`, keeping `.key`
(so `cutAway` and `inBucket` are unaffected) and taking `.label` from the lane's word.

- [ ] **Step 5: Run the gates and commit**

Run: `cd website && npm test && npm run lint:undef`, then `python -m pytest`.

```bash
git commit -m "fix: the Tasks rail says what the Work rail says, from the one vocabulary"
```

---

### Task 4: Extract the decision (spec §1, part one)

No behaviour change. Pure extraction, so a regression here is visible as a diff rather than a mystery.

**Files:**
- Create: `website/src/ReviewDecision.jsx`
- Modify: `website/src/ReviewView.jsx` (mounts the extracted component; deleted in Task 6)

**Interfaces:**
- Produces: `<ReviewDecision review={rv} onChanged={fn} onOpenTask={fn} />` — renders the inbound message, editable draft, TO/CC/attachments, the verdict buttons, the stale warning and its Refresh road, the held panel with *Answer now anyway*, the approval-interrupt compare, and the send-failed alert. Proposals render through `proposalPresentation()`.

- [ ] **Step 1: Move the per-review body out of `ReviewView.jsx` verbatim**

Everything inside `rows.map((r) => ...)` becomes the component. `decide`, `release`, `redraft`,
`edits`, `cc`, `interrupt`, `compare`, `sendErr` move with it — they are per-review state that
only looked like list state because the list owned them.

- [ ] **Step 2: `ReviewView` maps over `<ReviewDecision>`**

The filter pills and loading stay in `ReviewView`.

- [ ] **Step 3: Verify nothing changed**

Run: `cd website && npm test && npm run lint:undef`, rebuild the bundle, and walk the Review tab:
approve, no-reply, reject, redraft, a stale draft, a held draft, a playbook proposal.

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor: the decision is a component, not a row in one tab's list"
```

---

### Task 5: Stage 3 decides, and holds proposals too (spec §1)

**Files:**
- Modify: `website/src/TasksView.jsx` (stage 3)
- Modify: `website/src/taskLifecycle.js` (`focusStage`)
- Test: `website/test/taskLifecycle.test.mjs`

**Interfaces:**
- Consumes: `<ReviewDecision>` from Task 4.
- Produces: `focusStage` returns `"reply"` for a pending `Kind:"action"` review; `pendingProposals(reviews)` returns pending action reviews, newest last.

- [ ] **Step 1: Write the failing tests**

```js
// website/test/taskLifecycle.test.mjs — append. Every existing focusStage assertion must still pass.
test("a proposal waiting on you opens the stage, sender or no sender", () => {
  const p = { kind: "coding", task: "open", agent: "not started", reply: "not drafted",
              hasSender: false, proposal: true };
  assert.equal(focusStage(p), "reply");                       // a playbook has no sender and still needs a yes
  assert.equal(focusStage({ ...p, proposal: false }), "task");
});

test("proposals are not the reply, and the reply is not a proposal", () => {
  const reviews = [{ ReviewId: 2, Kind: "action", Status: "pending" },
                   { ReviewId: 1, Kind: "draft",  Status: "pending" }];
  assert.equal(pendingReplyReview(reviews).ReviewId, 1);
  assert.deepEqual(pendingProposals(reviews).map((r) => r.ReviewId), [2]);
});
```

- [ ] **Step 2: Run and watch fail**

Run: `cd website && npm test`
Expected: FAIL — `pendingProposals is not a function`.

- [ ] **Step 3: Implement**

```js
export const pendingProposals = (reviews = []) =>
  (reviews || []).filter((r) => r.Kind === "action" && r.Status === "pending").reverse();
```

`focusStage` gains `proposal` as its first rung, beside `reply === "draft ready"`.

- [ ] **Step 4: Mount it in stage 3**

The reply first, proposals beneath — sending is what settles the task. The stage renders on a
pending review, **not** on `sourceMessage`: a settings proposal from chat and a playbook after a
coding job both have no sender and still need a yes, so the "No inbound sender is attached"
empty state only shows when there is genuinely nothing waiting.

- [ ] **Step 5: Run the gates and commit**

```bash
git commit -m "feat: the task page decides - the reply and the proposal both wait on it"
```

---

### Task 6: Retire the tab (spec §4, §5, §8)

**Files:**
- Delete: `website/src/ReviewView.jsx`
- Modify: `website/src/TaskHubPage.jsx`, `FloatingAssistant.jsx`, `GeneralWorkspace.jsx`, `TasksView.jsx`
- Modify: `website/src/SettingsView.jsx:816`, `settingsMap.js`
- Modify: ~100 strings across `taskuary/`, `website/src/`, `docs/`

- [ ] **Step 1: Drop `Review` from `TABS`; move the badge to `Tasks`**

Counting **tasks, not reviews** — deduplicated by `TaskId`. A task holding a reply *and* a
playbook is one thing waiting on you, and `Tasks · 5` over four rows is the same lie Task 1 fixed.

- [ ] **Step 2: Remove `onGoReview`** — the prop, its three call sites in `TasksView`, and
  `TaskHubPage:450`. Every one of them says "go elsewhere to do this", which is now false.

- [ ] **Step 3: Docs into Settings**

`NAV` becomes `["about", "docs", "config", "policies", "memory", "audit", "updates"]`, with
`PAGES.docs` carrying title, icon and description. `DocsView` renders unchanged and keeps
reading its own hash.

**The deep links must follow it:** `TaskHubPage` routes `#playbook=` and `#profiles` to
`go("Docs")` — they become `go("Settings")` with the docs entry selected, or every connector
card's playbook link lands on a tab that no longer exists.

- [ ] **Step 4: The copy sweep**

`grep -rn "in Review\|to Review\|Review tab" taskuary/ website/src/ docs/`. Each becomes "on the
task". Agents read some of these aloud during connector setup, so they must read as instructions
to a person, not as a room name.

- [ ] **Step 5: Verify nothing still points at the tab**

Run: `grep -rn '"Review"' website/src/ | grep -v node_modules` — expect no nav or routing hits.
Run: `cd website && npm test && npm run lint:undef`, `python -m pytest`, rebuild the bundle.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat: review happens on the task - the tab, and the word for the place, retire"
```

---

### Task 7: The two surfaces agree on which stage opens (spec §7)

**Files:**
- Modify: `website/src/funnelPile.js` (`assistantFocus`)
- Modify: `website/src/taskLifecycle.js` (`focusStage`)
- Test: `website/test/assistantFocus.test.mjs`, `website/test/taskLifecycle.test.mjs`

**Interfaces:**
- Consumes: `pendingProposals` from Task 5.
- Produces: both functions honour the same exception. Asserted on both sides, so the lockstep
  `funnelPile.js:218` claims is enforced rather than hoped for.

- [ ] **Step 1: Write the failing tests, on both sides**

```js
// assistantFocus.test.mjs
test("an agent blocked on approval opens the thing it is waiting for", () => {
  const f = assistantFocus(item({ kind: "agent", lane: "blocked", sub: "approval", rid: 9, agent: "codex" }));
  assert.equal(f.card, "reply");                      // approving the proposal is what releases it
  assert.match(f.lead, /runs only if you say so/);
});

test("an agent blocked on a question is still the agent card", () => {
  const f = assistantFocus(item({ kind: "agent", lane: "blocked", sub: "asking", agent: "codex" }));
  assert.equal(f.card, "agent");
});
```

```js
// taskLifecycle.test.mjs
test("a waving agent outranks a proposal, unless the proposal is what it wants", () => {
  const base = { kind: "coding", task: "open", agent: "needs you", reply: "not drafted", proposal: true };
  assert.equal(focusStage({ ...base, agentSub: "asking" }),   "agent");
  assert.equal(focusStage({ ...base, agentSub: "approval" }), "reply");
});
```

- [ ] **Step 2: Run and watch fail.** Run: `cd website && npm test`

- [ ] **Step 3: Implement the exception in both**, with the same comment in both places naming
  the other, so the next reader finds its twin.

- [ ] **Step 4: Run the gates and commit**

```bash
git commit -m "fix: the proposal an agent is parked on is what opens, on both surfaces"
```

---

### Task 8: Ship it

- [ ] **Step 1: Full suite from the repo root**

Run: `python -m pytest` — a "no tests ran" is a failure.
Run: `cd website && npm test && npm run lint:undef`.

- [ ] **Step 2: Rebuild the committed bundle** — esbuild syntax-checks JSX that pytest never loads.

- [ ] **Step 3: Walk it in the running app**

A task with a drafted reply; a task with a playbook proposal and no sender; a task with both;
a task with a waving agent; the pill counts adding up; the Tasks badge; Docs under Settings;
a connector card's playbook deep link.

- [ ] **Step 4: Commit and push.**

---

## Self-review

**Spec coverage:** §1 → Tasks 4, 5. §2 → Task 3. §3 → Task 2. §4 → Task 6 step 4. §5 → Task 6 step 3. §6 → Task 1. §7 → Task 7. §8 → Task 6 step 1. No section unclaimed.

**Ordering:** Task 1 is independent and lands first. Task 2 must precede Task 6 or the three
task-less paths lose their surface when the tab goes. Task 4 must precede Task 5. Task 5 must
precede Task 7 (`pendingProposals`). Task 3 is independent of the rest but must keep
`stateOf(t).key` returning `done`/`dropped` for Task 1's `cutAway`.

**Type consistency:** `cutAway(stateKey, touchedToday, older)` is called with the same argument
order in Task 1 step 5. `pendingProposals(reviews)` is defined in Task 5 and consumed in Task 7.
`rowMeta({lane})` matches the existing `funnelPile.js` export.
