# Task View, Onboarding and Shutdown Implementation Plan (Stream D)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. (Executed directly by the Stream D fork on 2026-09-06 because forks may not spawn subagents.)

**Goal:** Quitting Taskuary waits for cleanup and leaves interrupted work visibly interrupted; every task-view control says what it does and runs through the shared operations road; assistant ideas have their triage matrix tested; the setup walkthrough gets its procedure from a shipped skill; browser control gets its review.

**Architecture:** `taskuary/desktop.py` gains a bounded `stop_server` that joins the server thread so the lifespan's cleanup (sessions, CLI children, drain) actually runs. `terminal.release_task` tags a task `interrupted` when shutdown or startup released it and the dispatch road clears the tag. `website/src/taskOps.js` is one helper that proposes and executes an operation; TasksView uses it for complete, reopen, coding dispatch and agent stop, and every button carries a caption stating task-vs-agent effect. A shipped `taskuary/templates/skills/taskuary-setup/SKILL.md` is appended to a setup task's worker prompt as its procedure.

**Tech Stack:** Python 3.10 / FastAPI / SQLite / pytest (unittest style); React + MUI, Node 22 `node --test` on JSX source text.

**Spec:** `docs/processing-walkthrough-todos.md` — PW-215..221 (lines 1215-1246), PW-188..193 (1074-1102), PW-202 (1153), PW-261..264 (1466-1484), PW-265..267 (1485-1499).

## Global Constraints

- Dense fast.ai code style; no formatters. Preserve each file's line endings (server.py CRLF, others LF). No backslash line-continuations through heredocs.
- Every button runs through the shared proposal/execute road (`POST /api/operations` → `POST /api/operations/{id}/execute`), never a second code path (owner, 2026-09-06). "Do not add phrase interpretation to button clicks" (PW-215).
- No hardcoded words or regex intent routing anywhere new.
- Colour identifies, never tints a whole surface.
- Tests from the worktree root: `python -m pytest -q -p no:cacheprovider`; JSX tests `npm exec --yes --package=node@22 -- node --test "test/**/*.test.mjs"` inside `website/` after `npm ci`; rebuild the bundle once at the end if JSX changed.
- Owner-approved text (PW-217): "Mark task done currently closes the live worker too; Reopen task changes task status without starting a worker." (PW-219): "Pause & save means end the session with saved continuation context, not suspend a live process. Keep Stop session distinct." (PW-218): "do not imply the full completion workflow happened when only a result was saved."
- The browser harness runs in demo mode where mutating requests are denied, so button behaviour is proven by backend TestClient tests plus JSX source tests, and that limit is stated in the docs.
- Nothing is pushed or merged; the branch stops at a review gate.

---

### Task 1: Orderly desktop shutdown with a bounded wait (PW-261, PW-263)

**Files:** Modify `taskuary/desktop.py`; Test `tests/test_desktop.py`.

**Interfaces:** `desktop.start_server(host, port) -> (server, url, thread)`; `desktop.stop_server(server, thread, timeout=30.0) -> 'clean' | 'timeout' | 'not_running'`; `desktop.SHUTDOWN_WAIT = 30.0`.

- [ ] Test: `start_server` returns a live thread; `stop_server` returns `'clean'` and the thread is dead; a fake server whose thread ignores `should_exit` returns `'timeout'` within `timeout + 1` seconds and logs; `main()`'s browser-fallback loop ends when `should_exit` is set.
- [ ] Implement: keep the thread; after `webview.start()` returns (or the fallback loop ends) call `stop_server`; log "waiting for the server to finish cleanup" and the outcome; on `'timeout'` log an error naming what is unverified and return non-zero from `main()`.
- [ ] Run `python -m pytest tests/test_desktop.py -q -p no:cacheprovider`; commit `feat: quitting the desktop waits for the server's cleanup, bounded, and says when it could not (PW-261, PW-263)`.

