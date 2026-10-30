# Quick General Work Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A general task that triage judged `difficulty=quick` is answered by one model call instead of a general-agent session. The call returns the report, the draft and the question that a finished general turn returns today, and work it cannot finish in one call escalates to today's deep path.

**Architecture:** A new module `taskuary/quickwork.py` decides depth from triage's existing readings (`brainroute.judged`, `ingest.triage_wants_browser`, `browserview.wanted`, origin). It builds one prompt from `general._prompt` and `general.history_brief`, asks a new `brainroute` job `quick_work` for a JSON answer, and files that answer through a `GeneralSession` method, `_file`. `_file` is the reply-filing tail of `send_prompt`, moved out unchanged, so the history, the record, Continue and every view read a quick run exactly as they read a general turn. A quick session is a parked `GeneralSession` with `quick=True`. It is left out of `blackboard.live_count`, so it takes no agent desk, and its first real `send_prompt` (Continue, an answer, a passed-in mail) makes it today's general session.

**Tech Stack:** Python 3.12, SQLite store (`MemoryStore` in tests), pytest + `unittest.mock`, `threading`.

**Spec:** `docs/superpowers/specs/2026-10-29-quick-general-work-design.md`

## Global Constraints

- Nothing in the UI or the actions changes: same Agent pane, same "what the agent found", same permission asks, same Approve / Continue / Run another, same receipts.
- Coding is untouched: coding tasks keep the CLI terminal. No change to coding agents, routines or reports.
- Nothing is ever sent automatically, and the quick path cannot act: it has no tool that writes, sends, pays or browses with a login.
- Strangers get exactly what the general agent gets on their tasks, under the existing stranger rules.
- No hard-coded words or regex decide meaning. Depth and escalation are the model's structured output (`difficulty` from triage, `escalate` from the quick call).
- `auto_start_ok` applies to quick calls unchanged: the switches, the danger hold and the stranger gate.
- No new settings page.
- Scope: only general tasks created from this release on. Open tasks are not migrated.
- Tests use invented stand-ins only: owner Alex Doyle `alex@northwind.example`, colleague Erin Blake `erin@northwind.example`, domain `northwind.example`, vendor `vendor.example`. No real names, domains or mail anywhere.
- Run pytest with `TASKUARY_HOME` set to a temp dir (`tests/conftest.py` also enforces this). Never read or write `~/.taskuary`.
- Write dense fast.ai-style code that matches the surrounding file. Don't run autoformatters.

## Review Focus

These are the five failure modes most likely to bite. Each has a named test in the task that owns it.

1. **The quick call fails, times out or returns unreadable JSON.** The task must not be left looking untouched or "working". It escalates to the deep path with the reason on the task, and its pool slot is released. Tests: `test_a_failed_quick_call_escalates_and_frees_its_slot` and `test_unreadable_json_escalates` (Task 4).
2. **A quick verdict on a stranger's task.** The deep path seeds a stranger's words through a file (`origin.SEED_LINE`) that the quick call cannot read, so a stranger's task never takes the quick path. It goes through today's start and its stranger rules. Test: `test_a_strangers_quick_task_takes_the_deep_path` (Task 1).
3. **A burst of 50 arrivals.** At most 8 quick calls run at once. Quick sessions take no agent desk, so a later deep task is not left "Waiting its turn" behind 50 parked quick answers. Test: `test_fifty_arrivals_run_eight_at_a_time_and_take_no_desk` (Task 5).
4. **The owner presses Continue, or answers the question, on a quick task.** This becomes today's general session: `job='general'`, the deep worker prompt, the quick turn in its conversation, and now counted as a desk. Tests: `test_continue_on_a_quick_task_runs_the_general_agent` and `test_an_answer_to_a_quick_question_runs_the_general_agent` (Task 4).
5. **An API brain without web search, and model text carrying `[[TASKUARY-...]]` markers.** A brain with no `takes_web` gets the schema and is told to escalate rather than guess. Markers inside the model's fields are stripped, so the call cannot attach a file, raise a sign-in or close the task except through `done`. Tests: `test_an_api_brain_without_web_gets_the_schema_and_the_escalate_line` (Task 2) and `test_markers_in_the_models_fields_do_nothing` (Task 3).

---

### Task 1: The `quick_work` job and the depth reading

**Files:**
- Create: `taskuary/quickwork.py`
- Modify: `taskuary/brainroute.py` (`JOBS`, `SLOT_OF`, `JOB_WORDS`, `PLURAL`, `DEFAULT_RULES` rule `work`)
- Modify: `tests/test_brainroute.py:96` (the gear assertion names the main-gear jobs)
- Test: `tests/test_quick_work.py` (new)

**Interfaces:**
- Consumes: `brainroute.judged(store, task) -> {difficulty, sure, data_class, by}`, `ingest.triage_wants_browser(store, tid) -> bool`, `browserview.wanted(task) -> bool`, `origin.of_task(store, tid) -> (origin, why)`, `general.handles(task)`, `general.is_dock(task)`, `slots.all_(store, tid) -> list`, `store.worker_events(tid)`.
- Produces:
  - `brainroute.JOBS` gains `'quick_work'`, `SLOT_OF['quick_work'] = 'assistant_ai'`, `JOB_WORDS['quick_work'] = 'quick general work'`, `PLURAL['quick_work'] = 'quick general work'`, and `'quick_work'` joins the `work` default rule's job list. `_fixed` needs no change: a job outside `ONE_SHOT`/`coding`/`assistant` already gets the general agents' pick and model on the `main` gear.
  - `quickwork.why_deep(store, tid) -> str`: `''` means quick. Otherwise it returns one code from `DEEP_WHY = ('kind', 'difficulty', 'browser', 'stranger', 'emails', 'ran deep')`.
  - `quickwork.takes(store, tid) -> bool`: `not why_deep(store, tid)`.
  - `quickwork.only_quick(store, tid) -> bool`: True when the task has worker events and every run event's `Source` is `'quick'`. Owner, judge and `answered` events are ignored.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_quick_work.py
