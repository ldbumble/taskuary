# Triage, Context and Delivery Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the named "partial" gaps recorded in `docs/processing-acceptance-ledger.md` for the open triage, conversation-context, dispatch and delivery items (PW-010..014, 021, 035, 041, 047, 049, 052, 056, 057, 062, 063, 066, 073, 078, 083, 085, 087, 088, 089, 096, 097, 098, 100, 129, 130, 132, 134, 143, 146, 149) so each can be ticked with a test, or left open with the exact decision or surface it still needs.

**Architecture:** Every item in scope already has an implementation; the ledger names one remaining gap per item. Each task below closes one gap cluster in the module that owns it (chains.py for history coverage, blackboard.py/ingest.py for dispatch retries, operations.py for execute-once and evidence, outbound.py for send capability, server.py for the retriage notice) with a regression test beside the existing test file for that module. Rendered-browser checks and new UI controls are recorded as open with the surface they need; they are not faked.

**Tech Stack:** Python 3.10, FastAPI, SQLite (`taskuary/store.py`), pytest with `unittest` style tests under `tests/`, loguru.

**Spec:** `docs/processing-walkthrough-todos.md` (the items above) and the gap text in `docs/processing-acceptance-ledger.md` rows for the same ids.

## Global Constraints

- Dense fast.ai code style; no formatters. Preserve each file's line endings (`taskuary/server.py` is CRLF; others LF). Never write a backslash line-continuation through a heredoc.
- Tests from the worktree root: `python -m pytest <files> -q -p no:cacheprovider`. Never run a test file directly.
- Owner rules (2026-09-06): no keyword/regex intent routing; a read receipt only on explicit read/done; the context gate before an ACTION always polls the provider (grace only for chat introductions); a task keeps its read state when the chat mirrors words onto it.
- Historical context must never create tasks, revive read items, or retrigger actions (PW-012): history rows stay `history`/`context`, never routed.
- Docs: tick only this plan's items in the todos and ledger; add one evidence block; touch no other lines.
- Nothing is pushed or merged; the branch stops at a review gate.

---

### Task 1: Chain coverage tells the truth and is scoped to the mailbox (PW-010, PW-011)

**Files:** Modify `taskuary/chains.py:29-47,88-105,116-184`, `taskuary/store.py:546-547,1202-1210`, callers `taskuary/channels.py:1162,1222`, `taskuary/imapmail.py:682,695`, `taskuary/ingest.py:1103`. Test: `tests/test_email_chains.py`, `tests/test_imap_history.py`.

**Gap (ledger):** empty/duplicate continued pages and failed IMAP FETCH commands still claim complete coverage; coverage is keyed by conversation id alone, not by mailbox/account.

- [ ] Test (append to `tests/test_email_chains.py`): a Graph listing whose second page is empty or repeats the first records `complete: False` with `error` naming the stopped listing; a mailbox B coverage row never satisfies `needs_history` for mailbox A on the same conversation id.
- [ ] Test (append to `tests/test_imap_history.py`): a FETCH returning `('NO', ...)` for one UID leaves `complete: False`, `error` counting the failed fetch, other UIDs still stored.
- [ ] `list_ids_graph` returns `(out, stopped)` where `stopped` is `''` or the reason (`'empty continued page'`, `'repeated page'`, `'page budget'`); `refresh_outlook` marks `complete=False, error=stopped` when non-empty.
- [ ] `refresh_imap`: count `failed` fetches; `cov['complete'] = failed == 0`, `error = f'{failed} message(s) could not be fetched'` when failed.
- [ ] Store: `chain` gets `PRIMARY KEY (Mailbox, ConversationId)` via a one-time migration that copies the old table (`chain_v1`) when the schema lacks the composite key; `set_chain_coverage`/`chain_coverage(conversation_id, mailbox=None)`; `chains.needs_history(store, conv, mailbox)` and `coverage(store, conv, mailbox)`; callers pass the mailbox they poll (`s['Address']` / `user`); ingest passes `msg.get('source_name')`.
- [ ] Commit: `feat: chain coverage is honest about stopped listings and failed fetches, and scoped to the mailbox (PW-010, PW-011)`

### Task 2: Fetched history keeps its attachments (PW-012, PW-014)

**Files:** Modify `taskuary/chains.py:69-87` (`_keep` takes `atts`), `:88-105` (Graph: `mail_attachments` when `hasAttachments`), `:116-184` (IMAP passes `_atts`). Test: `tests/test_email_chains.py`, `tests/test_imap_history.py`.

