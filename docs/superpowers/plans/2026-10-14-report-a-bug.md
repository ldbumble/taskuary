# Report a Bug Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Any error the Assistant or the bell shows offers **Report this bug**; one popup, already filled with a scrubbed
technical report and a short explanation, and Send opens GitHub's pre-filled new-issue page.

**Architecture:** The server builds the report (`taskuary/bugreport.py`: collect facts, scrub, explain) behind one
owner-only route. The client records the last error and recent actions (`website/src/lastError.js`), shows the popup
(`BugReportDialog.jsx`), and composes the issue body and URL in a pure, tested module (`website/src/bugReport.js`) so the
person's edits go straight into what is sent. A small owner-only route opens the GitHub URL in the system browser for
the desktop window.

**Tech Stack:** Python 3.10, FastAPI, pytest; React 18 + MUI 6, node:test.

**Spec:** `docs/superpowers/specs/2026-10-14-report-a-bug-design.md`

## Global Constraints

- The tracker is public: nothing the person did not see and approve leaves; mail, names, task text, repo names, user
  paths and credentials are scrubbed to `[removed]` before the person sees the draft. Scrub fails closed: on an
  exception the draft is refused with `could not prepare a safe report - copy the error yourself`.
- No GitHub token is used. Send opens `https://github.com/ldbumble/taskuary/issues/new?title=...&body=...&labels=bug`.
- The encoded URL stays under 7,500 characters; past that the technical section is cut and **Copy full report** puts the
  whole text on the clipboard.
- The routes are owner-only: agent and stranger tokens are refused (`guard` classification), and the open-URL route
  opens only `https://github.com/ldbumble/taskuary/issues/new` URLs.
- Quiet copy (the owner's taste): one small link "Report this bug" under errors; no icons, no colour alarm.
- Tests use invented people and RFC 2606 addresses only. Rebuild the committed bundle after UI changes.
- Screenshot: off by default; the blurred capture is the last task and may be dropped if it needs a dependency
  heavier than one small MIT library.

## Review Focus

1. **A private string surviving the scrub** through a field the tests did not seed - the explanation from the model,
   a log line, a route with a task id in it, an error text quoting a subject. Pinned in Tasks 2-3 with a planted-data
   test across every field.
2. **An edited popup sending more than it shows** - the URL must be built from exactly the text on screen. Pinned in
   Task 5.
3. **The desktop window not opening the browser** - pywebview may swallow `_blank`. Pinned in Task 4 (the open route)
   and Task 6 (the dialog uses it when `window.pywebview` exists).
4. **A route reachable by an agent** - the draft route reads the store; an agent or stranger token must get 403.
   Pinned in Task 4.
5. **No brain** - the draft still opens with the error's first line as title and an empty explanation. Pinned in Task 3.

---

### Task 1: `bugreport.collect` - the facts, by code

**Files:** Create `taskuary/bugreport.py`; Test `tests/test_bugreport.py`

**Interfaces:**
- Produces: `bugreport.collect(store, client: dict) -> dict` with keys `where`, `error`, `env` (str), `log` (str),
  `actions` (list[str]), `fingerprint` (str). `client` carries `screen`, `route`, `error`, `stack`, `actions`, `at` (ISO).

- [ ] **Step 1: failing tests** - `collect` returns: `env` naming `Taskuary <__version__>`, the install kind
  (`exe` when `sys.frozen`, `docker` when `/.dockerenv` exists or `TASKUARY_HOME == '/data'`, `source` when
  `pyproject.toml` sits beside the package, else `pip`), OS, Python `x.y`, brain types from `llm.brain_status` over
  `aidefaults.SLOTS` (types/CLI names only), active connector `Type`s; `log` = at most 30 lines of
  `config.home()/'taskuary.log'` nearest `client['at']` (a test writes a fake log with timestamps); `actions` = the last 5
  of `client['actions']`; `where` = `screen` + `route`; `fingerprint` = sha1 of error type + route-with-ids-normalised +
  first stack frame, 10 hex chars. Missing log -> `log == ''`, no exception.
- [ ] **Step 2: run, expect failure** (`python -m pytest -q tests/test_bugreport.py`).
- [ ] **Step 3: implement** in `taskuary/bugreport.py` (module docstring says why: the public tracker; dense style).
  Normalise routes: `/api/tasks/123/code` -> `/api/tasks/:id/code` (any all-digit segment, any 32-hex segment).
- [ ] **Step 4: pass; commit** - "A bug report's facts are collected by code: where, the error, versions, the log around it".

### Task 2: `bugreport.scrub` - nothing private leaves

**Files:** Modify `taskuary/bugreport.py`; Test `tests/test_bugreport_scrub.py`

**Interfaces:** Produces `bugreport.scrub(text: str, store) -> str`; `bugreport.Unsafe(Exception)`.

- [ ] **Step 1: failing tests** - seed a `MemoryStore` with invented people (`erin@northwind.example`, "Erin Blake"),
  a task titled "Renew the Payworth contract", a message subject/body, a connector named "alex@northwind.example",
  an agent `cwd_map` `{"northwind/ledger": "C:\\Users\\alexd\\src\\ledger"}`, owner "Alex Doyle"; text containing all of
  them plus `https://intranet.northwind.example/x`, `192.168.1.20`, `C:\Users\alexd\AppData\x.log`, `/home/alexd/x`,
  an API key shape `redact` catches. Assert none survive and `[removed]` appears; `https://github.com/ldbumble/taskuary`,
  `https://taskuary.com/docs/x`, `localhost:7787`, `127.0.0.1` survive; a user path becomes `~\AppData\x.log`.
  `scrub` raising inside (monkeypatch a lookup to raise) propagates as `Unsafe`.
- [ ] **Step 2: run, expect failure.**
- [ ] **Step 3: implement** - order: `redact.scrub`; user-folder paths -> `~`; then strings from the store
  (task Title/Summary, message Subject/BodyText/OwnText/FromName/FromEmail/recipients, `store.people`, owner name/email,
  `senders.own_addresses`, source Addresses, connector Names, `terminal.known_repos` except `ldbumble/taskuary`,
  cwd_map keys and values) - only strings of 4+ chars, longest first, case-insensitive exact substring; then emails,
  non-allowlisted URLs, non-loopback IPs and hostnames. Any exception -> `Unsafe`.
- [ ] **Step 4: pass; commit** - "A bug report is scrubbed of mail, names, task text, repos and user paths before anyone sees it".

### Task 3: the explanation and the draft

**Files:** Modify `taskuary/bugreport.py`; Test `tests/test_bugreport_draft.py`

**Interfaces:** Produces `bugreport.draft(store, client: dict, llm=None) -> dict` =
`{title, explanation, where, error, env, log, actions, fingerprint}` (every string scrubbed).

- [ ] **Step 1: failing tests** - with a fake brain recording its prompt: the prompt contains only scrubbed facts (assert
  no seeded private string reaches it), the brain's answer is scrubbed again (a fake brain that echoes a seeded name ->
  `[removed]`); title <= 80 chars; with `llm=None` and no brain, title = first line of the scrubbed error (<= 80) and
  explanation = ''. `Unsafe` from scrub propagates.