"""Quick general work (spec 2026-10-29): a general task triage judged quick is answered in one call, not an agent session."""
import json, threading, time, unittest
from unittest import mock
from taskuary import brainroute, browserview, general, ingest, llm, origin, quickwork, senders, terminal, workerstate as ws
from taskuary.store import MemoryStore

ASK = 'Erin Blake asks: does it make sense for us to go to the Northwind partner day on Friday?'

def home(**settings):
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't')
    for k, v in settings.items(): s.set_setting(k, v, 't')
    return s

def mail(**kw):
    return {'external_id': 'q1', 'channel': 'email', 'subject': 'partner day', 'body': ASK, 'from_email': 'erin@northwind.example',
            'from_name': 'Erin Blake', 'conversation_id': 'conv-partner', 'sent_at': '2026-10-29 09:00', 'source_name': 'alex@northwind.example', **kw}

def arrived(s, difficulty='quick', **verdict):
    "A general task as triage lands it, with _spawn caught: (task id, the names spawned)."
    said = lambda sy, u, **k: json.dumps({'intent': 'task', 'kind': 'general', 'why': 'w', 'difficulty': difficulty, **verdict})
    with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=True), \
         mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
        out = ingest.ingest_message(s, mail(), llm=said)
    return out['task_id'], [getattr(c[0][0], '__name__', '') for c in spawn.call_args_list]

def test_quick_work_is_a_job_on_the_general_agents_brain():
    s = home(); tid, _ = arrived(s)
    r, g = brainroute.choose(s, 'quick_work', tid), brainroute.choose(s, 'general', tid)
    assert 'quick_work' in brainroute.JOBS and (r.pick, r.model, r.gear) == (g.pick, g.model, 'main')
    assert r.difficulty == 'quick'                        # the depth reaches the router

def test_triage_difficulty_decides_the_depth():
    s = home(); q, _ = arrived(s)
    assert quickwork.why_deep(s, q) == '' and quickwork.takes(s, q)
    for d in ('standard', 'hard', None):                 # an unjudged task reads as deep
        s2 = home(); t2, _ = arrived(s2, d); assert quickwork.why_deep(s2, t2) == 'difficulty'

def test_a_browser_task_is_always_deep():
    s = home(); tid, _ = arrived(s); s.tag_task(tid, browserview.WANTS, actor='triage')
    assert quickwork.why_deep(s, tid) == 'browser'

def test_a_strangers_quick_task_takes_the_deep_path():
    s = home(); tid, _ = arrived(s)
    with mock.patch.object(origin, 'of_task', return_value=('stranger', 'a first message')):
        assert quickwork.why_deep(s, tid) == 'stranger'

def test_a_task_that_ran_deep_stays_deep():
    s = home(); tid, _ = arrived(s)
    ws.record(s, tid, 'deep1', 'working', source='api')
    assert quickwork.why_deep(s, tid) == 'ran deep' and not quickwork.only_quick(s, tid)
```

- [ ] **Step 2: Run them (expect FAIL: no module `quickwork`)**

`TASKUARY_HOME=$(mktemp -d) python -m pytest -q tests/test_quick_work.py -k "job or depth or browser or stranger or ran_deep"`

- [ ] **Step 3: Implement**

In `brainroute.py`, add `'quick_work'` to `JOBS` and to the `work` rule's `job` list, and add the `SLOT_OF`, `JOB_WORDS` and `PLURAL` entries. In `tests/test_brainroute.py:96`, change the gear line to `assert r.gear == ('main' if job in ('general', 'coding', 'quick_work') else 'light')`.

Create `taskuary/quickwork.py` with a short module docstring (the why, from the spec), `DEEP_WHY`, and:

```python
def why_deep(store, tid) -> str:
    "'' when this general task is answered in one call (quick), else why it takes the agent - one of DEEP_WHY."
def takes(store, tid) -> bool: return not why_deep(store, tid)
def only_quick(store, tid) -> bool:
```

`why_deep` checks in this order, returning the first that fails:
1. `kind`: the task is not `general.handles` or is `is_dock`, or its `SourceRef` is a setup walk.
2. `difficulty`: `brainroute.judged(...)['difficulty'] != 'quick'`. An unjudged task reads as deep.
3. `browser`: `browserview.wanted(task) or ingest.triage_wants_browser(store, tid)`.
4. `stranger`: `origin.of_task(...)[0] == 'stranger'`.
5. `emails`: `slots.all_(store, tid)` is non-empty, meaning several emails are owed, which is the deep agent's `DRAFT_LINE` job.
6. `ran deep`: worker events exist and `not only_quick`.

- [ ] **Step 4: Run (expect PASS), then the router suite**

`TASKUARY_HOME=$(mktemp -d) python -m pytest -q tests/test_quick_work.py tests/test_brainroute.py tests/test_brainroute_api.py`

- [ ] **Step 5: Commit**

```bash
git add taskuary/quickwork.py taskuary/brainroute.py tests/test_quick_work.py tests/test_brainroute.py
git commit -m "Quick general work: a quick_work job on the general agents' brain, and depth read from triage's difficulty and browser

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: The single call: prompt, lookups and structured answer

**Files:**
- Modify: `taskuary/quickwork.py`
- Modify: `taskuary/clis.py` (`QUICK_TOOLS`, `QUICK_READ`, `quick_read_args`)
- Modify: `taskuary/llm.py` (`make_cli_llm`: `research='web'` picks `quick_read_args`; signature unchanged, the value widened)
- Test: `tests/test_quick_work.py`

