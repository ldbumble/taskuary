# Processing redesign: staged implementation plan

Status: plan prepared 2026-09-05. Owner selected master for delivery and requested
pushing existing approved changes. Browser control/UI remains unreviewed. Scope:
every approved section of
[the walkthrough TODO](processing-walkthrough-todos.md). That document remains the
detailed acceptance record; this plan supplies dependencies, ownership, and gates.

## Delivery contract

Owner update, 2026-09-06: stop the specialist sub-agents and have the lead finish
the remaining fixes directly. This supersedes the multi-agent assignment rules
below for subsequent work; regression, browser, preservation, and delivery gates remain.

Implement one reviewable section, add its tests, integrate and review, run the
cumulative gates, commit and push, verify remote CI, then move to the next section.
Phases below may require several such sections; they are not giant single commits.
Never report an entire phase complete because only its backend or mocked path works.

Multiple agents work within the active phase, not on incompatible future redesigns.
The lead owns contracts, migrations, integration, and pushes. Implementation agents
own bounded file sets; a separate test/review agent checks requirements independently.
At most three workers plus the lead. Use isolated worktrees/branches based on the
accepted checkpoint; never let two agents edit the same shared file concurrently.
Agents submit commits/diffs and evidence to the lead; they do not push or merge.

Before each assignment specify: acceptance IDs, base commit, owned files, API/schema
contract, tests, forbidden changes, and dependency assumptions. Shared files such as
server.py, store code, concierge.py, FeedView.jsx, and TasksView.jsx require a single
owner per section. Rebase/integrate against the latest accepted checkpoint and rerun
tests; passing on an old base is not sufficient.

## Phase 0: baseline and acceptance ledger

Execution record: [implementation evidence](processing-implementation-evidence.md),
[acceptance ledger](processing-acceptance-ledger.md),
[state/migration contracts](processing-state-contracts.md), and
[existing failures](processing-existing-failures.md). The ledger assigns stable
PW IDs to every original checkbox; pending evidence is not implementation acceptance.

- Inventory the existing dirty tree before touching it. At planning time it contains
  README.md, walkthrough TODO, blackboard.py, concierge.py, counsel.md, and associated
  tests. Preserve and classify each change; do not sweep unrelated edits into a commit.
- Establish a reviewed baseline containing the applicable already-approved fixes.
  Never stash, discard, or overwrite unknown edits to make agent branches easier.
- Assign stable acceptance IDs to every TODO checkbox and map each to a phase,
  test, and eventual commit. Maintain a separate list of observed existing failures.
- Run the existing suites in an isolated test home; capture command, commit, OS,
  duration, and failures. Create representative redacted fixtures for the reported
  missing Unread items, grouped messages, agent waits, duplicate turns, and replay.
- Add behavioral regression tests, not only checks that source code contains strings.
  A future-feature test can land with its implementation; never leave required CI red
  or hide a current regression as an untracked skip.
- Agree exact state/API contracts and resolve superseded checklist language below.

Gate: baseline report, acceptance coverage ledger, safe fixture/browser harness, and
documented migration/rollback approach before state migrations begin.

## Phase sequence