### Task 2: Interrupted work is visible and continues only on request (PW-262)

**Files:** Modify `taskuary/terminal.py` (`release_task`), `taskuary/server.py` (`_dispatch_task_to_its_agent`, `start_session` path), `taskuary/store.py` (tag helpers if absent), `website/src/TasksView.jsx` (chip); Test `tests/test_terminal.py` or new `tests/test_interrupted_work.py`, `website/test/taskControls.test.mjs`.

**Interfaces:** `terminal.INTERRUPTED = 'interrupted'` tag; `release_task(store, tid, actor, note)` adds the tag when `actor in ('shutdown', 'startup')`; `store.add_tag(tid, tag)` / `store.remove_tag(tid, tag)` (implement on `Tags` comma string if absent); the dispatch road removes the tag when a worker starts.

- [ ] Test: `recover_after_restart` leaves the task `open` with the `interrupted` tag and a comment; `_dispatch_task_to_its_agent` (mock the session start) removes the tag; a plain WebSocket detach does not release the task (assert `release_task` not called when a subscriber leaves — use the Term `subs` mechanism found in terminal.py); JSX test: TasksView renders an `Interrupted` chip keyed on the tag and no auto-dispatch on reopen (`patch({ Status: "open" })` never calls dispatch).
- [ ] Implement; run the covering tests; commit `feat: interrupted work stays open and says so; continuing is the owner's click (PW-262)`.

### Task 3: Every task-view control says what it does (PW-217, PW-218, PW-219, PW-220)

**Files:** Modify `website/src/TasksView.jsx` button region (lines ~890-1160); Test `website/test/taskControls.test.mjs`.

Captions (exact copy, `Typography variant="caption"` under each control group, or `Tooltip title`):
- Mark task done — "Closes the task and ends the live agent session with it."
- Reopen task — "Reopens the task only. No agent starts until you choose one."
- Finish agent run → relabel "Save result & end session" — "Saves the agent's result and report and ends the session. The task stays open: Mark task done completes it and drafts the reply."
- Save stopped run result — "Saves the stopped session's result and report. The task stays open."
- Pause & save → relabel "End session & save handover" — "Ends the session and saves a handover note for the next one. Nothing keeps running."
- Stop session — "Ends the session without a report or handover. The task keeps its state."
- Write reply / Generate reply — "Opens a draft in Review. Nothing is sent until you approve it."
- Ask sender — "Drafts a question to the sender. It waits in Review for your approval; nothing is sent now."
- Review changes — "A viewer of the agent's diff. Nothing is approved or committed here."

- [ ] Test (source text): each label and caption present; `wrapUp` posts `{ close: false }`; `openReply` posts `{ draft: generate }` and never a send route; `Ask sender` posts to `/clarify`.
- [ ] Implement; run `npm exec --yes --package=node@22 -- node --test "test/**/*.test.mjs"`; commit `feat: task-view controls say what they do to the task and to the agent (PW-217..PW-220)`.

### Task 4: Task-view controls run through the shared operations road (PW-215, PW-216)

**Files:** Create `website/src/taskOps.js`; Modify `website/src/TasksView.jsx` (`finish`, Reopen, `startCodingAgent`, `stopAgent`); Test `tests/test_task_controls_operations.py` (TestClient), `website/test/taskControls.test.mjs`.

**Interfaces:** `runOperation(api, kind, target, params) -> execute result` (propose then execute with the returned version; throws the execute error detail); `finish("done")` → `task.complete`; Reopen → `task.reopen`; `startCodingAgent` → `dispatch.prepare {kind:'coding', agent, model, instructions}` then `setTerm(result.session)`; `stopAgent` → `agent.stop`.

