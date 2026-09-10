# Phase 2 intake: agent handoff record

Worker: Phase 2 intake agent (later also integrator, at the owner's direction), isolated worktree `../taskhub-phase2-intake`, branch
`processing/phase2-intake-poll`, base `ccde503` (origin/master, 2026-09-06). The four commits
below were rebased onto `7589b38` (Section 1.5), the UI packaged as `f244803`, and pushed to
master on 2026-09-06 at the owner's direction; CI run 34036813779 passed all ten jobs. No live app was
restarted, no production connector, live database, read state or owner document was
touched: every test used `MemoryStore` or the suite's disposable TASKUARY_HOME. The
browser-control redesign stays pending. This file is the worker's record; the lead
folds accepted rows into the evidence document and the acceptance ledger.

## Sections and commits

| Section | Acceptance | Commit | Files owned |
| --- | --- | --- | --- |
| 2.1a Poll lanes | PW-001, PW-002, PW-005 (backend part) | `5c8cf60` | `taskuary/server.py` (poll block + lifespan thread start + `/api/ingest/status` heal), `taskuary/ingest.py` (`drain`, `mark_fresh`, `await_quiet`), `tests/test_poll_lanes.py`, `tests/test_imessage.py` (one moved assertion), `tests/conftest.py` (new scheduler guard) |
| 2.1b Poll labels | PW-003, PW-004, PW-005 (settings part) | `3feb86d` | `website/src/pollFields.js` (new), `website/src/ConnectorsView.jsx` (six chat cards), `website/src/SettingsView.jsx` (Background sync help), `website/test/pollFields.test.mjs` |
| 2.2 Outlook catch-up | PW-006 | `a26feeb` | `taskuary/channels.py` (`_mail_msgs`, `_mail_cursor`, `_mail_folder`, outlook branch of `_poll_one`, per-folder error reporting), `tests/test_mail_catchup.py` |
| 2.3 IMAP catch-up | PW-007, PW-008 | `09bfd6a` | `taskuary/imapmail.py` (`_uids`, `_validity`, `_rewound`, `_batches`, `poll_sent`, `poll_imap`), `tests/test_imap_catchup.py` |

Not touched, by design: `store.py`, `concierge.py`, `funnel.py`, `funnel_presentation.py`,
`FeedView.jsx`, `AssistantView.jsx`, `TasksView.jsx`, the processing_* modules, the
evidence document and the ledger. PW-009 to PW-019 (full chains, routing) were not
started; see dependencies below.

## Contracts introduced or changed

- **Two poll lanes.** `_poll_reports()` is the full lane (channels, ordered triage drain,
  CI, wall roll-up, reports) under `_POLL_BUSY`; `_poll_reports(only=...)` now delegates
  to `_poll_quick()`, the chat lane under `_QUICK_BUSY`, which reads only the named
  connector types, has their lines judged first, and stops. `quick_forever()` is the
  chat clock (own thread, `QUICK_TICK` 5 s); `poll_forever()` keeps only the full clock.
  `poll_minutes` 0 still turns both off.
- **One connector type per lane at a time** (`_FETCHING`/`_fetching()`): the chat lane
  skips a type the full lane is reading; the full lane passes `only=` minus the types
  the chat lane holds. Dedupe therefore never races two fetches of one message.
- **Fast-clock stamps (PW-002):** the full lane stamps `_QUICK_LAST` for every chat type
  it read; the chat lane stamps when an attempt ends, success or failure; an attempt
  that never ran (lane busy, type in flight) is not stamped and is due again next tick.
  A blank saved `poll_seconds` means the default (30), not zero.
- **Drain order.** `ingest.drain(store, llm, progress, limit, fresh=(), only_fresh=False,
  wait=True)`: one drain at a time (`_DRAIN_LOCK`); `fresh` channels go first, arrival
  order within a channel is unchanged; `mark_fresh()` tells a running drain the same;
  `only_fresh` leaves the backlog to the full lane; `wait=False` returns 0 at once.
  `await_quiet(store, channels, timeout)` is the context gate's wait for judged lines.
  The default call `drain(store, llm)` behaves as before.
- **Context gate (`_refresh_chat_context`)** is unchanged at its call site; through the
  chat lane it now waits (`DRAIN_WAIT` 45 s) for an in-flight fetch and for its lines
  to be judged, and returns False (the existing "still syncing" path) when it cannot.
- **`ingest_status`** is the full lane's banner; the chat lane writes it only while no
  full sync runs, and the ghost heal idles a `running` flag only when neither lane
  holds its lock.
- **Outlook.** `_mail_msgs(tok, upn, since, folder, cap=MAIL_BATCH, inclusive=False,
  skip=0)` returns the OLDEST `cap` messages after `since`; `_mail_folder()` drains a
  folder batch by batch, keeping `mail_cursor[folder]` in the source's ConfigJson
  between batches and dropping it at the end. `LastPolledAt` moves only when every
  folder (Sent Items included) finished; a failed folder is reported on the card
  (`LastError`, joined per folder) while other folders and sources still read. The
  owner's `folders` key survives cursor writes (re-read before each save).
- **IMAP.** With a cursor: `UID cursor+1:*`, drained oldest-first in `BATCH` (25)
  rounds, `imap_uid` saved after each; the `SINCE` window applies to the first import
  only. `TRANSPORT` failures (`imaplib.IMAP4.abort`, `OSError`) stop the poll with the
  watermark on the last landed message and propagate to the card; one unreadable UID
  is stepped over. New connector config keys `imap_uidvalidity` and
  `imap_sent_uidvalidity`; a changed value re-imports that folder under the date
  window. `poll_sent(store, M, user, last_uid, days, state=None)` keeps its signature
  and `(n, uid)` return.

Migration: additive only. New JSON keys (`mail_cursor` on a source, `imap_uidvalidity`
and `imap_sent_uidvalidity` on a connector) are absent until first written; older code
ignores them. No schema change, no read-state or historical rewrite. Rollback is a
revert of the commits; a source left with a `mail_cursor` is harmless to old code
(the key is ignored and `LastPolledAt` still governs). No backup is needed because no
live migration runs.

## Tests and evidence

All commands ran in the isolated worktree on Windows, Python 3.10.8; frontend under the
disposable Node 22.23.2 from `npm exec --yes --package=node@22`, with the worktree's
`website/node_modules` a junction to the owner checkout's install (unlink it before
any `git worktree remove`). Logs: ignored `.codex-tmp/phase2-evidence/` in the worktree.

