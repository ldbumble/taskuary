# Processing walkthrough TODOs

Recorded during the owner-approved, step-by-step code review on 2026-09-04.
These are pending fixes, not implemented changes. Preserve existing read state and
triage behavior while addressing them.

## Poll scheduling and configuration

- [ ] Prevent slow AI triage and full-sync report execution from blocking fresh
  chat intake. Review the synchronous poll loop and `_POLL_BUSY` scope together;
  preserve safe deduplication and ordered task routing when separating work.
  Source: `taskuary/server.py`, `poll_forever()` and `_poll_reports()`.
- [ ] Account for chat fetches performed during a full sync in the fast-poll
  timestamps, so a redundant quick fetch does not immediately follow it. Define
  success/failure retry behavior explicitly.
  Source: `taskuary/server.py`, `_LAST_POLL` and `_QUICK_LAST`.
- [ ] Expose the supported fast-poll interval consistently for Teams, Slack,
  Telegram, and Discord, alongside the existing WhatsApp and iMessage fields.
  Keep the global interval in Settings; make connector-specific overrides clear.
  Source: `website/src/ConnectorsView.jsx` and `website/src/SettingsView.jsx`.
- [ ] Correct polling labels/help text: WhatsApp's interval covers connector
  intake, not only assistant chat; other chat connectors also default to fast
  polling. Document missing/default, explicit zero, and global background-off
  semantics accurately, including iMessage's misleading blank-value guidance.
  Source: `website/src/ConnectorsView.jsx`, `taskuary/server.py::_quick_due()`.
- [ ] Add regression tests for slow triage/report execution versus chat intake,
  full-sync/quick-sync overlap and timestamp bookkeeping, failed-fetch retries,
  interval overrides, disabled polling, and the settings labels/defaults.

## Email catch-up must not skip backlog

- [ ] Outlook: `_mail_msgs()` reads newest-first and stops at its default 500
  cap, while `_poll_one()` subsequently advances the source watermark to now.
  Preserve continuation/progress until the backlog is exhausted; never advance
  past unfetched mail. Test more than 500 messages per folder and slow fetches.
- [ ] Gmail/IMAP: Inbox and Sent polling select the last 25 qualifying UIDs and
  advance to their maximum, skipping lower pending UIDs. Drain oldest pending
  UIDs in bounded batches, preserving retryable failures and UID validity.
- [ ] Gmail/IMAP: the date search window can exclude mail received during a long
  absence even when its UID exceeds the saved cursor. Make established-cursor
  catch-up cover the full gap; distinguish initial-import limits from catch-up.
  Test both Inbox and Sent with long absences and more than 25 new messages.

## Full email conversation context

Owner-approved requirement: assemble the full accessible email chain for every
email connector by merging newly fetched messages with stored history. Do not
download or duplicate the entire chain on every reply. Fetch only missing history.
This is pending implementation, not a claim that current intake does this.

- [ ] Keep incremental polling for discovering new mail. Store each new message
  once and link it to existing thread records before context-dependent triage/task
  routing. For A -> B -> C already stored, receiving D must reuse A/B/C, not
  download their bodies again or copy their content into D.
- [ ] Track thread-history coverage and unresolved message references. Retrieve
  missing history when a thread is newly encountered or has gaps; listing provider
  thread IDs/metadata to discover gaps is distinct from re-fetching stored bodies.
  Include
  inbound and sent messages across accessible relevant folders, regardless of
  read status or the incremental polling window; follow pagination to completion.
- [ ] Apply the same contract to Outlook/Graph and Gmail/IMAP. Scope provider
  conversation/thread IDs to the mailbox/account; use Gmail native thread IDs
  where available and Message-ID/References/In-Reply-To relationships for generic
  IMAP. Preserve those headers for matching; do not merge unrelated mail merely
  because subjects match. Thread membership is not automatically task membership.
- [ ] Preserve individual messages, chronology, sender/recipient metadata, and
  attachment associations. Historical context must not create duplicate tasks,
  revive previously read items in unread, or retrigger old actions.
- [ ] Refresh the selected thread before assistant/agent context is assembled,
  reusing stored history and fetching missing/new messages. Make inaccessible or
  incomplete history explicit; do not silently present partial context as full.
- [ ] Test across email connectors: old roots outside the watermark, sent replies,
  archived messages, multi-page chains, attachments, duplicate fetches, unrelated
  same-subject mail, later replies, and retrieval failures. Verify triage and task
  context use the retrieved chain without altering historical read state.