**Interfaces:**
- Consumes: `general._prompt(store, tid) -> (system, user)`, `general.history_brief(store, tid, hands=False) -> (line, material)`, `llm.build_llm(store, ..., research, gear, task_id, job, trace, cancel)`, `llm.ask_json(brain, system, user, want=None, need=(), **kw) -> JsonAnswer`, `llm.watching(trace)`, `selfclose.mode`, `selfclose.stays_open`.
- Produces:
  - `clis.QUICK_TOOLS = 'WebFetch,WebSearch'`. `clis.QUICK_READ`: claude gets `('--dangerously-skip-permissions',)` dropped and `('--tools', QUICK_TOOLS, '--allowedTools', QUICK_TOOLS, '--disallowedTools', 'mcp__*')` added; every other CLI gets its `READONLY` entry.
  - `clis.quick_read_args(cmd, args) -> list`, the same shape as `report_read_args`.
  - `quickwork.QUICK_WANT`, a schema `{'name': 'quick_work', 'schema': {...}}` with all six fields required and `additionalProperties: False`: `report: string`, `draft: string|null`, `question: string|null`, `done: boolean`, `escalate: boolean`, `why: string`.
  - `class QuickAnswer(NamedTuple): report: str; draft: str; question: str; done: bool; escalate: bool; why: str`.
  - `quickwork.read(data) -> QuickAnswer | None`: None when `data` is not a dict, or has neither a `report` nor `escalate: true`. Markers are stripped from every string field (Task 3 tests this).
  - `quickwork.prompt(store, tid, ask: str, lookups: bool) -> tuple[str, str]`.
  - `quickwork.ask(store, tid, ask: str, steps: list = None, cancel=None) -> QuickAnswer | None`. This makes the one call. It raises what the brain raises and returns None for an unreadable answer.
  - Constants: `QUICK_TOKENS = 3_000`, `QUICK_LINE`, `NO_LOOKUP_LINE`, `NO_CLOSE_LINE`.

- [ ] **Step 1: Write the failing tests**

```python
class Brain:
    "A fake brain: answers `said`, records each call; takes_web/takes_want as an API connector says them."
    def __init__(self, said, web=False, want=True): self.said, self.calls, self.takes_web, self.takes_want = said, [], web, want
    def __call__(self, system, user, **k): self.calls.append((system, user, k)); return json.dumps(self.said)

ANSWER = {'report': 'Worth going: Erin is presenting.', 'draft': 'Yes, let us go.', 'question': None, 'done': False, 'escalate': False, 'why': ''}

def test_the_prompt_carries_what_the_general_agent_reads_plus_the_mail_history():
    s = home(); tid, _ = arrived(s)
    with mock.patch('taskuary.context.for_prompt', return_value='TODAY 14:00 partner day prep'), \
         mock.patch.object(general, 'earlier_mail', return_value='Erin Blake wrote on Monday about the agenda'):
        system, user = quickwork.prompt(s, tid, ASK, lookups=True)
    assert 'RULES (AGENT.md - every worker)' in system and quickwork.QUICK_LINE in system
    assert 'SOUL' not in system                          # SOUL.md stays with triage (PW-184)
    assert 'TODAY 14:00 partner day prep' in user and 'Erin Blake wrote on Monday' in user and ASK in user

def test_an_api_brain_with_web_searches_and_one_without_gets_the_schema():
    s = home(); tid, _ = arrived(s)
    web = Brain(ANSWER, web=True)
    with mock.patch.object(llm, 'build_llm', return_value=web) as build: out = quickwork.ask(s, tid, ASK)
    assert out.draft == 'Yes, let us go.' and web.calls[0][2].get('web') is True and 'want' not in web.calls[0][2]
    assert build.call_args.kwargs['job'] == 'quick_work' and build.call_args.kwargs['research'] == 'web'

def test_an_api_brain_without_web_gets_the_schema_and_the_escalate_line():
    s = home(); tid, _ = arrived(s)
    plain = Brain(ANSWER, web=False)
    with mock.patch.object(llm, 'build_llm', return_value=plain): quickwork.ask(s, tid, ASK)
    system, _, k = plain.calls[0]
    assert k['want'] == quickwork.QUICK_WANT and 'web' not in k and quickwork.NO_LOOKUP_LINE in system

def test_a_cli_quick_call_may_search_the_web_and_nothing_else():
    from taskuary import clis
    assert clis.quick_read_args('claude', ['-p', '--dangerously-skip-permissions']) == \
        ['-p', '--tools', 'WebFetch,WebSearch', '--allowedTools', 'WebFetch,WebSearch', '--disallowedTools', 'mcp__*']
    assert clis.quick_read_args('codex', ['exec', '--full-auto']) == clis.readonly_args('codex', ['exec', '--full-auto'])

def test_unreadable_answers_read_as_none():
    assert quickwork.read(None) is None and quickwork.read({'draft': 'x'}) is None
    assert quickwork.read({'escalate': True, 'why': 'books travel across three sites'}).escalate
```

- [ ] **Step 2: Run (expect FAIL)**

`TASKUARY_HOME=$(mktemp -d) python -m pytest -q tests/test_quick_work.py -k "prompt or brain or cli_quick or unreadable_answers"`

- [ ] **Step 3: Implement**

- In `clis.py`, add `QUICK_TOOLS`, `QUICK_READ` and `quick_read_args`. The body copies `report_read_args`.
- In `llm.make_cli_llm`, change `restrict = report_read_args if research else readonly_args` to `restrict = quick_read_args if research == 'web' else report_read_args if research else readonly_args` and import `quick_read_args`.
- `quickwork.prompt` steps:
  1. Call `general._prompt(store, tid)`, then `general.history_brief(store, tid, False)`. Append the line to `system` and put the material in front of `user`, the same way `send_prompt` does.
  2. Append `f'\n\n{ask}'` to `user`. This carries the ask the way `send_prompt` carries an `as_owner=False` instruction.
  3. Append `QUICK_LINE` to `system`. Add `NO_LOOKUP_LINE` when `not lookups`. Add `NO_CLOSE_LINE` when `selfclose.mode(store) == 'off' or selfclose.stays_open(store, tid)`.