- [ ] Test: a history message with one attachment stores one `attachment` row bound to the history `MessageId` (both providers); a duplicate fetch stores none twice.
- [ ] `_keep(..., atts=None)` calls `channels.save_attachments(store, mid, atts, ext)` after `add_message` when `atts`; `refresh_outlook` adds `$select` `hasAttachments` (already in `MAIL_SELECT`? verify) and fetches `channels.mail_attachments(tok, mailbox, m['id'])` only when `m.get('hasAttachments')`; `refresh_imap` passes `_atts`.
- [ ] Commit: `feat: fetched history keeps its attachments (PW-012, PW-014)`

### Task 3: The incomplete-history warning survives the context budget (PW-013)

**Files:** Modify `taskuary/ingest.py:1101-1110`. Test: `tests/test_message_thread.py`.

- [ ] Test: with `chain_coverage` incomplete and a budget that trims lines, the first line still starts with `… history incomplete` and the trim note follows it.
- [ ] Insert the warning AFTER the trim loop (trim, then the dropped note, then the warning at index 0).
- [ ] Docs: PW-013 gains the line `The refresh before assistant/agent context is the poll `_refresh_chat_context` runs, which re-lists any chain `needs_history` still reports incomplete (chains.needs_history); the warning is now inserted after budget trimming.`
- [ ] Commit: `fix: the incomplete-history warning is never trimmed away by the context budget (PW-013)`

### Task 4: Retriage is announced when new lines land, before their triage result (PW-052, PW-057)

**Files:** Modify `taskuary/server.py` `_poll_quick` (add `on_fetched` callback fired right after `poll_channels` returns with `added > 0`), `_poll_reports(..., on_fetched=None)`, `_refresh_chat_context(..., on_fetched=None)`, `_refresh_chat_key(..., on_fetched=None)`, `concierge_stream` (passes `lambda n: put({'type': 'context_update', 'say': RETRIAGE_STARTED, 'stage': 'started'})` once). Test: `tests/test_chat_freshness.py`.

- [ ] Test: with `_poll_reports` faked to call `on_fetched(2)` then return 2, `_refresh_chat_context(..., on_fetched=spy)` calls the spy once with 2 before returning; no call when nothing was fetched.
- [ ] `RETRIAGE_STARTED = "New messages came in on this conversation. I'm sending it through triage again before we continue."` emitted at most once per stream turn; the existing `_notice_once` line follows as the result.
- [ ] Commit: `feat: the owner hears that retriage started when new lines land, then its result (PW-052, PW-057)`

### Task 5: A queued general launch that fails keeps its retry row; every restored deadline is armed (PW-073, PW-085, PW-088, PW-089)

**Files:** Modify `taskuary/ingest.py:1363-1378` (`_start_general` returns `True` on success, `False` after recording the failure), `taskuary/blackboard.py:381-425` (`drain`: on `False` do not clear or say Started; at the end `schedule_due(store)`), `:365-376` (`schedule_due` arms the earliest and returns the delay — unchanged — but `drain` re-arms after each pass). Test: `tests/test_dispatch_retries.py`.

- [ ] Test: a queued GENERAL task whose `general.start_session` raises keeps its dispatch row in `retrying` with `Attempts == 1` and no "Started from the dispatch queue" comment; two rows with distinct `NextAt` both run when due (fake timer records both delays).
- [ ] Commit: `fix: a queued general launch that fails is a counted retry, and every restored deadline is armed (PW-073, PW-085, PW-088, PW-089)`

### Task 6: Execute once under concurrency; no evidence from an outcome that says it failed (PW-129, PW-130, PW-134)

**Files:** Modify `taskuary/operations.py:205-233`, `taskuary/store.py` (add `claim_operation(op_id, version) -> bool`: `UPDATE operation SET Status='running', UpdatedAt=? WHERE OpId=? AND Version=? AND Status IN ('proposed','error')` returns rowcount 1). Test: `tests/test_operations.py`.

- [ ] Test: two threads executing the same proposal run the handler once; the second gets `duplicate: True` or `status: running`. An outcome `{'ok': False, 'error': 'x'}` writes `Evidence: 'none'` and no correction row.
- [ ] `execute`: after the stale checks, `if not store.claim_operation(op_id, version): return {**_public(store.get_operation(op_id)), 'duplicate': True}`; on exception restore `Status: 'error'` (already). `_evidence`: when `OutcomeJson` is a dict with truthy `error` or `ok is False`, record `Evidence: 'none'`.
- [ ] Commit: `fix: a proposal executes once under concurrent confirms, and a failed outcome teaches nothing (PW-129, PW-130, PW-134)`