- [ ] Test incremental merging explicitly: D joins stored A/B/C without repeated
  body downloads or duplicate records; D referencing absent C retrieves the
  missing history. Repeated polls must remain idempotent, with complete context
  assembled from individual records rather than a copied chain per message.

## Routing: email identity versus chat intent

Owner-approved change: remove fuzzy task matching for email. This is pending
implementation; current `routing.route()` still scores email subjects/senders/body.

- [ ] Email: link new messages by actual conversation identity, merge missing
  chain records, and use the conversation's existing task association. Do not
  attach unrelated threads based on subject, sender, or body similarity. Missing
  thread identity must not fall back to fuzzy automatic attachment.
- [ ] Keep chain storage separate from task lifecycle. A reply on a closed task's
  email thread is retained as conversation context without automatically reopening
  the task. Triage determines whether the new reply requires further work.
- [ ] WhatsApp/Teams/Slack: use AI to determine whether a new message continues an
  existing ask or starts a different ask. A shared chat/room ID alone must not
  decide task membership. Preserve the conversation context for that decision.
- [ ] Add regression tests: unrelated emails with identical subjects remain
  separate; genuine replies reuse their chain/task association; missing identity
  cannot force a similarity match; closed-task replies do not automatically reopen
  work; one chat can contain multiple asks while follow-ups join the correct ask.

## Fresh evaluation for each new message

Owner requirement: when a new message arrives, reevaluate using the updated full
chain. An old message/chain evaluation must not determine the new verdict.

- [ ] Remove the automatic thread-dismissal veto through `ruled_on_thread()` /
  `store.owner_verdict_on_thread()` from both existing-task and new-task intake
  paths. An earlier owner `ignore` must not cause a new reply to be filed without
  fresh evaluation, whether or not an agent run is recorded as running.
- [ ] Merge the new message into its chain before evaluation. Evaluate the latest
  message in full conversation context, without carrying over an old FYI/ignore
  verdict or using that verdict as a presumption about the new message. Retain old
  decisions as history, not as an automatic suppression rule.
- [ ] Preserve the separately approved explicit feed-only and standing-policy
  bypasses. A per-message dismissal must not implicitly become a standing policy.
- [ ] Preserve old read/dismissed state: reevaluation of new activity must not
  resurrect each historical message as fresh unread work or automatically reopen
  a closed task. Fresh triage decides whether new activity needs action.
- [ ] Test a previously ignored/FYI chain receiving a new actionable request and
  a non-actionable acknowledgement, on both open and closed tasks, with and
  without an agent run. Assert fresh evaluation and retained chain context;
  duplicate fetches of the same message must not trigger another evaluation.

## Clean, complete context for AI triage

- [ ] Remove the historical-verdict prompt override in
  `triage.classify_intent()` (`_agreement`, "SETTLED BY YOUR OWNER", and the
  "Answer fyi - no exceptions" instruction). Repeated past evaluations must not
  force the verdict on new activity. Keep explicitly configured standing policies
  separate from historical message judgments.
- [ ] Replace `exchange_lines()`'s 12-message/300-character excerpt dependency
  with the approved assembled email-chain context. Audit downstream payload cuts
  too: `classify_intent()` currently truncates the cleaned current body to 1500
  characters. Preserve substantive requests and replies throughout the chain;
  disclose context-budget limitations instead of silently claiming completeness.
- [ ] Before sending email content to triage, remove signatures, automatic
  external-sender banners, confidentiality/legal notices, tracking/footer clutter,
  and other boilerplate. Keep original stored messages unchanged; cleaning creates
  a separate triage representation, not a destructive edit to source history.
- [ ] Represent each message's substantive content once. Remove repeated quoted
  copies only when their content is retained elsewhere in the assembled chain;
  preserve unique forwarded/quoted context and inline replies. Keep sender,
  recipients, timestamp, message identity, and meaningful attachment references as
  structured context. Do not strip actual requests merely because they mention
  security, notices, or signatures.
- [ ] Apply the same cleaning/context contract across email connectors. Extend
  existing `strip_boilerplate()` where appropriate rather than creating divergent
  per-connector cleaners.