- What `QUICK_LINE` tells the model:
  - Answer in one go as the JSON object. The `[[TASKUARY-...]]` marker instructions above are expressed as fields here: the reply goes in `draft`, a question to the owner in `question`, and the finish in `done` with `why`.
  - Set `escalate` with one line in `why` when the job needs more than a lookup: acting anywhere, files to work through, booking, or multi-step research.
  - Never claim an action.
- What `NO_LOOKUP_LINE` says: this AI cannot look anything up, so escalate rather than answer from memory when a fact must be checked.
- `quickwork.ask` steps:
  1. Build the brain with `llm.build_llm(store, job='quick_work', task_id=tid, research='web', gear='main', trace=..., cancel=cancel)`. `trace` appends `(kind, name, detail)` to `steps`.
  2. Set `lookups = getattr(brain, 'takes_web', False) or brainroute.choose(store, 'quick_work', tid).pick.startswith('cli:')`.
  3. Call `ask_json(brain, system, user, want=None if web else QUICK_WANT, max_tokens=QUICK_TOKENS, **({'web': True} if web else {}))` inside `llm.watching(trace)`. Here `web` is `takes_web`, because a provider's web search and an enforced schema do not combine (`llm.make_llm`: `if web and not want`).
  4. Return `read(answer.data)`.
  5. Raise `RuntimeError(general.NO_AI ...)` when `build_llm` returns None.

- [ ] **Step 4: Run (expect PASS)**

`TASKUARY_HOME=$(mktemp -d) python -m pytest -q tests/test_quick_work.py tests/test_assistant_can_look_things_up.py tests/test_general_agent_permissions.py`

- [ ] **Step 5: Commit**

```bash
git add taskuary/quickwork.py taskuary/clis.py taskuary/llm.py tests/test_quick_work.py
git commit -m "Quick general work: one call with the general agent's context, web lookups only, a JSON answer

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: File the answer the way a general turn files it

**Files:**
- Modify: `taskuary/general.py` (move the tail of `send_prompt` into `GeneralSession._file`, add `quick = False`, `file_quick`, and `send_prompt` clears `quick`)
- Modify: `taskuary/blackboard.py:388` (`live_count` skips quick sessions)
- Modify: `taskuary/quickwork.py` (`as_reply`, `_unmark`)
- Test: `tests/test_quick_work.py`, plus the existing `tests/test_general.py` and `tests/test_general_turn_ends_short.py` unchanged as the guard on the move

**Interfaces:**
- Consumes: the filing functions `send_prompt` already uses: `selfclose.reply_marker`/`ask_markers`/`chat_marker`, `wrapup.agent_reply`, `workerstate.record`, `hooks.judge_ended`, `sessionrecord.keep_turn`, `store.add_comment(..., ASSISTANT_TYPE, ...)`, `GeneralSession._close_out`.
- Produces:
  - `GeneralSession._file(self, reply: str, paths: list, t0: float, browser_tools: bool = False, browser_offer: bool = False) -> str`. This is the block of `send_prompt` from `if not reply: raise RuntimeError('the model returned an empty response')` through the close-out timer, moved verbatim. `send_prompt` then ends with `return self._file(reply, paths, t0, browser_tools, browser_offer)`.
  - `GeneralSession.quick = False` (class attribute). `send_prompt` sets `self.quick = False` right after `self._take(...)`, so the first real turn makes it a counted desk.
  - `GeneralSession.file_quick(self, ask: str, out: 'quickwork.QuickAnswer', steps: list, as_owner: bool = True) -> str`. It takes the turn lock, runs `selfclose.forget`, records `ws.record(..., 'working', source='quick')`, adds the owner row of `ask` when `as_owner`, sets `self.trace` to the start entry plus `steps` (through `_remember_trace`), and returns `self._file(quickwork.as_reply(out), [], t0)`. In `finally` it clears busy and releases the lock, as `send_prompt` does. On an exception it records `failed` with `source='quick'` and re-raises.
  - `quickwork.as_reply(out: QuickAnswer) -> str`: the report, then `[[TASKUARY-REPLY]]{draft}[[/TASKUARY-REPLY]]` when there is a draft, then `[[TASKUARY-ASK]] {question}` when there is a question, then `f'{selfclose.MARKER} {why}'` when `done`. The answer is the markers a general turn emits, so `_file` reads it the same way.
  - `quickwork._unmark(text) -> str`: strips any `[[ TASKUARY... ]]` / `[[/TASKUARY...]]` tag from a model field. `read` applies it to every string.
  - `blackboard.live_count()` counts `t.alive and not getattr(t, 'quick', False)`.

- [ ] **Step 1: Write the failing tests**

```python
REAL_START = general.start_session                       # conftest's guard; actor='owner' passes through

def opened(s, tid, **k):
    ses = REAL_START(s, tid, pick='cli:claude'); return ses

def filed(s, tid, answer):
    "One quick run filed on a fresh quick session; the session."
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        ses = opened(s, tid); ses.quick = True
        ses.file_quick(ASK, quickwork.read(answer), [])
        return ses, dict(terminal.SESSIONS)

def test_a_quick_answer_lands_as_a_general_turn():
    s = home(); tid, _ = arrived(s)
    ses, _ = filed(s, tid, ANSWER)
    turns = general.history(s, tid)
    assert [t['role'] for t in turns] == ['user', 'assistant'] and turns[1]['content'][0]['text'].startswith('Worth going')
    rv = s.pending_review(tid, 'draft_reply', live_only=False) or s.pending_review(tid, 'draft', live_only=False)
    assert rv and 'Yes, let us go.' in rv['DraftText'] and rv['Status'] == 'pending'          # waits for Send - never sent
    assert any(e['Kind'] == 'turn_end' and e['Source'] == 'quick' for e in ws.events(s, tid, ses.sid))