- [ ] **Step 2: run, expect failure.**
- [ ] **Step 3: implement** - `llm.build_llm(store, gear='light')`; `llm.ask_json(brain, SYSTEM, user,
  want={"title": str, "explanation": str}, max_tokens=300)`; SYSTEM: write a GitHub issue title and two or three
  sentences (what the person was doing, what happened, what was expected) from these facts only; no guessing names.
- [ ] **Step 4: pass; commit** - "A bug report's title and explanation are written from the scrubbed facts only".

### Task 4: the two owner-only routes

**Files:** Modify `taskuary/server.py`, `taskuary/guard.py`; Test `tests/test_bugreport_api.py`

**Interfaces:** `POST /api/bug-report/draft` body = client dict -> draft dict, or 422 `{detail: <unsafe sentence>}`;
`POST /api/open-url` body `{url}` -> `{opened: true}`; only URLs starting
`https://github.com/ldbumble/taskuary/issues/new` (400 otherwise).

- [ ] **Step 1: failing tests** (copy the TestClient pattern of `tests/test_problems_dismiss.py`; seed with
  `mock.patch.object(server, 'store', s)`): draft returns scrubbed fields; agent token -> 403, stranger token -> 403
  (use `guard.stranger_token`); `Unsafe` -> 422 with the sentence; open-url with the GitHub URL calls a patched
  `webbrowser.open` once; any other URL -> 400 and not opened; agent token -> 403; `tests/test_guard.py`'s
  every-write-route check stays green (classify both routes OWNER_ONLY).
- [ ] **Step 2: run, expect failure. Step 3: implement. Step 4: pass; commit** -
  "The owner's own routes draft a bug report and open GitHub's new-issue page; no session can reach them".

### Task 5: `bugReport.js` and `lastError.js` - pure client modules

**Files:** Create `website/src/bugReport.js`, `website/src/lastError.js`; Test `website/test/bugReport.test.mjs`,
`website/test/lastError.test.mjs`

