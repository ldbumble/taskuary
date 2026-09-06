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

Status: implementation in progress from CI-verified `3dc3a5e`. PW-006 through
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
