# Close out in the agent's chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** On a non-coding task the agent's chat is the task's whole conversation - triage's reading on top, the work folded under "Working on this…", each turn ending in What this is about / What I did / Next steps with the draft cards and On you steps inside it - and Close out stops being a section there. Coding tasks do not change.

**Architecture:** Triage's existing call grows a `thread` object, kept on the route and copied to `task.ThreadJson`. A review gains `AnswersMid` (delivery target) beside `MessageId` (freshness) and `DraftWhy`. The general agent gets one goal and ends turns with a `[[TASKUARY-SUMMARY]]` block parsed like the other selfclose markers; the page draws `[from, agent]` where the chat is the task's home.

**Tech Stack:** Python 3 + SQLite (`taskuary/`), unittest/pytest; React + MUI built by Vite into the committed `taskuary/web`; node:test (`website/test`); browser tests (`website/browser`, `harness.mjs`).

**Spec:** `docs/superpowers/specs/2026-11-04-closeout-assistant-design.md`

## Global Constraints

- Invented people only: Alex Doyle, `alex@northwind.example`, Northwind, Ray Colton, Gail Moreno, Erin Blake, RFC 2606 `*.example`; never a real name, company or address in code, tests, fixtures, comments or commits (TQ-1258 goes in by its shape only).
- fast.ai dense style; keep each file's line endings (several `taskuary/*.py` and `templates/triage.md` are CRLF); no black/yapf/autopep8/prettier.
- `toolcatalog.block()` under 7950 characters (`tests/test_assistant_lines_kept.py`, `test_assistant_meeting.py`, `test_assistant_whole_app.py`).
- `tests/test_verdict_shape.py` keeps the contract line (`templates/triage.md` "JSON only:"), the wire schema (`triage.verdict_schema`) and the CLI retry (`need=('title', 'summary')`) in step.
- After any `website/src` change: `cd website && npm run build`, then `git checkout -- 'taskuary/web/OFL-*.txt'`; commit `taskuary/web` with the source.
- Python: `TASKUARY_HOME=$(mktemp -d) python -m pytest <files> -q`. Node: `cd website && npm exec --yes --package=node@22 -- node --test <files>`. Browser: `cd website && TASKUARY_BROWSER_PLAIN_ENV=1 npm exec --yes --package=node@22 -- node --test --test-concurrency=1 <files>`.
- `website/deadend_check.mjs` `WALK_SKIP` gives a reason for any verb the walk never presses.
- Commit from bash; every message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- No keyword rules (aside, the ask, a correction are the model's to say); never an auto-send, auto-close, second copy of a draft, or text typed into a coding terminal.

## Review Focus

1. Every mail after the ask is thanks, or every mail is: `asks` is empty, so delivery falls back to `MessageId` as today (test in Task 2.2).
2. Older verdicts with no `thread` or a partial one (`{"asking": "x"}`, a string `mid`, `aside: null`) are "no reading" everywhere, never an exception (tests in Tasks 1.1, 1.3).
3. A turn that ends without the SUMMARY block, or with broken JSON in it: today's display, no summary row, On you items untouched (test in Task 3.5).
4. A task going general→coding with a pending draft: three sections again and the summary stops drawing the card - one home (test in Task 4.1).
5. Two pending drafts in one conversation with `AnswersMid` on different mails: each Send, envelope and "Answering" line uses its own; an aside mail stales neither (test in Task 2.4).
6. A chat source (Teams, monday.com) has no reply-all: `AnswersMid` changes which line is answered, never adds recipients (test in Task 2.3).

---

## Phase 1 - Triage's thread reading

### Task 1.1: The verdict's `thread`

**Files:** Modify `taskuary/triage.py` (`verdict_schema` ~232-318, bullets ~168-189, `classify_intent` guide appends ~880-900 and output ~935-990), `taskuary/templates/triage.md` (bullets ~127-151, contract ~182). Tests: create `tests/test_thread_reading.py`; modify `tests/test_verdict_shape.py`.

**Interfaces:** `triage.THREAD_SCHEMA` (`type ['object','null']`, `additionalProperties False`, required `asking, your_part, others[{who,did}], asks[{mid:int,about}], aside[{mid:int,why}], on_you[str]`) added to every schema; `triage.THREAD = _bullet('thread')`; `triage.thread_of(j: dict, earlier: set) -> dict | None` (strings trimmed - `asking`/`your_part` 300, others 200; lists cut to 6; a mid kept only if `int(mid) in earlier | {0}`, 0 = the mail being judged; missing keys filled; None when `j['thread']` is not a dict or nothing survives); `classify_intent` sets `out['thread']`.

- [ ] Failing tests (`tests/test_thread_reading.py`): `test_the_schema_asks_for_the_reading_on_every_verdict` (`verdict_schema()['schema']['properties']['thread']['type'] == ['object','null']`, required set as above); `test_a_reading_keeps_only_mids_it_was_shown` (`asks [{mid 11},{mid 99}]`, `aside [{mid 0, why 'thanks only'}]`, earlier `{11,12}` -> asks `[{'mid': 11, 'about': 'pay date'}]`, aside kept); `test_an_older_or_partial_reading_is_no_reading_or_filled` (`thread_of({}, set()) is None`; `thread_of({'thread': 'text'}, set()) is None`; `thread_of({'thread': {'asking': 'x'}}, set())['asks'] == []`; `thread_of({'thread': {'asks': [{'mid': 'eleven'}], 'aside': None}}, {11}) is None`); `test_classify_carries_the_reading` (fake brain, `thread={'exchange': ['[#11] Ray Colton · 11-02 09:00: when do you pay?']}` -> `out['thread']['asks'][0]['mid'] == 11`). In `test_verdict_shape.py`: `test_the_contract_line_names_the_thread_reading` (`'"thread": {"asking"'` in the JSON only line; a CLI brain answering title+summary without thread is asked once).
- [ ] Run `TASKUARY_HOME=$(mktemp -d) python -m pytest tests/test_thread_reading.py tests/test_verdict_shape.py -q`; expect `AttributeError: ... 'thread_of'` / `KeyError: 'thread'`.
- [ ] Implement: schema entry unconditional; `if '**thread**' not in base: system += '\n\n' + THREAD` beside the WATCH append (~897); `if (th := thread_of(j, earlier_ids)): out['thread'] = th` after rests_on. In triage.md one bullet line `- **thread** - for every verdict: …` (builder's words; must say mids are the `exchange` `[#n]`, 0 is this message, `asks` holds the mail(s) carrying the ask, `aside` the mails that do not change it) and `"thread": {"asking": "...", "your_part": "...", "others": [], "asks": [], "aside": [], "on_you": []}` inside the contract braces.
- [ ] Run again plus `tests/test_profile_is_a_role.py tests/test_agent_profiles.py`; pass.
- [ ] `git add taskuary/triage.py taskuary/templates/triage.md tests/test_thread_reading.py tests/test_verdict_shape.py && git commit -m "Triage reads the whole thread on every verdict: who asks what, the owner's part, the mails that are aside"`.

Note: triage already gets the thread so far - `ingest.judge` passes `exchange_lines(..., ids=True)` as `exchange` (ingest.py:651).

### Task 1.2: Triage sees its last reading and the agent's report

**Files:** Modify `taskuary/ingest.py` `thread_task` (~1669-1678). Test: `tests/test_thread_reading.py`. Do after Task 1.3.

**Interfaces:** `thread_task(store, tid)` adds `'reading'` (`store.task_thread(tid)`) and `'agent_said'` (newest `wrapup.is_report` comment through `wrapup.report_body`, cut to 600), each only when present.

- [ ] Failing `test_the_thread_task_carries_the_last_reading_and_report` (ThreadJson `asking 'Ray wants the pay date'`, comment `'AGENT REPORT\nSummary: the pay run is Friday'` -> `ht['reading']['asking']`, `'Friday' in ht['agent_said']`). Run; `KeyError: 'reading'`.
- [ ] Implement; run; pass. Commit `taskuary/ingest.py tests/test_thread_reading.py`: "Triage measures a new mail against its last reading of the thread and the agent's report".

### Task 1.3: `task.ThreadJson` and aside mids

**Files:** Modify `taskuary/store.py` (`TASK_COLS` ~124, task ALTER block ~1116-1148, `add_route` ~4895-4910). Test: `tests/test_thread_reading.py`.

**Interfaces:** module `store.thread_pinned(thread, mid) -> dict` (mid 0 -> `mid`); `add_route` stores the verdict pinned and, with `tid`, `UPDATE task SET ThreadJson=?` before the INSERT; `SQLiteStore.task_thread(task_id) -> dict | None`; `SQLiteStore.aside_mids(task_id) -> set[int]` (union over the task's route `VerdictJson`, unreadable rows skipped); column `task.ThreadJson TEXT`.

- [ ] Failing: `test_a_route_with_a_reading_copies_it_to_the_task` (`add_route(7, tid, …, verdict={'intent': 'reply_only', 'thread': {…, 'aside': [{'mid': 0, 'why': 'thanks only'}]}})` -> `task_thread(tid)['aside'][0]['mid'] == 7`, `aside_mids(tid) == {7}`); `test_old_rows_have_no_reading` (VerdictJson `'{"intent": "fyi"}'` and `'not json'` -> None and `set()`). Run; AttributeError.
- [ ] Implement; run; pass. Commit `taskuary/store.py tests/test_thread_reading.py`: "The newest thread reading is kept on the task, with the mail's own id in place of 0".

### Task 1.4: "What's going on" and part 1 of the chat

**Files:** Create `website/src/threadReading.js`, `website/src/ThreadReading.jsx`, `website/test/threadReading.test.mjs`, `website/browser/thread-reading.test.mjs`. Modify `taskuary/server.py` `_assistant_payload` (~2229-2261), `website/src/GeneralWorkspace.jsx` (`GeneralWorkspace` ~666), `website/src/TaskPage.jsx` (Came from slot ~2865), `taskuary/demo.py` `seed` (~670: ThreadJson on one general and one reply task), `website/package.json` (`test:browser`).

**Interfaces:** `readingOf(raw) -> object | null` (string or object; null without `asking`/`your_part`); `readingLines(r, mails = [{MessageId, FromName, SentAt}]) -> [{k: "ask"|"part"|"others"|"aside"|"onyou", text}]`, aside as `` `${n} ${n === 1 ? "email is" : "emails are"} ${why}, so the reply answers ${who}'s ${M/D} email` `` (newest ask); `ThreadReading({ reading, mails, variant: "chat" | "from" })` with `data-tq-reading`, "What's going on" title on `from`. `_assistant_payload` adds `'thread': store.task_thread(task_id)`. Before any agent turn, `on_you` is text only.

- [ ] Failing node test: `readingOf('{"intent":"fyi"}') === null`; with asks `[{mid: 11}]`, aside 12 and 13 `why "thanks"`, mails `[{MessageId: 11, FromName: "Ray Colton", SentAt: "2026-11-02 09:00"}]` the aside line is `"2 emails are thanks, so the reply answers Ray Colton's 11/2 email"`. Python `test_the_chat_payload_carries_the_reading` (`server._assistant_payload(tid)['thread']['asking']`, TASKUARY_HOME temp before import). Browser: the seeded general task shows `[data-tq-reading]` atop the agent section and "What's going on" in Came from; the seeded coding task shows none in its terminal.
- [ ] Run the three; expect module missing / KeyError / no element.
- [ ] Implement; run; pass. Build; revert OFL.
- [ ] Commit the listed files + `tests/test_thread_reading.py taskuary/web`: "The task says what's going on: triage's reading on top of Came from and the agent's chat".

---

## Phase 2 - The reply target and the drafter's WHY

### Task 2.1: `review.AnswersMid`, `review.DraftWhy`

**Files:** Modify `taskuary/store.py` (review ALTER block ~1090-1114, methods ~5422-5450). Test: create `tests/test_answers_mid.py`.

**Interfaces:** `set_review_answers(rid, mid | None)`, `set_review_why(rid, why | None)` (`by_sentence(why, 400)`), guarded like `update_review_message` (no write once claimed/sending/unknown/sent), each `_review_changed`. Columns `AnswersMid INTEGER`, `DraftWhy TEXT`.

- [ ] Failing `test_a_review_keeps_its_target_and_why_apart_from_its_freshness` (MessageId 12; answers 11; why set; after `DeliveryState='sent'` a second `set_review_answers(rid, 10)` leaves 11). Run; AttributeError.
- [ ] Implement; pass. Commit `taskuary/store.py tests/test_answers_mid.py`: "A draft keeps which mail it answers apart from the newest mail it saw".

### Task 2.2: `wrapup.answers_for` and the agent's reply tool

**Files:** Modify `taskuary/wrapup.py` (`reply_target` ~126-140, `agent_reply` ~296-378), `taskuary/server.py` (`AgentReplyBody` ~5209, `/api/agent/reply` ~5216-5224), `taskuary/cli.py` (`--reply` args ~312-330, post ~399), `taskuary/floor.py` (`_TASKUARY_WITH` ~143). Test: `tests/test_answers_mid.py`.

**Interfaces:** `wrapup.answers_for(store, task_id, mid, to='') -> int | None` - the newest `asks[].mid` of `store.task_thread(task_id)` that is a message on the task, in `mid`'s `ConversationId`, `<= mid`; with `to`, only one whose `_person` is `_person(store, mid)`. `agent_reply(..., answers: int | None = None)`: after `pin_review_context`, `set_review_answers(rid, answers or answers_for(...))`; envelope and `agent_signed` use `get_message(AnswersMid or mid)`; an explicit `answers` replaces the envelope; one not an inbound mail on the task -> `{'ok': False, 'why': f'#{answers} is not a mail on this task'}`. CLI `--answers N`; `AgentReplyBody.answers: int | None = None`; `'--answers'` in `floor._TASKUARY_WITH`.

- [ ] Failing: `test_the_reply_answers_the_mail_that_holds_the_ask` (Ray asks #11 To Alex, Cc Gail; Gail "Thanks!" #12; Ray "thanks" #13; asks `[11]`, aside 12, 13 -> `MessageId == 13`, `AnswersMid == 11`, envelope to `ray@northwind.example`, cc has `gail@northwind.example`); `test_a_thread_of_only_thanks_answers_the_newest_as_today` (no asks -> `AnswersMid is None`, envelope on #13); `test_answers_names_the_mail_the_owner_means` (12 -> 12; 999 -> `ok False`); `test_the_cli_and_floor_know_answers`. Run; AttributeError.
- [ ] Implement; run with `tests/test_agent_reply.py tests/test_reply_target.py tests/test_floor*.py`; pass.
- [ ] Commit the five files + test: "The agent's reply answers the mail that holds the ask, and can be pointed at another".

### Task 2.3: The drafter answers the ask and says WHY

**Files:** Modify `taskuary/responder.py` (`FILES_RULE` ~157-160, `_answer`/`files_said` ~420-438, `draft_reply` ~530-632, `draft_for_review` ~635-675, `draft_for_message` ~728-774). Test: `tests/test_answers_mid.py`.

**Interfaces:** `WHY = 'WHY:'`, `WHY_RULE` (end with `WHY: <one or two sentences for the owner on what you read and why the reply says this>`, never sent, appended beside `FILES_RULE` in both writers); `why_said(out) -> (text, why | None)`; `_answer(...) -> (text, files, why)` parsing WHY and FILES in either order; `draft_reply(..., answers=None)` - `asked = get_message(answers)` when given, its From/`_to_cc`/`triage_read` used, `seen['why'] = why`; `draft_for_review`: `ans = wrapup.answers_for(store, task_id, (seen['saw'] or {}).get('MessageId'))`, passed as `answers`, envelope on `get_message(ans) or saw`, then `set_review_answers`, `set_review_why`; `draft_for_message` unpacks three and stores why.

- [ ] Failing: `test_why_is_taken_off_and_kept` (brain `"Friday works.\nWHY: He asked for a pay date; the run is Friday.\nFILES PROMISED: unnamed"` -> draft starts `Friday works.`, no `WHY:` in it, `DraftWhy` starts `He asked`, `FilesPromised == '{"named": []}'`); `test_the_drafter_answers_the_ask_to_everyone_on_it` (Task 2.2's thread -> AnswersMid 11, to Ray, cc Gail, MessageId 13); `test_a_chat_has_no_reply_all` (same on `Channel='teams'` -> `review_envelope(rid) == {}`, AnswersMid 11). Run; unpack error.
- [ ] Implement; run with `tests/test_drafter_*.py tests/test_reply_*.py tests/test_files_promised*.py`; pass.
- [ ] Commit `taskuary/responder.py tests/test_answers_mid.py`: "The drafter answers the mail that holds the ask and leaves the owner one line on why".

### Task 2.4: Send goes to the ask; aside mails move nothing

**Files:** Modify `taskuary/verdicts.py` (`context_moved` ~20-46, `_deliver_review` ~218, sent mark ~254), `taskuary/ingest.py` (attach branch ~951-1046, `behind` block ~1009-1022), `website/src/pendingDrafts.js` (`draftAnswers` ~10). Tests: `tests/test_answers_mid.py`, `website/test/pendingDrafts.test.mjs`.

**Interfaces:** `_deliver_review`: `msg = store.get_message(rv.get('AnswersMid') or rv.get('MessageId'))`, both rows marked sent after a send. `context_moved`: the `_own_lines` branch's `later` skips `store.aside_mids(tid)`. `ingest.is_aside(verdict) -> bool` (any `thread.aside[].mid == 0`); `if behind and not is_aside(follow):` guards stale, re-point and `_auto_draft`. `draftAnswers` prefers `AnswersMid`.

- [ ] Failing: `test_a_thanks_does_not_mark_the_draft_stale` (#12 aside -> `context_moved == (False, None)`); `test_a_real_reply_still_moves_it` (#14 not aside -> True); `test_send_goes_to_the_ask` (stub send; the snapshot's message is #11); `test_two_drafts_answer_their_own_mails` (AnswersMid 11 Ray and 15 Erin Blake in one conversation; each delivery uses its own message and envelope; aside #16 leaves both `Stale == 0`); `test_an_aside_mail_is_not_redrafted` (attach with fake judge `reply_only` + aside `[{mid: 0}]`, `ingest._spawn` patched -> MessageId kept, not stale, nothing spawned). Node: `draftAnswers({AnswersMid: 11, MessageId: 13}, [{MessageId: 11}, {MessageId: 13}]).MessageId === 11`. Run; fail.
- [ ] Implement; run with `tests/test_no_redraft_after_send.py tests/test_stale_session_draft.py tests/test_review_delivery_safety.py` and the node test; pass. Build; revert OFL.
- [ ] Commit the four files + tests + `taskuary/web`: "A thanks on the thread leaves the draft where it was, and Send goes to the mail that asked".

---

## Phase 3 - The agent's new goal and the summary block

### Task 3.1: Diagnose TQ-1258 (read-only)

**Output:** `phase3-finding.md` in the session scratchpad (shape only: no names, addresses, repo names or values) - consumed by Task 3.2. Nothing in the repo; no commit.

- [ ] New shell; `export TASKUARY_HOME=$(mktemp -d)` before anything imports taskuary.
- [ ] `python -I` with plain `sqlite3`, `connect('file:' + ~/.taskuary/taskuary.db + '?mode=ro', uri=True)`: for TaskId 1258 print the task row (Kind, Assignee, Tags, Summary), comments in order (ActorType, 400 chars), route `VerdictJson` (`kind`, `profile`, `checklist`, `offer`), reviews (Kind, Status, 300 chars), setting `default_profile`, and the KEYS of every agent's `Config.cwd_map`.
- [ ] Read `~/.taskuary/artifacts/1258/general-steps.jsonl`: what it listed or read, and whether any read was under a `cwd_map` path.
- [ ] `cx.backup()` into `$TASKUARY_HOME/taskuary.db`, then on the copy `general._prompt(SQLiteStore(copy), 1258)`: is the project with the `.env` in `general.repos_block`; which `PROFILE RULES (` rode.
- [ ] Classify as one of: **A** the project was not in `repos_block` (no SOUL repo line, no `cwd_map` entry, or a plain folder); **B** listed, but nothing told it the owner's part was supplying that login; **C** listed and clear, but a profile's rules or ASSISTANT.md's "Ask first: guessing at a fact" sent the step back. Write the letter, the evidence (shape only) and the one-sentence context fix.

### Task 3.2: Fix by context, pinned by an eval case

**Files:** Create `tests/agent_cases.py`, `tests/test_agent_cases.py`. Modify for **A** `taskuary/general.py` `repos_block` (~655-674: also list each agent `cwd_map` folder that is not a repository, under "THE OWNER'S PROJECTS AND REPOSITORIES"); **B**/**C** are fixed by Task 3.4 and 3.3.

**Interfaces:** `agent_cases.CASES = [(name, setup(store) -> tid, needs: list[str], never: list[str])]`; `test_the_prompt_carries_what_the_case_needs` asserts each `needs` in `general._prompt(s, tid)` (system + user), no `never`, the pattern of `tests/advisor_cases.py`.

- [ ] Case `login_kept_in_a_project`: Ray Colton asks Alex for the vendor-portal login so Gail Moreno can upload the payment file; an agent's `cwd_map` maps `northwind/ledger` to a temp folder with `.env` `PORTAL_USER=placeholder`; ThreadJson `your_part "give Gail the portal login"`. `needs`: that folder path, `"Your part: give Gail the portal login"`, `"never paste a secret"`; `never`: `"PROFILE RULES (RESEARCHER"`.
- [ ] Run `TASKUARY_HOME=$(mktemp -d) python -m pytest tests/test_agent_cases.py -q`; expect needs missing.
- [ ] A: implement. B/C: mark `@unittest.expectedFailure` ("Task 3.4") - removed in 3.4's commit.
- [ ] Commit the case files (+ `general.py` for A): "An agent asked for a login kept in a project is shown where the project is (an invented case)".

### Task 3.3: Triage stops choosing a profile; every general task runs the assistant

**Files:** Modify `taskuary/triage.py` (`verdict_schema` ~232/288 and `classify_intent` ~731/844/946-951: drop `profiles` and the `profile` output), `taskuary/templates/triage.md` (drop "**Which worker.**" ~113 and `profile` from ~182), `taskuary/ingest.py` (`judge` ~733 no `profiles=`; ~1197 `routed_role(store, f['kind'], '')`), `taskuary/agents.py` (`routed_role` ~1139-1164: `''` for general, no `default_profile`), `taskuary/concierge.py` (~4716-4724: `params['profile'] = picked.get('agent') or None`, `clear = True`, no "The X takes it."), `taskuary/toolcatalog.py` (`regular_agent` ~426: drop the `as` clause), `taskuary/roles.py` (stop writing `default_profile`), `website/src/RoleStart.jsx` (~13: drop the "goes to" sentence). Tests: `tests/test_profile_is_a_role.py` (~31-180), `tests/test_agent_profiles.py` (~200-292), `tests/test_verdict_shape.py` (~180), `tests/test_roles.py` (~83).

**Interfaces:** `verdict_schema(repos=None, candidates=None, playbooks=None, same=False, …)`; `classify_intent(…)` without `profiles`; `routed_role(store, kind, profile) -> str` = `coding_role(store)` for coding, else `''`, so `general._prompt` (~726) runs `assistant`. Routines and workflows keep a profile through `Assignee` (`workflows.py:359`, `flow.py:380`), which `general.assigned_role` still reads.

- [ ] Failing (rewritten): `test_triage_is_shown_no_workers` (`'THE WORKERS' not in prompt`); `test_general_takes_the_assistant` (`routed_role(s, 'general', 'researcher') == ''`); `test_the_contract_line_names_no_profile`; `test_verdict_shape` drops `profiles=` and `'profile'` from its asked list; `test_roles.py::test_general_work_goes_to_the_assistant` (no `default_profile` after applying the AP role); `test_agent_profiles` classify tests assert `'profile' not in out` when the brain names one; `test_a_workflow_still_names_its_worker` (a workflow defn with `agent: analyst` -> `Assignee == 'agent:analyst'` and `PROFILE RULES (ANALYST.md)` in its prompt). Run the five files plus `tests/test_assistant_lines_kept.py`; fail.
- [ ] Implement. UI with a profile choice for a task: none left - the hand-off and New's general picker hide it (`ui.jsx` `AgentPicker` `handOff`); RoleStart's routing sentence changes here; Docs → Profiles' "on the roster" chip (`agents.roster_line`) is REMOVED (owner, 2026-11-04) - profiles are for routines only; test `test_profiles_show_no_roster_chip`. Whether profiles should exist at all is left open (owner: "not sure it needs profiles at all").
- [ ] Run with `tests/test_workflows*.py tests/test_concierge*.py`; pass. Build; revert OFL.
- [ ] Commit the listed files + `taskuary/web`: "Triage no longer picks a worker for a task: every general task runs on the one assistant; routines still name theirs".

### Task 3.4: One goal - get the owner to done

**Files:** Modify `taskuary/templates/assistant.md` (35 lines, rewritten), `taskuary/general.py` (`_prompt` ~676-850: system ~700-716, `head` ~836-843; new `reading_block`), `taskuary/selfclose.py` (`SUMMARY_LINE` beside `REPLY_LINE` ~308). Tests: `tests/test_general.py`, `tests/test_agent_cases.py`.

**Interfaces:** `general.GOAL_LINE` (builder's words; must contain "get the owner to done" and "never paste a secret", and say: read the reading first, do as much of their part as you can, look in the listed projects before saying it cannot be found, draft every email through your tools, a secret follows separately as an On you step). `general.reading_block(store, tid) -> str` ('' with no reading; "THE ASK, AS TRIAGE READ IT (check it against the mail):" with Asking / Your part / Already handled / The mail the reply answers `[#mid] who · M/D` / Aside / On you, then "THE MAIL ON THIS TASK:" one `[#mid] who · M/D HH:MM` per inbound mail, for `--answers`; 1500 chars). `_prompt` adds `GOAL_LINE` and `selfclose.SUMMARY_LINE` for every non-dock task not `connector:setup`/`SETUP_REF`, and `reading_block` right after the TASK lines, never on a stranger's task. `assistant.md` is rewritten around the goal with "When the task needs research or analysis" folding in one or two lines each from `researcher.md` (sources, dates, what was not found), `analyst.md` (whose figures, how computed, the check), `coordinator.md` (who owes what by when; never book without asking), `marketer.md` (voice; claims need a source); `trader.md` stays routine-only.

- [ ] Failing: `test_every_general_task_has_the_one_goal` (both phrases and `[[TASKUARY-SUMMARY]]` in system); `test_the_reading_leads_the_brief` (`'Your part: give Gail the portal login'` and `'[#11] Ray Colton'` in user); `test_no_reading_no_block`; `test_the_shipped_assistant_doc_carries_research_know_how`. Drop 3.2's `expectedFailure`. Run with `tests/test_general_knows_the_repos.py`; fail.
- [ ] Implement (an owner-edited ASSISTANT.md stops tracking its template, store.py ~1519-1523 - hence the code lines). Run; pass.
- [ ] Commit the four files + tests: "The general agent's one goal is to get the owner to done, starting from triage's reading".

Note: `brief.build` only seeds terminal sessions (`terminal.seed_text` ~1925); the general agent's brief is `general._prompt`.

### Task 3.5: The SUMMARY block

**Files:** Modify `taskuary/selfclose.py` (~300-470), `taskuary/general.py` (`SUMMARY_TYPE` ~23, `GeneralSession._file` ~1409-1525, `shown_history` ~346-357), `taskuary/store.py` (checklist ~2238-2290), `taskuary/ingest.py` (after the route ~1334). Test: create `tests/test_turn_summary.py`.

**Interfaces:** `SUMMARY_OPEN, SUMMARY_CLOSE = '[[TASKUARY-SUMMARY]]', '[[/TASKUARY-SUMMARY]]'` (not `SUMMARY:`, which `_prompt` already uses as the task-summary label); `SUMMARY_LINE` asks for `{"about", "did", "on_you": [], "nothing_left": bool}` at the end of every turn, and a question as one or two plain sentences (choices only via `[[TASKUARY-ASK]]` when real). `summary_marker(text) -> (text, dict | None)` (block always removed; `about`/`did` 600, `on_you` 6×200, `nothing_left` bool; None on bad JSON); `for_screen` strips it. `general.SUMMARY_TYPE = 'assistant_summary'`; `_file` after the tick markers takes it, and after the answer's `add_comment` files `json.dumps(summ)` as a `SUMMARY_TYPE` row and calls `store.set_on_you(tid, summ['on_you'], 'assistant')`; an emptied reply becomes `summ['did']`. `SQLiteStore.set_on_you(task_id, texts, actor) -> list` keeps non-on_you and ticked on_you items, replaces unticked on_you with `{id, text, done: False, on_you: True}`. `shown_history` puts `summary` on the assistant message a `SUMMARY_TYPE` row follows. In ingest, a `Kind == 'reply'` task with no `live_agent` takes triage's `thread.on_you` through `set_on_you(..., 'triage')`.

- [ ] Failing (GeneralSession with `_selected` and `build_llm` patched, as `tests/test_agent_reply.py`): `test_a_turn_ends_with_three_parts` (no marker on screen; `shown_history(s, tid)[-1]['summary']['on_you'] == ['send Gail the portal login through your password tool']`; one on_you item); `test_a_later_summary_replaces_only_unticked_on_you`; `test_a_turn_without_the_block_is_today` (no block, and `[[TASKUARY-SUMMARY]]{not json[[/TASKUARY-SUMMARY]]`: no summary row, checklist unchanged, no marker text shown); `test_triage_on_you_only_where_no_agent_runs`. Run; AttributeError.
- [ ] Implement; run with `tests/test_agent_reply.py tests/test_general_turn_ends_short.py tests/test_api_worker_signals.py`; pass.
- [ ] Commit the four files + test: "Each agent turn ends with what it is about, what it did and what is on the owner".

### Task 3.6: `AgentSummary.jsx` and "Working on this…"

**Files:** Create `website/src/agentSummary.js`, `website/src/AgentSummary.jsx`, `website/test/agentSummary.test.mjs`. Modify `website/src/GeneralWorkspace.jsx` (`AgentBand` ~110-158, `AssistantMessage` ~196-229, `AssistantThread` ~424), `website/browser/general-chat.test.mjs`.

**Interfaces:** `foldedSummaries(messages) -> Set<id>` (all but the newest summary); `nextSteps({ summary, reviews = [], checklist = [], cards = true }) -> { drafts, onYou, nothing }` (`drafts` = pending replies when `cards`; `onYou` = unticked on_you items; `nothing = !drafts.length && !onYou.length && !!summary?.nothing_left`). `AgentSummary({ summary, reviews, checklist, cards = true, folded = false, onChanged })` with `data-tq-summary`, headed "What this is about", "What I did", "Next steps". GeneralWorkspace: one `data-tq-working` line "Working on this…" with the steps folded under it; a message with `summary` draws `AgentSummary`; earlier ones fold to "What I did".

- [ ] Failing node: `foldedSummaries([{id: "a", summary: {}}, {id: "b"}, {id: "c", summary: {}}])` has "a" not "c"; `nextSteps({summary: {nothing_left: true}}).nothing === true`; one unticked on_you item -> `onYou.length === 1`. Browser (`general-chat.test.mjs`): `"working folds the steps"`, `"an agent's question reads in plain words"`. Run; fail.
- [ ] Implement; pass. Build; revert OFL. Commit the files + `taskuary/web`: "The agent's chat says Working on this…, and ends each turn in three parts".

---

## Phase 4 - Close out folds in

### Task 4.1: `[from, agent]` where the chat is home

**Files:** Modify `website/src/taskLayout.js` (`SECTIONS` ~95), `website/src/TaskPage.jsx` (`useTaskMoves` ~522-526, `TASK_KEYS` ~566, `SECTIONS` uses ~1795-1818, `workspaceMode` ~1674, held section ~1753-1760, `slot("close", …)` ~3357). Tests: `website/test/taskLayout.test.mjs`, `website/test/agentSummary.test.mjs`.

**Interfaces:** `chatHome({ kind, terminal = false }) = !terminal && (isGeneralKind(kind) || kind === "reply")`; `taskSections(home)` (`["from","agent"]` or `SECTIONS`); `homeSection(home, here) = home ? "agent" : here`. `useTaskMoves(sec, home)`: `close = home ? sec === "agent" : sec === "close"` (Mark done, Close with a note, Attach, Share on the agent strip). TaskPage: `home = chatHome({ kind: t?.Kind, terminal: !!term?.alive })`, `secs = taskSections(home)` replaces `SECTIONS`/`TASK_KEYS`, no `slot("close")` when `home`.

Note: the spec's switch is `workspaceMode === "general"`, but that mode is `"empty"` on a reply task no agent ran (`taskWorkspace.js:6`), which the spec draws in the chat - so `chatHome` reads the kind (spec's `useSpineVerbs` change is really `useTaskMoves`, which wraps it).

- [ ] Failing node: `chatHome` true for `general`, `reply`; false for `coding`, `task`, `{kind: "general", terminal: true}`; `taskSections(true)` keys `["from","agent"]`; `homeSection(true, "close") === "agent"`; Review Focus 4: a pending draft with `nextSteps({…, cards: false}).drafts.length === 0`. Run; fail.
- [ ] Implement; pass. Build; revert OFL. Commit the files + `taskuary/web`: "A task whose home is the chat shows Came from and the agent, and opens on the chat".

### Task 4.2: Next steps draws the cards; the chat with no agent

**Files:** Modify `website/src/AgentSummary.jsx`, `website/src/TaskPage.jsx` (agent slot ~2975-3300, `noticeOn`/`agentDrafts` ~2709), `website/src/GeneralWorkspace.jsx`. Create `website/browser/closeout-in-chat.test.mjs`; add it to `test:browser`.

**Interfaces:** On the newest summary and only when `cards`: first draft `<ReviewDecision review={r} onChanged />`, the rest `<MoreDrafts reviews messages />`, emails owed `<SlotList taskId checklist reviews onChanged />`, each on_you item "On you: …" with an owner mark (`data-tq-on-you`), or "Nothing left to do here". `NoAgentChat({ task, reviews, checklist, mails, onChanged })` (in AgentSummary.jsx): reading, "What I did" = the pending review's `DraftWhy`, the card; its box posts `/api/tasks/{id}/dispatch` `{ kind: "general", instruction }` (Send to agent's road, which switches the kind; the spec's `agent_on_reply` is the mail road). `noticeOn` is false when `home`. `cards = home`.

- [ ] Failing browser: `"each draft is sent from inside the chat"` (two `[data-tq-summary] [data-tq-review]`, Send on one leaves one, no `[data-tq-slot=close]`); `"Mark done lights when the On you step is ticked"` (agent strip's Mark done has class `p`); `"a reply with no agent shows the reading, why and the draft"`; `"a coding task is unchanged"`; `"one copy of each draft"`. Run; fail.
- [ ] Implement; pass. Build; revert OFL. Commit the files + `website/package.json taskuary/web`: "Draft cards, emails owed and On you steps live in the agent's summary; Close out is gone on chat tasks".

### Task 4.3: The Advisor reads the summary

**Files:** Modify `taskuary/advisor.py` (`_prompt` checklist lines ~748-751). Test: `tests/test_turn_summary.py`.

**Interfaces:** `advisor.summary_line(store, tid) -> str`: "THE AGENT'S LAST SUMMARY: nothing left to do here" (newest summary `nothing_left`, no pending draft, no unticked on_you), "THE AGENT'S LAST SUMMARY: on you - <items>", or ''. The Advisor lights Mark done on it; nothing presses it.

- [ ] Failing `test_the_advisor_is_told_nothing_is_left` (and '' with a pending draft). Run; fail. Implement; run with `tests/test_advisor_cases.py`; pass.
- [ ] Commit `taskuary/advisor.py tests/test_turn_summary.py`: "The Advisor reads the agent's last summary, so Nothing left to do lights Mark done".

### Task 4.4: The walk table and dead ends

**Files:** Modify only what fails among `website/browser/walk-table.test.mjs`, `walkdriver.mjs`, `send-and-close.test.mjs`, `three-sections.test.mjs`, `spine-stage-moves.test.mjs`, `website/deadend_check.mjs` (`WALK_SKIP` ~93), `website/browser/deadend-baseline.json`.

- [ ] Run those four browser files and `npm run test:walk`; list failures.
- [ ] Fix each: on a chat task, Send and close is pressed on the card in `[data-tq-summary]` (same verb id); three sections are asserted on coding tasks only; a verb a chat task no longer offers gets a `WALK_SKIP` reason (e.g. `"close-tab": "a chat task has no Close out tab; the coding task's walk presses it"`).
- [ ] Re-run; pass. Commit the touched files: "The walk sends and closes from the chat on chat tasks; coding tasks keep Close out".

---

## Phase 5 - A warm session and learning

### Task 5.1: Measure, and stay warm while on screen

**Files:** Modify `taskuary/clipool.py` (`_reap` ~101-108), `taskuary/general.py` (`assistant_reply` audit ~1513), `taskuary/server.py` (new `POST /api/tasks/{task_id}/assistant/seen` beside ~2267), `website/src/GeneralWorkspace.jsx` (60 s heartbeat while mounted). Test: `tests/test_clipool.py`.

**Interfaces:** `clipool.is_live(key) -> bool`; `clipool.touch(prefix) -> int` (sets `used = time.time()` on matching live processes); `clipool.GRACE = IDLE_SECONDS` unless the measurement says otherwise; the endpoint returns `{'warm': clipool.touch(f'general:{task_id}') > 0}`; the audit detail gains `'warm'` read at turn start. Scope: keep-warm already exists for Claude Code (`keep=f'general:{tid}'` general.py:1256, 30-minute reaper, `MAX_LIVE = 6`); new are the on-screen touch and the numbers. Other brains and the backup provider keep resume-per-turn.

- [ ] Failing: `test_touch_keeps_a_process_from_the_reaper` (fake Live used 31 min ago; `touch('general:5') == 1`; not reaped); `test_is_live`. Run; fail. Implement; pass.
- [ ] Measure on a dev home (never the live one): five "cc Gail" turns cold (after `clipool.close('general:')`) and five warm; medians of `took` from `SELECT Detail FROM audit WHERE Action='assistant_reply'`. Put both and the chosen `GRACE` in the commit message.
- [ ] Build; revert OFL. Commit the files + `taskuary/web`: "The agent's process stays warm while its task is on screen (cold N s, warm M s)".

### Task 5.2: Corrections reach the learning paths

**Files:** Modify `taskuary/selfclose.py` (`summary_marker` keeps `corrections`), `taskuary/general.py` (`_file`), `taskuary/byrecipient.py` (new `keep_instruction`), `taskuary/server.py` (`_keep_instruction` ~3835 calls it). Test: `tests/test_turn_summary.py`.

**Interfaces:** SUMMARY may carry `"corrections": [{"kind": "redraft" | "ask", "review": id | null, "said": "<owner's exact words>"}]`. `byrecipient.keep_instruction(store, rid, said)` = today's `_keep_instruction` body. `general.take_corrections(store, tid, corrections) -> int`: kept only when `said` is in the owner's newest `USER_TYPE` comment; `redraft` with a pending review -> `keep_instruction`; `ask` -> `learn.learn_from(store, "owner_correction on TQ-n: the reading was …; the owner said: …; the thread: …")` (1500 chars of `exchange_lines`).

- [ ] Failing: `test_a_redraft_word_is_kept_on_the_draft` ("Cc Gail on it" in `Instructions`); `test_said_twice_for_one_person_becomes_a_style_line` (`byrecipient.lines`); `test_not_the_ask_is_an_owner_correction` (`learn.learn_from` patched, called once with `owner_correction`); `test_words_the_owner_never_said_are_dropped`. Run; fail.
- [ ] Implement; run with `tests/test_voice_by_recipient.py`; pass. Commit the files + test: "A correction typed in the chat is learned the way the draft box's words were".

### Task 5.3: The drafter reads how the owner works

**Files:** Modify `taskuary/learned_cut.py` (`READS` ~26). Test: `tests/test_voice.py`.

**Interfaces:** `READS['drafter'] = ('people', 'work')`; `BUDGET['drafter']` stays 600.

- [ ] Failing: `test_the_drafter_reads_how_you_work` (a "How you work" line is in `responder.voice_line(s, ['ray@northwind.example'])`); `test_voice_line_stays_in_budget` (40 long lines -> `len <= 600 + len(responder.PEOPLE_HEAD) + 200`). Run; fail.
- [ ] Implement; run with `tests/test_learned*.py`; pass. Commit: "Drafts read how the owner works, inside the same budget".

---

## Phase 6 - Reports, FYI and dashboards

### Task 6.1: The reading on an item

**Files:** Modify `taskuary/store.py` (new `message_thread(mid) -> dict | None` from the message's newest route `VerdictJson.thread`), `taskuary/server.py` (the item payload the canvas reads for a message adds `reading`), `website/src/threadReading.js` (`itemLines(r) -> [{k: "says"|"matters", text}]` = `asking`, `your_part`), `website/src/ItemSections.jsx` (middle section). Tests: `tests/test_thread_reading.py`, `website/test/threadReading.test.mjs`, `website/browser/item-sections.test.mjs`.

- [ ] Failing: `test_a_filed_mail_keeps_its_reading`; node `itemLines`; browser: the demo FYI shows "What this says" and "What matters to you". Run; fail.
- [ ] Implement; pass. Build; revert OFL. Commit: "An FYI or a report says what it says and what matters to you".

### Task 6.2: The item's box answers - no task, no agent (owner, 2026-11-04: "question on report should not start task")

**Files:** Modify `website/src/ItemSections.jsx` (the box posts to the Assistant with the item pinned - the same `concierge.say` door the dock uses, `item` = this report/FYI/dashboard, `view` sent with the turn), `taskuary/concierge.py` (a turn whose item is a report/FYI/dashboard answers from it - `_task_whole`-like block for the item: its text, triage's reading, its links - and never calls `dispatch`/`agent.start`). Tests: `tests/test_assistant_item_answers.py` (new), `website/browser/item-sections.test.mjs`.

- [ ] Failing: `test_a_question_on_a_report_is_answered_from_it_and_files_nothing` - before/after `store.list_tasks()` equal, no run started, the answer quotes the report's figure; browser: typing in an FYI's box shows the Assistant's answer under it and the row stays an FYI. Run; fail.
- [ ] Implement; pass. Build; revert OFL. Commit: "A question on a report, FYI or dashboard is answered from it - no task, no agent".
