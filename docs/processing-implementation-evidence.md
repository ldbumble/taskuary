# Processing implementation evidence

## Phase 0 / section 0.1: baseline and test infrastructure

Status: implemented, cumulatively tested locally and independently reviewed; remote CI pending. Base `2689679dd87227ff9102bb7d7feb8920e3c47ca6`.
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
| P0-REGRESSION | Full cumulative suites/build/native PTY and baseline failures | Backend 2186 + 66 subtests; frontend 262; browser 2; build parity passed |
| P0-REVIEW | Independent final diff and isolation review | Astra Extra High independent code/isolation review approved; final evidence audit before push |
| P0-REMOTE | Scoped push to origin/master and exact-SHA CI | Local gates passed; push and exact-SHA CI pending |

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

### Migration, rollback and limitations

Phase 0 makes no database schema or live data migration. Synthetic reopen evidence
and the additive migration/backup/rollback contract are prerequisites to later state
changes. Preserve all original read evidence, attachments, task history and custom
documents. No app restart, production connector use, outbound delivery or real model
run is part of this section. Browser-control ownership/UI remains pending owner review.

Remote verification is the only remaining section 0.1 delivery gate. No later phase
may be accepted on these baseline results alone; each must rerun cumulative gates.