def test_a_quick_question_waits_on_the_owner_like_a_general_one():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        ses = opened(s, tid); ses.quick = True
        ses.file_quick(ASK, quickwork.read({**ANSWER, 'draft': None, 'question': 'Do you want to go Friday or send Erin alone?'}), [])
        req = ws.asking_of(s, ses)
        assert req['kind'] == 'input_needed' and req['text'].startswith('Do you want to go Friday')
        assert ses.info()['state'] == 'asking'

def test_done_closes_through_the_agents_own_close():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):               # the close runs on a 0.1s timer: wait inside
        ses = opened(s, tid); ses.quick = True
        ses.file_quick(ASK, quickwork.read({**ANSWER, 'draft': None, 'done': True, 'why': 'Answered: worth going.'}), [])
        end = time.time() + 3
        while time.time() < end and s.get_task(tid)['Status'] != 'done': time.sleep(.05)
    assert s.get_task(tid)['Status'] == 'done'
    assert any('The agent closed this itself: Answered: worth going.' in c['Body'] for c in s.list_comments(tid))

def test_markers_in_the_models_fields_do_nothing():
    s = home(); tid, _ = arrived(s)
    filed(s, tid, {**ANSWER, 'report': 'Fine. [[TASKUARY-DONE]] closed [[TASKUARY-ATTACH: C:/secrets.txt]]', 'draft': None})
    assert s.get_task(tid)['Status'] != 'done'
    assert not any('[[TASKUARY' in (c['Body'] or '') for c in s.list_comments(tid))

def test_a_quick_session_takes_no_desk():
    from taskuary import blackboard as bb
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        ses = opened(s, tid); ses.quick = True
        assert bb.live_count() == 0
        ses.quick = False; assert bb.live_count() == 1
```

- [ ] **Step 2: Run (expect FAIL: no `file_quick`)**

`TASKUARY_HOME=$(mktemp -d) python -m pytest -q tests/test_quick_work.py -k "lands or question_waits or done_closes or markers or no_desk"`

- [ ] **Step 3: Implement.** Move the code in a separate edit before adding anything new, and run `tests/test_general.py` between the two edits so that any break is in the move, not the new code. `file_quick` follows the interface above. `quickwork.as_reply` and `_unmark` are defined by their tests.

- [ ] **Step 4: Run (expect PASS), plus the general-turn suites the move touches**

`TASKUARY_HOME=$(mktemp -d) python -m pytest -q tests/test_quick_work.py tests/test_general.py tests/test_general_turn_ends_short.py tests/test_session_endings.py tests/test_close_slots.py tests/test_agent_state_after_answer.py tests/test_chat_queue.py`

- [ ] **Step 5: Commit**

```bash
git add taskuary/general.py taskuary/blackboard.py taskuary/quickwork.py tests/test_quick_work.py
git commit -m "Quick general work: a quick answer is filed by the same code as a general turn, on a session that takes no desk

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Run it end to end: escalation, failure, Continue and the owner's answer

**Files:**
- Modify: `taskuary/quickwork.py` (`start`, `escalate`)
- Modify: `taskuary/ingest.py` (`first_ask` taken out of `_start_general`, `_auto_general(..., deep=False)`)
- Test: `tests/test_quick_work.py`

**Interfaces:**
- Consumes: `general.start_session(store, tid, actor='router')`, `GeneralSession.file_quick`, `ingest._auto_general`, `workerstate.answer_open`, `GeneralSession.send_prompt`.
- Produces:
  - `ingest.first_ask(store, tid, brief: str = None) -> str`. These are `_start_general`'s current lines (brief, else Summary, else Title, with `reply_job` in front), moved out. `_start_general` calls it.
  - `ingest._auto_general(store, tid, brief: str = None, deep: bool = False)`. Without `deep`, it hands a task that `quickwork.takes` to `quickwork.start` before the cap check. That wiring lands in Task 6; this task adds only the parameter, so escalation can never loop back into the quick path.
  - `quickwork.start(store, tid, brief: str = None, as_owner: bool = True) -> str`, returning `'filed' | 'escalated'`. The steps:
    1. Build `ask = ingest.first_ask(store, tid, brief)`.
    2. Call `out = ask(...)` with a `QUICK_TIMEOUT = 180` cancel timer.
    3. If the call raised, or `out` is None, or `out.escalate`, call `escalate(...)` and return.
    4. Otherwise call `general.start_session(store, tid, actor='router')`, set `quick = True`, and `file_quick(ask, out, steps, as_owner)`.
  - `quickwork.escalate(store, tid, ask: str, why: str, report: str = '') -> None`:
    1. Write the router comment `f'{ESCALATED}{why}'`, where `ESCALATED = 'A quick look found this needs the agent: '`.
    2. Audit `quick_escalated`.
    3. Call `ingest._auto_general(store, tid, brief, deep=True)` with `brief = ask` plus an `ESCALATE_BRIEF` paragraph that carries `why` and `report`. The cap, the queue and the retry budget apply as they do to any deep start.
  - A failed or unreadable call escalates with `why = f'the quick answer could not be made ({e})'` or `'the quick answer could not be read'`.

- [ ] **Step 1: Write the failing tests**