- [ ] Add regression tests for historical-verdict unanimity versus a new request,
  chains longer than 12 messages, substantive text beyond existing character cuts,
  signatures/disclaimers/banners, quoted duplication, unique forwarded material,
  inline answers, and preserved original messages. Assert the actual model payload
  contains the clean substantive context and no forced historical verdict.

## Chat relationships in the same triage evaluation

Owner-approved requirement: messaging triage must identify whether a message
relates to an earlier message/ask, alongside its intent and kind, but only within
the same calendar day in the configured timezone. This is not a rolling 24-hour
window. A message from a prior day is new for automatic chat grouping regardless
of similarity or shared room identity.

- [ ] Extend the single triage verdict for WhatsApp, Teams, Slack, and similar
  messaging connectors with `relationship` (`new`, `continues`, `answers`, or
  `uncertain`), `related_message_ids`, and optional `existing_task_id`. Related
  messages need not already belong to a task. Keep intent/kind classification and
  relationship judgment in the same call, replacing a separate potentially
  conflicting chat-association classifier.
- [ ] Restrict automatic relationship candidates to the same chat/conversation
  and same local calendar date as the incoming message's timestamp. Use message
  dates, not processing dates, for delayed sync/backfill. Do not auto-attach to an
  older ask/task by bypassing the date restriction via a task ID or room match.
- [ ] Validate returned message/task IDs against the eligible candidate context.
  `uncertain` must not cause an automatic join. Prior-day messages cannot receive
  `continues`/`answers` links through this automatic grouping path.
- [ ] Keep this date restriction chat-only: email chains and structural identities
  of GitHub, Monday, Jira, and similar items are not reset at midnight. This rule
  controls chat grouping, not deletion of historical messages or forced creation
  of a task for every new informational message.
- [ ] Add tests for same-day continuations, answers before a task exists, multiple
  asks in one room, uncertain matches, invalid/cross-room IDs, yesterday/two-week-old
  candidates, midnight and timezone boundaries, delayed sync spanning dates, and
  unchanged cross-day email/tracker item association.

## Explicit triage errors and retry

Owner-approved requirement: failed triage is an error, not FYI/filed, and must have
a visible retry button. Pending implementation only.

- [ ] Store failed triage as a distinct message `Status='error'`, including model
  call failures, unusable/degraded verdicts, and exceptions caught by the queue
  drain. Audit existing-task follow-up failures too; do not silently treat them
  as successfully classified work. Preserve message content, existing task links,
  and diagnostic route records.
- [ ] Show a clear "Triage failed" state with a useful failure reason and a
  "Retry triage" button on the affected timeline item/message detail. Keep failed
  items discoverable; do not present them as successfully processed FYI.
- [ ] Adapt the existing retriage endpoint and `claim_retriage()` to the error
  state, including linked messages. Retry the same message with refreshed context
  and attachments, atomically claiming error -> triaging. Prevent repeated clicks
  or concurrent requests from creating duplicate tasks, drafts, or agent starts.
- [ ] On successful retry, apply the new verdict and clear the error indication;
  on another failure, return to error with the updated reason and retry available.
- [ ] Define a safe upgrade for identifiable historical triage-failure records
  currently stored as filed. Do not bulk-convert genuine FYI or reset historical
  read state. Handle missing AI configuration explicitly rather than presenting it
  as a successful FYI evaluation.
- [ ] Test model exceptions, malformed verdicts, drain failures, linked-message
  failures, visible retry controls, concurrent/double retry, repeated failure,
  successful recovery, retained attachments/context, and unaffected genuine FYI.

## Review progress

- Reviewed: poll scheduling/configuration, connector selection/dispatch, Outlook
  fetch and email catch-up limits, intake deduplication, and the approved
  incremental thread-merge requirement; feed/trigger gate, saved policies, triage
  queue, and deterministic task matching. Email/chat routing replacement approved.
- Reviewed: inherited email-thread dismissal; approved fresh evaluation on new
  messages instead of carrying the previous dismissal forward.
- Reviewed: AI context assembly and historical-verdict prompt override; approved
  clean full-chain triage context and removal of the forced historical verdict.
- Reviewed: AI intent/kind output categories; approved adding same-day chat
  relationships to the same triage verdict.
- Reviewed: FYI handling; approved distinct triage errors and a visible retry action.
- Next: reply_only handling.
- Remaining: message storage, triage/grouping/importance, unread and assistant
  selection, ignore/skip/memory, task creation, coding/general-agent dispatch,
  agent attention, and completion. Review one piece at a time with owner approval.