| Phase | Section scope | Prerequisites | Required acceptance evidence |
| --- | --- | --- | --- |
| 1. Shared state and Unread | Canonical item IDs/context revisions, read/deferred/actionability state, common All/Unread filters, shared ordering, counts, pagination, Current/Next; preserve funnel UI, remove Needs me, All detail-only | 0 | Same eligible item set across views; old reads preserved; assistant consumes shared order; working agents band 5 and input/approval band 2; no false empty states |
| 2. Intake and full context | Poll isolation/settings; safe Outlook and IMAP catch-up/cursors; incremental full email chains, attachments, identity-based email routing, cleaning and context budgets | 1 contracts | Backlogs beyond prior caps; A/B/C plus D without repeated body fetches; gaps recovered; no historical read reset; slow triage/report cannot block chat intake |
| 3. Unified triage | Fresh evaluation on new context, same-day chat association, error/retry, general default, task summary/checklist, people/project/repo evidence, incoming procedures, assistant ideas and opt-in report triage | 1–2 | One verdict drives classification/association; valid scoped IDs; old verdict not a veto; stable checklist edits; visible failures; generated ideas cannot duplicate active work or loop |
| 4. Shared actions, evidence, history | Typed action schemas/execution services for task creation/completion, deferral, preferences/exclusions and dispatch preparation; proposal IDs/revisions/idempotency; action-driven correction evidence; source-linked discussion | 1–3 | No mutation before required confirmation; successful corrections recorded once across entry points; failed/cancelled actions do not teach; taskless FYI history links on conversion |
| 5. Agent startup and coordination | Common coding/general dispatch, settings/trust, explicit manual repo choice, capacity, two retries, live wall lifecycle, AGENT/CODER brief split, task-view startup parity | 2–4 | Actual prompt acceptance distinct from workspace creation; both worker kinds count while waiting; no duplicate start; no overlap queue; no closed-run wall notes; repo cancellation safe |
| 6. Worker events and completion | Provider adapters, input/approval/working/finished state, request-bound replies, final answer/checklist/artifact persistence before worker close; general/coding pause/stop parity | 4–5 | Duplicate/out-of-order/stale events safe; delivery acknowledged; provider approval mechanism verified; explicit work finish not inferred from quiet/exit; recoverable save failure |
| 7. Replies and delivery | Always draft, style/signature/recipients, shared freshness including email, stale-approval popup, completion-to-reply, success/failed/unknown delivery, close-without-send | 2–6 | Reply all default, editable recipients, exact context snapshot, uncertain send reconciled without duplicate send, success closes task, blocked send keeps draft and offers explicit closure |
| 8. Assistant conversation/UI | AI interpretation and clarification replaces decide_words and competing prompts; COUNSEL migration; bottom prompt suggestions, confirmation cards, full task/FYI presentation, named references, direct question relay, consistent task-view actions | 1–7 | Real rendered UI + API state agree; no keyword bypass; immediate Next/draft exceptions; handoff advances once; unsolicited notices only bottom strip; workers open in their own workspace |
| 9. Chat lifecycle and retention | Durable Current, blank New chat, read-only archived history, streamed-turn identity/cancellation, duplicate response prevention, independent 15-day configurable cleanup | 4, 8 | Reload/tab switch restores correctly; old response cannot enter new chat; cleanup preserves task history/evidence/rules; history read performs no writes |
| 10. Reports, workflows, direct setup | Separate workflow definitions/procedures; direct general-agent workflow runs; durable Run now; AI-led real report/connection configuration using confirmed shared actions | 3–8 | Report/workflow survives navigation; no triage on configured workflow trigger; report triage opt-in works; actual resource created, not placeholder task; secure auth and no secret history |
| 11. Minimal onboarding | Name and coding CLI readiness first; top Assistant system-setup entry; shipped Taskuary setup skill; style draft preview; resumable system configuration | 8–10 | Fresh install can reach usable AI; user edits preserved; setup uses skill and validated tools; no hardcoded dialogue, duplicate configuration or unapproved agent launch |
| 12. Shutdown and release hardening | Await backend cleanup on desktop quit; owned child cleanup, recovery after crash; final load/replay/input and packaged UI checks | All | No orphaned owned workers after normal quit; interrupted state on restart; history survives; tab changes do not stop runs; source and shipped UI match |

Shutdown race and terminal/loading regression tests start in phase 0; do not wait
until phase 12 to detect them. A bounded fix can be pulled forward once its contract
is stable. End-to-end performance is checked on every UI/state phase, not postponed
until release. Each phase updates its settings/help text and migration tests with
the implementation rather than leaving misleading UI until the end.

## Contracts to freeze before dependent agents code