```python
def run(s, tid, brain, deep=None):
    "quickwork.start on a fake brain, the deep start caught."
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(llm, 'build_llm', return_value=brain), \
         mock.patch.object(general, 'start_session', side_effect=opened), \
         mock.patch.object(ingest, '_auto_general', side_effect=deep or (lambda *a, **k: None)) as auto:
        said = quickwork.start(s, tid)
        return said, auto, dict(terminal.SESSIONS)

def test_escalate_starts_the_general_agent_with_the_notes():
    s = home(); tid, _ = arrived(s)
    said, auto, live = run(s, tid, Brain({**ANSWER, 'escalate': True, 'why': 'it means booking travel across three sites', 'report': 'Two dates fit.'}))
    assert said == 'escalated' and not live                                   # no quick session was opened
    (store_, t, brief), k = auto.call_args
    assert t == tid and k == {'deep': True} and 'booking travel across three sites' in brief and 'Two dates fit.' in brief
    assert any(c['Body'] == quickwork.ESCALATED + 'it means booking travel across three sites' for c in s.list_comments(tid))

def test_a_failed_quick_call_escalates_and_frees_its_slot():
    s = home(); tid, _ = arrived(s)
    def boom(*a, **k): raise TimeoutError('timed out after 180s')
    boom.takes_web = False
    said, auto, _ = run(s, tid, boom)
    assert said == 'escalated' and auto.call_args.kwargs == {'deep': True}
    assert any('the quick answer could not be made (timed out after 180s)' in c['Body'] for c in s.list_comments(tid))
    assert quickwork.POOL._value == quickwork.QUICK_POOL                      # the slot came back (Task 5 adds POOL)

def test_unreadable_json_escalates():
    s = home(); tid, _ = arrived(s)
    garbled = lambda *a, **k: 'not json at all'; garbled.takes_web = False; garbled.takes_want = True
    assert run(s, tid, garbled)[0] == 'escalated'

def test_continue_on_a_quick_task_runs_the_general_agent():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'start_session', side_effect=opened):
        with mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)): quickwork.start(s, tid)
        ses = general.session_for(tid); assert ses.quick
        deep = mock.Mock(return_value='Booked nothing; here is the plan.')
        with mock.patch.object(llm, 'build_llm', return_value=deep) as build: ses.send_prompt('go on', pick='cli:claude')
        assert build.call_args.kwargs['job'] == 'general' and not ses.quick
        system, user = deep.call_args[0][:2]
        assert 'Worth going: Erin is presenting.' in user                     # the quick turn is in its conversation

def test_an_answer_to_a_quick_question_runs_the_general_agent():
    s = home(); tid, _ = arrived(s)
    q = {**ANSWER, 'draft': None, 'question': 'Friday or Saturday?'}
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'start_session', side_effect=opened):
        with mock.patch.object(llm, 'build_llm', return_value=Brain(q)): quickwork.start(s, tid)
        with mock.patch.object(llm, 'build_llm', return_value=mock.Mock(return_value='Friday it is.')) as build:
            out = ws.answer_open(s, tid, 'Friday', 'owner')
        assert out['delivered'] and build.call_args.kwargs['job'] == 'general' and not general.session_for(tid).quick
```

- [ ] **Step 2: Run (expect FAIL)**

`TASKUARY_HOME=$(mktemp -d) python -m pytest -q tests/test_quick_work.py -k "escalate or failed_quick or unreadable_json or continue_on or answer_to"`

- [ ] **Step 3: Implement** `first_ask`, the `deep` parameter, `start` and `escalate` as listed under Interfaces. The pool assertion depends on Task 5. Until then, mark that one line `# Task 5` and leave it out, or do Task 5 first; the two tasks are independent apart from it.

- [ ] **Step 4: Run (expect PASS), plus auto-start and Continue**

`TASKUARY_HOME=$(mktemp -d) python -m pytest -q tests/test_quick_work.py tests/test_auto_start.py tests/test_continue_session.py tests/test_reopened_conversation.py tests/test_dispatch_retries.py tests/test_reply_needs_agent.py`

- [ ] **Step 5: Commit**

```bash
git add taskuary/quickwork.py taskuary/ingest.py tests/test_quick_work.py
git commit -m "Quick general work: one call per task, escalating to the agent with its notes when it needs more or fails

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: The pool

**Files:**
- Modify: `taskuary/quickwork.py`
- Test: `tests/test_quick_work.py`

**Interfaces:**
- Produces: `QUICK_POOL = 8` and `POOL = threading.BoundedSemaphore(QUICK_POOL)`. `start` holds `POOL` only around `ask(...)`, never while filing or escalating, so a slow deep start cannot hold a slot. The pool is separate from `ingest.auto_sessions`.

- [ ] **Step 1: Write the failing test**

```python
def test_fifty_arrivals_run_eight_at_a_time_and_take_no_desk():
    from taskuary import blackboard as bb
    s = home(); tids = [arrived(s)[0] for _ in range(50)]
    gate, now, most, lock = threading.Event(), [0], [0], threading.Lock()
    def slow(system, user, **k):
        with lock: now[0] += 1; most[0] = max(most[0], now[0])
        gate.wait(5)
        with lock: now[0] -= 1
        return json.dumps(ANSWER)
    slow.takes_web, slow.takes_want = False, True
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(llm, 'build_llm', return_value=slow), \
         mock.patch.object(general, 'start_session', side_effect=opened):
        ts = [threading.Thread(target=quickwork.start, args=(s, t)) for t in tids]
        for t in ts: t.start()
        time.sleep(.5); gate.set()
        for t in ts: t.join(10)
        assert most[0] == quickwork.QUICK_POOL == 8
        assert bb.live_count() == 0 and not s.queued_dispatches()             # no desk taken, nothing "Waiting its turn"
```

The test calls `ingest.ingest_message` 50 times, so before the loop, check that `arrived` makes a new task for each mail. If one conversation id joins them all, give each mail its own `external_id`/`conversation_id` through `mail(**kw)`.

- [ ] **Step 2: Run (expect FAIL: `most` is 50)**

`TASKUARY_HOME=$(mktemp -d) python -m pytest -q tests/test_quick_work.py::test_fifty_arrivals_run_eight_at_a_time_and_take_no_desk`

- [ ] **Step 3: Implement** `POOL` and the `with POOL:` around the call in `start`.

- [ ] **Step 4: Run the whole file (expect PASS)**

`TASKUARY_HOME=$(mktemp -d) python -m pytest -q tests/test_quick_work.py`

- [ ] **Step 5: Commit**

```bash
git add taskuary/quickwork.py tests/test_quick_work.py
git commit -m "Quick general work: at most eight quick calls at once, apart from the agent cap

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Wire it into the auto-start and the follow-up path

