# Triage names the step, triage's goal kind, work facts into playbooks (build step 5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A mail on another thread that serves a goal's step is attached under that step by triage (and may tick it); triage opens a goal, not a task, for the open-ended ask, with no steps, and the planner proposes them; what the ledger counts about a kind of work reaches its playbook as a proposal for the owner's yes.

**Architecture:** Triage's prompt gains the open goals with their steps (`context.open_goals`), the verdict gains `serves {task, step, done}` validated against what was shown, and ingest attaches the mail to the step's child task or the goal and stores the step on the route's verdict; the goal page reads arrivals per step from the route rows. Triage's verdict gains `goal` + `done_when`; ingest creates a goal (DoneWhen, DueAt, Tags goal, no checklist) and hands it to the existing planner; the kind memory learns `goal` on the same door as any kind. `outcomes.work_facts(slug)` counts closes, reopens and "closed with an open question" per playbook; `playbook_facts.py` compiles facts at reflection and files an `amend_playbook` proposal (a task-less review) that `playbooks.write` carries out on approval.

**Tech Stack:** Python 3.12 / SQLite / FastAPI, pytest; React for the goal page's step rows.

**Spec:** `docs/superpowers/specs/2026-10-12-goals-outcomes-advisor-design.md`: "Goals are tasks" ("Where a goal comes from", "Which step does this serve"), "The outcome ledger" (facts about kinds of work), build step 5.

## Global Constraints

- Public repo: stand-ins only (northwind.example, Alex Doyle, Gail Moreno, Ray Colton, Payworth).
- Concise fast.ai style matching the file; `website/src` stays LF.
- Always the model, never a word match: which step a mail serves, whether it completes it, whether an ask is a goal - all the model's answer, validated by code against what it was shown; what a work fact MEANS is the model's at reflection, the numbers are the ledger's.
- A derived line never acts on its own: playbook facts are a proposal for the owner's yes; a step ticks itself only on the model's `done` and only when nobody holds it.
- The triage prompt stays small: at most 5 open goals × 12 steps, titles only.
- Push only after the full pytest suite from the repo root plus `cd website && npm test && npm run build`; a `docs/site` edit needs `npm run build:docs`; `python -m taskuary.toolcatalog` regenerates the tools page when DECISIONS or operations change.
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Review Focus

1. **A mail that serves a step whose child task is held by an agent**: it attaches to the child, never ticks the box, and the agent's task gets the arrival. Pinned in Task 1 (`test_a_held_step_gets_the_mail_and_keeps_its_box`).
2. **The model names a step that was not shown** (a hallucinated id): the verdict's `serves` is dropped, the mail routes as it would have. Pinned in Task 1 (`test_a_step_not_shown_is_ignored`).
3. **A goal verdict on a plain reply thread** (the model says goal on a two-line question): a goal needs `done_when`; without it the verdict is a task. Pinned in Task 2 (`test_a_goal_without_done_when_is_a_task`).
4. **The owner says "that was a task, not a goal"**: the goal's DoneWhen clears, its steps stay as boxes, and the kind memory learns `task` for that sender/subject on the usual curve. Pinned in Task 2 (`test_not_a_goal_clears_done_when_and_teaches`).
5. **A playbook proposal must never block a live task's close-out**: the review carries no TaskId. Pinned in Task 3 (`test_the_proposal_has_no_task_and_blocks_nothing`).

---

### Task 1: Which step does this serve

**Files:**
- Modify: `taskuary/context.py` (`open_goals`), `taskuary/ingest.py` (the prompt hook after `open_work`; the attach on `serves`), `taskuary/triage.py` (`verdict_schema`: `serves`; `FIELDS` line; validation beside `same_as`), `taskuary/templates/triage.md` (§3 one paragraph, §7 the answer), `taskuary/store.py` (`step_arrivals`), `taskuary/server.py` (`GET /api/tasks/{id}/steps` gains `arrivals`), `website/src/TaskPage.jsx` (`GoalSteps` sub-row)
- Test: `tests/test_goal_serves.py` (new), `website/test/goalArrivals.test.mjs` (new, a source regex)

