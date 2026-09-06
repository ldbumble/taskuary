# Processing implementation evidence

## Phase 0 / section 0.1: baseline and test infrastructure

Status: section 0.1 CI-verified at 9bef568. Phase 0 baseline infrastructure is accepted. Base `2689679dd87227ff9102bb7d7feb8920e3c47ca6`.
No Phase 1 state migration or browser-control redesign has started.

### Baseline and ownership

- Original checkout: master at base, matching origin/master on 2026-09-06.
  Only README.md was dirty; Git reported no content diff (line-ending/index state).
  Preserved untouched. No stash/reset/clean or user-data edits.
- Checkpoint CI: [run 34010359323](https://github.com/ldbumble/taskuary/actions/runs/34010359323)
  completed successfully for the exact base SHA: six Python OS/version jobs,
  frontend, Docker smoke and Windows executable.
- Existing approved queued-start and complete COUNSEL fixes already belong to base.
  No second implementation or live document update is needed.
- Integration: root in isolated processing/phase0-integration checkout; sole owner
  of docs/ledger, CI, packaged UI, integration commits and pushes.
- Implementation: phase0_fixtures (Sol High), tests/conftest.py and new synthetic
  fixtures/preservation tests in processing/phase0-fixtures.
- Implementation: phase0_browser (Sol High), isolated rendered-browser harness
  in processing/phase0-browser. No browser-control product changes.
- Independent integration/review: phase0_review (Astra Extra High), read-only audit
  of safety, contracts and final diff. Agents do not push or merge.

### Acceptance and contracts

Owner policy response, 2026-09-06: preserve historical read results, including old
display-only handling, and apply the new display-does-not-read semantics going forward.
This resolves the historical migration ambiguity without authorizing a blanket unread reset.
Owner ordering response, 2026-09-06: approved the five proposed bands and chose
oldest activity first within each band, after triage priority. Band 1 covers urgent
requests and current/starting-within-15-minutes calendar items; bands 2 through 5
are agent waits, other actionable tasks/finished results, FYIs, and working agents.

| Phase 0 ID | Requirement | Evidence/status |
| --- | --- | --- |
| P0-INVENTORY | Preserve/classify dirty tree and verify checkpoint CI | Complete inspection above; README untouched |
| P0-LEDGER | Every TODO checkbox has stable phase/test/commit tracking | 267 permanent PW IDs; JSON/Markdown ledger; coverage validator |
| P0-CONTRACT | State contracts and superseded language documented | processing-state-contracts.md; unresolved policy questions pending |
| P0-ISOLATION | Disposable test homes and external-effect prevention | Implemented and independently reviewed; executed evidence below |
| P0-FIXTURE | Synthetic Unread/group/wait/duplicate/replay and legacy preservation | Implemented and independently reviewed; executed evidence below |
| P0-BROWSER | Real rendered-browser harness, loading/replay timing | Implemented and independently reviewed; executed evidence below |
| P0-REGRESSION | Full cumulative suites/build/native PTY and baseline failures | Backend 2187 + 66 subtests; frontend 262; browser 2; build parity passed |
| P0-REVIEW | Independent final diff and isolation review | Astra Extra High independent code, isolation and final staged evidence review approved |
| P0-REMOTE | Scoped push to origin/master and exact-SHA CI | 9bef568; CI run 34012833267: all 10 jobs successful |

See processing-existing-failures.md for observed deficiencies separately from test
failures. Every unchecked PW requirement remains pending implementation. Previously
checked document-only changes retain their original scope; no expanded claims.

### Commands and results

OS: Windows; Python 3.10; baseline Node 20.10.0, final Node 22.23.2; npm 10.2.3. All commands run in the isolated
integration checkout, never the directory serving the owner's app. Runner durations
are listed separately from dependency installation and orchestration time.

| Command | Base/input | Result | Duration |
| --- | --- | --- | --- |
| gh run list --commit 2689679dd87227ff9102bb7d7feb8920e3c47ca6; gh run view 34010359323 | Remote base | All 9 jobs successful | Existing run |
| npm ci (website) | Locked baseline dependencies | Installed; Node engine warnings recorded as OBS-007 | 51 s |
| npm test (website) | Unchanged baseline frontend | 262 passed; 0 failed/skipped | 2.113 s |
| npm run build (website) | Unchanged baseline source | Passed; generated assets differ from committed baseline; initial parity discrepancy resolved below | 52.89 s |
| npm run build (website), then git diff --exit-code -- taskuary/web and untracked-asset check | LF-normalized baseline inputs | Passed; exact committed asset content/names restored. Difference was CRLF encoding, not stale source | 12.80 s |
| python -m pytest -q tests/test_processing_ledger.py tests/test_processing_demo_replay.py | Integration plus bounded Replay compatibility fix | 4 passed | 2.82 s |
| python -m pytest -q | 2689679 + isolation a0ce5c2 + Replay fix + ledger tests | 2157 passed, 12 failed, 1 existing skip, 66 subtests; isolation guards blocked legitimate synthetic CLI/MCP children and platform probe, and a browser mock masked direct tests. Initial failed gate, repaired in final run below | 160.61 s |
| python -m pytest -q -ra | Integrated isolation/preservation 6dd42b4, Replay fix and ledger tests | **2186 passed, 66 subtests passed, 1 existing clock-dependent skip**, 149 warnings. All 12 initial failures resolved without changing earlier assertions | 157.55 s |

The existing skip is `tests/test_digest_brief.py:138` before the 08:00 daily slot.
Existing `FakeScreencast.stop()` teardown warnings in tests/test_browserview.py stop
an asyncio loop before coroutine cleanup; they are recorded separately and are not
proof of successful shutdown. Full regression includes native Windows ConPTY tests
using reviewed synthetic Python children; it does not establish real provider approval.

The rendered fixture exposed missing `demo.Replay.quiet_for`, which disconnected
the real terminal websocket during attachment. Local commit `6a50579` supplies the
no-op recording contract and tests two real websocket reattachments, ready/replay,
subscription cleanup, preserved idle state and ignored input. Independent Astra review
approved this bounded Phase 0 loading fix. No real terminal or browser-control redesign.

### Final frontend/browser gate

The original Puppeteer 25.8.0 dependency lock is retained byte-for-byte from 2689679.
Use Node 22 for all frontend gates. On this machine the disposable runtime came from
`npm exec --yes --package=node@22 -- node -p "process.execPath"`; its directory was
prepended to PATH only in each test shell. No global runtime installation was changed.
CI web/browser jobs now use Node 22. The npm test script explicitly selects all
`test/**/*.test.mjs` files because Node 22 no longer accepts the old directory argument;
all 52 existing files and 262 cases remain covered, with no earlier assertion edits.

| Command (website, disposable Node 22.23.2) | Result | Duration |
| --- | --- | --- |
| npm ci | Baseline lock installed; no introduced dependency advisories | Dependency installation |
| npm test | **262 passed; 0 failed/skipped** | 1.467 s |
| npm run build | Passed; original asset filenames/content retained | 24.67 s |
| npm run test:browser | **2 passed; 0 failed/skipped** | 43.454 s |
| git diff --exit-code -- taskuary/web; git ls-files --others --exclude-standard -- taskuary/web (repository root) | Both empty: source/shipped UI parity | After final build |

Real Edge/Chromium on a fixed 37-item invented demo SQLite fixture, with isolated
homes/ports and blocked outbound HTTP/WebSockets/TCP. Current/Next, double Walk,
explicit Next, tab return/reload, no duplicate/unsolicited turn, Tasks/Board/Reports,
terminal output/ready, input emission during replay and reconnect were exercised.

| Measurement | Integrated Windows result | Provisional enforced ceiling |
| --- | --- | --- |
| Assistant first visible | 5259 ms | 8000 ms |
| Composer input | 862 ms | 1500 ms |
| Tasks / Board / Reports visible | 196 / 225 / 238 ms | 3000 ms each |
| Terminal replay visible | 4031 ms | 10000 ms |
| Terminal input emission | 65 ms | 1500 ms |
| Terminal reconnect | 870 ms | 10000 ms |

The recording intentionally ignores input: browser emission is not provider acceptance.
The backend suite separately tests native ConPTY with synthetic Python children.
Performance budgets are repeatable smoke/regression ceilings, not a general load-test
or provider-response guarantee. Keep the recorded fixture size and ceilings in later gates.

### Remote checkpoint repair

First push: `75a7604b374e8eb7f5cc1543eb9e1b38413d730c`,
[CI run 34012476316](https://github.com/ldbumble/taskuary/actions/runs/34012476316).
Web tests/build/parity, rendered browser and Docker passed. The Python matrix
failed collecting the new fixture package: `pytest` does not add the repository
root to imports in the same way as `python -m pytest`. The sibling import was
changed from `tests.processing.fixtures` to `.fixtures`; no test assertions changed.
Independent Astra review approved the correction. The exact console entrypoint
`pytest -q -ra` then revealed the local editable install selected the original
checkout rather than this worktree: 2184 passed and the two new Replay tests failed
in 158.42 s, with traceback paths proving the wrong source. Test data remained in
the isolated home. The bootstrap now prepends its own checkout before application
imports and rejects a previously loaded wrong-root package; a new test verifies
package/config/server provenance. This correction also received independent Astra
review. The corrected console entrypoint is rerun locally, followed by another
scoped push and exact-SHA CI.
This first remote checkpoint is not accepted; no Phase 1 code has started.

Corrected console-entrypoint gate: `pytest -q -ra` on the integration worktree
passed **2187 tests and 66 subtests**, with the same one existing time-dependent
skip and 150 warnings, in **155.86 s**. Application import paths now resolve to the
tested checkout. Frontend/browser/runtime source and dependency lock did not change
during this collection/bootstrap repair; their passing results above remain applicable.

### Migration, rollback and limitations

Phase 0 makes no database schema or live data migration. Synthetic reopen evidence
and the additive migration/backup/rollback contract are prerequisites to later state
changes. Preserve all original read evidence, attachments, task history and custom
documents. No app restart, production connector use, outbound delivery or real model
run is part of this section. Browser-control ownership/UI remains pending owner review.

Section 0.1 delivery gates are complete. No later phase may be accepted on these
baseline results alone; each must rerun cumulative gates.

### Accepted remote checkpoint

Implementation checkpoint: `9bef568093b6085821e384b3cc66974fde6d2351` on
origin/master. [CI run 34012833267](https://github.com/ldbumble/taskuary/actions/runs/34012833267)
completed successfully for that exact SHA: six Python jobs (Windows/Linux/macOS,
3.10/3.12), frontend tests/build/packaged parity, rendered browser, Docker smoke,
and Windows executable. The earlier failed checkpoint is superseded, not concealed.

The original README.md remains unmodified, SHA256
`EDF56683E29A34789B2EBEF73E131FBD7B318AE498BC761668BCB70854D91BAB`.
Raw local logs are preserved under the integration worktree's ignored
`.codex-tmp/phase0-evidence/`; only scoped source/tests/docs entered the commits.

Next: Phase 1 canonical identity/context and historical-read preservation foundation.
Later grouping/action/deferral policy transitions remain separate pending decisions.

## Section 1.1 — canonical identity and historical-evidence foundation

Status: section 1.1 is CI-verified at `85c2e1b`. This accepts the foundation only,
not the entire Phase 1 redesign.
Base `8be0b769b411346b2a380e0037a54426703c5af5` passed all ten jobs in
[CI run 34013108300](https://github.com/ldbumble/taskuary/actions/runs/34013108300).
PW-101 and PW-104 are partial targets; no Phase 1 feature checkbox is completed by
additive storage alone. Shared feed/UI adoption, final read cutover, ordering and
Current/Next remain subsequent sections.

### Ownership and boundaries

- Sol High storage agent: isolated `processing/phase1-store`, sole owner of
  `taskuary/store.py` and storage/migration tests.
- Sol High model agent: isolated `processing/phase1-model`, pure
  `taskuary/processing.py` and fingerprint/legacy-evidence tests.
- Lead: isolated `processing/phase1-integration`, seam tests, integration,
  cumulative gates, documentation and delivery.
- Astra Extra High reviewer: independent architecture and final-diff review.

User decisions carried forward: preserve old effective read results with their
provenance; use display-does-not-read after the later semantics switch. Sort within
the five approved bands by triage priority, oldest activity, then stable identity.
New activity during deferral and grouped Done remain pending policy decisions.

### Implemented scope and review

Durable alias/member continuity, independent digest ideas, provider scope isolation,
full-body/attachment context fingerprints, view-only changes, uncapped legacy
capture of 507 messages, atomic rollback/retry, concurrent initialization, repeated reopen and
unchanged original records/documents. Independent seam tests compare captured
legacy evidence against both explicit expected outcomes and the unchanged feed.

Startup adds storage only. Explicit synthetic baseline capture does not activate
new read semantics. The eventual cutover must capture/reconcile final historical
evidence atomically; later arrivals must not receive repeated legacy inference.
No live app restart or migration is included. Browser control/UI redesign remains
pending review.

The canonical tables retain exact entity targets, active and retired memberships,
explicit aliases, item redirects, independent wrapper relations and versioned legacy
evidence. Unscoped provider IDs are not inferred from display names. Each baseline
stores full context/view inputs once per item/version under the same completion
transaction, while preserving raw legacy records. Replaying a completed baseline
does not recapture later owner writes or new arrivals. A subsequent explicit capture
can retain an FYI identity when it gains a task anchor.

Current snapshot getters use one SQLite read transaction even across an external
connection's merge. Their computed revisions cover complete message bodies (tested
beyond the old 4000-character preview), task summary/context, attachment metadata,
idea substance and explicit relations. Drafts, route verdict/errors, task status,
priority, legacy read/defer, category settings and supplied worker attention affect
the view revision. Missing worker observations are distinct from observed empty
ones; copied nested payloads cannot change after a revision has been returned.

Astra independently compared the legacy predicate against 1,500 synthetic cases;
selected key and observed unread agreed in every case. It also AST-compared all
pre-existing store methods with the accepted base: none changed. Reviews corrected
provider display-name inference, due-note and closed-worker enrichment, idea ordering,
omitted raw/excluded evidence, merge-history visibility, concurrent captures, mutable
worker snapshots and an insufficient resolver-race assertion before final approval.
No previous assertion or skip was weakened.

### Local gates

| Gate | Result | Duration |
| --- | --- | --- |
| `python -m pytest -q tests/processing` | 98 passed, including all Phase 0 fixture/isolation gates | 6.30 s |
| First full `python -m pytest -q -ra` | 2262 passed, 66 subtests, one existing pre-08:00 skip; before final projection/worker additions | 168.73 s |
| Final full `python -m pytest -q -ra` | 2267 passed, 66 subtests, one existing pre-08:00 skip, 150 existing warnings | 159.43 s |
| Node 22 `npm test` | 262 passed; no failures or skips | 1.342 s |
| Node 22 `npm run build` | Passed; packaged assets match committed source output exactly | 27.00 s |
| Node 22 `npm run test:browser` | 2 real-browser scenarios passed | 44.364 s |

The unchanged 37-item synthetic demo/browser harness measured first visibility
5875 ms, input 738 ms, Tasks/Board/Reports 146/231/187 ms, terminal replay 3877 ms,
input emission 122 ms and reconnect 1089 ms. All existing ceilings passed without
changes. The demo recording still proves input emission, not provider acceptance.
The final worker-copy repair only affects explicit foundation APIs unused by the
current demo/production consumers; frontend source, packaged assets and browser flows
did not change after this browser run.

Local logs are retained under the isolated integration worktree's ignored
`.codex-tmp/phase1-evidence/`. Existing FakeScreencast teardown and Pydantic warnings
remain recorded; they are not evidence of a new shutdown fix.

### Delivery checkpoint

Source integration commit: `81981b8`. Agent source commits are `13d4aab` (pure
model), `f5ac813` (storage) and `7ce76bf` (projection tests), integrated as `917123a`,
`9a1636b` and `2e458de` before the lead's seam corrections. All local gates and
independent review above cover the final integrated source. Delivery checkpoint
`85c2e1b104059e906fbfcca46809db9b0a2a7d4c` passed all ten jobs in
[CI run 34014667609](https://github.com/ldbumble/taskuary/actions/runs/34014667609):
the six Python matrix jobs, frontend/build parity, real browser, Docker and Windows
executable. The original checkout was fast-forwarded after that result; README SHA256
remains `EDF56683E29A34789B2EBEF73E131FBD7B318AE498BC761668BCB70854D91BAB`.

Rollback compatibility: additive tables and APIs leave existing consumers unchanged.
An older app can ignore the new tables but cannot consume canonical evidence. No
automatic backup restoration is performed; corrective migration must preserve writes
after any baseline. The eventual live cutover still requires the consistent-backup
and final-evidence gate in the state contract. No live migration or restart occurred.

## Section 1.2 — All and Unread view controls

Status: CI-verified at `2557c94`, from accepted base `85c2e1b`.
Scope: PW-107's approved two-view UI. Remove every Needs me navigation/filter entry
and enforce All as a detail-only surface while preserving the Unread funnel,
Current/Next and deliberate task/detail actions. Canonical inventory adoption, new
read semantics, ordering and unresolved grouped/defer/exclusion transitions remain
separate work; this section does not activate them.

Sol High UI agent owns `FeedView.jsx` and frontend contract tests in isolated
`processing/phase1-views-ui`. A second Sol High agent owns rendered-browser acceptance
in `processing/phase1-views-browser`. The lead integrates on `processing/phase1-views`,
builds packaged assets, runs cumulative gates and delivers. Astra Extra High provides
independent review. Existing assertions are retained unless a Needs me expectation is
explicitly superseded by PW-107, with replacement behavioral evidence recorded here.

The feed no longer constructs `pending_only` or exposes Needs me navigation and
statistics. Action-needed status remains available. All retains deliberate detail
actions; entering, hovering, pinning and returning to it cannot start Walk, settle
an item or create an assistant turn. Unread retains Current/Next and chat/task mode.
All/Unread changes reuse their identical underlying feed query rather than fetching
it again solely because the view changed. Existing refresh and mutation paths still
refresh data. Switching views clears detail and invalidates pending hover responses;
it does not clear or advance Current.

The two old source-location assertions in `funnelPile.test.mjs` now verify wiring
to the extracted `feedInteraction` helper. Its behavioral truth table covers All,
Unread, chat/task mode and callback availability. All other prior assertions remain;
the new real-browser tests additionally verify rendered controls and durable state.
PW-107 stays partial because live-state-before-selection is not activated here.

Local cumulative backend gate: `python -m pytest -q -ra`, 2267 passed plus 66
subtests, one existing pre-08:00 skip and 150 existing warnings, 159.72 seconds.
Final Node 22 frontend gate: 264 passed, no failures/skips, 1.325 seconds.
Final packaged build: passed in 11.43 seconds, including the pending-detail fix.
Logs remain in ignored `.codex-tmp/phase1-views-evidence/` in the isolated integration
worktree. Final browser race coverage, review and remote checkpoint follow below.

Independent Astra Extra High review approved the final UI, tests and scope. Its
pending-hover finding is fixed in `ac5f192`. The real browser regression in
`d60e2ab` uses a fresh page and CDP latency on an actual fixture detail GET, switches
to Unread while that request is pending, and waits for the full body and rendering.
It then verifies visible Unread chat, unchanged Current/Next and exact durable turns.
Negative control against the exact pre-fix UI `3a5fc4a` fails because stale detail
replaces chat; the exact fixed UI passes (15.710 seconds for the focused scenario).
No harness network guards or previously accepted tests/ceilings were relaxed.
Agent commits: UI `3a5fc4a`, browser `c535f4e` and race follow-up `830094b`;
integrated as `0435ce9`, `2977162` and `d60e2ab`, with the lead's `ac5f192` fix.

Final integrated Node 22 `npm run test:browser`: 3/3 passed, no failures/skips,
35.762 seconds. First visibility/input: 2348/472 ms; Tasks/Board/Reports:
136/160/136 ms. Terminal replay/input/reconnect: 3459/52/698 ms. Existing ceilings
and network isolation passed unchanged. Desktop, narrow-screen and delayed-response
tests cover the final source; packaged assets were generated from that exact UI.
Delivery `2557c946d23903ea28662b05e343c6f19776cc0a` passed all ten jobs in
[CI run 34016219556](https://github.com/ldbumble/taskuary/actions/runs/34016219556),
including packaged parity and the new browser regression. The original workspace
was then fast-forwarded; its README hash is unchanged. No live app restart, data migration or
production connector was used. Browser-control redesign remains pending.

## Section 1.3 — frozen inventory, ordering and pagination foundation

Status: CI-verified at `162afbc`, from accepted base `2557c94`.
Partial acceptance targets: PW-101/102/103/106/109/110/111/112. This section adds
internal read-only enumeration and pure ordering/pagination mechanics. No server
endpoint, feed/assistant consumer, live migration or read-policy transition is
activated. Canonical roots are read in one SQLite transaction without age/category
caps. Coverage reports uncatalogued records and unsupported adapters explicitly;
an empty canonical table is not proof of an empty inbox.

The store agent owns `store.py` and focused inventory-store tests in isolated
`processing/phase1-inventory-store`. The pure-model agent owns
`processing_inventory.py` and its tests in `processing/phase1-inventory-model`.
Both use Sol High. The lead owns integration tests/docs/gates on
`processing/phase1-inventory`; independent review uses Astra Extra High.
Source activity and recognized priority can support raw chronological ordering;
priority bands require explicit revision-bound ranking facts where persisted state
cannot establish live attention. Unknown facts stay diagnostic, never guessed read,
exclusion or automatic-selection decisions. Calendar enumeration remains unsupported.

### Implementation and review

Store agent source `eac48c7` integrates as `b1ea30d`. It factors the existing
single-item snapshot body into a private cursor helper, preserving the public
getter's output, and adds `processing_inventory_snapshot(fixed_now=..., live_state=...)`.
All roots, memberships, projections, exact legacy evidence and coverage share one
SQLite read transaction. Full snapshot content and the frozen complete worker input
contribute to revisions. Worker unavailability differs from an observed empty set;
non-JSON input is rejected before opening a transaction. No schema or runtime
consumer changed, and no getter allocates identity or writes receipts.

Pure-model source `9b0281a` integrates as `d696114`.
`processing_inventory_page` supports raw All/priority order with transport pages of
1–500 items; 507-item tests prove there is no inventory cap. Cursor tokens bind
snapshot, order, normalized ranking facts, query version, position and anchor.
Changed or malformed inputs require an explicit restart/error. Counts remain raw
canonical/member/returned/remaining counts, never eligible or unread totals.
Returned data is detached from caller snapshots, which remain immutable across pages.

Ranking facts require the exact current item view revision. Urgent/current-or-soon
calendar facts rank first, owner input/approval second; working remains band 5 even
with generic FYI/actionable/old-result signals. Without working, actionable/finished
and FYI facts use bands 3 and 4. Priority then oldest activity and stable identity
break ties; All uses newest comparable activity. Calendar is current on a half-open
start/end interval or starts within an inclusive 15 minutes of the frozen clock.
Missing/naive activity remains unknown and sorts last within its applicable band
and priority. Source timestamps retain exact-entity provenance. Task creation cannot
replace a message's older activity, and a related idea cannot lend activity to a
different canonical wrapper. Read, defer, exclusion and actionability stay unknown.

Astra Extra High independently approved storage, model and the initial integration
test design. Review corrected working precedence and cross-item idea activity before
acceptance. Lead review also corrected timestamp formatting, calendar endpoints,
task-only activity fallback and malformed cursor/count validation. No earlier test
assertion or skip was weakened. All 144 integrated processing tests pass (8.66 s),
including 507-item storage/page coverage, owner-table preservation, concurrent WAL
merge isolation, six in-place revision changes, stale facts/cursors, failed projection
cleanup/retry, old uncatalogued arrivals and independent wrapper/idea identities.

### Cumulative gate findings

The first cumulative backend run had 2312 passes plus 66 subtests, one existing
pre-08:00 skip and one failure: `test_index_serves_ui` observed HTTP 503 while the
lead ran Vite's output replacement concurrently. The unchanged serving code returns
that status when `index.html` is temporarily missing. The focused test passes after
the build (0.79 s); a full rerun with stable assets is required below. The plan now
explicitly sequences these dependent gates. No test expectation was changed.

Frontend: 264 passed (1.394 s). Build: passed (13.65 s), with packaged assets
identical to the accepted source output. The first browser run passed two scenarios
but failed PW-107's narrow-screen Next equality; Current stayed unchanged. This is
being investigated before delivery, without relaxing the accepted assertion.

The final backend rerun with stable packaged assets passed: 2313 tests plus 66
subtests, one existing pre-08:00 skip and 150 existing warnings, 167.08 seconds.
The existing fake-screencast teardown/Pydantic warnings remain unchanged.

The browser investigation reproduced the exact Next change in real fixture API
state: immediately after Walk all three recorded demo sessions were working and
Next was the Q3 review; 7.751 seconds later they were parked/waiting and Next was
the Northwind census agent. That is a legitimate background promotion, not a view
navigation mutation. PW-107's setup now waits for those actual sessions to reach
their final waiting state before the first page opens. It requires a nonempty set
and the census session. A deliberately slow run then exposed the watcher's separate
12-second dwell: it subsequently recorded three legitimate waiting notifications.
Setup therefore also waits until those exact session task IDs are durably announced
and a subsequent forced pile has no events, then starts a fresh synthetic conversation
before any page opens. Every Current/Next, history, gesture and isolation assertion
is retained; no runtime or harness behavior is suppressed. The normal run passed
and an added 8.5-second post-Walk diagnostic delay passed (44.49 s). That temporary
delay was removed; the final focused run passed (38.72 s including setup/teardown).
The terminal replay scenario still uses its separate live recording and original
timing gates. This fixture correction does not claim unsolicited watcher behavior
is redesigned; that remains a later acceptance item.

### Final local gates and delivery

| Gate | Result | Duration |
| --- | --- | --- |
| Integrated processing tests | 144 passed | 8.66 s |
| Final full backend | 2313 passed, 66 subtests; one existing skip | 167.08 s |
| Node 22 frontend tests | 264 passed, no failures/skips | 1.394 s |
| Packaged build | Passed; output unchanged from accepted UI | 13.65 s |
| Final cumulative real browser | 3 passed, no failures/skips | 58.780 s |

Final browser timings: first visibility/input 2433/468 ms; Tasks/Board/Reports
150/145/130 ms; terminal replay/input/reconnect 3455/81/785 ms. Every original
ceiling passed. Setup stabilization source `afc3a10` integrates as `3334680`;
lead integration tests are `5b8044b`. Independent review approved final source,
schema preservation, tests, fixture correction and partial acceptance scope.
Logs remain in ignored `.codex-tmp/phase1-inventory-evidence/` in the isolated
integration checkout. README SHA256 remains
`EDF56683E29A34789B2EBEF73E131FBD7B318AE498BC761668BCB70854D91BAB`.
No live data, read states or documents were migrated; no live app was restarted.
Delivery `162afbc7760192bdb0ef039f663c522e88ca8cb7` passed all ten jobs in
[CI run 34017816426](https://github.com/ldbumble/taskuary/actions/runs/34017816426).
The original workspace was then fast-forwarded with its README change preserved.

## Section 1.4 — complete display freshness

Status: CI-verified at `3ef0bdc`. PW-106 is a partial target: this section refreshes the existing runtime
presentation without activating canonical identities/read policy or shared Next.

Sol High backend work in `processing/phase1-freshness-backend` owns funnel presentation
fingerprints and focused tests. Sol High UI work in `processing/phase1-freshness-ui`
owns Assistant presentation replacement, lazy content refresh and frontend tests.
The lead owns the completed HTTP response seam, API/browser evidence, packaged build,
integration and delivery. Astra Extra High independently reviews the changes.

Backend `8b634b9` integrates as `334642a`; UI `ef324b8` as `5109c9d`.
Per-item `presentation_revision` covers complete backing rows, including full source
bodies, exact task members, drafts, attachments, comments, runs, waitroom and reply
capability inputs. Taskless conversation context is tracked separately from the exact
task membership boundary. Nested FYI presentations are stamped recursively. The
completed response's `display_revision` includes ordered items, displayed counts,
rules, lanes, alerts and query-specific Current, including explicit null. Transient
events and revision fields do not create a self-changing hash; legacy `rev` remains.

The UI prefers the complete display revision and replaces fresh Current data rather
than merging removed fields back into it. Lazy source/draft/report readers refetch on
presentation changes and discard obsolete responses. Unsaved local draft edits stay
intact. Current refs are synchronized before asynchronous responses arrive; a response
for an earlier Current cannot overwrite a later selection. Explicit null clears stale
data, with the existing narrow same-task working handoff retained. Next selection,
event scheduling, read semantics and actions are not redesigned in this section.

An accepted repeat-Next test caught display metadata defeating durable duplicate
suppression. Only transient `presentation_revision` is omitted from serialized durable
cards, including actual nested FYI children; live responses retain it. Atomic store
deduplication and semantic card fields are unchanged. No earlier assertion was weakened.

Initial integrated display/API tests pass. The browser fixture's existing startup
stabilization was extracted unchanged into `processing-fixtures.mjs`. New private
fixture edits simulate source/member/draft updates in the disposable database, with
bounded parameters and actual feed-change delivery. They are installed only by the
fixture server after outbound guards; every production route retains its original
demo refusal. A unit test checks those refusals and rejects malformed edits.

### Final local gates and delivery

The real browser scenario uses actual saved drafts, a two-message task and websocket
source updates. It verifies same-ID draft edits/clearing, source edits/clearing,
and preservation of unsaved owner text after observing the newer saved draft response.
The delayed-response case captures the old body and waits for that exact network
request to finish after release before checking that newer rendered context survives.
Current, durable conversation history and assistant/settle request counts stay fixed.
The focused scenario passed (32.058 s; 53.178 s including process setup/teardown).

| Gate | Result | Duration |
| --- | --- | --- |
| Integrated processing tests | 162 passed | 13.05 s |
| Full backend (`python -m pytest -q -ra`) | 2332 passed plus 66 subtests; no skips | 203.13 s |
| Node 22 frontend (`npm test`) | 271 passed; no failures/skips | 1.676 s |
| Packaged build (`npm run build`) | Passed; generated assets included | 37.40 s |
| Cumulative real browser (`npm run test:browser`) | 4 passed; no failures/skips | 121.037 s |

The prior clock-dependent digest test ran after 08:00 in this suite. Backend emitted
151 warnings; details are retained in the full log. Browser first visibility/input
were 2515/957 ms, Tasks/Board/Reports 234/383/250 ms, and terminal replay/input/reconnect
2520/107/1045 ms, all within the existing ceilings. No earlier assertion was weakened.
Independent Astra Extra High review cleared backend/UI source, root API and fixture
seams, the delivered-old-response proof, and generated asset integrity. Logs are in
ignored `.codex-tmp/phase1-freshness-evidence/` in the integration checkout.

README SHA256 remains
`EDF56683E29A34789B2EBEF73E131FBD7B318AE498BC761668BCB70854D91BAB`.
No live app restart, live data migration, read-state reset or owner-document edit.
Delivery `3ef0bdc4e999d3b4ca268b56ca01e90e8f6789e9` passed all ten jobs in
[CI run 34033187439](https://github.com/ldbumble/taskuary/actions/runs/34033187439).
The first normal push encountered an intervening download-statistics bot commit;
rebasing preserved that docs-only update. The tested application and test files
were unchanged. Final backend/UI source commits are `34d4d65` and `87a69e4`.
The original workspace was fast-forwarded with its README edit preserved.
PW-106 remains partial because shared selection and canonical runtime adoption
are later work.

## Section 1.5 — shared captured Next and stable Current

Status: CI-verified at `7589b38`, implemented from CI-verified `3ef0bdc`.
Sol High backend owns funnel selection, the captured concierge surface path and
focused backend tests. Sol High UI owns server-derived Next, exact request scope,
Walk resume, stale-response handling and passive-event Current preservation.
The lead owns API admission/concurrency, New chat coordination, real browser
evidence, integration and delivery; Astra Extra High independently reviews.
Claude separately owns Phase 2 intake; this section does not edit intake files.

This slice retains legacy eligibility and read policy. It adds a read-only capture,
an explicit revision/key/FYI-members binding and a guarded modern automatic Next
path. Named-key pulls and old clients remain compatible and outside that guard.
The process-local reservation coordinates navigation and New chat, including a
post-model check and short commit lock. It does not provide a transaction against
external SQLite writers or durable/restart/multi-process operation idempotency.
An accepted request may create an empty dock before model work; initially stale
requests must not create a dock or make any selection-dependent writes.

The backend's single native observation required one authorized additive store
seam: `feed(..., live_state=...)` can consume the captured list; its default keeps
legacy behavior. Captured questions retain their rendered text. Failed native
observations raise `selection_unavailable`, never a known-empty selection.
Only the selected item/FYI members bind full presentation revisions; unrelated
working-tail churn cannot repeatedly invalidate an otherwise unchanged Next.
Calendar selection hashes its eligibility boundary rather than elapsed minutes.
Background cards receive explicit provenance going forward; historical untagged
cards are preserved and are not guessed or rewritten.

The original backend source is `83ddd3c8263a57fcda0da0f3fe212c1fb33f5352`, integrated
as `c640586`; its consistency follow-up `d878d7e3805b776689a0c62f8a0d81480adbbbbd`
integrates as `9f82ee4`. Integrated API/display/fixture seams passed
31 tests (3.45 s); cumulative processing tests passed 197 tests (20.36 s).

UI source `170de0b`, `8dd0baa`, `995944c` integrates as `f4669a2`, `98c7505`,
`c43ef5f`. Modern Next uses the exact scope/revision/key/member binding. Structured
initial or late stale/unavailable responses never fall back to a second request;
sparse late errors invalidate the token, and server outcome messages remain truthful.
Walk validates/resumes its current subject and aborts across a chat epoch change.
The existing rendered Walk control is welcome-only, so valid-Current Walk resume
is not claimed as a newly exposed UI control. Scoped-empty mail navigation remains
reachable to clear mail scope without inventing a Next badge. Passive cards remain
readable but cannot choose Current or become its interactive action card.

The real-browser stale-Next case pauses the actual POST, changes the selected task's
context, and observes HTTP 409 with no plain fallback, no Current change and no
durable assistant turn. A new owner click consumes the displayed next item exactly.
A bounded synthetic passive card then tests live ingestion/reload while preserving
both Current and its original interactive card title/buttons; native watcher
production of the provenance flag is covered by backend tests.

Two negative controls demonstrate the browser checks detect the prior behavior:
the old UI sends no selection revision; the pre-fix async Walk, after its held pile
response is released following a completed New chat, sends an obsolete navigation
request. The final Walk test waits for that exact old response to finish delivery,
then verifies no navigation request, Current or durable turn enters the new chat.
The first positive navigation run passed its behavioral assertions but used the
wrong object for the isolation assertion; it was corrected to `page.fixtureEscapes`.
An intermediate cumulative run passed four scenarios and failed only launching
Chrome for the terminal fixture's unique profile. No owned browser remained after
cleanup; the final unchanged terminal scenario passed, without weakening its gates.

Final frontend tests: 278 passed (1.385 s). Final packaged build: exit 0 (13.09 s).
Final cumulative rendered browser: six passed (186.280 s), no skips. First
visibility/input were 933/502 ms; Tasks/Board/Reports 170/166/150 ms; terminal
replay/input/reconnect 2089/81/952 ms, within every existing ceiling. Independent
Astra Extra High review cleared final backend, UI, root API/fixture/browser seams,
and generated assets. Final backend rerun and remote delivery are recorded below.

Final backend (`python -m pytest -q -ra --tb=short`): 2367 passed plus 66 subtests,
151 warnings, no skips, 197.21 seconds. The warnings retain the existing Pydantic
and fake-screencast cleanup observations. All local gates passed. No live restart,
connector test, read migration or owner-document change was performed.
Logs are ignored `.codex-tmp/selection-*.log` in the isolated integration checkout.
Delivery `7589b386f166e70450f3baa6481e6da1d937e5f0` passed all ten jobs in
[CI run 34035165692](https://github.com/ldbumble/taskuary/actions/runs/34035165692).
The original workspace was fast-forwarded; its README hash remains the preserved
`EDF56683E29A34789B2EBEF73E131FBD7B318AE498BC761668BCB70854D91BAB`.

## Section 2.1 — independent poll scheduling and settings

Status: integration in progress from CI-verified `7589b38`. This section does not
depend on the still-pending Phase 1 read-policy answers or activate the canonical
inventory. The owner assigned Phase 2 intake to Claude in parallel; its isolated
handoff is in `processing/phase2-intake-poll`. Initially, only the polling/settings
commits were integrated: `4591fcd` as `e7c47dc`, and `12c1a4e` as `2daacc6`.
Outlook/IMAP catch-up and full-chain work remain separate sections.

The handoff introduces separate full/quick polling clocks, fresh-channel ordered
drain priority, full-fetch interval bookkeeping and shared polling labels for all
six chat connector cards. The six earlier rendered-browser scenarios remain gates.
Astra Extra High review found four issues before acceptance: non-atomic connector
admission, a synchronous quick-owned judge still blocking intake, stale banner
ownership on quick-first overlap, and connector types incorrectly used as message
channels for email overrides. Sol High owns bounded poll/ingest fixes and regression
tests; another Sol High agent owns rendered settings coverage. The lead owns API
responsiveness/preservation tests, integration, assets, evidence and pushes.

Worker `bff3e89e63805f03b479c8f91b9a182f01b51e22` integrates as `e7354f4`.
Connector admission is now atomic with owned release; the full lane stamps each
claimed chat attempt before releasing its claim, including failures. A skipped
attempt remains due. Fetch clocks submit to one ordered drain worker and release
their fetch locks before an explicit action waits for routing. Fresh-channel
tickets wait through route/review writes, but empty channels and finished fresh
routes need not wait for unrelated mail. Connector types map to stored channels.
Banner ownership is coordinated for either overlap order. Workers capture their
store/model factory; shutdown closes admission, retains timed-out workers, and
tests join owned drains before closing disposable stores.

Corrected label/browser source `4534104f3d5162c6dd2d6540921dd3e7d5c03370` integrates
as `841e085`. Copy distinguishes both recurring clocks from explicit/action/startup
fetches and separates inbound notification-chat replies from event-driven sends.
The unused handoff-only JavaScript parser and its duplicate-oracle tests were
replaced with tests of the actual Python parser; no previously accepted assertion
was removed or weakened. All six connector cards and Settings are checked in a
real read-only browser scenario with unchanged fixture state and zero writes.

Integrated focused gate: 68 tests passed (3.85 s), including the 33 polling-worker
tests and 35 root API/parser cases. The real feed API exposes two arrivals before
a held judge finishes, then verifies arrival-order routing and preserved historical
funnel state/custom documents. Another case fetches Teams in the full pass, holds
its report, then confirms a second Teams fetch and API visibility before that
report ends. Frontend: 281 passed (1.800 s); packaged build exit 0 (13.36 s).
Follow-up `de837503922a5efcb4a0ec73cb651378378777b6` integrates as `a4fdb5f`.
Scheduled polls recheck their due list while holding connector ownership, so a
timer decision made before a full fetch cannot immediately refetch after it.
Explicit context refreshes bypass cadence. Astra Extra High cleared the final
source, labels/browser and root API tests with no remaining source blockers.

An intermediate cumulative backend run passed 2434 tests plus 66 subtests and
failed the new fresh-route/unrelated-backlog test because its held mail was
released before the quick request was actually submitted. The follow-up waits
for the real ticket submission before releasing mail, preserving the same
completion assertion. Final focused integration passed 69 tests (3.67 s).
The intermediate browser run passed all seven scenarios (205.141 s). Full backend
and browser gates are being rerun on the final integrated source.

During those gates, another agent pushed its original polling and Outlook/IMAP
handoff to `origin/master` at `f244803beeee21f6079b4749e1df6c6e7ed4de8d`.
The polling source matches the handoff already reviewed here. Integration will
preserve that remote history and apply the reviewed polling corrections on top.
The email catch-up code's presence on master is not acceptance: repeated-page
completion, UIDVALIDITY identity, retry failures and concurrent settings updates
remain review findings for the following email catch-up section. No live app
restart or connector invocation was performed by this integration.

Reconciliation preserved remote `f244803` and replayed the reviewed corrections
as `9425824`, `6dec327`, `e837543` and `a0629e4`. Only generated-asset renames
conflicted; those were resolved to the reviewed source build and regenerated.
The source/test difference from the pre-rebase tree is exactly the four concurrent
email files (`channels.py`, `imapmail.py`, and their two catch-up test files).
Those four files match origin/master byte-for-byte. Before reconciliation, the
final polling tree passed 2436 backend tests plus 66 subtests (205.43 s, no skips)
and all seven browser scenarios. Cumulative gates on the combined remote base
follow; the email requirements remain unchecked until their review fixes land.

Final combined-base gates passed: 2452 backend tests plus 66 subtests, 151 existing
warnings, no skips (216.28 s); 281 frontend tests (1.533 s); packaged build exit 0
(14.29 s), with no asset drift; all seven rendered-browser scenarios (209.356 s).
First visibility/input were 2016/1500 ms; Tasks/Board/Reports 308/403/358 ms;
terminal replay/input/reconnect 2312/97/887 ms, inside every existing ceiling.
Astra verified the rebased polling source/tests/UI/assets are unchanged from the
reviewed tree and retained the separate, pending email-catch-up review boundary.
PW-001 through PW-005 are implemented; remote delivery/CI verification follows.
Logs: ignored `.codex-tmp/poll-remote-base-*.log` in the integration checkout.
Gates on the rebased tree: full backend 2403 passed plus 66 subtests (186.76 s); Node 22
frontend 283 passed; no-undef lint clean (nine pre-existing rule-definition notices in files not
touched); packaged build 15.11 s. One existing assertion moved with explanation (the chat clock
left `poll_forever` for `quick_forever`); none weakened. No live restart, connector, database or
owner-document change; browser-control redesign untouched.

## Section 3.1 — fresh evaluation for each new message

Status: implemented and tested locally at `c8769f6`; remote CI pending on the pushed
checkpoint. Acceptance PW-020, PW-022, PW-023, PW-024, PW-025 implemented; PW-021 partial
(evaluation runs in the stored conversation's context via `exchange_lines`; the full-chain
merge is PW-009 to PW-015, not yet built). The thread-dismissal veto (`ruled_on_thread`) and
the "SETTLED BY YOUR OWNER" prompt order are removed; the owner's ruling on the conversation
leads the EVIDENCE list (`ingest.thread_ruling`) and past verdicts stay in it verbatim.

Tests changed with explanation, none weakened: `test_verdict_sticks.py` (three veto cases
rewritten to evidence semantics, one added), `test_verdict_paths.py` (ruled-for-life case
rewritten), `test_assistant_reactions.py` (one case), `test_cc_triage.py` and
`test_learnedgraph.py` (settled-prompt cases inverted), `test_kind_dispatch.py`
(`_agreement` helper tests replaced by an evidence test). New: `tests/test_fresh_evaluation.py`
(15 cases). Full backend on this tree: 2415 passed plus 66 subtests, 151 warnings,
224.74 s. No frontend change; packaged assets unchanged. No live restart, connector, database
or owner-document change.

## Section 3.2 — explicit triage errors and retry

Status: implemented and tested locally at `ed2bb98`; remote CI pending on the pushed
checkpoint. Acceptance PW-036 to PW-040 implemented; PW-041 partial (no rendered-browser
click of the Retry control yet; backend, API and pure-UI state tests cover the rest).

Failed triage - a model exception, an answer that is not a verdict, a queue-drain failure, a
missing AI connector, and a failed follow-up judgement on an existing task - now lands the
message as `Status='error'` with the reason on its route, keeping content, attachments and any
task link; it was `filed`, the face of "nothing to do". `claim_retriage` claims error -> triaging
atomically (a legacy taskless `filed` row qualifies only when its last route is a failure
diagnostic); the retriage endpoint accepts linked error rows and returns a row to error with the
new reason when the retry fails again. `store.upgrade_triage_failures()` runs once at startup
and converts historical failures identified by their last route (never genuine fyi, never a row
the owner later ruled on, never a no-AI install's "awaiting" history), leaving funnel read state
untouched. In the pile an error row is unread information (fyi lane) as the Phase 1 inventory
tests already required; the All view and detail panel show "triage failed" with Retry.

Decision recorded for the owner: a no-AI install now shows new arrivals as "awaiting AI triage"
errors (with Retry explaining that no brain is configured) instead of filed fyi; historical
no-AI rows are left as they were. Tests changed with explanation, none weakened:
`test_api.py` (push without AI), `test_async_triage.py`, `test_assistant_reactions.py` (two
cases), `test_verdict_sticks.py` (unusable answer). New: `tests/test_triage_errors.py` (16 cases)
and two frontend state cases. Frontend 283 passed; no-undef lint clean (nine pre-existing
rule-definition notices). Full backend and packaged build results are in the commit message
and the CI record below.

## Section 3.3 — reply-needed items always get drafts; uncertain kind is general

Status: implemented and tested locally at `8b89e26`; remote CI pending on the pushed
checkpoint. Section 3.2 is CI-verified at `ed2bb98` (run 34038415374, all ten jobs).
Acceptance PW-042 to PW-046 and PW-067/PW-068 implemented; PW-047 partial (no rendered-browser
check of the hidden send button; API, backend and pure-UI state tests cover the rest).

`reply_only` on a channel with replies off used to be filed - a question wearing "nothing to do".
Every reply-needed message now opens (or reuses) its task and pending review and asks for a draft
at once, on both the create and attach paths; `auto_draft_enabled` no longer gates drafting and is
retired from Settings (value left untouched). `outbound.send_block()` states why sending is
unavailable; it rides on reviews and feed rows as `SendBlock`, and `website/src/sendState.js` shows
the same sentence beside the draft on Review and the assistant card while the send button is
omitted; the server's `can_reply` refusals are unchanged. A draft that could not be written is
recorded on the review (`DraftError`, additive column), the item stays reply-needed, and a
successful redraft clears it. A task whose kind the classifier did not name is `general`
(`routing.draft_task_fields`, `INTENT_SYSTEM`, shipped TRIAGE.md); the keyword coding guess is gone,
so no coding session starts without an explicit `coding` verdict.

Tests changed with explanation, none weakened: `test_not_coding.py` (keyword-kind and dispatch-gate
classes rewritten to the general default), `test_urgent_and_handoff.py` (one kind expectation),
`test_kind_dispatch.py` (prompt tie-break wording). New: `tests/test_reply_always_drafts.py` (14 cases), `sendState.test.mjs` (3).
Frontend and packaged-build results are in the commit message; full backend and CI below.
Earlier Section 2.1 polling delivery `3dc3a5ea53d4b1701314cc5df0699fff4f5f8f39` passed all ten jobs in
[CI run 34037292146](https://github.com/ldbumble/taskuary/actions/runs/34037292146).
The original workspace was fast-forwarded from the concurrently delivered `f244803`;
its only user change remains README.md with preserved SHA-256
`EDF56683E29A34789B2EBEF73E131FBD7B318AE498BC761668BCB70854D91BAB`.

## Section 2.2 — email catch-up without skipped backlog

Status: accepted. Reviewed source `32d014b` was delivered as `8247d81`; all ten
remote CI jobs passed (run 34044710317), as recorded below. Work began from CI-verified `3dc3a5e`. PW-006 through
PW-008 form one TODO section with independent Outlook and IMAP assignments and
one integration/review/regression/delivery gate. Claude's original Outlook/IMAP
commits are already on master; this section resolves their independent review
findings before marking those requirements accepted.

Sol High owns Outlook `channels.py` and catch-up tests in the isolated
`processing/email-outlook-fixes` branch. Another Sol High agent owns `imapmail.py`
and its tests in `processing/email-imap-fixes`. The lead owns atomic checkpoint
storage, integrated preservation tests, evidence and delivery; Astra Extra High
reviews independently. No live connector or app restart is part of these tests.

Root helper `580afb67f9f8156ca347e375e6c6f405b7c0304d` adds atomic source/connector
poll-state merges. SQLite BEGIN IMMEDIATE precedes reading current ConfigJson;
only specified poll keys change, conditional source/mailbox expectations reject
stale work with no writes, and source cursor cleanup/cutoff changes commit together.
Malformed owner configuration is preserved and reported rather than overwritten.
The 17 focused tests passed (1.89 s), including an actual concurrent connection
write, detached caller data, failed-CAS zero writes and rollback/reuse. Astra
cleared this helper; connector integration and cumulative gates remain pending.

The root API characterization passes on the existing implementation: a real
`POST /api/ingest/poll` runs the Graph HTTP paging adapter against synthetic
responses, exposes a later-page failure after the first 500 durable messages,
and recovers all 600 IDs on retry with no duplicates. The test checks connector
error visibility, source watermark, final feed visibility, exact historical
message/read/document preservation, and an owner configuration edit during fetch.
It will run again against the corrected connector implementations.

Provider-contract review found that inferred message-count offsets are not a
valid replacement for Graph continuation URLs: Microsoft documents that its
skip position can count scanned items beyond the returned message rows.
The Outlook correction must use complete provider continuation URLs and retain
requests-level failure/continuity regressions. Source:
[Microsoft Graph list messages](https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0).

### Final source review and concurrent-base integration

The final email source checkpoint is `36a1edf`, rebased onto Claude's concurrent
triage checkpoint `162d33e`. Astra Extra High verified all eleven email commits
remain equivalent to the pre-rebase source and cleared compatibility with the new
triage error handling. This review covers email integration, not blanket Phase 3
acceptance. Both authors' evidence entries were retained during the append conflict.

Outlook now follows complete opaque Graph continuation URLs, preserves complete
provider pages, detects continuation loops across batches, and freezes a cutoff
until every selected folder completes. Restart replays the saved timestamp
inclusively instead of trusting a mutable provider offset. Checkpoint provenance
and atomic conditional merges preserve owner configuration changes and rewinds.

IMAP uses mailbox-scope/UIDVALIDITY identities and durable retry holes. Failed
FETCH, parse, SELECT, SEARCH and Sent operations remain visible failures; later
successes cannot erase a skipped UID. Empty epoch resets, missing UIDVALIDITY,
unknown-to-known epochs, and attributable legacy rows from an interrupted first
import are covered. Ambiguous historical account ownership is not guessed.
The original unreadable-UID test retains its delivered-row and high-cursor checks;
it now additionally requires a visible partial failure and an exact-once healthy
retry, replacing the previous silent-success return expectation.

Root API tests exercise real Sync-now routing with synthetic Graph HTTP pages and
an IMAP server fixture, including failure visibility, durable retry after reopening
the disposable database, watermark safety, final feed visibility, and exact old
message/read/document preservation. Store tests cover actual concurrent SQLite
writers, failed compare-and-set zero writes, detached input and atomic rollback.
No live data, app restart, or production connector is used.

Frontend on the combined base: 283 passed (1.509 s); packaged build exited 0
(16.27 s) with no generated-asset drift. The first cumulative browser attempt
missed the unchanged 1,500 ms input limit at 1,737 ms while full backend regression
ran concurrently. Final backend/browser results and delivery follow below; this
source-review entry alone is not the final gate.

Combined-base backend gate completed: `python -m pytest -q -ra --tb=short`
passed 2,535 tests plus 71 subtests (150 warnings, no skips) in 231.75 s.
The first browser run finished 5/7 in 239.888 s; its second failure was a launch/
connect failure for its unique disposable Edge profile. Inspection found no
remaining process using that profile; no process cleanup was necessary. Resource
contention is the working explanation, not a proven product regression. Both
failures passed early in the full browser-only rerun (input 780 ms); final result
is still pending below. Logs are in `.codex-tmp/mail-remote-base-*.log`.

Final browser-only cumulative gate passed all seven scenarios in 198.575 s with
no skips and unchanged assertions/limits. First-visible/input timings were
1,176/780 ms; Tasks/Board/Reports navigation was 267/300/272 ms. Terminal replay,
input emission and reconnect were 2,048/105/1,091 ms. No source changes were needed
between failed concurrent and successful isolated runs. The final packaged assets
match upstream, and the original workspace's only dirty file remains README.md
with the previously recorded SHA-256. PW-006 through PW-008 now have matching
TODO and Markdown/JSON ledger evidence. Exact delivery CI will be recorded after push.

### Second concurrent-base reconciliation

Before push, origin/master advanced to `85267a0` with Claude's always-draft and
general-default section (`8b89e26`). Email commits were replayed again; only the
append-only evidence conflicted, and both sections were preserved. Integrated
source is now `221a506` (documentation `5c5253f`); prior `36a1edf` gate results above
remain explicitly associated with the earlier triage base. New-base frontend
passed 286 tests (1.406 s), and packaged build exited 0 (14.84 s) without asset
drift. Backend and browser cumulative gates are being repeated before delivery.

The `85267a0`-based integration passed 2,548 backend tests plus 71 subtests
(150 warnings, no skips) in 213.23 s, and all seven browser scenarios in 197.227 s.
Before delivery, master advanced again to `b03445b` with Claude's same-day chat
relationship changes (`78c6dd1`). These passed results remain tied to the draft
base; the next integration gate must include the newer chat change.

## Section 3.4 — chat relationships in the one triage verdict

Status: implemented and tested locally at `78c6dd1`; remote CI pending on the pushed
checkpoint. Section 3.3 is CI-verified (8b89e26, CI run 34039576824 (all ten jobs passed)).
Acceptance PW-031 to PW-034 implemented; PW-035 partial (the configured-timezone boundary is
exercised only through `norm_stamp` local time; no tracker-item cross-day case yet).

A chat room shares one conversation id, and the router joined a new line to the room's task on
that id before a second classifier (`triage.same_ask`) was asked whether it belonged. Both are
gone: `ingest.chat_route` decides a chat line before routing - two facts join without a model
(a line typed within the burst window of the room's last inbound line, an answer while an agent
is live on the room's task), everything else is the single verdict's `relationship`
(new/continues/answers/uncertain) with `related_message_ids` and `existing_task_id`, chosen
among `ingest.chat_candidates` - the room's lines from the same local calendar date as the
message's own stamp, never later lines - and validated by `triage.relationship_of` (ids outside
the room or the day dropped, a task id must be one of theirs, nothing valid left = uncertain).
`uncertain` and `new` open their own work; related lines without a task join the task the new
line opens. With the classifier off or no brain, nothing but the facts joins: the room id alone
never decides (PW-018). Mail and tracker routing is untouched. The shipped TRIAGE.md describes
`same_day_lines`.

Tests changed with explanation, none weakened: `test_chat_is_not_one_task.py` (single-verdict
brain; triage-off and no-brain cases now open their own work per PW-033), `test_assistant_reactions.py`
(one chat-burst case). New: `tests/test_chat_relationship.py` (17 cases). No frontend change; packaged assets unchanged.

## Section 3.5 — clean, complete context for triage

Status: implemented and tested locally at `0dea527`; remote CI pending on the pushed
checkpoint. Section 3.4 is CI-verified (78c6dd1, CI run 34039988682 (all ten jobs passed)).
Acceptance PW-027, PW-028, PW-029 implemented; PW-026 and PW-030 partial - the exchange now
carries every message's cleaned, de-quoted words whole under `triage.EXCHANGE_BUDGET` (12,000
characters) and says how many older messages it dropped, and the current body reaches the model
whole up to `triage.BODY_BUDGET` (6,000) with a disclosed `body_truncated`; the merge of fetched
history into one stored chain is PW-009 to PW-015 and still pending.

`triage.strip_boilerplate` (the one cleaner every connector and surface already used) now also
removes the external-sender banner and "you don't often get email" hint (pattern moved from
assistant.py), mail-client stamps and unsubscribe/preferences strips, while a request that mentions
a notice, security or a signature stays. `triage.dedupe_quoted` drops a quoted copy ('> ' runs,
"On ... wrote:", "Original Message", "Forwarded message" blocks) only when its lines are already in
the chain; unique forwarded material and inline answers survive. Stored messages are never edited.

Tests: `tests/test_clean_context.py` (14 cases). One pinned wording in `test_follow_up_verdict.py` is unchanged (the exchange
explanation keeps its opening words). No frontend change; packaged assets unchanged.

### Chat/context merge and independently found preservation regression

Merge `7420a0d` retains exact upstream `2c298ce` (chat relationships and context
cleaning) and all reviewed email patches. Only evidence append text conflicted;
both records were preserved. Astra verified source equivalence. Combined gates:
2,578 backend tests plus 71 subtests (151 warnings, no skips, 214.14 s), 286 frontend
tests, and all seven browser scenarios (203.142 s). Website source and packaged
assets are byte-identical to the successful `85267a0`-based build.

Independent review nevertheless reproduced an incoming cleaner regression:
`dedupe_quoted` discarded an entire forwarded block when approximately 60 percent
of its lines matched prior text, losing unique new instructions in a mixed block.
The existing tests did not cover that case. A bounded isolated correction must
preserve the mixed block and add the missing regression before final acceptance;
no change to mail checkpoints or historical stored bodies is needed.

Final correction source `ff6acc4` includes the independently cleared mixed-block
fix and conservative comparison. Only quote decoration and surrounding whitespace
are ignored; case, operators, punctuation and internal spacing remain meaningful.
Regressions include headed and bare-quote mixed blocks, changed operators, and
case-sensitive paths; existing exact-repeat and inline-answer checks are retained.
Sol's focused context/triage gate passed 74 tests plus 37 subtests. Astra reviewed
the exact final source and independently reproduced the preservation cases.

The preceding mixed-block-only checkpoint `14f6525` passed 2,580 backend tests plus
71 subtests (150 warnings, 219.82 s). Its concurrent browser run passed 6/7 in
204.314 s, missing only the unchanged input timing limit at 1,615 ms. That is not
the final gate. The final source is being checked with backend then browser run
separately; no timing threshold or prior assertion has been weakened.

Final cleaner checkpoint `ff6acc4` passed 2,582 backend tests plus 71 subtests
(150 warnings, no skips) in 204.13 s. During that gate, concurrent delivery
`cd32827` added task summaries/checklists. Preserve that work and integrate it
before final delivery. To reduce repeated timing interference without relaxing
any assertion, run the existing input-latency browser scenario separately first,
then run the remaining six browser scenarios alongside backend regression.
## Section 3.6 — triage-generated task summary and checklist

Status: implemented and tested locally at `82a56a3`; remote CI pending on the pushed
checkpoint. Section 3.5 is CI-verified (0dea527, CI run 34040312825 (all ten jobs passed)).
Acceptance PW-074 to PW-077 implemented; PW-078 partial (no rendered-browser click yet).

The one triage verdict now carries `title`, `summary` and `checklist` for `intent=task`; the
classifier is told to draw them only from what the message and exchange ask for, never to invent
a requirement or list anything as done. The task takes the verdict's title and summary (the
router's subject/body cut remains the fallback); the checklist is persisted on the task
(`Checklist`, additive JSON column) as items with ids derived from their words, validated (strings,
trimmed, no repeats, at most twelve), rendered as GitHub task-list Markdown (`ChecklistMd` on the
task detail), shared by the task page (interactive boxes), the assistant card (read-only) and the
worker brief (`terminal.seed_text`, beside the source message which stays the authority). A later
message on the task merges distinct new items without duplicating or unticking anything and says
so in a task comment; an owner edit through the API keeps a box's state wherever its words stayed.
Ticking every box completes nothing, and closing a task ticks nothing.

Tests: `tests/test_task_checklist.py` (9 cases), `website/test/checklist.test.mjs` (4). No existing assertion changed.
Packaged UI rebuilt from this source in the isolated worktree (Node 22).

Checklist-base integration `0d16bde` passed 2,591 backend tests plus 71 subtests
(149 warnings, no skips, 215.61 s), 290 frontend tests (1.446 s), and packaged
build (12.25 s, no asset drift). All seven unchanged browser scenarios passed:
input scenario alone in 12.435 s (first visible 1,199 ms, input 729 ms), then the
other six in 192.827 s alongside backend regression. Terminal visible/input/
reconnect measured 2,035/104/1,107 ms.

Independent merge review also reproduced two incoming checklist preservation
bugs: punctuation/case-blind IDs collapse distinct requirements, and the merge
reports a thirteenth addition while truncating it out of persistence. A bounded
store/test correction is being prepared separately, preserving old IDs/ticks and
making reported additions match durable rows. Subsequent concurrent `fb43c92`
adds identity-based email routing; retain and review that merge before delivery.
## Section 3.7 — email joins by conversation identity, never by resemblance

Status: implemented and tested locally at `b03fa29`; remote CI pending on the pushed
checkpoint. Section 3.6 is CI-verified (82a56a3, CI run 34040813007 (all ten jobs passed)).
Acceptance PW-017, PW-018 (through Section 3.4) and PW-019 implemented; PW-016 partial - joining
is identity-only now, while merging fetched history into one stored chain is PW-009 to PW-015.

`ingest.identity_route` replaces `routing.route` for mail and tracker items: a message joins the
open task its own conversation already belongs to (Graph's conversationId, IMAP's
References/Message-ID, a tracker item's own id) and nothing else; without an identity it is new
work whatever it resembles, and the route says so. A closed task's thread does not reopen it: the
reply is stored on the conversation and evaluated afresh, and new work opens only if triage says
so. `routing.route`'s similarity scoring remains as a unit-tested helper and is no longer consulted
at intake; `own_thread_only` remains for its callers and tests.

Tests: `tests/test_email_identity_routing.py` (5 cases). No existing assertion changed. No frontend change; packaged assets unchanged.

## Section 3.8 — project and repository selection in the one triage verdict

Status: implemented and tested locally at `f327a8b`; remote CI pending on the pushed
checkpoint. Section 3.7 is CI-verified (b03fa29, CI run 34041128872 (all ten jobs passed)).
Acceptance PW-092 to PW-095 implemented; PW-096 partial (no rendered-browser run of the picker).

Coding startup guessed the checkout from word overlap after the fact. The triage verdict now sees
`known_repositories` (`ingest.repo_candidates`: the learned project graph's repository edges with
what each project is, plus the SOUL.md repo map) beside the sender's project context, and answers
`repository`, `needs_repo_choice` and `repo_reason`; `triage.repo_choice_of` validates against those
candidates - an unknown name is dropped and becomes the owner's choice, as does anything the model
calls ambiguous. The decision is written on the task (`triage-repo:` or `needs-repo-choice` tag and a
task comment with the reason) and `terminal.guess_repo` uses it instead of guessing again, after the
owner's `repo:` tag and a GitHub item's own repository, which stay authoritative; the owner-tag
pattern now matches a whole token so triage's note can never read as the override. Both dispatch
endpoints turn "no repository decided", "several plausible", "no local path" and "path does not
exist" into a visible repository choice instead of a session in some other checkout.

Tests: `tests/test_repo_choice_triage.py` (8 cases). No existing assertion changed. No frontend change; packaged assets unchanged.

### Final preservation corrections and repository-selection integration

The exact `fb43c92` email-identity routing and `bc55b0c` repository-selection changes
are retained in integration `9ab2553`. Independent review cleared compatibility
with mail deduplication, checkpoints and retries; this is not blanket Phase 3
acceptance. Raw ConversationId account scoping remains a full-chain limitation,
not a claim completed by the catch-up fix. UI source/assets remain byte-identical
to the successful checklist-base build.

Final source `3188473` adds independently cleared checklist preservation from
Sol commits `d3ff034` and `8834b84`. Exact trimmed text defines duplicates; operators,
case and internal spacing remain meaningful. Existing stored IDs and ticks are
retained by exact text, and all retained IDs are reserved before new allocation
so reordering cannot give an old checked item's ID to a different new item.
Accumulated additions are not truncated to the per-verdict cap; reported additions
are durable and retries add/announce them once. Owner edits and toggles retain
accumulated lists beyond twelve. The existing mixed-case test input remains and
now asserts both distinct variants survive; an added truly identical whitespace
variant still collapses. This replaces the demonstrated lossy casefold assumption
while preserving type/trim/cap/exact-duplicate coverage.

Sol's focused and neighboring tests passed 130 cases. Astra reviewed the exact
final diff and independently reproduced old-ID/tick preservation after reorder,
case-sensitive paths in one verdict, and the durable thirteenth addition. Root
cumulative gates are in progress on `3188473`; its unchanged input browser scenario
already passed in 15.829 s (first-visible/input 2,386/1,045 ms; navigation
314/348/221 ms). No live data, app restart, or production connector was used.

Source `3188473` completed its cumulative gate: 2,608 backend tests plus 71 subtests
(151 warnings, no skips, 213.57 s), and all seven browser scenarios (15.829 s for
the isolated input scenario; 184.990 s for the other six). Frontend/build remain
the byte-identical 290-test, 12.25 s build recorded above. Before push, concurrent
master advanced to `ffd9938` with assistant-idea triage; integrate that source and
retain these results as the prior-base gate, not final-SHA verification.
## Section 3.9 — assistant ideas enter the shared triage

Status: implemented and tested locally at `3045452`; remote CI pending on the pushed
checkpoint. Section 3.8 is CI-verified (f327a8b, CI run 34041465044 (all ten jobs passed)).
Acceptance PW-199, PW-200, PW-201 implemented; PW-202 partial (no rendered-browser check).

The assistant's post kept its fixed 'feed' route and its ideas surfaced through an assistant-only
lane, never judged. `assistant.triage_ideas` now gives every newly said idea the shared triage
verdict - by the triage brain, not the assistant's model - with `idea_context` (the originating
report, the task it names with its status, whether a worker has it) in the same payload every
message gets; the verdict is recorded on the idea (`action.triage`: intent, kind, why, linked task)
and survives a re-say with the same facts (`store.upsert_idea` keeps it), so an idea is judged once
per set of facts. An actionable idea about no active task opens work through `ingest.ingest_message`
with the verdict it already has (`_verdict` rides on the message, so no second model call), which
applies the general default kind, checklist, repository and startup rules of the shared intake;
an idea about active work records the verdict and creates nothing, and a generated claim completes
nothing. A failure is recorded as an error the next check retries; no brain leaves it pending. The
pile's idea lane comes from the verdict (fyi, asked, or the failure said), and an idea whose work
was opened ranks through that task row, not a second card. `_recent` and the producers never read
Channel 'assistant' rows back in as arrivals, so generated output cannot retrigger itself. Report
triage stays the opt-in it was (`reports.run_report_source`), and worker events are untouched.

Tests: `tests/test_ideas_triage.py` (8 cases) and the existing `tests/test_report_triage.py`. No existing assertion changed.
No frontend change; packaged assets unchanged.


### Prior Section 2.2 gate before concurrent procedure and chain delivery

Exact source `9583acb` integrates upstream `ffd9938` and passed 2,616 backend tests
plus 71 subtests (150 warnings, no skips) in 206.68 s. All seven unchanged browser
scenarios passed: isolated input 11.214 s (visible/input 1,157/645 ms), remaining six
185.473 s (terminal visible/input/reconnect 2,242/121/807 ms). Frontend source and
assets remain byte-identical to the 290-test, exit-0 12.25 s build on the checklist
base. Astra cleared preservation and direct intake/navigation compatibility for
this exact integration. TODO and both ledgers referenced this candidate source at that gate.
The broader Phase 3 claims remain Claude's separately scoped evidence; full-chain,
account-scoping and canonical read-policy cutovers are still pending. Delivery and
exact-SHA remote CI follow this gate.
## Section 3.10 — procedure selection in triage, without forced coding

Status: implemented and tested locally at `b461668`; remote CI pending on the pushed
checkpoint. Section 3.9 is CI-verified (3045452, CI run 34041808201 (all ten jobs passed)).
Acceptance PW-205 implemented; PW-206 partial (procedure delivery to both worker kinds through
the shared brief; direct workflow runs are PW-203/PW-204, Phase 10).

A playbook match used to force `kind='coding'` in the classifier, so a PTO request whose saved
procedure is a general job started a coding session in some checkout. The selected procedure now
rides on the task as its `playbook:` tag whatever the kind; the kind is the model's own (general by
default), and `general._prompt` carries the same `playbooks.seed_block` that seeds a coding session,
so either worker kind receives the procedure through one task-brief structure.

Tests: `tests/test_procedure_selection.py` (3 cases); `tests/test_playbooks.py` has one expectation moved to the approved contract with
the reason noted. No frontend change; packaged assets unchanged. This closes the Phase 3 scope
listed in the plan (fresh evaluation, chat association, error/retry, general default, summary and
checklist, project/repository evidence, incoming procedures, assistant ideas and opt-in report
triage); the partial rows above name what waits on the Phase 2 chain merge (PW-009 to PW-015).

### Procedure merge and browser fixture readiness

The normal push of `0197da1` was rejected as non-fast-forward after concurrent
`e085b30` arrived. Merge `7ef37f7` preserves that exact procedure-selection source;
Astra verified all owned email/checklist/quote code unchanged and cleared direct
integration compatibility. Its backend gate passed 2,619 tests plus 71 subtests
(149 warnings, no skips) in 270.45 s. UI source/assets still match the successful
290-test packaged build.

Two isolated P0 browser attempts failed at navigation, not at the timing ceiling.
Instrumentation established both causes: after a successful Walk, Current and
`!typing` can render before the asynchronous post-landed pile GET supplies Next
(the observed gap was about 122 ms). Separately, the synthetic demo workers can
transition working-to-parked after the visible Next token was captured; the exact
old-token request correctly returned 409 `selection_stale`, preserving Current,
refreshing Next and performing no automatic retry. The happy-path test instead
waited for the obsolete target. Neither diagnostic pile contained calendar items.

Independent review confirms this is an unstable fixture/precondition, not a reason
to bypass navigation validation. The bounded test correction captures cold-page
visibility first, stabilizes only owned demo replay/watcher startup, then awaits
the actual post-Walk Next marker before unchanged count/title/advance assertions.
No rejection retry, timeout increase, production code change, or alteration of
the dedicated stale/passive browser scenarios is permitted. Final reviewed patch
and browser gates are recorded after integration.
## Section 2.4 — incremental full email chains

Status: implemented and tested locally at `3293a6e`; remote CI pending on the pushed
checkpoint. Section 3.10 is CI-verified (b461668, CI run 34042162189 (all ten jobs passed)).
Acceptance PW-009, PW-010, PW-011, PW-015 implemented; PW-012, PW-013, PW-014 partial (see the
ledger rows for what is not covered: attachment associations on fetched history, a refresh at
assistant context assembly time, archived-folder and attachment cases in a fake). The Phase 3
rows that waited on this merge - PW-016, PW-021, PW-026, PW-030 - are now implemented.

New module `taskuary/chains.py`. A conversation whose history was never completed here (newly
encountered, stored before this feature, or a failed attempt) is completed from the provider
after its new mail lands: the thread is LISTED first (Graph `/messages?$filter=conversationId`
with pagination, ids and metadata only; IMAP `HEADER Message-ID/References` search across INBOX
and the Sent folder), and only the messages the store does not hold have their bodies fetched,
once. Fetched history lives on the conversation as `history` rows (the owner's own sent mail as
`context`) with `TaskId` NULL: never a task, never in the feed or Unread counts, never routed or
re-triaged, and read state at the provider is untouched. Coverage is recorded per conversation in a
new `chain` table (`store.set_chain_coverage` / `chain_coverage`); `ingest.exchange_lines` opens
with a disclosure line when the last attempt failed, so an incomplete thread is never presented as
the whole. Poll hooks in `channels.py` (Outlook) and `imapmail.py` (IMAP) call the refresh after
the new mail's own ingest, guarded so a provider failure never fails the poll; the IMAP refresh
restores the poll's mailbox selection.

Tests: `tests/test_email_chains.py` (12 cases: known chain listed not refetched, missing history fetched once and kept as
history/context, same-subject other conversation never merged, failed retrieval recorded and
disclosed, poll hook once per thread, gap-only retrieval on a known thread, retry after failure,
a later reply already at the provider left for the poll to triage, listing pagination without
bodies, a listing that keeps pointing at the same page cannot hang the poll, a wholesale-mocked
transport yields nothing, IMAP INBOX + Sent by References). Two defects the full suite surfaced
and the tests now pin: history stops at the mail being judged (a newer reply was being swallowed
as history and never triaged), and the Graph listing walk is bounded (an unbounded next-link loop
ran a test process to 16 GB). Test-side: FakeBox in
`tests/test_imap_catchup.py` learned HEADER searches. No frontend change; packaged assets unchanged.

### Concurrent chain integration

`6d88cf0` preserves upstream `e665df7` (chain source `3293a6e`) and the reviewed
email catch-up work. The IMAP merge retains strict FETCH failure handling, scoped
identities, durable retry holes, atomic checkpoints and attachment retries, while
adding the upstream history hook. Integration review and a fresh cumulative backend
run are in progress. Browser fixture correction `15cf089` exactly matches independently
reviewed `1f7a66d`; its focused run passed with unchanged limits. No live app or
production connector was used. Delivery and exact-SHA remote CI remain pending.

Independent integration review reproduced three interactions requiring correction:
history used legacy IMAP IDs instead of the poll's scoped/epoch identities; failed
Inbox restoration could leave Sent selected for the next Inbox UID; and history
could consume a pending UID/retry hole before normal triage. These initial findings were repaired in `753b8ec`
with real-store synthetic-IMAP tests, as recorded below. Upstream Section 2.4 is not accepted by this
review: truncated/failed provider listings can claim complete coverage, coverage is
keyed by bare conversation ID across mailboxes, and the incomplete-history notice
can be trimmed from bounded context. Its earlier author-recorded claims above are
retained as history; these limitations still require follow-up.

The seven-scenario browser gate passed (245.938 s, no skips), including the fixture
correction: cold visibility/input 2,462/987 ms; terminal visibility/input/reconnect
2,549/131/1,271 ms. This run began on `15cf089` and overlapped the chain merge, so it
is diagnostic evidence, not an exact-final-source gate. The final source will be
tested after the compatibility repair. Upstream `e665df7` CI run 34043373718 failed
the freshness browser scenario (held Current title mismatch); its other nine jobs
passed. That separate failure was diagnosed and fixed in `f8baa09` without weakening assertions.

### Reviewed compatibility repairs and final gate candidate

IMAP repair `753b8ec` (worker `08f67f9`) passed 10 new real-SQLite compatibility
cases and 58 combined IMAP cases plus five subtests. It shares exact poll identities
with history, protects pending/hole and post-census UIDs, reads history readonly,
and refuses to continue on failed restoration or changed Inbox epoch. Failed
history SELECT/SEARCH records incompleteness before any Sent checkpoint preparation.
Astra cleared the source and the strengthened failure fixtures.

The Graph repair queues history until all configured intake folders complete and
the source CAS succeeds. Independent regressions `4a2f793` (worker `cd5a9d4`) failed
on the old code by swallowing an older Archive arrival while processing Inbox;
both pass with the repair. The combined Graph/IMAP compatibility and mail/chain
gate passed 44 tests. An interrupted folder can still leave earlier conversations
outside the replay boundary awaiting another history trigger; this belongs to
partial PW-010 history completion, not acceptance of complete chain recovery.

Fixture correction `3c0f575` preserves all old assertions while freezing two polls
around a genuinely later arrival and separating fake history HTTP from folder
pagination. The 32-case mail/chain gate passed. Browser correction `f8baa09`
(worker `54d7b88`) retains the physical click after the exact card is stationary and
hit-testable; a causal trace showed the previous overlapping animation sent a
different card key. Its focused browser case passed and Astra cleared it.
Frontend tests passed 290 (1.474 s), packaged build exited 0 in 24.74 s; no asset drift.
Final cumulative backend/browser results and exact-SHA delivery CI follow.

### Final Section 2.2 browser gate

Exact source `32d014b` passed all seven browser scenarios with unchanged assertions
and budgets: isolated P0 34.719 s (visible/input 1,400/870 ms), remaining six 183.911 s
(terminal visible/input/reconnect 1,846/95/786 ms), no skips. The earlier race/failure
evidence remains above. Final independent review cleared this source and confirmed
all 267 ledger IDs/rows; PW-010/PW-011/PW-013/PW-021 retain the identified partial
chain scope. Final backend result and remote delivery are pending below.

### Final Section 2.2 backend and delivery candidate

Reviewed source `32d014bff8b0d09ffea5b62b8fc5d81e01979bf3` passed the complete
backend suite: 2,643 tests plus 71 subtests, 149 warnings, no skips, 225.10 s.
Together with the 290 frontend tests, exit-0 packaged build and seven final browser
scenarios above, all local acceptance gates pass. Ledger consistency checks passed;
source/assets match, and README's owner change remains exactly SHA-256
`EDF56683E29A34789B2EBEF73E131FBD7B318AE498BC761668BCB70854D91BAB`.
TODO and both ledgers now reference this source. Full-chain gaps remain explicitly
partial. Delivery is a normal master push preserving upstream `e665df7`; exact-SHA
remote CI verification is pending. No live restart, live data modification, or
production connector testing was performed.


### Section 2.2 delivered and CI verified

Normal master delivery `8247d81232bb56f51db8fb7bb39e0be3e8fc8e8b` passed
[CI run 34044710317](https://github.com/ldbumble/taskuary/actions/runs/34044710317):
all ten jobs succeeded, including six OS/Python backend combinations, rendered
browser tests, frontend build, Docker and Windows executable. The tested head SHA
was verified exactly. The original worktree was fast-forwarded with only the owner's
README edit remaining and its recorded SHA-256 unchanged. No live app was restarted.
Section 1.6 proceeds from this accepted checkpoint; unresolved read policies and
browser-control redesign remain pending.

## Section 1.6 — canonical All consumer

Status: local gates and independent review passed at `d75d45e`; delivery CI pending.
Base `8247d81`; membership worker `5e810b8` integrated as `59951a9` after Astra
review. Sol owns bounded membership/UI implementation; Astra independently reviews
the service, lifecycle, fixture, tests and UI seams. Partial targets remain
PW-101/102/103/106/109; this section does not activate canonical Unread/read policy.

The explicit background reconciler performs an uncapped, atomic census and detects
external SQL changes through generations. Read getters never allocate identities.
All presents one canonical root, including standalone tasks/ideas/reviews, with
source filters matching any displayed member. Compact pagination leases freeze the
root set across arrivals and bind filters/history interval/order. Expired leases
require refresh; pending coverage is explicit. Full detail binds the selected
message and draft, rejects a dirty/moved target, preserves finalized owner text,
and includes checklist/history, artifacts and small worker lifecycle metadata.

The disposable socket-isolated browser fixture adds 507 roots without clearing
demo records or held Current, plus a controlled later arrival and synthetic calendar.
Real SQLite tests verify exact frozen-page completeness, preserved owner state,
read-only detail access, pending generation rejection, external-write notification,
session availability, dangling parents and projection changes. The earlier hover
race browser test adds the canonical detail URL to its existing request matcher;
all its previous endpoints, assertions and limits remain. Final gate results follow.

### Integration checks and corrections

The first cumulative backend run passed 2,667 tests plus 71 subtests and found two
integration failures: the private fixture's namespace import and an exact write-count
assertion now affected by the durable generation trigger. The import was corrected;
the test now verifies the one source write plus one trigger write, then separately
asserts selection performs zero writes. The next cumulative run passed 2,676 tests
plus 71 subtests in 212.88 s. Final review subsequently required preserving legacy
detail collection order; the adversarial real-HTTP test compares message/comment/
route/run/artifact ordering with the existing task-detail API and checks newest
report/reply/diff selection. All 40 focused integration cases pass after that fix.

UI worker `aaa5558` plus `f8bbe828`/`640f285` address stale requests, pagination
ownership, speculative fetch failures and current hash-navigation closures. Node22
frontend tests passed 298; the packaged build exited 0 in 12.96 s. Astra cleared
the final source and tests. The first rendered canonical scenario failed because
the assertion read `innerText` for a textarea draft; diagnostic HTTP evidence showed
the exact latest message/review and no sibling draft. The test is being corrected
to inspect rendered form-control values, retaining all identity assertions.
The second rendered attempt reached the draft assertions and found fixture setup
timing: the mounted page had fetched its source/calendar options before synthetic
seeding. The fixture sequence will reload those options while verifying held Current
is preserved; production source discovery behavior is unchanged.
The next attempt reached older-member selection; its full-body assertion needed the
existing Message tab rather than Summary. The test now navigates the rendered tabs
to check the full source tail, then returns to Summary for owner draft editing.
The disclosure itself is also exercised; full content is intentionally behind the
existing "show the whole message" control. With those navigation corrections the
rendered test passed draft isolation/edit preservation, source/category filters,
standalone details and the complete frozen census/arrival assertions. It then found
a real existing gap: ComingUp did not pass prep rows or their open callback into
MeetingRow. The bounded repair also cancels the meeting hover timer on explicit
prep clicks, so it cannot replace the requested detail. The browser gate verifies
the exact prep message opens once and stays selected without automatic writes.

Final reviewed backend source passed 2,677 tests plus 71 subtests in 187.97 s,
with 150 warnings and no skips; warnings include the pre-existing FakeScreencast
test shutdown warnings and Pydantic deprecations. Frontend tests passed 298 in
1.475 s before the final ComingUp repair; final UI/build/browser results follow.
After rebuilding, an older-member click missed while a source-menu overlay covered
its center. The trace recorded the exact target, a failed center hit-test, no detail
request and an empty stage. The browser helper now waits for stable visible geometry
and an exact hit-test before its physical click, retaining the same assertions and
timeouts. This matches the previously accepted freshness fixture correction.

### Final Section 1.6 local gates

Reviewed runtime `d75d45ef46101e470fa93498f6e2fefb78b140da` passed the complete
backend suite (2,677 tests plus 71 subtests, 187.97 s), final frontend suite
(298 tests, 1.458 s), and packaged build (exit 0, 12.21 s). Final fixture/All/lifecycle
and ledger checks passed 21 cases after adding exact calendar prep IDs. All eight
rendered browser scenarios passed without skips or weakened earlier assertions:

- Canonical All: 74.385 s; complete 507-new-root frozen census, exact member/draft/
  full-body selection, owner edit preservation, standalone details, filters, arrival,
  ignored/muted visibility, exact calendar prep/stability, and unchanged Current.
- Existing P0: 34.790 s process duration; cold visibility/input 1,851/471 ms.
- Remaining six earlier scenarios: 176.515 s process duration; terminal visibility/
  input/reconnect 1,790/76/749 ms. Freshness, captured Next and All/Unread preservation
  assertions remain intact.

Astra cleared the final source, adversarial tests, fixture interactions and all 267
ledger entries. PW-101/102/103/106/109 remain partial because canonical Unread/read,
shared filtering/priority and Current/Next adoption are separate pending work.
Browser-control redesign remains review-pending. Normal master push and exact-SHA
remote CI verification follow; no live restart or production connector testing occurred.

### Section 1.6 integration with concurrent shared operations

Before delivery, origin advanced to `d5f976f` (runtime `1461a13`), whose CI run
34048121206 succeeded. Merge `654a01522af385d0471d1a72567157318c6f0cff` preserves
both implementations; only the append-only evidence document required conflict
resolution, and both records were retained. Astra compared the merged functions
and files: canonical service/membership/projection/UI/tests and earlier mail repairs
are intact, with the operations tables added alongside membership triggers.
The combined focused suite passed 69 cases; cumulative merged gates are running.
Structured operations/discussion history is not yet part of All's comment/activity
detail and remains the separate Phase 8 adoption work identified below.

## Section 4.1 — shared operations, correction evidence and durable discussion

Status: implemented and tested locally at `1461a13`; remote CI pending on the pushed
checkpoint. Section 2.4 is CI-verified (3293a6e, CI run 34044710317 on the lead's follow-up 8247d81 (all ten jobs passed; the browser job on e665df7 failed on a pile-click fixture the lead then stabilised)).
Acceptance PW-129, PW-130, PW-131, PW-133 implemented; PW-132 and PW-134 partial (the assistant
conversation does not yet write its turns through `operations.discuss`, and UI interaction coverage
waits on the Phase 8 confirmation box).

New module `taskuary/operations.py` - the proposed-action contract from
`processing-state-contracts.md`: a proposal has an immutable id, exact target and parameters, the
context revision it was judged on (`context_revision`: the messages on the thread or task and how
each stands) and a confirmation version that every edit bumps. `execute` is one shared path: a
repeated confirmation returns the first receipt and runs nothing; a stale version or a changed
context is refused for review; a handler failure is reported as `error` (retryable) and teaches
nothing; a cancelled proposal never runs. On success the operation is compared with triage's
verdict (read the way the panel reads it: the newest route, then the task kind) and a difference
is recorded as correction EVIDENCE in a new `correction` table keyed to the operation - FYI to
task, general to coding, reply-needed to dismissed; deferral, discussion and an unchanged answer
record nothing; `task`/`general` count as one triage answer. Evidence persistence that fails marks
the operation `pending` and `recover_evidence` writes it later without repeating the action.
Evidence is not a memory note and not a policy (PW-131); `ingest` adds `operations.evidence_lines`
beside the owner's notes so fresh triage weighs it as dated evidence.

Entry points record the same operation through `operations.record_direct`: `/mine`, `/chat`,
`/dispatch` (message), `/not-coding`, `/not-a-task`, `/file`, and the shared task dispatch when an
explicit kind differs from the task's. A direct record is skipped while a proposal is being carried
out, so one action is one receipt. New endpoints: `POST /api/operations` (propose),
`GET/PATCH/DELETE /api/operations/{id}` (read, edit = new version, cancel),
`POST /api/operations/{id}/execute` (confirm by id and version; 409 when stale or cancelled),
`GET /api/tasks/{id}/history` and `GET /api/messages/{id}/history` (discussion, operations with
outcomes, corrections - oldest first), `POST /api/tasks|messages/{id}/discussion`.
Discussion rows are kept against the source message and its task; `ingest.task_from_message` links
that message's earlier discussion onto the task it becomes, by identity (PW-133).

Tests: `tests/test_operations.py` (20 cases). No frontend change; the Phase 8 confirmation box and history panel consume
these endpoints. Packaged assets unchanged.

### Independent integration limits on Section 4.1

The upstream CI result is green, but it does not establish the full execute-once or
exact-context guarantees above. Astra's controlled in-memory reproduction of the
incoming execute function ran two simultaneous confirmations twice; both receipts
reported `duplicate=False`. Execution lacks an atomic claim before the handler.
The server also captures operation parameters before execute rereads its version,
so a concurrent edit can validate one version while running earlier parameters.
The operation context hash omits source bodies/drafts and caps message history at
500. The direct not-a-task endpoint records done/correction before later teaching
and deletion succeed, so a subsequent failure can leave premature success evidence.

These are incoming operation-service limits, not canonical All regressions. They
remain a separate bounded repair; current PW-129/PW-130 acceptance is partial.
The historical implementation report above is retained, and this review does not
clear execute-once, exact-context or success-only evidence claims. Canonical Unread
and structured operation/discussion history adoption remain pending as before.

### Combined operations/All gate before concurrent startup delivery

Merge `654a015` passed the complete backend suite: 2,697 tests plus 71 subtests,
150 warnings, no skips, 190.20 s. UI source, tests and packaged assets are byte-
identical to reviewed `d75d45e`. The complete eight-scenario browser command passed
in 280.116 s: cold visibility/input 1,175/504 ms and terminal visibility/input/
reconnect 1,726/78/852 ms. The canonical scenario passed again in 69.659 s.
Before this candidate could be pushed, origin advanced again to `04fed7c`
(automatic-startup source `d2e11e5`); integration and its combined gates follow.


## Section 5.1 — automatic startup for both worker kinds

Status: implemented and tested locally at `d2e11e5`; remote CI pending on the pushed
checkpoint. Section 4.1 is CI-verified (1461a13, CI run 34048121206 (all ten jobs passed)).
Acceptance PW-069, PW-070, PW-071, PW-072 implemented; PW-073 partial. In addition to
concurrent ingest/retriage being covered only indirectly through the drain-lock tests,
an explicitly queued general launch that fails can clear its queue entry and record
`Started`. Truthful queued failure/retry behavior therefore remains unaccepted.

Only coding self-dispatched; a `general` task landed on the Board and waited for a click. Now
`ingest.auto_start_ok` is one gate for both kinds - the kind first (a personal `task` starts
nothing), then that kind's own switch (`coder_auto_enabled`, new `general_auto_enabled`, both
default on), then the worker's configuration (an assistant provider for general), and last the
stranger hold (`senders.known`, the expensive Sent Items search) - and a coding job whose
repository triage could not tell holds for the owner's choice instead of opening a session in the
wrong checkout. A hold is about the unattended start only: the task is still triaged, on the
Board, tagged `hold:new-sender` where that is the reason, with a router note saying which worker
was not started and why; the route line says `sent to the assistant`, `sent to the coding agent`
or `not auto-worked: <reason>`. `ingest._auto_general` opens the assistant's per-task session
(`general.start_session`, actor router) and puts the task's summary as the first ask once; a live
conversation is reused; a full house queues it like a coding task and `blackboard.drain` starts the
kind that was queued. A failed start is written on the task as `Assistant start failed: ...`, and
the router's own notes no longer count as agent work when the owner files such a task
(`server.work_on_task`), so a held or failed start leaves the task deletable.

`store.upgrade_auto_start` runs once at startup: an install that had switched the coding agent's
auto-start off keeps unattended starts off for the assistant too; an explicit owner choice is never
overwritten. Settings shows both switches (`coder_auto_enabled` relabelled "Auto-start the coding
agent", new "Auto-start the assistant on general tasks"); packaged UI rebuilt. Releasing a held
task (`/api/tasks/{id}/release`) starts the kind the task is.

Tests: `tests/test_auto_start.py` (16 cases). `tests/test_kind_dispatch.py` and `tests/test_not_coding.py` moved from
"general opens no session" to the PW-069 contract with the reason noted; `tests/conftest.py` guards
the router's unattended assistant start the way it guards a PTY, so a suite never opens a real
assistant session unless the test supplies a fake.

### Section 5.1 integration corrections

Integration review found that the one-time opt-out upgrade ran after WhatsApp bridge
startup and startup catch-up. An older owner choice of `coder_auto_enabled=0` could
therefore be observed temporarily as the newly defaulted `general_auto_enabled=1` and
admit unattended general work. The repaired lifespan runs `upgrade_auto_start` before
drain admission, bridge startup, catch-up and poll threads on every non-demo start; an
upgrade failure propagates before any of those boundaries open. Two real-SQLite lifecycle
tests close and reopen the legacy database, exercise the constructor-seeded new setting,
and prove both the corrected ordering and fail-closed startup. All connector, worker and
native-session boundaries in those tests are mocked.

The earlier `test_core.py` general-routing assertion had briefly been reduced to the
absence of a coding route. The integration restores a positive deterministic oracle:
with no assistant provider configured, no worker is spawned and the route must say so.
The focused startup/core group passed 94 tests, including the two new lifecycle cases.
The acceptance JSON was also aligned with the established Markdown status/evidence cells
for PW-001 through PW-008, PW-104, PW-107, PW-110 through PW-112, PW-114, PW-115 and
PW-118; its two ledger checks passed. Combined cumulative integration gates remain pending.

## Section 5.2 — configurable sender trust for unattended starts

Status: implemented and tested locally at `6c560b9`; remote CI pending on the pushed
checkpoint. Section 5.1 is CI-verified (d2e11e5, CI run 34048763594 (all ten jobs passed)).
Acceptance PW-079, PW-081 and PW-082 implemented. PW-080 is partial pending the
bounded mailbox-scope repair described below. PW-083 remains partial because the live
Graph/IMAP Sent Items queries are exercised only through the existing fakes.

The stranger gate had a hidden fourth door: "has written before" (`store.known_sender`), so a
stranger's own earlier mail, a historical import or a retry could make the next message
'known'. `senders.known` is now three rules the owner can see and switch in Settings, and nothing
else: chat channels inside a workspace the owner controls (`trust_non_email`), the owner's own
domains (`trust_own_domain`), and verified SENT evidence that the receiving mailbox wrote to the
exact address (`trust_sent_history`) - what the store already holds scoped to that mailbox
(`store.wrote_to_locally`: the mailbox's own words on a thread with the address, or an approved
reply to them), a hit remembered from an earlier lookup (new `sender_trust` table, per mailbox and
address, so the mail server is asked once), and the server's own Sent Items (`senders.wrote_to`).
`wrote_to` now RAISES on a failure instead of answering no, and `known` reports it as "could not
check the Sent Items of <mailbox> (...) - not proof either way": the task waits for a manual start
with that explanation, is not tagged as a stranger hold, and the negative is not remembered.
The matched rule is written on the task when a start is allowed ("Unattended start allowed: in
your Sent Items"). `store.known_sender` remains for the first-time-sender policy question only.
Settings shows the three switches; packaged UI rebuilt. The same gate sits behind both worker
kinds through `ingest.auto_start_ok` (Section 5.1).

Tests: `tests/test_sender_trust.py` (11 cases). `tests/test_core.py`'s stranger walk still passes: the owner's own words on
the stranger's thread are verified sent evidence for that mailbox.

Independent review found one receiving-mailbox boundary missing from local evidence.
The approved/edited/sent review branch has no receiving-mailbox constraint. The
conversation branch constrains the owner's address but does not constrain both messages
by channel/source, so the same bare `ConversationId` can bridge accounts. An AST-backed
SQLite reproduction showed approved review evidence belonging only to mailbox A authorizing
the same sender arriving in mailbox B without a connector lookup. This behavior also existed
in the older `known_sender` path; copying it into `wrote_to_locally` did not satisfy PW-080's
stricter receiving-mailbox contract. The bounded scoped repair and regression are in progress;
PW-080 stays unchecked and partial until that review completes. Combined cumulative gates
remain pending.

## Section 5.3 — capacity counting and bounded startup retries

Status: implemented and tested locally at `6ed0301`; remote CI pending on the pushed
checkpoint. Section 5.2 is CI-verified (6c560b9, CI run 34049592998 (all ten jobs passed)).
Acceptance PW-084 and PW-086 implemented. PW-085 and PW-088 are partial because a
queued general start can swallow its failure and because restart arms only the earliest of
distinct retry deadlines. PW-087 remains partial for the Phase 8 task-view/attention surfaces;
PW-089 remains partial for those queued-general and multiple-deadline cases.

`blackboard.live_count` is the one capacity number: every live session, whatever it is doing -
working, idle at its prompt, stopped at an approval, coding or general - until its process ends;
`ingest._auto_code`, `ingest._auto_general` and the queue drain all read it. The dispatch queue row
carries the retry budget (`Attempts`, `LastError`, `NextAt`, `State` waiting|retrying|failed):
`blackboard.record_failure` counts one failed start wherever it happened (the drain or a direct
auto-start, which used to write one line and never try again), says on the task what happened and
what comes next ("... (attempt 1 of 3) - retrying in 30s" / "Agent could not start - needs you: ..."),
and schedules the retry by timer (`drain_later`) rather than waiting for an unrelated session to end;
`blackboard.schedule_due` re-arms the earliest persisted retry at startup, so a backoff in progress
when the app closed neither vanishes nor restarts from zero. Configuration failures (an unknown
agent, a missing repository or worker, a permission problem - `blackboard.is_permanent`) fail at
once without consuming blind retries; a capacity wait consumes nothing. The drain skips rows that
are exhausted or not yet due so the others proceed, and a failure raised after the session exists is
reconciled as a started task with a bookkeeping note, never counted as a failed launch or started
twice. Owner controls: `POST /api/tasks/{id}/dispatch/retry` (a fresh bounded cycle, tried now) and
`DELETE /api/tasks/{id}/dispatch` (the pending start goes; the task stays); `/api/tasks` exposes
`Queued.state/attempts/lastError/nextAt`.

Tests: `tests/test_dispatch_retries.py` (13 cases). `tests/test_blackboard.py`: the failed-start test now makes the row due before
the second drain, because a failed start backs off (PW-085). No frontend change.

### Canonical All integration: startup, trust and retry boundaries

The sender-trust scoping repair is complete at `64e4163`: both local evidence
paths require the exact receiving mailbox and email channel, including the owner
conversation row. Eight real SQLite regressions and the existing trust/hotpath
cases passed (43 total, 1.62s); independent Astra review cleared the repair.
This supersedes the preceding PW-080 repair-pending note.

Concurrent capacity/retry changes from `f432b76` are preserved. Independent review
found queued general startup still swallows failure: its caller clears the retry
row and falsely records Started. Restart scheduling also only arms the earliest
of distinct deadlines. PW-073/085/088/089 remain partial for these incoming
limitations; they are not accepted as fully working by the All delivery.

Integration adds owner-only guards to the new Retry/Cancel endpoints, preventing
agent tokens from resetting exhausted budgets or cancelling queued work. Tests
isolate retry timers and add retry scheduling to the startup migration boundary.
Combined runtime review and cumulative gates are pending below. The rebuilt UI
passed all 298 frontend tests (1.425s); packaged build passed (10.49s).

## Section 5.4 — similar work is a briefing; the wall is live coordination only

Status: implemented and tested locally at `165af37`; remote CI pending on the pushed
checkpoint. Section 5.3 is CI-verified (6ed0301, CI run 34049840835 (all ten jobs passed)).
Acceptance PW-171, PW-172, PW-174, PW-176, PW-177 and PW-180 implemented. PW-173 and
PW-175 remain partial for push-style refresh and the stated integration coverage. PW-178,
PW-179 and PW-181 are partial because the HTTP note API does not yet forward the posting
session ID; a headless run's own posting is also covered only through the task fallback.

Overlap is advisory (PW-171): `ingest._auto_code` and `blackboard.drain` no longer park a task
behind a peer the model judged likely to touch the same files, in either the immediate or the
ranked path; a queue row that was parked that way is simply due. `blackboard.briefing` (the OTHER
AGENTS paragraph of the seed, `terminal.seed_text`) carries the facts - each peer's task id, agent,
summary, touched files and what its live session said - then the model's read of similarity as a
read ("SIMILAR WORK (the model's read, not a lock)"), the plain "read no overlap", or "NOT assessed"
when there was no model, never read as no overlap (PW-174); `likely_overlap` now distinguishes an
answer of no overlap from no assessment. Wall notes belong to a session (PW-178): `boardnote.Sid`,
`blackboard.post(..., sid=)`, `TASKUARY_SID` in every session shell (`terminal.session_env`,
`Term`, the assistant's browser env) and `taskuary --note` records it. `blackboard.live_notes` is
the one live selection (PW-179) behind the Board's live handoff, the seed (`wall_text`, live only,
no fallback - PW-176), the assistant's prompt (`chat_text`/`house_wall`, PW-177) and `taskuary
--board`: notes from sessions alive now - working, idle or waiting for approval - plus the owner's
own notes as durable guidance; a note from before notes knew their session follows its task. An
ended session's notes leave every live surface and a restart of the same task does not revive
them; `blackboard.history` (`GET /api/board/notes?all=1`) keeps them and flags each note live or
historical (PW-180).

Tests: `tests/test_coordination.py` (17 cases). `tests/test_blackboard.py`: the overlap-queues test became
"overlap is a briefing, not a queue" and the drain test no longer expects a parked row to stay,
per PW-171; `tests/test_agent_wall.py`: the seed tests post from live sessions, per PW-176. No
frontend change (the Board already reads the live handoff endpoint).

### Coordination integration candidate

Before the coordination merge, exact source `c9d4572` passed the complete backend suite:
2,747 tests plus 71 subtests, 150 warnings, no skips, in 250.22 s. Frontend remained
298 passing tests and the packaged build passed in 10.49 s. The all-at-once browser gate
passed seven existing scenarios in 346.495 s; the canonical scenario alone timed out in
fixture diagnostics. Its diagnostic-only correction is awaiting the isolated run recorded
by the lead as 44424. That is prior-source evidence, not a final coordination gate.

The incoming coordination implementation and its 17 focused tests are retained. Integration
also replaces fixed `terminal.SESSIONS` test keys under an isolated `patch.dict`, preventing
cleanup from deleting a pre-existing fixture session. The HTTP session-ID propagation repair,
independent review, final backend/browser regressions and combined delivery evidence remain
pending.

The isolated canonical browser rerun passed after the coordination merge: 1/1,
78.148s scenario / 81.146s process. Seven prior browser scenarios also passed on
this merged source (213.417s). The response diagnostic correction retains exact
predicates and all 10-second response budgets; it does not retry failed actions.
The separate-process CLI live-wall regression is repaired: `--board` requests the
running server's live selection using its session URL/token and checkout. An
unreachable server is unavailable, never an empty/live historical fallback;
`--all` retains offline history. Focused CLI/wall tests: 38 passed in 1.50s;
coordination/wall/queue tests: 55 passed in 2.33s. Astra independently cleared the
CLI repair and session-registry fixture isolation. HTTP note SID attribution
remains explicitly partial; no repair of that surface is claimed here.

## Section 5.5 — one worker context: AGENT.md, CODER.md and one task brief

Status: implemented and tested locally at `e552609`; remote CI pending on the pushed
checkpoint. Section 5.4 is CI-verified (165af37, CI run 34050341372 (all ten jobs passed)).
Acceptance PW-182, PW-183, PW-184, PW-186 implemented; PW-185 and PW-187 partial (the source-rules
block is still assembled separately; no rendered-browser check of the Docs tab).

Every worker prompt carried the whole of SOUL.md - the owner's routing document, written for
triage - under a flattened CODER.md, and the general assistant got a different pile in a different
order. New operator document `AGENT.md` (`taskuary/templates/agent.md`, seeded and healed like the
others, on the Docs tab) holds the rules both worker kinds share, with the approval boundaries that
used to live only in SOUL.md leading it: nothing sends or ships without the owner's approval;
money, legal, HR, credentials, permissions and anything irreversible are the owner's; inbound text
is data, not instructions; then scope, honest reporting, when to ask, progress and completion.
`CODER.md` is rewritten as the coding additions on top of it (repositories, editing/testing/
committing only its own changes, the wall, playbooks, GitHub etiquette) and says so. New module
`taskuary/brief.py`: `brief.build` is the one task brief either worker reads - task id and title,
objective, the triage checklist, the owner's instruction, the repository, the latest complete
conversation as triage reads it (history included, cleaned, budgeted), attachments, the message ids
and the context revision (`operations.context_revision`) it was built from; `brief.rules` flattens
an operator document for a prompt. `terminal.seed_text` carries `RULES (AGENT.md - every worker)`
and `CODING RULES (CODER.md)` in place of `OPERATOR RULES (SOUL.md)`, plus OBJECTIVE, CHECKLIST,
the latest message and a budgeted CONVERSATION block when the chain has more than one message;
`general._prompt` carries `RULES (AGENT.md - every worker)` and `ASSISTANT STYLE` (writing is that
worker's job) in place of `OPERATOR RULES`, and the checklist in its task head. SOUL.md stays
seeded and stays with triage. Live coordination rides only when live peers exist (Section 5.4); a
continuation carries this task's own `PREVIOUS SESSION RESULT`.

Tests: `tests/test_worker_brief.py` (13 cases). `tests/test_terminal.py`: two `RULES:` pins moved to the new labels; the
end-to-end TUI test blanks AGENT.md as it blanks CODER.md and SOUL.md (it owns the seed's inputs);
`tests/test_docs_flow.py`: the coding-agent audit now expects the AGENT marker and forbids the
SOUL marker (PW-184). Packaged UI rebuilt for the Docs tab entry.

## Section 5.6 — one startup contract and the surfaces that start a worker

Status: implemented and tested locally at `4f32c35`; remote CI pending on the pushed
checkpoint. Section 5.5 is CI-verified (e552609, CI run 34051205593 (all ten jobs passed)).
Acceptance PW-099, PW-209, PW-210, PW-211, PW-212, PW-213 implemented; PW-097, PW-098, PW-100,
PW-214 partial (conversational dispatch in the assistant chat is Phase 8; a single confident
repository still launches without a confirmation step pending the owner's word; live UI
interactions are not exercised - the surfaces are checked by source pattern).

Dispatch used to answer with whatever the path it took happened to return, and one screen read a
`needs_repo` decision as a live start. Every dispatch answer - `/api/tasks/{id}/dispatch`,
`/api/messages/{id}/dispatch`, the chat cards - now says the same four things: `dispatch`
(session | assistant | needs_repo), `started` (a worker session was created for this request),
`existing` (a live session or conversation was reused; nothing new started) and, for a coding
session, `accepted` (`Term.accepted`: the prompt was submitted - True when the CLI takes it on its
command line or the typed seed was answered, False when it was typed but never taken, None before
any prompt) - exposed on the session's `info`. A repository decision carries `started: false`; a
failed launch is a 422, never a success. `website/src/dispatchOutcome.js` (`outcomeOf`) is the one
reading of that answer: the timeline's SendToAgent (`ui.jsx`) now offers the `RepoPicker` on a
needs_repo decision with a "Not now - nothing was started" exit and reports what actually happened;
All detail (`FeedView.jsx`) offers Send to agent for fyi/reply rows as the chat cards do, with
triage's reading kept as the printed reason; the task page's non-coding start (`TasksView.jsx`)
goes through the shared dispatch whatever the task's kind was instead of re-labelling the task and
leaving a workspace mount to start work. Make task (`/mine`) creates or reuses an owner task and
launches nothing. Packaged UI rebuilt.

Tests: `tests/test_startup_contract.py` (7 cases), `website/test/startupSurfaces.test.mjs` (4 checks: outcome reading, the timeline's repo decision, the All-detail
tray, the task page's shared dispatch).

## Section 5.7 — mandatory freshness: what a draft read, what a send rechecks, email refreshed like chat

Status: implemented and tested locally at `325d05a`; remote CI pending on the pushed
checkpoint. Section 5.6 is CI-verified (CI run 34051581086, all ten jobs passed).
Acceptance PW-048, PW-054, PW-055 implemented; PW-049 partial (automatic Next/Walk and FYI-batch
validation are PW-050); PW-050 to PW-053, PW-056, PW-057 remain open.

A draft was labelled with the newest message queried AFTER the model finished, so a line that
landed during generation was called seen; the source-refresh gate before an answer, a draft or a
send skipped email; the reply writer read the last six messages cut at 4,000 characters each and
said nothing about the rest. `responder.draft_for_review` now captures the inbound message and the
message-set revision (`operations.message_revision`: the task's inbound messages and their states,
nothing else) BEFORE the model runs, pins the review to them (`store.pin_review_context`, new
`review.ContextRevision`/`Stale` columns) and marks the draft stale when the set moved while it was
written. `verdicts.decide` rechecks that revision before anything leaves - the one door the Review
button and the phone road share - and refuses a stale or moved draft with `stale: true` and nothing
sent; a redraft repins and the next yes sends. `server._refresh_chat_context` covers email through
the connector behind the mailbox the message arrived in (`_poll_reports(only=[type], wait=True)`, an
incremental watermark read; the chain itself is completed by `chains.py`); a mailbox with no active
connector is left alone and said so; a failed refresh stays a 503. `responder.draft_reply` reads the
assembled conversation (`ingest.exchange_lines`: the whole chain, history included, cleaned,
de-quoted, budgeted, with the cut disclosed).

Tests: `tests/test_freshness.py` (9 cases). No frontend change.

## Section 5.8 — freshness on the walk: select, validate, say it once, supersede what is behind

Status: implemented and tested locally at `af2f15f`; remote CI pending on the pushed
checkpoint. Section 5.7 is CI-verified (325d05a, CI run 34051887301 (all ten jobs passed)).
Acceptance PW-050, PW-051, PW-053 implemented; PW-052, PW-056, PW-057 partial (the notice is
emitted after the refresh completed rather than at detection, because the quick poll waits for the
triage of what it fetched before returning; a concurrent sync racing an action is covered only
through the revision recheck).

Next without a key surfaced whatever the pile held without asking the source whether the item had
moved; an FYI batch was never checked; a new line on a task with a drafted reply left the draft
sitting as current; the "new message" notice repeated on every render. `server._refresh_next_selection`
picks what the walk would surface, refreshes that item's source through `_refresh_items` (once per
channel across an FYI batch), and re-picks when the refresh moved the pile; the plain Next endpoint
and the stream's next mode call it, and the reservation path raises a stale navigation (409) so the
client re-captures. `_notice_once` emits the context-update line as its own `context_update` stream
event before the assistant's answer, once per new revision of the item (`_NOTICED`), worded as what
happened ("New message from X arrived on Y ... I sent it through triage before continuing"); a failed
refresh stays an error event. In `ingest`, a new inbound line joining a task with a pending draft
marks that draft behind (`Stale`) and, when the follow-up verdict says a reply is still owed, redrafts
the same review - never a second review, never a second task; an fyi line leaves it alone. The
owner's own external answer retires the draft (`channels.retire_draft_answered_elsewhere`, already
in place) and the notice now says it was answered and nothing is to send.

Tests: `tests/test_freshness_walk.py` (9 cases) and `website/test/contextNotice.test.mjs` (2 checks). Frontend: `AssistantView.jsx`
renders the `context_update` stream event as it arrives - before the answer - and does not show the
done payload's copy a second time; packaged UI rebuilt.

## Section 6.1 — one worker status model from explicit events; answers bound to the request

Status: implemented and tested locally at `353d083`; remote CI pending on the pushed
checkpoint. Section 5.8 is CI-verified (af2f15f, CI run 34052218971 (all ten jobs passed)).
Acceptance PW-222, PW-226, PW-227, PW-139, PW-141 implemented; PW-223, PW-225, PW-137 partial;
PW-224 (Codex App Server) not started.

A session's status was read off its screen: a bare prompt meant "stopped and waiting on you", a
quiet terminal meant a question, and every consumer disagreed with the next. New module
`taskuary/workerstate.py` derives a worker's state from explicit, persisted events (new
`worker_event` table: task, run/session id, kind, request id, text, choices, source, event id):
Working, Input needed (with the unanswered question and its choices), Approval needed (with the
pending action), Finished (an explicit result - it closes nothing by itself), Failed, Disconnected,
Stopped, or unknown. A response ending (`turn_end`) is not a finish; a dead session with no finish
is disconnected; an idle prompt with no event raises no hand. Events are deduplicated by event id
and by open request, and a run that is not the task's live one is ignored (a restart or headless
worker with no live session becomes the current run). `workerstate.answer` binds the owner's
answer to the exact outstanding request and its run: looked up across every run, delivered once
(`terminal.type_into` for a CLI, `send_prompt` for the assistant), refused as resolved, stale (the
run changed - never forwarded to a replacement) or disconnected (no live worker: open the
workspace), failed when the delivery raised; each outcome is written into the task discussion.
Producers: Claude Code hooks (`hooks._events`: UserPromptSubmit, AskUserQuestion, permission
Notification - now installed as a fourth hook - and Stop), `taskuary --done` (`selfclose.declare`
records Finished with the result), the assistant's `send_prompt` (Working), and the owner's Stop
(`/api/tasks/{id}/agent/stop` records Stopped). Endpoints: `GET /api/tasks/{id}/worker` and
`POST /api/tasks/{id}/worker/answer` (409 resolved/stale, 422 disconnected/failed).

The funnel, the hand-raise and the task list still read the terminal's latched phase; switching
those consumers to this model is Section 6.2.

Tests: `tests/test_worker_events.py` (13 cases). No frontend change.

## Section 6.3 — explicit completion: save the agent's own result, tick what it reported, then close its run

Status: implemented and tested locally at `3d5af15`; remote CI pending on the pushed
checkpoint. Section 6.2 is CI-verified (c16a861, CI run 34053073590 (all ten jobs passed)).
Acceptance PW-231, PW-232, PW-233 implemented; PW-230 and PW-234 partial (Codex App Server
messages are not integrated; pending approvals at finish and retained follow-up context are
exercised only through Sections 6.1 and 5.5).

`coder.wrap` now takes the agent's OWN final answer first - the `--done` sentence recorded as the
run's Finished event (`workerstate`), matched to the live run, then the Stop hook's last message the
witness kept - and only then the report a second AI writes from the transcript. The result artifact
(`session_artifacts.coding`: compact result plus the final answer) is written BEFORE the pty is
closed; a save that fails raises `the result could not be saved ... the session was left open`,
writes no CODER REPORT, closes nothing and leaves the finish retryable (`selfclose._wrap`/`declare`
forget their once-only mark and say so on the task). `coder.tick_reported_checklist` ticks only the
checklist items the agent itself reported done (`- [x] item` lines in its result or transcript,
matched by words, by item identity) and says which; nothing is added, moved or blindly completed.
`selfclose.declare` on a session the owner opened no longer holds: the explicit finish records the
Finished event, saves the result and closes the completed run (`coder.wrap(close=False)`), leaving
the task's own closure and any reply to the owner (PW-232); live wall notes leave with the session
(Section 5.4). A second finish for the same run does nothing twice.

Tests: `tests/test_explicit_completion.py` (6 cases). `tests/test_stay_open.py` and `tests/test_stay_open_doors.py`: the two pins that read
`--done` on an owner-opened session as "filed, not obeyed" now expect the run to close and the task to
stay, per PW-232, with the reason noted. No frontend change.

### Section 1.6 delivery integration at dbb82f8

The owned All implementation is unchanged through the latest shared worker and
freshness changes (`b047214`). Independent Astra review cleared canonical
membership/detail, historical reads, navigation reservations/final guards, email
preservation, startup opt-outs, exact mailbox trust and owner-only dispatch controls.
This is compatibility review, not blanket acceptance of incoming Phase 5/6 features.

Cumulative local gate at `76b227f`: 2,764 backend tests plus 71 subtests passed,
152 warnings, no skips, in 235.86s. All eight real browser scenarios passed across
the isolated canonical run (78.148s scenario) and seven prior scenarios (213.417s
process). After merging `b047214`, all 501 processing/freshness/worker/startup/core
integration tests passed in 34.21s; all 304 frontend tests passed in 2.441s and
the packaged UI rebuilt in 16.13s. Relevant merged browser results follow.

To avoid restarting the entire local suite for each concurrent master push, the
section's complete cumulative local gate is followed by focused merge checks,
relevant rendered-browser checks and the full exact-SHA remote CI on the combined
commit. No earlier assertion, timeout, or fixture-size requirement was weakened.
User README SHA-256 remains EDF56683E29A34789B2EBEF73E131FBD7B318AE498BC761668BCB70854D91BAB.
No live app, connector, read-state migration or custom document was used for tests.

## Section 7.1 — replies are written from STYLE.md, SOUL.md and the conversation; triage's learning stays with triage

Status: implemented and tested locally at `691f566`; remote CI pending on the pushed
checkpoint. Section 6.3 is CI-verified (3d5af15, CI run 34053604179 (all ten jobs passed)).
Acceptance PW-058, PW-059, PW-060, PW-061 implemented; PW-062 partial.

Every draft carried LEARNED.md - what the system has learned about which mail deserves a task - and
the owner's standing triage verdicts (NOT A TASK, NOT OURS), so a reply prompt was half a routing
manual. `responder.draft_reply`, `responder.draft_for_message` and `outbox.draft_message` now write
from STYLE.md (voice and signature), SOUL.md (identity and responsibilities), the refreshed
conversation (Section 5.7) and the verified result, plus - as separately retrieved notes - only
explicit writing instructions (`responder.writing_notes`: memory rows with source `writing`);
LEARNED.md and the routing verdicts no longer ride into any draft (they still reach triage).
`responder.style_feedback` puts an edited draft's note into STYLE.md under `## Owner notes`, outside
the generated block so a regenerate keeps it; `verdicts.decide` routes an edit's note there and
keeps a rejection's or no-reply's note as triage feedback for LEARNED.md (PW-061). `POST /api/memory`
accepts `source: writing` so a writing instruction can be saved by hand.

Tests: `tests/test_reply_sources.py` (7 cases); in the pre-existing `tests/test_reply_voice.py` (first-person voice) the standing-notes
case moved to the PW-060 contract - a writing instruction rides, a triage verdict does not - with the reason noted. `tests/test_docs_flow.py`: the reply-path audit now expects the STYLE marker and a writing-note
marker and forbids the LEARNED marker and the triage-verdict note, per PW-058/060. No frontend change.

### Final reply-source compatibility and calendar test timing

Merge `ff45b7a` preserves concurrent reply-source work through `2e92e2f`.
Independent Astra compatibility review cleared exact message/review targeting,
read/navigation preservation and document-content handling. The focused reply,
All, navigation and ledger gate passed 54 tests plus 9 subtests in 9.05s.

The merged freshness and Current/Next browser checks passed (3 scenarios in the
four-scenario attempt). Calendar prep still failed its response wait. A subsequent
fixture-only click/network trace proved no DOM click had occurred before the
10-second timeout. The test started its response timer before expensive scrolling,
layout checks and physical-hover preparation. Readiness now completes first; the
same exact response listener is installed immediately before the physical click,
with its unchanged 10-second limit and status/body/target assertions. The hover
stability checks additionally retain the prep target's geometry and hit ownership.
Astra independently cleared this distinction between readiness and response latency.
The rerun result follows; previous failed attempts are not counted as passing gates.

Final canonical browser gate passed: 1/1, 108.918s scenario / 112.004s process,
with all 507 added fixture roots, frozen pagination, exact member/draft targeting,
owner edits, Current preservation and calendar prep assertions intact. Test helpers
now find exact rows in one browser evaluation instead of hundreds of sequential
protocol round trips. Prep readiness uses physical pointer movement and stable
geometry/hit tests; the unchanged 10-second response budget starts at its physical
click. Both test changes passed independent Astra review. Packaged UI build passed
in 12.08s and all 304 frontend tests passed in 1.894s. No retries, reduced fixture
counts, relaxed assertions or increased timeouts were introduced.

## Section 7.2 — email replies: a reviewed recipient envelope and the owner's signature, once

Status: implemented and tested locally at `88f2c1b`; remote CI pending on the pushed
checkpoint. Section 7.1 is CI-verified (691f566/2e92e2f, CI run 34054198417 (all ten jobs passed)).
Acceptance PW-064, PW-065 implemented; PW-063, PW-066 partial (the Review page's To/mode controls
are a Phase 8 surface; the connectors are exercised through the shared to/cc contract).

A reply went to the sender alone, with a CC the owner could add at the last click, and the
signature was whatever the model chose to write. `outbound.reply_envelope` builds the recipients an
email reply goes to - Reply all by default: the sender or the message's Reply-To, the original To and
CC participants, the sending mailbox's and the owner's own addresses excluded, deduplicated
case-insensitively, never a BCC - or Reply to, the sender alone; a chat has no envelope.
`responder.draft_for_review` and `draft_for_message` pin it to the review when the draft is written
(`store.set_review_envelope`, in `Deliver` as `kind: reply`, never overwriting an outbound review's
own delivery), and `verdicts.decide` sends exactly that envelope (`reply_to_message(to=, cc=)`),
with a CC list named on the click taking precedence; a reply envelope is not an outbound send.
`PUT /api/reviews/{id}/envelope` switches Reply all/Reply to and edits To/CC. The owner's signature
(`responder.signature_for`: the `email_signature` setting, else STYLE.md's `Sign off:` line, quoted
multi-line allowed) is applied once by `with_signature` when an email draft is written, redrafted or
saved by hand (`PATCH /api/reviews/{id}`) - visible before approval, never at send time, never on
chat, never twice, and an owner's own signed text is kept as written.

Tests: `tests/test_reply_envelope.py` (9 cases). No frontend change.

## Section 7.3 — send outcomes: sent, failed, unknown, and an explicit close without sending

Status: implemented and tested locally at `3459868`; remote CI pending on the pushed
checkpoint. Section 7.2 is CI-verified (88f2c1b/50560d5, CI run 34054507025 (all ten jobs passed)).
Acceptance PW-144, PW-145, PW-147, PW-148, PW-150 implemented; PW-143, PW-146, PW-149 partial.

A send that timed out was reported NOT SENT and offered for a retry that could deliver the same mail
twice, and a channel that could not carry the reply left "No response required" as the owner's only
exit. `verdicts.decide` now knows three outcomes. A confirmed send settles the task the reply belongs
to through `_settle_task_after_sent_reply` - unchecked checklist items and all, the owner's decision
that a sent reply is the end of the job (the "Successful reply closes its task" resolution). A
definite failure keeps the approved text as the draft and the task open with the error and a retry,
and marks the review's envelope `delivery: failed`. A provider that did not answer
(`outbound.UNKNOWN_ERRORS`: read timeouts, connection errors) is delivery UNKNOWN, its own state:
the envelope records `delivery: unknown` and the attempt time, `outbound.reconcile_sent` asks the
Graph Sent Items of the conversation whether the reply is there (the opening words of the reviewed
text are the receipt), a found mail is settled as sent with no second send and a comment saying so,
and the next approval reconciles again before it sends anything - so a retry is safe. The wording
never says sent or not sent until it is known. A second approval of a decided review is refused by
the existing decided-review guard (`already`).

Close without sending is the owner's explicit verb, `close_unsent` (`VERB2STATUS` → `closed_unsent`):
the unsent draft stays on the review, the closure and its reason (the click's note, else the
channel's `send_block`) are recorded as a comment and audit row, the task closes as the owner's word,
and nothing reads as Sent. It is never an automatic consequence of a failed or blocked send. The
Review page's blocked-channel button now sends this verb instead of `no_reply`, with the reason in
its title. A proposal (`Kind: action`) is rejected, not closed without sending (`422`).

Decision recorded: a clarification is the one send that does not end the task - it asks, it does
not answer - so the task stays `waiting` (the existing `_settle_task_after_sent_reply` rule).

Tests: `tests/test_send_outcomes.py` (8 cases). Frontend: `website/src/ReviewView.jsx` (verb + title only; rebuilt bundle).

### All compatibility with saved reply envelopes and send outcomes

The merge through `9c6017e` now displays the exact selected review's saved To and
CC, preserves owner-edited CC (including an explicit empty list) across refresh,
and resets recipient edits when the exact message/review changes. Email approval
waits for the full review; an explicitly empty To envelope cannot silently fall
back to an unseen sender. Unknown delivery remains unknown on reopen, and no copy
claims it was definitively unsent or encourages a manual duplicate. Independent
Astra review cleared these bounded compatibility repairs.

Final gates: 306 frontend tests passed (1.636s); packaged build passed (12.97s);
38 reply-envelope/send-outcome/All/lifecycle/ledger tests passed (3.98s). The complete
canonical browser scenario passed (69.077s scenario / 72.138s process), including
saved recipients, persisted unknown delivery, owner-cleared CC retention during
real draft refresh, distinct sibling-review recipients, and every earlier All
assertion. Other cumulative and merge-specific gate results are recorded above.
Delivery is pending the exact-SHA remote CI, not acceptance of all Phase 1 work.

## Section 7.4 — completion-to-reply freshness: refresh, reassess, then draft

Status: implemented and tested locally at `ecabef1`; remote CI pending on the pushed
checkpoint. Section 7.3 is CI-verified (3459868/9c6017e, CI run 34054847136 (all ten jobs passed)).
Acceptance PW-235 to PW-238 implemented.

The agent's result became a reply the moment the session closed, written against the ask as it
stood when the work began. `coder.finish` now refreshes the source conversation first through
`coder.REFRESH`, the hook the server installs over `_refresh_chat_context` (the same gate the
Assistant and approvals use, incremental, connector-typed), and `coder.freshen` says where the ask
stands: fresh; changed (a newer inbound message - the review is pinned to it, the reason says the
thread moved on, and the drafting source carries the newest message so the reply answers what is
asked now); answered (`coder.answered_elsewhere`: the owner's own line newer than the newest inbound
message - a comment says so, a held draft is retired as no_reply, the task closes, nothing is drafted);
unresolved (the refresh failed - the draft is written from the saved result and marked stale with the
reason, so Send waits for a refresh that succeeds); or unchecked when no refresh is installed, which
is never called fresh. `raise_reply` reuses the held triage draft, else the pending review an earlier
completion event raised, so a repeated completion rewrites one review and never sends; the draft is
written from the saved final result and the current thread with its context revision pinned by
`responder.draft_for_review`, and the saved result survives a failed draft, which stays retryable.

The always-draft rule (PW-237): a channel that cannot carry the reply no longer suppresses it.
`finish` and `wrap` return `can_send` and `send_block` alongside `drafting`; the review is raised, the
task waits, the Review page hides Send with the reason and offers Close without sending (Section 7.3).
Only a row nobody sent - a report, work started here, the assistant's own post (`coder.no_one_behind`)
- drafts nothing; a report whose card names a findings target still delivers there. The pins in
`tests/test_reply_channels.py` and `tests/test_api.py` that said "GitHub replies off closes clean with
no draft" were rewritten to this rule.

Tests: `tests/test_completion_freshness.py` (11 cases), `tests/test_reply_channels.py` (3 pins rewritten), `tests/test_api.py` (1 pin
rewritten). No frontend change.