**Files:**
- Modify: `taskuary/ingest.py` (`_auto_general`, `_pass_general`, `_carry_on`)
- Test: `tests/test_quick_work.py`, plus the unchanged `tests/test_auto_start.py`, `tests/test_reply_needs_agent.py`, `tests/processing/test_auto_start_preservation.py` and `tests/test_danger_holds_start.py` as the guard that `auto_start_ok` still decides

**Interfaces:**
- Consumes: `quickwork.takes`, `quickwork.only_quick`, `quickwork.start`, `quickwork.ask`, `GeneralSession.file_quick`, `ingest._pass_turn(msg)`.
- Produces:
  - `_auto_general(store, tid, brief=None, deep=False)`: when `not deep and quickwork.takes(store, tid)`, it returns `quickwork.start(store, tid, brief)` before the cap check. Every door already passes `auto_start_ok` before it gets here: arrival, `agent_on_reply`, release, reroute, the Advisor and workflows. So the gate is unchanged, and a workflow or hand-off task that triage never judged reads as deep.
  - `_pass_general(store, tid, msg)`: when the live session `ses.quick` and `quickwork.takes(store, tid)` hold, the new line becomes another quick run on that session, `quickwork.again(store, tid, ses, _pass_turn(msg))`, filed `as_owner=False`. Otherwise `send_prompt` runs as today.
  - `quickwork.again(store, tid, session, turn: str) -> str`: the pooled call, then `session.file_quick(turn, out, steps, as_owner=False)`, or `escalate`. The escalation's deep start reuses the live quick session, because `start_session` returns `session_for(tid)`.
  - `_carry_on`: when nothing is live and `general.handles(t) and quickwork.only_quick(store, tid) and quickwork.takes(store, tid)` hold, it spawns `quickwork.start(store, tid, _pass_turn(msg), False)` in place of `_continue_general`, after `carry_on_why` has passed and before the cap check. Otherwise it behaves as today.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_quick_arrival_gets_one_call_and_no_agent_session():
    s = home(); tid, spawned = arrived(s)
    assert spawned == ['_auto_general']                                       # arrival is unchanged: auto_start_ok decided
    with mock.patch.object(quickwork, 'start', return_value='filed') as quick, mock.patch.object(ingest, '_start_general') as deep:
        ingest._auto_general(s, tid)
    quick.assert_called_once(); deep.assert_not_called()

def test_a_hard_arrival_starts_the_agent_as_today():
    s = home(); tid, _ = arrived(s, 'hard')
    with mock.patch.object(quickwork, 'start') as quick, mock.patch.object(ingest, '_start_general', return_value=True) as deep:
        ingest._auto_general(s, tid)
    quick.assert_not_called(); deep.assert_called_once()

def test_a_held_start_stays_held():
    s = home(general_auto_enabled='0'); tid, spawned = arrived(s)
    assert spawned == []                                                      # the owner's switch holds quick work too

def test_more_mail_on_a_live_quick_task_is_answered_quick_again():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'start_session', side_effect=opened), \
         mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)) as build:
        quickwork.start(s, tid)
        ingest._pass_general(s, tid, {**mail(body='Erin Blake: also, can Gail Moreno come?'), 'message_id': None})
        assert [c.kwargs['job'] for c in build.call_args_list if c.kwargs.get('job') != 'judge'] == ['quick_work', 'quick_work']

def test_more_mail_judged_hard_carries_on_as_the_general_agent():
    s = home(); tid, _ = arrived(s)
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general, 'start_session', side_effect=opened):
        with mock.patch.object(llm, 'build_llm', return_value=Brain(ANSWER)): quickwork.start(s, tid)
        s.judge_task(tid, {'difficulty': 'hard'}, 'triage')
        with mock.patch.object(llm, 'build_llm', return_value=mock.Mock(return_value='On it.')) as build:
            ingest._pass_general(s, tid, {**mail(body='Erin Blake: please book it for three of us'), 'message_id': None})
        assert build.call_args.kwargs['job'] == 'general'
```

- [ ] **Step 2: Run (expect FAIL)**

`TASKUARY_HOME=$(mktemp -d) python -m pytest -q tests/test_quick_work.py -k "arrival or held_start or more_mail"`

- [ ] **Step 3: Implement** the three edits and `quickwork.again` as listed under Interfaces.

- [ ] **Step 4: Run (expect PASS), plus the gate and follow-up suites**

`TASKUARY_HOME=$(mktemp -d) python -m pytest -q tests/test_quick_work.py tests/test_auto_start.py tests/test_reply_needs_agent.py tests/test_danger_holds_start.py tests/processing/test_auto_start_preservation.py tests/test_kind_dispatch.py tests/test_signup_routing.py tests/test_origin_roads.py`

- [ ] **Step 5: Commit**

```bash
git add taskuary/ingest.py taskuary/quickwork.py tests/test_quick_work.py
git commit -m "Quick general work: a quick task starts with one call where it would have opened the agent, and more mail re-decides

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: The replay (offline, counts only)

**Files:**
- Create: `tools/quick_replay.py`
- Test: `tests/test_quick_replay.py` (new)