**Interfaces:**
- `bugReport.js`: `issueBody(d) -> string` (the spec's template: What happened / Where / Error / Environment /
  `<details>` Log lines / fingerprint line), `issueUrl(title, body, max=7500) -> {url, cut: bool}` (cuts the
  `<details>` log first, then the Error section, never the title or What happened), `fullReport(title, body) -> string`.
- `lastError.js`: `record(err)` (keeps the last error: message, stack, route, at), `recordAction(method, url)` (keeps the
  last 5 non-GET API calls as normalised `METHOD /api/x/:id`), `snapshot(screen) -> client dict`, `last()`.

- [ ] **Step 1: failing tests** - body has every section; URL starts with the GitHub new-issue address and has
  `labels=bug`; a 20 KB log yields `cut: true`, URL length <= 7500, title and explanation intact; editing the title
  changes the URL (the URL is built from exactly the given text); `recordAction` normalises ids and keeps 5;
  `snapshot` carries the last error and actions.
- [ ] **Step 2: run, expect failure** (`cd website && npm exec --yes --package=node@22 -- node --test test/bugReport.test.mjs test/lastError.test.mjs`).
- [ ] **Step 3: implement. Step 4: pass; commit** - "The issue body and its link are built from exactly what the popup shows".

### Task 6: the popup and where it opens

**Files:** Create `website/src/BugReportDialog.jsx`; Modify `website/src/api.js` (response-error interceptor ->
`lastError.record` + request interceptor -> `recordAction` for non-GET), `website/src/main.jsx` (`Boundary.componentDidCatch`
-> `record`; `window.onerror` and `unhandledrejection` -> `record`), `website/src/assistantStream.js` (stream errors ->
`record`), `website/src/AssistantView.jsx` (receipt `status === "error"` gets the link at ~610; the page-level `err` line
at ~2181 too), `website/src/TaskHubPage.jsx` (Bell item link after Dismiss ~114; the Help icon ~396 opens the dialog
instead of `SUPPORT_URL`); rebuild `taskuary/web`.

- [ ] **Step 1:** `BugReportDialog({open, onClose, screen, error})` - on open POSTs `lastError.snapshot(screen)` (with the
  given error merged) to `/api/bug-report/draft`; shows Title (TextField), What happened (multiline), Technical details
  (collapsed, editable, monospace), the line "This goes to a public GitHub page. Check it before you submit.", buttons
  **Copy full report** and **Send**. Send: `issueUrl(title, issueBody(...))`; if `cut`, copy `fullReport` to the
  clipboard first and say so; then if `window.pywebview` POST `/api/open-url {url}`, else `window.open(url, "_blank",
  "noopener")`. On 422 show the unsafe sentence and only Copy (the raw error text). Follow
  `NewPlaybookDialog.jsx`'s Dialog pattern.
- [ ] **Step 2:** wire the four entry points; the link text is exactly "Report this bug", small, DIM.
- [ ] **Step 3:** `cd website && npm exec --yes --package=node@22 -- npm run build`; `npm test` (`# fail 0`);
  `python -m pytest -q tests/test_api.py -k index_serves`.
- [ ] **Step 4: commit** (`git add` the src files and `git add -A taskuary/web`) -
  "Every error the Assistant or the bell shows offers Report this bug, and Help opens the same popup".

### Task 7: optional blurred screenshot

**Files:** `website/src/BugReportDialog.jsx`, `website/package.json` (only if a dependency is needed)

- [ ] **Step 1:** check whether a capture is possible without a dependency (e.g. SVG `foreignObject` of the app root
  with a CSS rule that blurs every text node, drawn to a canvas). If not, use `html-to-image` (one MIT package); if
  neither is clean, drop this task and leave the checkbox out of the dialog (record it in the report).
- [ ] **Step 2:** "Add a screenshot" checkbox, off by default; when ticked, capture with text blurred, put the PNG on the
  clipboard (`navigator.clipboard.write([new ClipboardItem({'image/png': blob})])`), and add "Paste the screenshot here."
  to the body. Test the body line in `bugReport.test.mjs`.
- [ ] **Step 3:** build, web tests, commit.

### Task 8: docs, gates, merge

- [ ] **Step 1:** `docs/site/troubleshooting.md`: a short "Report a bug" section (what is sent, that it is scrubbed and
  previewed, that you press Submit on GitHub). Rebuild `site/docs`; commit only real changes.
- [ ] **Step 2:** full gates from the worktree root: `python -m pytest -q` (agent env vars unset) and `npm test` in
  website (Node 22). Then rebase onto `origin/master` (rebuild the bundle on conflict), re-run the gates, and push
  `HEAD:master` only when `origin/master` is the merge base.