- Canonical item: stable source/task identity, context revision, read/defer state,
  triage priority, worker attention, and shared order/actionability. No second
  assistant funnel and no source-specific silent exclusions.
- Proposed action: owner, exact target/parameters, context revision, confirmation
  identity, execution state/outcome, and replay protection. All entry points use
  the same effects. Automatic triage/workflow dispatch uses configured authority,
  not the manual-chat confirmation route, and still uses shared safety guards.
- Worker event: task/run/turn/request identity, state, question/approval payload,
  delivery acknowledgement, and result version. Hooks are not assumed to provide
  every reply capability; validate installed integrations before committing to one.
- Persistence: source discussion and task history separate from chat retention;
  correction evidence separate from deterministic exclusion rules; explicit durable
  operation records make action retries safe without repeating external effects.
- Freshness: capture the input revision actually used, invalidate old proposals
  on material updates, preserve edits, and never treat failed refresh as current.

## Superseded wording and remaining decisions

Apply newer owner approvals over historical TODO wording; document reconciliations
in phase 0 without silently inventing policy:

- Assistant menus become prompt suggestions plus confirmed structured actions.
  Earlier FYI/task action-button requirements mean capability parity, not retention
  of the obsolete assistant menus. Task-view controls remain.
- Immediate draft preparation and explicit Next are exceptions to confirmation.
  Confirmed successful handoff advances once; background events cannot advance.
- Successful reply closes its task even with unchecked TODOs. Closure without
  sending requires its own warning/confirmation; failure is never implicit closure.
- Correction evidence is automatic after successful owner overrides, not a second
  memory prompt; explicit broad rules/preferences retain confirmation.
- Old 20-day chat hiding/mutation is replaced by independent 15-day default cleanup.
- Overlap never queues work; capacity holds and bounded failed-start retries remain.
- COUNSEL loader/truncation fixes already checked must not be implemented twice;
  earlier prose describing them as pending is historical, not a new requirement.
- Ordering resolved by owner on 2026-09-06: urgent requests/current or starting-within-
  15-minutes calendar first, agent waits second, other actionable tasks/finished results
  third, FYIs fourth, working fifth. Within bands: triage priority, oldest activity first.
  See the state contract for deterministic identity ties and preserved Current.
- Still confirm transitions for Done on FYI batches, new activity during deferral,
  historical effects of exclusions, and auto-advance after successful sends/other
  actions. Preserve existing data; isolate unresolved policies from unrelated work.
- Clarification-send behavior versus the newer any-reply-closes-task approval must
  be explicitly resolved before phase 7; current code has a keep-waiting exception.

## Cumulative regression gates for every section

1. New focused unit/service tests demonstrate the requested behavior and failure
   paths. Independent reviewer checks the actual changes against acceptance IDs.
2. Run all previously accepted cross-phase contract tests, then the full backend
   suite (`python -m pytest -q`) and frontend suite (`npm test`, in website).
3. Build the frontend (`npm run build`, in website). Verify packaged taskuary/web
   output is from the same source commit; only the integration owner generates it.
   Vite empties that output directory: build in the isolated integration checkout,
   not a workspace serving the owner's running app.
   In that checkout, do not overlap the build with backend tests: the API suite
   serves packaged assets and can observe Vite's temporary empty output directory.
4. Run rendered-browser scenarios against an isolated fixture server for changed
   flows plus earlier critical paths. Existing Node tests are not a substitute for
   browser input, websocket reconnect, task switching, or native Windows PTY checks.
5. Run migration/reopen tests on a synthetic legacy database: retain identities,
   read states, owner documents/settings, attachments, and historical task records.
   Use additive compatibility where possible; never blanket reset read state.
6. Check diff/secret exposure and ensure no unintended live DB, config, credentials,
   generated logs, or unrelated work entered the commit. Inspect exact staged diff.
7. Commit the scoped implementation/tests and acceptance evidence. Push only after
   local gates pass. Wait for required remote CI and inspect the tested commit SHA;
   if CI fails, repair this section before beginning the next dependent section.

