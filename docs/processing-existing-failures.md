# Processing baseline observations

Baseline: `2689679dd87227ff9102bb7d7feb8920e3c47ca6`. Observed deficiencies below
are separate from executed test failures. Passing existing tests can encode behavior
that the owner has since approved replacing; record that replacement explicitly.

| ID | Observation and evidence | Required follow-up |
| --- | --- | --- |
| OBS-001 | `tests/conftest.py` trusts TASKUARY_TEST_HOME and only disables coding auto-start. Server lifespan starts WhatsApp/catch-up/poll/waitroom. | Phase 0 isolated home and side-effect guards before full local pytest. |
| OBS-002 | `terminal.pretrust` can write the owner's `~/.claude.json` even under TASKUARY_HOME; mocked Term alone is insufficient isolation. | Phase 0 prevent trust/hook writes outside disposable test workspace. |
| OBS-003 | `desktop.start_server` discards its daemon Thread; `main` sets should_exit without waiting. Server-only interrupt returns without that signal. Existing desktop smoke does not await cleanup. | Phase 0 behavioral characterization, Phase 12 (or reviewed earlier fix) shutdown completion and owned-child cleanup. |
| OBS-004 | Lifespan poll/watch loops can outlive cleanup; worker/CLI cleanup snapshots permit late-start races. Direct CLI kill does not prove process-tree cleanup. | Phase 12 real quit/restart and child ownership tests. |
| OBS-005 | `funnel_state` lacks explicit read provenance. `store.feed` infers handling from surfaced, deferred, task/review state, ignored rows and age; FunnelKey changes with attention state. | Phase 1 canonical IDs and provenance-preserving migration after unresolved policy is settled. |
| OBS-006 | Existing `test_funnel.py` expects showing=>read, historical suppression, age/cap filtering and waiting-before-urgent ordering. | Retain baseline evidence; replace only with explicit approved contract mapping and stronger behavioral assertions in Phase 1. |
| OBS-007 | Node 20.10.0 is installed; locked puppeteer-core 25.8.0 declares Node >=22.12.0. npm ci warns. | Phase 0 browser runtime compatibility; do not silently claim existing CI covers rendered browsers. |
| OBS-008 | Windows CRLF in a multiline BrowserPane JSX title compiles to an extra escaped carriage return, cascading three chunk hashes despite identical Git source. Build CI did not compare committed assets. | Phase 0 targeted LF attributes, normalized integration build inputs and CI packaged-asset parity check. This is line-ending nondeterminism, not evidence of stale source. |
| OBS-009 | Existing FakeScreencast.stop in tests/test_browserview.py stops its asyncio loop before coroutine cleanup; full runs report unraisable/never-awaited warnings. | Keep recorded; this is not proof of orderly shutdown. No browser-control redesign is included. |
| OBS-010 | Demo Replay omitted quiet_for required by the real terminal websocket; rendered replay closed on attach. | Fixed by Phase 0 commit 6a50579; real websocket reconnect and rendered-browser regressions required. |

## Executed baseline tests

Windows, Python 3.10, Node 20.10.0; isolated integration worktree based on 2689679.
`npm test` in website: **262 passed, 0 failed, 0 skipped**, runner duration 2.113 s.
Backend/build/browser results will be recorded in the section implementation evidence.
No new future-feature skips or expected-failure markers are authorized by this list.

Final integrated backend: 2186 passed and 66 subtests passed in 157.55 s; one
pre-existing clock-dependent skip (test_digest_brief.py:138 before08:00). The twelve
initial full-run failures were isolation compatibility issues, subsequently fixed
without weakening existing assertions. Final browser tooling retains the baseline
Puppeteer25.8.0 lock and uses disposable Node22; no dependency downgrade is retained.