**Interfaces:**
- Consumes: `quickwork.why_deep`, `quickwork.ask`, `ingest.first_ask`, `store.SQLiteStore(path)`.
- Produces:
  - `replay(store, days: int = 14, now: datetime = None, ask: int = 0) -> dict`. It covers general tasks with `CreatedAt` in the window, so `Kind` is in `general.GENERAL_KINDS` and the dock is excluded. It returns counts only: `{'general': n, 'quick': n, **{f'deep:{why}': n for why in quickwork.DEEP_WHY}}`. With `ask > 0`, it also runs `quickwork.ask` on up to `ask` would-be-quick tasks and adds `{'asked': n, 'escalated': n, 'unreadable': n, 'failed': n}`. It files nothing.
  - `main(argv)`: `python tools/quick_replay.py --db PATH [--days 14] [--ask 0]`. It copies `PATH` to a temp file before opening it, because reads such as `origin.of_task` write a cache. It sets `TASKUARY_HOME` to a fresh temp dir before importing `taskuary`. It prints one `key: count` line per count and no titles, names or text. `--db` has no default: the script never finds the owner's home itself.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_quick_replay.py
import importlib.util, json, pathlib
from datetime import datetime
from unittest import mock
from taskuary import browserview, llm
from taskuary.store import MemoryStore

spec = importlib.util.spec_from_file_location('quick_replay', pathlib.Path(__file__).parents[1] / 'tools' / 'quick_replay.py')
qr = importlib.util.module_from_spec(spec); spec.loader.exec_module(qr)

def test_counts_only_by_depth_and_reason():
    s = MemoryStore()
    a, b, c = (s.create_task({'Title': f'Northwind job {i}', 'Kind': 'general', 'OriginBase': 'owner'}, 'triage') for i in range(3))
    s.judge_task(a, {'difficulty': 'quick'}, 'triage'); s.judge_task(b, {'difficulty': 'hard'}, 'triage')
    s.judge_task(c, {'difficulty': 'quick'}, 'triage'); s.tag_task(c, browserview.WANTS, actor='triage')
    out = qr.replay(s, now=datetime.now())
    assert {k: v for k, v in out.items() if v} == {'general': 3, 'quick': 1, 'deep:difficulty': 1, 'deep:browser': 1}
    assert all(isinstance(v, int) for v in out.values())                    # counts, never text

def test_asking_counts_escalations_and_files_nothing():
    s = MemoryStore()
    a = s.create_task({'Title': 'Northwind job', 'Kind': 'general', 'OriginBase': 'owner'}, 'triage')
    s.judge_task(a, {'difficulty': 'quick'}, 'triage')
    brain = lambda *x, **k: json.dumps({'report': '', 'draft': None, 'question': None, 'done': False, 'escalate': True, 'why': 'files'})
    brain.takes_web, brain.takes_want = False, True
    before = len(s.list_comments(a))
    with mock.patch.object(llm, 'build_llm', return_value=brain): out = qr.replay(s, now=datetime.now(), ask=5)
    assert (out['asked'], out['escalated']) == (1, 1) and len(s.list_comments(a)) == before
```

- [ ] **Step 2: Run (expect FAIL: the file does not exist)**

`TASKUARY_HOME=$(mktemp -d) python -m pytest -q tests/test_quick_replay.py`

- [ ] **Step 3: Implement** `tools/quick_replay.py` as listed under Interfaces. It uses `argparse`, `shutil.copy` into `tempfile.mkdtemp()`, and `SQLiteStore(copy)`. Don't run it against any real database. The owner runs it on a copy of their own.

- [ ] **Step 4: Run (expect PASS)**

`TASKUARY_HOME=$(mktemp -d) python -m pytest -q tests/test_quick_replay.py tests/test_quick_work.py`

- [ ] **Step 5: Commit**

```bash
git add tools/quick_replay.py tests/test_quick_replay.py
git commit -m "Quick general work: an offline replay that counts which general tasks would be quick and how many escalate

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### After the last task

- [ ] Run the spec's UI proof, unchanged: the browser smoke set and the agent-presses tests (memory: `TASKUARY_BROWSER_PLAIN_ENV=1`, Node 22 + Chrome). Then run `TASKUARY_HOME=$(mktemp -d) python -m pytest -q tests/` once. Nothing under `website/` changes; if a browser test needs an edit, the UI moved and the change is wrong.
- [ ] `git grep -n "quick_work\|quickwork" -- taskuary tests tools`: every new name is used, and the names match this plan.

## Self-review against the spec

- **Coverage.**
  - `difficulty=quick` takes the quick path, and standard/hard take the deep path (T1, T6). `needs_browser` always takes the deep path (T1).
  - The prompt carries the message, the task, the thread history via `history_brief`, LEARNED.md and today's calendar (both through `context.for_prompt` inside `_prompt`), AGENT.md and the profile, and not SOUL.md (T2).
  - Lookups are the provider's web search only: no shell and no file access (T2 `QUICK_READ`).
  - The output is report, draft, question, done, escalate and why (T2), written through the same functions (T3).
  - Escalation sends the notes and a task comment to the deep path (T4). An owner's answer and Continue reach a general session (T4).
  - The pool is 8 (T5). Mail on a quick task re-decides (T6). Any brain works: CLI and API, with or without web (T2). Never auto-send / cannot act (T2 tools, T3 markers, the draft stays `pending`).
  - Strangers take the deep path (T1). `auto_start_ok` is unchanged (T6). The replay counts only (T7). Open tasks are not migrated: only tasks judged quick and with no deep run qualify (T1 `ran deep`).
- **Calls this plan makes where the spec left it to the builder:**
  - The quick call uses `general._prompt` in full, not a slimmer cut, so strangers, AGENT.md, the profile and the Hub read stay one definition.
  - It runs on its own `quick_work` slot, which resolves to the general agents' brain on the main gear.
  - A quick run is one `GeneralSession` with one `sid`, so the record, the replay and "earlier runs" show one run.
- **Calls the owner may want to check:**
  - A quick session stays parked like a general session today, so the question shows as "asked you something", but it takes no desk (`live_count`). The cap number shown elsewhere counts only real agents.
  - A task that owes several emails (`slots`) takes the deep path, and the replay counts it as `deep:emails`.
  - A failed quick call escalates to the agent rather than failing the task.