Existing CI tests Python 3.10/3.12 across Windows/Linux/macOS, frontend tests/build,
and Docker smoke. Master/main pushes also build a Windows executable. The selected
master delivery path triggers this existing CI; feature-branch pushes alone do not.
Use normal pushes only; no force push, release tag, package publication, or live app
restart implied by the implementation cadence. Owner selected origin/master
(ldbumble/taskuary): all accepted checkpoints integrate and push to master.
Temporary isolated agent worktrees are for safe work, not a separate delivery
branch or PR. Only lead pushes; inspect CI on each pushed SHA before continuing.

Missing CI for browser/PTY/LLM behavior must be added or covered with an explicit
repeatable evidence gate, not described as covered by existing pytest. Add prompt
evaluation cases for paraphrases, questions containing action words, ambiguous
targets, corrections, and malicious source instructions. Deterministic fake-model
tests prove routing safety; isolated real-model/provider runs test integration and
conversation quality without asserting that a model is perfectly deterministic.

## Safety and performance evidence

- Every test server/process uses a unique temporary TASKUARY_HOME, fixture database,
  test tokens/ports, and isolated workspace. tests/conftest.py already isolates
  pytest; browser/CLI subprocesses need their own equivalent setup before imports.
  Set TASKUARY_API explicitly for frontend tests: the dev proxy otherwise targets
  port 7787. Do not run mutation-capable screenshot scripts against the owner URL.
- Disable/stub every real connector, scheduler, outbound send, and worker launch
  by default, including general-agent auto-start. Use dedicated sandbox accounts
  and disposable checkouts for explicitly scoped integration tests; never use the
  owner's inbox or live report jobs as ordinary regression fixtures.
- Measure baseline and post-change time-to-visible on Tasks/Board/Reports, terminal
  reconnect/replay, input latency during output, and event-loop responsiveness
  during sync. Use fixed fixture sizes; record timings and tune thresholds in
  phase 0. Fail later sections on material regression, not just HTTP success.
- Crash/timeout/duplicate/late-event tests are required for context refresh,
  dispatch, confirmation, send, history reset, and worker completion.
- Back up application data consistently before approved live migration. Never
  restore a backup over newer user work automatically. Prefer corrective commits
  and reversible migrations; a Git revert alone does not undo database changes.

## Per-section handoff record

Record acceptance IDs, owner agents, touched contracts/files, implementation
commit, exact test commands/results, independent review, browser/provider evidence,
migration/rollback notes, pushed SHA and remote CI outcome. Mark TODOs complete
only when their required evidence exists; distinguish implemented, tested locally,
CI-verified, and live-verified. Report the next section and unresolved issues.

No test strategy guarantees zero regressions. This cumulative gate makes previous
behavior executable and blocks later work from silently discarding it. Tests may
only change when the owner-approved contract changes, with an explicit explanation;
never weaken an earlier assertion just to make the next phase green.

## Browser-control review gate

Browser control by the assistant and its UI have not been reviewed. Before changing
that integration, walk through actual ownership, visible browser/task/chat layout,
manual takeover, confirmations, credentials, cancellation, and recovery with the
owner. Direct configuration tools can be implemented independently; setup approval
does not authorize an unreviewed browser-control redesign.

## First execution assignment after plan approval

Lead: reconcile the baseline and record acceptance IDs/state contracts. Worker A:
build canonical All/Unread behavioral fixtures and legacy-data preservation tests.
Worker B: build an isolated rendered-browser harness and reproduce the critical
Current/Next/duplicate-turn cases. Reviewer: independently audit fixture isolation,
coverage, and the baseline diff. These are phase-0 tasks, not permission to implement
future phases in parallel. First push is the reviewed baseline/test infrastructure
section; phase 1 follows only after its required CI is verified.

Planning reviews completed by separate dependency and test/CI agents. They inspected
code/configuration read-only; no test suite or live integration was run in planning.
