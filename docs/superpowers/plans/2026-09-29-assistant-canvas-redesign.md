# Assistant canvas redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One screen - a narrowed work rail on the left drives the app, and the assistant canvas on the right shows the
task view, agent sessions and the Connections/Settings/Reports/Hub cards inside the conversation; the tab strip goes.

**Architecture:** The rail (`FeedView` + `AssistantView.Pile`) keeps today's look at ~340px with a button stack on top.
Levels move to `funnelPile.LEVEL_ORDER = urgent, task, agents, later, reports, ideas, fyi`, mirrored server-side by
`funnel.level_of` so a section walk (`section` on `/api/concierge/next`) agrees with the rail. The Tasks tab's detail
pane is extracted as `TaskPage.jsx` and becomes the walk's only item card. Browsing is client state in a new
`CanvasBrowse.jsx` that mounts the existing editors (ConnectorsView card, SettingsView group, ReportsView editor,
HubView). `TaskHubPage` drops the tab strip for Brand · Board · icons, and deep links open canvas cards.

**Tech Stack:** React 18 + MUI 6 (website/src, vite), FastAPI + SQLite (taskuary/), node --test source/pure tests,
pytest, puppeteer-core screenshot gates against `taskuary --demo`.

**Spec:** `docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md` · mockup
https://claude.ai/artifact/1mGxS2sJGWXFtwcc1nx9Qp (boards Main / Browse / Phone).

## Global Constraints

- Every card keeps the look of the tab it comes from; only the width changes.
- Rail: today's spine, source dot, 58px age gutter, category pills, bordered rows (11.5px/500 titles), ON THE TABLE pill.
- Sidebar ~340px (mockup 340; spec "~320"): buttons New · Reports · Connections · Hub · Settings, one line each; then a
  full-width `Work | Timeline` selector with the filter as a small icon button beside it; then counts / checked / Sync now.
- Only the rows scroll; the buttons, selector and Sync line stay fixed; section headings stick (`.tq-pile-head`).
- The Sync now line never moves or wraps.
- Sections in order: On you · Agents working · For later · Reports · Advisor ideas · FYI.
- For later gutter = time until it comes back, `railAge` short form (`< 30m`, `3h`, `2d`), soonest first.
- `fillCaps` unchanged in rule: reports, ideas and fyi divide what is left; work is never capped.
- No terminal grows after first output (ConPTY corruption). Fold/unfold/expand/Back never request `/api/funnel/pile`.
- At most one TaskPage, one terminal and one browse detail mounted.
- Irreversible actions still wait for a yes on the card.
- Public repo: only invented people and RFC 2606 domains in tests, fixtures, commits (repo CLAUDE.md).
- Build the bundle in this worktree only; `taskuary/web` is committed with its source in the same commit.
- Node 22 for tests: `npm exec --yes --package=node@22 -- node --test "test/**/*.test.mjs"`; vite build via
  `npm exec --yes --package=node@22 -- node node_modules/vite/bin/vite.js build`.

## Screenshot gate (run after every task)

`website/canvas_shots.mjs <url?token=> <outdir> <label>` (created in Task 0) shoots against a demo server
(`TASKUARY_HOME=<scratch> TASKUARY_ALLOW_TEST_HOME=1 python -m taskuary.cli --demo --no-browser --port 7791`) at 1440x900
and 390x844: the rail (top, scrolled, each section heading, For later, filter popover open, Timeline mode), each sidebar
button's result, the item on the table for every card kind the demo pile holds (task with agent, task without, fyi,
report, idea), expanded, folded earlier items, and each browse level (sections, list, one, Back). It logs hscroll,
xterm boxes, and whether `/api/funnel/pile` was requested during client-only actions. Every shot is read and compared
with the mockup and today's tabs; anything off is fixed before the task's ledger line.

## Review Focus