- [ ] Backend test: propose+execute `task.complete` on a task with a live session (mock `hub_term.session_for`/`close`) closes the task and stops the session; `task.reopen` reopens without starting a worker; `dispatch.prepare` with an unknown agent → 422 error in the execute result and no task change; `dispatch.prepare` while a worker is live → 409, no duplicate start; executing the same proposal twice → the second is refused as stale/duplicate.
- [ ] JSX test: the four handlers call `runOperation` with those kinds; no `api.patch(... Kind: "coding")` remains in `startCodingAgent`.
- [ ] Implement; verify `start_session(store, tid, agent, model, instruction)` picks the task's repository itself (read it first; if it needs `repo`/`cwd`, extend `DispatchBody` with optional `repo`/`cwd` and pass them through `dispatch.prepare` params rather than reintroducing `openTerm`).
- [ ] Run pytest + website tests; commit `feat: task-view controls run the shared operations road; coding starts through dispatch (PW-215, PW-216)`.

### Task 5: Idea-triage matrix tests (PW-202)

**Files:** Test `tests/test_ideas_triage.py` (extend).

- [ ] Add: an urgent idea ranks urgent through the shared order; a duplicate report run creates no second idea/task; report triage off leaves informational report rows untriaged while workflow triggers and worker-status paths are untouched (find the setting the report card uses — grep `triage` in `taskuary/reports.py`/`assistant.py`).
- [ ] Run; commit `test: the idea-triage matrix - urgent, duplicate runs, triage off, no retrigger (PW-202)`.

### Task 6: A shipped setup skill and the visible setup entry (PW-190, PW-189)

**Files:** Create `taskuary/templates/skills/taskuary-setup/SKILL.md`; Modify `taskuary/general.py` (`_prompt`: append the skill for `SourceRef == 'assistant:setup'` tasks as `PROCEDURE FOR THIS JOB`), `website/src/AssistantView.jsx` (header button "Set up Taskuary" calling the existing `setup()`); Test `tests/test_setup_skill.py`, `website/test/setupEntry.test.mjs`.

- [ ] Skill content: prerequisites (owner name, one AI brain: CLI or API key, one inbound source), the tabs' own roads (Connections cards, Reports composer, Docs), verification (test endpoints, first sync), what never happens in chat (secrets), how to inspect existing configuration (`/api/setup` state), resume rules (never redo a done step, never create a duplicate connector/report).
- [ ] Tests: a setup task's worker prompt contains the skill's heading and a non-setup task's does not; the Assistant header exposes the entry after onboarding (source test) and it calls `setup()` not a wizard route.
- [ ] Commit `feat: the setup walkthrough reads a shipped skill; the entry is on the Assistant header (PW-189, PW-190)`.
- PW-188, PW-191, PW-192, PW-193 stay open: they redesign SetupWizard.jsx (599 lines) around name + CLI only and move style generation into the assistant with preview/confirm; that needs the owner's decision on which wizard steps move and is recorded as a note under each.

### Task 7: Browser control review (PW-265, PW-266, PW-267)

**Files:** Modify `docs/processing-walkthrough-todos.md` (notes under each; items stay unticked — owner review required).

- [ ] Trace `taskuary/browserview.py` and its UI (grep `browserview`, `WANTS`, `BrowserPane`), then write under each item: findings (who owns the browser, when it opens, what is visible, manual takeover, relation to chat and task workspace; navigation vs consequential actions, credentials, cancellation, recovery) and one proposed decision each. Commit `docs: browser-control review findings for the owner (PW-265..PW-267)`.

### Task 8: Gates, acceptance record

- [ ] Full pytest; website tests; `node --test taskuary/whatsapp/`; `npm run build` in website/ (JSX changed).
- [ ] Tick PW-261, 262, 263, 264 (264: cite tests), 215..221 (221: cite tests + the demo-mode limit), 202, 189, 190 with one evidence line each; ledger rows → `implemented` with test files; evidence block. Commit `docs: record Stream D acceptance (PW-189, PW-190, PW-202, PW-215..221, PW-261..264)`.
- [ ] Stop at the review gate.