### Task 7: The assistant conversation is durable per item (PW-132)

**Files:** Modify `taskuary/concierge.py` `record_related` (after the task mirror, `operations.discuss(store, actor, text, message_id=item.get('mid'), task_id=tid)` for the discussed item, guarded so failures never break the turn). Test: `tests/test_concierge.py` (append).

- [ ] Test: surfacing an item and saying one line about it leaves `operations.discussion(store, message_id=mid)` with both the assistant's and the owner's turns, attributed by actor, and the dock task's own history unchanged in count.
- [ ] Commit: `feat: what is said about an item in the chat is kept against the item (PW-132)`

### Task 8: Send capability is probed before the first send (PW-143, PW-146)

**Files:** Modify `taskuary/outbound.py:156-166` (`send_block` calls `send_probe`), add `send_probe(store, channel, mailbox=None) -> str`: email via IMAP connector with no SMTP host configured → `'no SMTP host is configured for <address> (its card)'`; email via Outlook whose connector config records `granted_scope` without `Mail.Send` → `'the Microsoft sign-in did not grant Mail.Send - sign in again on the Outlook card'`. `taskuary/msauth.py:128` keeps `scope` in `_tokens`; where the exchange result is saved (grep `refresh_token` in `channels.graph_creds`/`msauth`), persist `granted_scope` into the connector config. Test: `tests/test_send_outcomes.py`.

- [ ] Test: an IMAP mailbox with blank `smtp_host` and no default → `send_block` names the missing SMTP host and the Review payload hides Send; an Outlook connector with `granted_scope='Mail.Read'` → the Mail.Send reason; with `Mail.Send` present → `''`.
- [ ] Commit: `feat: a reply that cannot leave says why before the first send is tried (PW-143, PW-146)`

### Task 9: Canonical Unread drops a settled reply (PW-149)

**Files:** Test only: `tests/processing/test_processing_unread.py`.

- [ ] Test: a routed message with a pending review is in Unread; after `verdicts._settle_task_after_sent_reply(store, review, 'owner', True)` and the review marked sent, the canonical Unread no longer lists it and All still does.
- [ ] Commit: `test: a confirmed send leaves Unread and stays in All (PW-149)`

### Task 10: Test-only closures (PW-021, PW-035, PW-056, PW-062, PW-066, PW-083)

- [ ] PW-035: `tests/test_fresh_evaluation.py` or `tests/test_message_thread.py` gains a tracker-item cross-day association case and a configured-timezone midnight case.
- [ ] PW-056: `tests/test_chat_freshness.py` gains a concurrent sync/action case (a sync that lands between capture and commit makes the operation stale).
- [ ] PW-062: `tests/test_reply_voice.py` gains a before/after payload diff after a writing-feedback save.
- [ ] PW-066: `tests/test_reply_envelope.py` exercises the IMAP and Graph send fakes with the exact to/cc envelope.
- [ ] PW-021: `tests/test_fresh_evaluation.py` asserts the chain is complete (coverage row) before the context-dependent triage worker sees the message.
- [ ] PW-083: tick with the note that live Graph/IMAP Sent queries are the connector boundary the fakes stand in for.
- [ ] Commit: `test: acceptance cases for chain-before-triage, cross-day association, concurrent sync, reply voice, per-connector envelope (PW-021, PW-035, PW-056, PW-062, PW-066, PW-083)`

### Task 11: Record, and name what stays open

Open with the surface they need (not faked): PW-041, PW-047, PW-078, PW-096, PW-100, PW-134's UI half (rendered-browser runs of Retry, hidden Send, checkbox, repository picker, confirmation box); PW-063's To/mode controls on the Review page; PW-087's task-view Retry/Cancel buttons and attention-pipeline row; PW-097's conversational repository picker; PW-098 (owner decision: does a single configured repository still need the confirmation step?).

- [ ] Gates: full pytest; `node --test taskuary/whatsapp/`.
- [ ] Tick the closed items in the todos with one evidence line each; ledger rows → `implemented` with the test file; one evidence block.
- [ ] Commit: `docs: record triage/context/delivery acceptance (PW-010..014, 021, 035, 049, 052, 056, 057, 062, 066, 073, 083, 085, 088, 089, 129, 130, 132, 143, 146, 149)`