| Gate | Result |
| --- | --- |
| `python -m pytest -q tests/test_poll_lanes.py` (20 cases: lanes, stamps, in-flight exclusion, context gate, banner, ghost heal, both clocks, lifespan guard, drain order x6) | 20 passed |
| `python -m pytest -q tests/test_mail_catchup.py` (8: asc/cap, inclusive, 1050 backlog, resume after a dead batch, same-second boundary, only-seen batch, Sent, dead folder) | 8 passed |
| `python -m pytest -q tests/test_imap_catchup.py` (8: 80 pending UIDs, abort at 140 then resume, one NO, two-week gap under a 3-day window, first import, UIDVALIDITY change, no validity, Sent gap) | 8 passed |
| Neighbours after 2.1: sync clock, imessage, chat freshness, poll parallel, api, mail folders, isolation contract, async triage, chat queue | 195 passed |
| Neighbours after 2.2/2.3: mail folders, poll parallel, imessage, chat freshness, cc, cc triage, mark read, msauth, audit fixes, setup, imapmail, imap history | 183 + 45 passed |
| Full backend after 2.1 (`python -m pytest -q -ra`) | 2333 passed, 66 subtests, 0 failed, 164.27 s |
| Full backend on the final tree, `python -m pytest -q -ra` (`09bfd6a` + this record) | 2350 passed, 66 subtests, 0 failed, 0 skipped, 149 existing warnings, 198.55 s |
| `npm test` (Node 22; also Node 20 with an explicit file list) | 269 passed, 0 failed, 0 skipped (264 existing + 5 new) |
| `eslint -c eslint.undef.mjs` (no-undef) | 0 no-undef problems; 9 pre-existing "rule react-hooks/exhaustive-deps not found" notices in files this work did not touch |
| `vite build --outDir <scratch> --emptyOutDir` (Node 22.23.2) | built in 25.86 s; nothing written under `taskuary/web` (packaged output stays the integration owner's gate) |

Existing assertions changed: one. `test_imessage.test_poll_minutes_zero_silences_the_fast_clock_too`
now drives `quick_forever()` instead of `poll_forever()`; its two assertions (off switch,
exact call) are unchanged. Reason: PW-001 moves the chat clock off the full loop, where a
branch could never fire during a long sync. No assertion was weakened and no skip added.

TDD record: every new test file was run and seen failing before implementation (lanes
16/19 failed, Outlook 7/8, IMAP 7/8; the passers were pre-existing behaviour kept on
purpose - arrival order, the one-batch case, no-validity servers).

## Dependencies and flags for the lead

- **server.py is shared.** This work owns lines around the poll block (`_POLL_BUSY` to
  `_poll_quick`), the lifespan `quick_forever` thread start, and one line in
  `ingest_status()`. The Phase 1 freshness branches do not touch server.py; a later
  inventory endpoint section will, so rebase order matters only textually.
- **conftest.py gained one guard line** (`quick_forever` stopped in the test lifespan)
  and two comment counts; the isolation contract test still passes unchanged.
- **Unfinished Phase 1 not required** for these sections: none of them consume the
  canonical inventory or freshness presentation. PW-009 to PW-015 (full chains,
  context revision at intake) DO depend on Phase 1.1's canonical item identity and
  `context_revision` being the agreed handle for "what triage consumed"; PW-016 to
  PW-019 (routing by conversation identity) depend on the chain storage from PW-009+.
  They should start only from the accepted checkpoint that includes both.
- **Packaged output not generated here.** The source compiles (scratch-directory Vite
  build above); the integration owner regenerates `taskuary/web` from the accepted commit
  as before. Node 20.10 cannot run the locked Vite; use the disposable Node 22.
- **Browser gate.** No rendered-browser scenario was added: the changed flows are
  background scheduling and connector fetches with no UI path beyond card text.
- **Behaviour the owner may notice.** Chat connectors are checked every 5 s against
  their interval (before: every 30 s tick), so "every 30 seconds" now means that; a
  Teams line arriving during a mail catch-up is judged after at most one triage call
  instead of after the whole backlog; a big Outlook backlog is read to the end in one
  poll (progress shown per batch on the banner) instead of 500 per ten minutes.
- **Open policy question surfaced:** `_poll_quick` returns False on a failed fetch, so
  `_refresh_chat_context` reports "still syncing" rather than the connector error when
  `poll_channels` itself raises (per-connector errors still surface via `LastError`).
  Left as is; wording can be reconsidered with PW-049's shared freshness check.