**Interfaces:**
- Produces: `context.open_goals(store, limit=5) -> list[{tid, ref, title, done_when, steps: [{id, k, text, done, who, tid}]}]` (open tasks with DoneWhen, newest activity first; steps from `store.goal_steps`); thread key `open_goals`; verdict `serves: {task: int, step: str, done: bool} | null` (schema only when goals were shown; validated: `task` in the shown goal tids, `step` one of that goal's step ids); `ingest`: on a valid `serves`, the mail is landed and routed `attach` to the step's child tid when it has one, else to the goal tid, with `verdict['serves']` stored on the route; a box with no child ticks when `done` is true (`store.tick_checklist_item(goal, step, True, 'triage')`); `advisor.notice(store, 'message.attached', 'task', <goal tid>)`; `store.step_arrivals(goal_tid) -> dict[step_id, list[{mid, who, at, subject}]]` (route rows whose `json_extract(VerdictJson, '$.serves.task')` is the goal, by step); `/steps` rows gain `arrivals`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_goal_serves.py
"""Which step does this serve (spec 2026-10-12, build step 5): triage names the goal and the step, the mail lands under it."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock
from taskuary import context, ingest, triage
from taskuary.store import MemoryStore

def ago(days=0, hours=0): return (datetime.now() - timedelta(days=days, hours=hours)).strftime('%Y-%m-%d %H:%M:%S')

def goal(s):
    g = s.create_task({'Title': 'Migrate the census export', 'Kind': 'task', 'Status': 'open', 'DoneWhen': 'the nightly census lands in the new ledger'}, 'owner')
    s.set_task_checklist(g, ['Gail sends the accruals', 'Ray: schema sign-off', 'Export job on the new schema'], 'owner')
    return g, [x['id'] for x in s.goal_steps(g)]

def mail(s, who='gail@northwind.example', subject='Accruals for September'):
    return {'external_id': f'm-{subject}', 'channel': 'email', 'from_email': who, 'from_name': 'Gail Moreno', 'subject': subject,
            'body_text': 'Attached, as promised.', 'conversation_id': f'c-{subject}', 'sent_at': ago(hours=1)}

def brain(answer):
    def llm(system, user, max_tokens=400, images=None, want=None, **kw): llm.seen = user; return json.dumps(answer)
    llm.takes_want = False; return llm


class ServesTests(unittest.TestCase):
    def test_open_goals_carry_their_steps_for_the_prompt(self):
        s = MemoryStore(); g, ids = goal(s)
        og = context.open_goals(s)
        self.assertEqual((og[0]['tid'], og[0]['done_when'][:11], [x['text'] for x in og[0]['steps']][:1]), (g, 'the nightly', ['Gail sends the accruals']))

    def test_a_mail_that_serves_a_step_lands_under_it_and_may_tick_it(self):
        s = MemoryStore(); g, ids = goal(s)
        v = {'intent': 'fyi', 'kind': None, 'why': 'the accruals the goal waits on', 'title': 'Accruals', 'summary': 'x', 'checklist': None, 'urgent': False,
             'due': None, 'sender_class': 'person', 'outputs': None, 'serves': {'task': g, 'step': ids[0], 'done': True}}
        out = ingest.ingest_message(s, mail(s), 'test', brain(v))
        self.assertEqual(out['task_id'], g); self.assertIn('OPEN GOALS', brain(v).seen if hasattr(brain(v), 'seen') else 'OPEN GOALS')
        self.assertTrue(s.goal_steps(g)[0]['done'])
        self.assertEqual(list(s.step_arrivals(g)), [ids[0]])
        self.assertEqual(s.step_arrivals(g)[ids[0]][0]['who'], 'Gail Moreno')

    def test_a_held_step_gets_the_mail_and_keeps_its_box(self):
        s = MemoryStore(); g, ids = goal(s)
        c = s.create_task({'Title': 'Ray: schema sign-off', 'Status': 'waiting', 'Assignee': 'agent:coder', 'ParentId': g}, 'owner'); s.link_step(g, ids[1], c, 'owner')
        v = {'intent': 'fyi', 'kind': None, 'why': 'x', 'title': 'Schema', 'summary': 'x', 'checklist': None, 'urgent': False, 'due': None,
             'sender_class': 'person', 'outputs': None, 'serves': {'task': g, 'step': ids[1], 'done': True}}
        out = ingest.ingest_message(s, mail(s, 'ray@northwind.example', 'Schema v2'), 'test', brain(v))
        self.assertEqual(out['task_id'], c); self.assertFalse(s.goal_steps(g)[1]['done'])

    def test_a_step_not_shown_is_ignored(self):
        s = MemoryStore(); g, ids = goal(s)
        v = {'intent': 'task', 'kind': 'task', 'why': 'x', 'title': 'Other', 'summary': 'x', 'checklist': None, 'urgent': False, 'due': None,
             'sender_class': 'person', 'outputs': None, 'serves': {'task': g, 'step': 'nope', 'done': True}}
        out = ingest.ingest_message(s, mail(s, 'omar@northwind.example', 'Something else'), 'test', brain(v))
        self.assertNotEqual(out['task_id'], g); self.assertEqual(s.step_arrivals(g), {})
```

(`ingest.ingest_message(store, msg, actor, llm, file_only=False)` is at `ingest.py:589`; read how `tests/test_ingest_*.py` or `tests/test_triage*.py` build a minimal `msg` and a fake brain - `grep -rn "def brain\|ingest_message(" tests/*.py | head` - and copy that shape if it differs. The seen-prompt assertion is simpler as `self.assertIn('OPEN GOALS', llm.seen)` with one `llm = brain(v)`.)

- [ ] **Step 2: Run** `python -m pytest tests/test_goal_serves.py -q` → FAIL (`open_goals` missing).

- [ ] **Step 3: Implement**

`taskuary/context.py`:
```python
def open_goals(store, limit: int = 5) -> list:
    """The open GOALS with their steps, titles only, for triage's "which step does this serve" (spec 2026-10-12)."""
    from .store import is_goal
    from .processing_unread import holder_name
    gs = [t for t in store.list_tasks(active_only=True) if is_goal(t)][:limit]
    out = []
    for t in gs:
        steps = [{'id': x['id'], 'k': k + 1, 'text': x['text'][:120], 'done': bool(x.get('done')), 'tid': x.get('tid'),
                  'who': holder_name((x.get('child') or {}).get('Assignee'))} for k, x in enumerate(store.goal_steps(t['TaskId']))][:12]
        out.append({'tid': t['TaskId'], 'ref': task_ref(t['TaskId']), 'title': t.get('Title') or '', 'done_when': str(t.get('DoneWhen') or '')[:200], 'steps': steps})
    return out
```
`taskuary/ingest.py`, after `still = taskcontext.recent_open(store, msg)` … : `goals = taskcontext.open_goals(store)` and `if goals: thread = {**thread, 'open_goals': goals}`. `taskuary/triage.py`: `FIELDS['open_goals'] = "open_goals is the OPEN GOALS and their steps: when this message serves one step (it delivers it, answers it, or is about it), answer serves {task, step, done} - done true only when the message completes that step."`; `verdict_schema(..., goals=False)` adds `serves: {'type': ['object','null'], 'additionalProperties': False, 'required': ['task','step','done'], 'properties': {'task': {'type': 'integer'}, 'step': {'type': 'string'}, 'done': {'type': 'boolean'}}}` when `goals`; at the call site pass `goals=bool(goal_steps)` where `goal_steps = {int(g['tid']): {x['id'] for x in g['steps']} for g in (thread or {}).get('open_goals') or []}`; validation beside `same_as`: `sv = j.get('serves'); if isinstance(sv, dict) and sv.get('task') in goal_steps and sv.get('step') in goal_steps[sv['task']]: out['serves'] = {'task': int(sv['task']), 'step': str(sv['step']), 'done': bool(sv.get('done'))}`. `templates/triage.md` §3 gains a paragraph: "When `open_goals` is given, say which step this message serves with `serves` - the step it delivers, answers or is plainly about - and `done: true` only when the message completes it. A message that serves no step answers null." and §7 lists `serves`.

`taskuary/ingest.py`, in the routed path right after `same = intent.get('same_as')` (before `_join_same`): 
```python
    sv = intent.get('serves')
    if sv and store.get_task(sv['task']):
        # WHICH STEP DOES THIS SERVE (spec 2026-10-12): under the step's own task when somebody holds it, else under the goal; a box
        # nobody holds ticks on the model's `done`. The arrival is news on the goal (processing_unread.goal_facts reads routes).
        step = next((x for x in store.goal_steps(sv['task']) if x['id'] == sv['step']), None)
        tid = (step or {}).get('tid') or sv['task']
        mid = _land(store, msg, tid, 'filed' if intent.get('intent') == 'fyi' else 'routed')
        store.add_route(mid, tid, 'attach', 1.0, f"triage: serves step {sv['step']} of {task_ref(sv['task'])}", [], 'triage', verdict=_stored_verdict(intent))
        store.add_comment(tid, 'triage', 'agent', f"{msg.get('from_name') or msg.get('from_email')} sent \"{msg.get('subject')}\" - it serves step {sv['step']}")
        if sv.get('done') and step and not step.get('tid'): store.tick_checklist_item(sv['task'], sv['step'], True, 'triage')
        from . import advisor
        advisor.notice(store, 'message.attached', 'task', sv['task'])
        return {'status': 'attached', 'task_id': tid, 'message_id': mid}
```
(`_land` and `_stored_verdict` are the file's own helpers - read their signatures: `grep -n "^def _land\|^def _stored_verdict" taskuary/ingest.py`; `_stored_verdict` must keep `serves` in the JSON it stores - read it.)

`taskuary/store.py`:
```python
    def step_arrivals(self, goal_tid: int) -> dict:
        """Mail that served a goal's steps, by step id - the route rows triage wrote with `serves` (spec 2026-10-12)."""
        rows = self._rows("SELECT r.MessageId mid, json_extract(r.VerdictJson, '$.serves.step') step, m.FromName who, m.FromEmail em, m.SentAt at, m.Subject subject "
                          "FROM route r JOIN message m ON m.MessageId=r.MessageId WHERE json_extract(r.VerdictJson, '$.serves.task')=? ORDER BY m.SentAt", (int(goal_tid),))
        out = {}
        for r in rows: out.setdefault(r['step'], []).append({'mid': r['mid'], 'who': r['who'] or r['em'] or '', 'at': r['at'], 'subject': r['subject'] or ''})
        return out
```
`server.goal_steps`: `arr = store.step_arrivals(task_id)` and each row gains `'arrivals': arr.get(x['id'], [])`. `TaskPage.jsx` `GoalSteps`: under each step row, `{(s.arrivals || []).map((a) => <Typography key={a.mid} variant="caption" sx={{ color: FAINT, pl: 4.5, display: "block" }}>↳ {a.who} sent "{a.subject}" · {a.at?.slice(0, 16)}</Typography>)}`. `website/test/goalArrivals.test.mjs`: `assert.match(src, /s\.arrivals \|\| \[\]/)` on TaskPage.jsx.

- [ ] **Step 4: Run** `python -m pytest tests/test_goal_serves.py tests/test_goals_store.py tests/test_triage*.py tests/test_ingest*.py -q` (use the file names that exist) and `cd website && npm test && npm run build` → PASS.

- [ ] **Step 5: Commit** `"Triage names which goal step a mail serves; the arrival shows under the step and may tick it"`.

---

### Task 2: Triage's goal kind

**Files:**
- Modify: `taskuary/triage.py` (`verdict_schema`: `goal`, `done_when`; `FIELDS`; validation), `taskuary/templates/triage.md` (§4 a paragraph; §7), `taskuary/ingest.py` (the create path), `taskuary/routingmemory.py` (`lesson` for kind `goal`), `taskuary/server.py` (`task.set_kind` accepts `goal` and `task`-from-goal; teaches kind)
- Test: `tests/test_goal_serves.py` (append)

**Interfaces:**
- Produces: verdict `goal: bool` and `done_when: str|null`; a verdict with `goal` true and a non-empty `done_when` creates the task with `DoneWhen`, `DueAt` from `due`, `Tags` `goal`, no checklist, `Assignee` unset, and schedules the planner (`_read_hand_task(tid, words, goal=True)` through the server's background road - read `server.py:625/660`; from ingest, call `remind`-style: `from . import server` is circular, so ingest calls `store.set_setting`? No: ingest calls the planner directly, `server.plan_goal` lives in server.py - move its body to `goals.plan(store, tid, text)` in a new small module `taskuary/goals.py` and have both `server.plan_goal` and ingest call it (in a daemon thread from ingest, inline with `wait=True` in tests)); routing memory field `kind` accepts the value `goal`; `task.set_kind` with `kind='goal'` sets `DoneWhen` to the task's summary when blank and `Tags` `goal`, with `kind='task'` on a goal clears `DoneWhen` and keeps the boxes, and both teach `kind` through `_teach_routing`.

- [ ] **Step 1: Failing tests**

```python
class GoalKindTests(unittest.TestCase):
    def _v(self, **kw):
        return {'intent': 'task', 'kind': 'general', 'why': 'x', 'title': 'Move the census to the new ledger', 'summary': 'several sites, Gail and Ray', 'checklist': None,
                'urgent': False, 'due': None, 'sender_class': 'person', 'outputs': None, 'goal': True, 'done_when': 'the census lands in the new ledger for all three sites', **kw}

    def test_an_open_ended_ask_becomes_a_goal_with_no_steps_and_the_planner_runs(self):
        s = MemoryStore()
        with mock.patch('taskuary.goals.plan') as plan:
            out = ingest.ingest_message(s, mail(s, subject='Census migration'), 'test', brain(self._v(due='2026-12-01')))
        t = s.get_task(out['task_id'])
        self.assertEqual((t['DoneWhen'][:10], t['DueAt'], t.get('Tags')), ('the census', '2026-12-01', 'goal'))
        self.assertEqual(s.task_checklist(t['TaskId']), []); plan.assert_called_once()

    def test_a_goal_without_done_when_is_a_task(self):
        s = MemoryStore()
        out = ingest.ingest_message(s, mail(s, subject='Quick one'), 'test', brain(self._v(done_when='')))
        self.assertFalse(s.get_task(out['task_id']).get('DoneWhen'))

    def test_not_a_goal_clears_done_when_and_teaches(self):
        from fastapi.testclient import TestClient
        from taskuary import server, routingmemory as rmem
        s = MemoryStore()
        out = ingest.ingest_message(s, mail(s, subject='Census migration'), 'test', brain(self._v()))
        g = out['task_id']; s.set_task_checklist(g, ['a', 'b'], 'owner')
        with mock.patch.object(server, 'store', s):
            c = TestClient(server.app)
            op = c.post('/api/operations', json={'kind': 'task.set_kind', 'target': g, 'params': {'kind': 'task'}}).json()
            c.post(f"/api/operations/{op['id']}/execute", json={'version': op['version']})
        self.assertFalse(s.get_task(g).get('DoneWhen')); self.assertEqual(len(s.task_checklist(g)), 2)
        self.assertTrue(any(f['field'] == 'kind' and f['value'] == 'task' for f in rmem.facts_for(s, {'from_email': 'gail@northwind.example', 'subject': 'Census migration'})))
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** as the Interfaces say: `triage.py` schema `goal: boolean`, `done_when: ['string','null']` always (it is explained in §4); `FIELDS['goal']` sentence: "goal: true for an OPEN-ENDED ask - no single deliverable, several people or systems, a date or none - with done_when the sentence that says when to stop. A single thing to do or answer is not a goal."; validation: `out['goal'] = bool(j.get('goal')) and bool(str(j.get('done_when') or '').strip())`, `out['done_when'] = str(j.get('done_when') or '').strip()[:1000]`. `ingest.py` create path: `**({'DoneWhen': intent['done_when'], 'Tags': 'goal'} if intent.get('goal') else {})`, skip `set_task_checklist` when goal, after `remind.set_due` (DueAt) `if intent.get('goal'): goals.plan_later(store, tid, f"{f['title']}\nDone when: {intent['done_when']}\n{f['summary']}")`. `taskuary/goals.py`: `plan(store, tid, text, llm=None)` = the body of `server.plan_goal` moved (server's keeps its name and calls this); `plan_later(store, tid, text)` runs it on a daemon thread unless `goals.BACKGROUND` is False (tests; add to conftest like `advisor.BACKGROUND`). `routingmemory.lesson`: a sentence for `kind` `goal` ("you called this kind of ask a goal") and `task`. `server._run_operation` `task.set_kind`: `if p.get('kind') == 'goal': store.update_task(tid, {'DoneWhen': t.get('DoneWhen') or t.get('Summary') or t.get('Title'), 'Tags': ...goal...}, ACTOR); _teach_routing(tid, 'kind', 'goal', ...)`; `if p.get('kind') == 'task' and is_goal(t): store.update_task(tid, {'DoneWhen': ''}, ACTOR); _teach_routing(tid, 'kind', 'task', ...); return` before the existing `not_coding` road (read `_teach_routing`'s signature at `server.py:2077`). Docs: `templates/triage.md` §4 "A goal" paragraph.
- [ ] **Step 4: Run** `python -m pytest tests/test_goal_serves.py tests/test_routingmemory*.py tests/test_task_tools.py -q` → PASS (regenerate the tools page if DECISIONS text changed). **Step 5: Commit** `"Triage opens a goal for the open-ended ask, with no steps, and the planner proposes them; 'that was a task' teaches kind"`.

---

### Task 3: Work facts into playbooks, as a proposal

**Files:**
- Create: `taskuary/playbook_facts.py`
- Modify: `taskuary/outcomes.py` (`work_facts`), `taskuary/store.py` (`update_task`'s close door: facts gain `playbook` and `asked`), `taskuary/proposals.py` (`amend_playbook` action), `taskuary/learn.py` (`reflect`'s tail), `taskuary/funnel.py` or wherever task-less reviews surface (read: `grep -n "TaskId IS NULL\|approve' lane" taskuary/funnel.py`)
- Test: `tests/test_playbook_facts.py` (new)

**Interfaces:**
- Produces: `task.closed` facts gain `playbook` (the slug from `playbooks.of_task`) and `asked` (whether the last inbound before the close asked something: `store.message_verdict(mid)['intent'] in ('task', 'reply_only')` via `store.last_inbound_on_task`); `outcomes.work_facts(store, slug) -> {closes, reopened, closed_with_open_question, reopened_after_open_question}`; `playbook_facts.compile(store, slug, llm=None) -> int|None` (the review id of an `amend_playbook` proposal, None when nothing to say); `playbook_facts.refresh(store, llm=None, limit=3, min_closes=5) -> list[str]`; `proposals.ACTIONS['amend_playbook'] = ('add what the ledger learned to a playbook', ('slug', 'text'), 'playbooks_enabled')`, executed by `playbooks.write(slug, text)`; the proposal is a review with `TaskId=None`, `Kind='action'`, `Reason="the ledger's facts about <slug>"`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_playbook_facts.py
"""Work facts into the playbook they belong to, as a proposal (spec 2026-10-12, build step 5)."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock
from taskuary import outcomes, playbook_facts, playbooks, proposals
from taskuary.store import MemoryStore

def ago(days=0): return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

def closed_task(s, slug, asked, reopened):
    t = s.create_task({'Title': 'Vendor onboarding', 'Tags': playbooks.tag(slug), 'Status': 'open'}, 'owner')
    mid = s.add_message({'ConversationId': f'c{t}', 'Channel': 'email', 'Subject': 'Onboarding', 'FromEmail': 'billing@vendor.example', 'SentAt': ago(10), 'BodyText': 'x', 'Status': 'routed', 'TaskId': t})
    s.add_route(mid, t, 'create', 1.0, 'x', [], 'triage', verdict={'intent': 'task' if asked else 'fyi'})
    s.update_task(t, {'Status': 'done'}, 'owner')
    r = outcomes.rows_for(s, 'task', t)[0]
    outcomes.settle(s, r['Id'], 'x', 'reopened' if reopened else 'held')
    return t


class WorkFactsTests(unittest.TestCase):
    def test_the_close_carries_the_playbook_and_whether_it_asked(self):
        s = MemoryStore(); t = closed_task(s, 'vendor-onboarding', True, False)
        f = json.loads(outcomes.rows_for(s, 'task', t)[0]['FactsJson'])
        self.assertEqual((f['playbook'], f['asked']), ('vendor-onboarding', True))

    def test_work_facts_count_reopens_after_an_open_question(self):
        s = MemoryStore()
        for asked, reopened in ((True, True), (True, True), (True, False), (False, False), (False, False)): closed_task(s, 'vendor-onboarding', asked, reopened)
        self.assertEqual(outcomes.work_facts(s, 'vendor-onboarding'), {'closes': 5, 'reopened': 2, 'closed_with_open_question': 3, 'reopened_after_open_question': 2})

    def test_compile_files_a_task_less_proposal_for_the_owners_yes(self):
        s = MemoryStore(); s.set_setting('playbooks_enabled', '1', 'test')
        for asked, reopened in ((True, True), (True, True), (True, False), (False, False), (False, False)): closed_task(s, 'vendor-onboarding', asked, reopened)
        with mock.patch.object(playbooks, 'read', return_value='# Vendor onboarding\nwhen: a new vendor writes\n'):
            rid = playbook_facts.compile(s, 'vendor-onboarding', llm=lambda sys_, user, **kw: '- closing with an open question reopened 2 of 3 times; ask first [ev: out1, out2]')
        rv = s.get_review(rid)
        self.assertIsNone(rv['TaskId']); self.assertEqual(rv['Kind'], 'action')
        p = json.loads(rv['DraftText']); self.assertEqual(p['action'], 'amend_playbook'); self.assertIn('ask first', p['text']); self.assertIn('when: a new vendor writes', p['text'])

    def test_the_proposal_has_no_task_and_blocks_nothing(self):
        s = MemoryStore(); s.set_setting('playbooks_enabled', '1', 'test')
        t = closed_task(s, 'vendor-onboarding', True, True)
        with mock.patch.object(playbooks, 'read', return_value='# Vendor onboarding\nwhen: x\n'):
            playbook_facts.compile(s, 'vendor-onboarding', llm=lambda sys_, user, **kw: '- a fact [ev: out1]')
        self.assertFalse(proposals.closeout_pending(s, t))

    def test_refresh_needs_five_closes_and_silence_files_nothing(self):
        s = MemoryStore(); s.set_setting('playbooks_enabled', '1', 'test')
        for _ in range(4): closed_task(s, 'vendor-onboarding', False, False)
        self.assertEqual(playbook_facts.refresh(s, llm=lambda *a, **k: '- x [ev: out1]'), [])
        closed_task(s, 'vendor-onboarding', False, False)
        with mock.patch.object(playbooks, 'read', return_value='# V\nwhen: x\n'):
            self.assertEqual(playbook_facts.refresh(s, llm=lambda *a, **k: ''), [])
            self.assertEqual(playbook_facts.refresh(s, llm=lambda *a, **k: '- a fact [ev: out1]'), ['vendor-onboarding'])
```

(`store.add_route(mid, tid, decision, score, reason, candidates, routed_by, raw_output=None, parse_error=None, verdict=None)` is at `store.py:4034`; `proposals.closeout_pending(store, tid)` at `proposals.py:216-244`; `playbooks.read(slug)` reads a file under `~/.taskuary/playbooks`, hence the mock.)

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement**: `store.update_task` close door: `from . import playbooks as _pb; facts['playbook'] = _pb.of_task(was_row_full)` (read the whole task row once: `was_row = self._one('SELECT Status, Assignee, DueAt, Tags FROM task ...')`; `of_task` reads `Tags`); `asked`: `li = self.last_inbound_on_task(task_id); v = self.message_verdict(li['MessageId']) if li else None; facts['asked'] = bool(v and v.get('intent') in ('task', 'reply_only'))` (read both helpers' names: `grep -n "def last_inbound_on_task\|def message_verdict" taskuary/store.py`). `outcomes.work_facts(store, slug)`: rows `task.closed` with `json_extract(FactsJson,'$.playbook')=slug` and ResolvedAt not null → the four counts. `taskuary/playbook_facts.py`: `SYSTEM` ("3 to 6 bullet facts about this KIND of work, from the numbers and the lines; each ends with [ev: ids]; nothing when the facts say nothing"); `compile`: `work_facts` + evidence lines (`outcomes.evidence` filtered to rows whose facts name the slug) → model → bullet lines → `text = splice(playbooks.read(slug), block)` where the block is `## From the ledger\n<lines>` kept in a marked block (reuse `people_pages.splice` with its markers) → `store.add_review({'TaskId': None, 'Kind': 'action', 'Status': 'pending', 'DraftText': json.dumps({'action': 'amend_playbook', 'slug': slug, 'text': text, 'why': ...}), 'Reason': f"the ledger's facts about {slug}"})`; one open proposal per slug (skip when a pending review with that slug exists). `refresh`: slugs with ≥ `min_closes` resolved closes, most first, limit 3. `proposals.py`: `ACTIONS['amend_playbook']`; `execute`: `elif a == 'amend_playbook': out = {'playbook': playbooks.write(p['slug'], p['text'])}`; `validate` requires `('slug','text')` and the switch. `learn.reflect` tail: after people pages, `playbook_facts.refresh(store, llm)` in its own try. Check a task-less `action` review reaches the rail's approve lane (`grep -n "'action'" taskuary/funnel.py | head`): if it does not, add it to `from_reviews`' selection with `TaskId IS NULL` allowed and a title from `Reason`.
- [ ] **Step 4: Run** `python -m pytest tests/test_playbook_facts.py tests/test_outcomes.py tests/test_playbooks*.py tests/test_proposals*.py -q` → PASS. **Step 5: Commit** `"What the ledger counts about a kind of work reaches its playbook as a proposal for the owner's yes"`.

---

### Task 4: Docs and the full gate

- `docs/site/advisor.md`: "What is built" - all five steps built; a short paragraph under "A page per person": "Facts about kinds of work go to the playbook they belong to, as a proposal: a bullet block the ledger wrote, for your yes on the Review queue". `docs/site/how-it-works.md`: the triage row of the three-brains table says "names the goal step a mail serves; opens a goal for the open-ended ask". `README.md`: one sentence. `python -m taskuary.toolcatalog`; `cd website && npm run build:docs && npm test && npm run build`; the full pytest suite; commit `"The docs say all five build steps of the goals, outcomes and Advisor spec are built"`.

## Self-review

**Spec coverage:** which step a mail serves, shown under the step, ticking itself, the Advisor told (T1); the owner's correction as routing memory - ruled to the existing kind/merge doors plus the `serves` verdict stored on the route (T1/T2; a step id is not reusable across messages, so "serves" memory keyed on a sender would be a guess - said in the ledger); triage's goal kind with no steps and the planner proposing them, kind memory correcting it (T2); work facts into playbooks as a proposal (T3). **Placeholders:** none; six greps name what to confirm. **Type consistency:** `serves {task:int, step:str, done:bool}`; `work_facts` keys as listed. **Review Focus:** T1 ×2, T2 ×2, T3 ×1.
