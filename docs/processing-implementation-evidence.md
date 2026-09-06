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

Status: implemented, independently reviewed and cumulatively tested from
CI-verified `85c2e1b`; remote CI gate pending.
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
Original workspace remains at the previously accepted checkpoint until remote CI
passes; its README hash is unchanged. No live app restart, data migration or
production connector was used. Browser-control redesign remains pending.