1. A For later row whose return time has already passed - it must leave For later (back on you), never show a negative age.
2. Clicking a section heading while an item is on the table and the section then empties - Next says "<Section> done" once and resumes the normal walk, no loop.
3. An item that stops having a task mid-view (task closed from the agent) - TaskPage must fall back to the message card, not blank.
4. A phone-width window resized to desktop with the drawer open - rail must come back docked, canvas not hidden.
5. Deep link to a connector/setting that no longer exists - the canvas says so, it does not crash or open an empty card.

---

### Task 0: Screenshot harness

**Files:** Create `website/canvas_shots.mjs`.

- [ ] Write the harness (puppeteer via `browser.mjs` `launch`), two viewports, `hush()` toasts, request log for `/api/funnel/pile`, writes `<label>-<w>-<name>.png` + `facts.json`.
- [ ] Run it against a demo server on today's build; read every shot; this is the baseline "today's tabs" set.
- [ ] Commit `test: canvas screenshot harness`.

### Task 1: Rail levels - For later, Advisor ideas, new order (client)

**Files:** Modify `website/src/funnelPile.js` (LEVEL_META, LEVEL_ORDER, levelOf, LEVEL_ROLE, CAPPED, new `railBack`,
`backAt`); `website/src/AssistantView.jsx` (Pile gutter for `later`, BAND_SAYS); Test `website/test/funnelPile.test.mjs`.

**Interfaces - Produces:**
- `LEVEL_ORDER = ["urgent","task","agents","later","reports","ideas","fyi"]`
- `levelOf(item)`: `"later"` when `item.deferred` or (`item.surfaced` and band 2); `"ideas"` when `item.kind==="idea"` and band 4; else as today.
- `backAt(item)` -> ISO string | null: `item.back_at` (server) else `item.defer_until`.
- `railBack(iso, now)` -> `"< 30m" | "<n>h" | "<n>d"` for a future time; `""` for past/none.
- `CAPPED = ["reports","ideas","fyi"]`; `LEVEL_META.later.word = "for later"`, `LEVEL_META.ideas.word = "advisor ideas"`, `LEVEL_META.agents.word = "agents working"`, `LEVEL_META.task.word = "on you"`, urgent folds into On you's heading.

- [ ] Failing tests: level order; idea -> ideas; deferred -> later; surfaced band-2 -> later; railBack forms incl. past -> ""; later band sorted soonest first (`bandsOf`); fillCaps caps ideas.
- [ ] Run `node --test test/funnelPile.test.mjs` - FAIL.
- [ ] Implement; run - PASS; full node suite.
- [ ] Commit.

### Task 2: Server - back_at, level_of, section walk

**Files:** Modify `taskuary/funnel.py` (`level_of`, `back_at` on items, `next_item(..., section=None)`),
`taskuary/concierge.py` (`surface(..., section=None)`, "FYI done" line), `taskuary/server.py` (`SurfaceBody.section`,
`ConciergeStreamBody.section`, bypass captured selection when `section` is set); Test `tests/test_canvas_sections.py`.

**Interfaces - Produces:** `funnel.level_of(item) -> str` (same rules as `funnelPile.levelOf`);
`funnel.SECTION_WORDS = {'task':'On you','agents':'Agents working','later':'For later','reports':'Reports','ideas':'Advisor ideas','fyi':'FYI'}`;
`POST /api/concierge/next {section}` -> first eligible item of that level (a named surface), or
`{item: None, say: "<Section> done", section_done: section}`.

- [ ] Failing tests on a temp store: level_of mirrors the JS for each lane/kind; back_at = surfaced_at + return_minutes and = RemindAt for a deferred task; section walk returns only that level and never the excluded current; empty section says "FYI done" and returns section_done.
- [ ] Implement; `pytest tests/test_canvas_sections.py` PASS; full pytest.
- [ ] Commit.

### Task 3: Sidebar chrome

**Files:** Modify `website/src/FeedView.jsx` (rail width `clamp(320px, 24vw, 360px)`, header: button stack
`SideNav`, full-width Work|Timeline group + filter icon, New moved to the stack), `website/src/AssistantView.jsx`
(heading click -> `walkSection(level)`; Next carries `section` until `section_done`), `website/src/TaskHubPage.jsx`
(`onNavigate` from the stack opens the existing tabs for now); Test `website/test/feedViews.test.mjs`, `website/test/canvasSidebar.test.mjs`.

**Interfaces - Produces:** `FeedView` prop `nav: {onNew, onGo(where)}`; Pile prop `onSection(level)`; `data-tq-section-head={level}` on headings; `data-tq-sidenav` on the stack.

- [ ] Failing source tests: nav stack order; Feed views group full width; filter is an IconButton with a tooltip naming the filter; rail clamp; heading click handler.
- [ ] Implement; node suite PASS; build; screenshot gate; fix.
- [ ] Commit (source + bundle).

### Task 4: Extract TaskPage

**Files:** Create `website/src/TaskPage.jsx` (the detail pane: state, effects, handlers, JSX lines 1099-2000 of
TasksView); Modify `website/src/TasksView.jsx` (list + `<TaskPage/>`); Test `website/test/taskPage.test.mjs`
plus all existing Tasks tests unchanged.

**Interfaces - Produces:** `TaskPage({ taskId, listRow, waitingN, active, autostart, onAutostarted, openAct, onActOpened, onChanged, onClose, onGoReports, compact=false, extraBar=null, onNext=null, canvas=false })`.

- [ ] Move code verbatim; every reference to `tasks`/`loadTasks`/`onSelect` becomes a prop.
- [ ] Node suite (existing TasksView regex tests may re-point to TaskPage.jsx - ledger each); lint:undef via esbuild; build; gate: Tasks tab shots identical to baseline.
- [ ] Commit.

### Task 5: The walk shows TaskPage

**Files:** Create `website/src/CanvasItem.jsx` (item on the table: TaskPage when `tid`, else message/report/idea first
card with Next/Make a task/Send to agent/Not ours/Mark read; Expand); Modify `AssistantView.jsx` (earlier items fold to a
title line, click re-surfaces; only the current is live), `TaskPage.jsx` (`canvas` mode: agent stage near full height,
Task/Close out collapsed to headers; Next on the bar), `taskuary/concierge.py` (turn context adds the agent's state,
last witness message and open question for the item on the table); Tests `website/test/canvasItem.test.mjs`,
`tests/test_canvas_relay.py`, `website/test/terminalGeometry.test.mjs` (pty opens at expanded size; fold clips).

- [ ] Failing tests: fold state is client-only (no api call in fold/expand handlers); one TaskPage; relay context contains the agent tail.
- [ ] Implement; remove the old per-kind walk cards from the item path; suites; build; gate incl. request log shows no pile fetch on fold/expand.
- [ ] Commit.

### Task 6: Browse pattern

**Files:** Create `website/src/CanvasBrowse.jsx` (sections -> list -> one -> Back, for connections/settings/reports/hub);
Modify `ConnectorsView.jsx`, `SettingsView.jsx`, `ReportsView.jsx` (export the single-card/group/editor pieces),
`AssistantView.jsx` (sidebar buttons post browse cards; open card key is the chat context); Test `website/test/canvasBrowse.test.mjs`.

- [ ] Failing tests: Back restores list without fetch; one detail mounted; chips from catalogue groups / settings schema groups.
- [ ] Implement per area; suites; build; gate.
- [ ] Commit per area.

### Task 7: Remove the tabs; deep links

**Files:** Modify `TaskHubPage.jsx` (Brand · Board · icons; `#task=`, `#settings=`, `#connector=`, `#report=` open canvas cards); Test `website/test/deepLinks.test.mjs`.

- [ ] Failing tests; implement; suites; build; gate (ui_audit.mjs desktop + mobile).
- [ ] Commit.

### Task 8: Phone

**Files:** Modify `AssistantView.jsx`/`FeedView.jsx` (drawer, full-width canvas, agent session full screen with back),
`taskuary/remote_assistant.py` (section picks, For later come-back times, task view as three parts, agent relay);
Tests `tests/test_remote_sections.py`, `website/test/canvasPhone.test.mjs`.

- [ ] Failing tests; implement; suites; build; gate at 390.
- [ ] Commit.
