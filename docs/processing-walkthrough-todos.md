# Processing walkthrough TODOs

Recorded during the owner-approved, step-by-step code review on 2026-09-04.
These are pending fixes, not implemented changes. Preserve existing read state and
triage behavior while addressing them.

Implementation sequencing and cumulative multi-agent test/push gates are in
[processing-implementation-plan.md](processing-implementation-plan.md). This TODO
remains the detailed acceptance record. Newer explicit owner decisions supersede
historical wording; the plan lists reconciliations and unresolved policy boundaries.

## Poll scheduling and configuration

Execution tracking: [acceptance ledger](processing-acceptance-ledger.md) and
[section evidence](processing-implementation-evidence.md). PW IDs are permanent;
adding them does not change approval or completion status.
Phase 0 infrastructure is CI-verified at `9bef568` (run 34012833267, all 10 jobs).
Unchecked feature requirements below remain pending their own implementation gates.

- [x] <a id="pw-001"></a>**PW-001** Prevent slow AI triage and full-sync report execution from blocking fresh
  chat intake. Review the synchronous poll loop and `_POLL_BUSY` scope together;
  preserve safe deduplication and ordered task routing when separating work.
  Source: `taskuary/server.py`, `poll_forever()` and `_poll_reports()`.
- [x] <a id="pw-002"></a>**PW-002** Account for chat fetches performed during a full sync in the fast-poll
  timestamps, so a redundant quick fetch does not immediately follow it. Define
  success/failure retry behavior explicitly.
  Source: `taskuary/server.py`, `_LAST_POLL` and `_QUICK_LAST`.
- [x] <a id="pw-003"></a>**PW-003** Expose the supported fast-poll interval consistently for Teams, Slack,
  Telegram, and Discord, alongside the existing WhatsApp and iMessage fields.
  Keep the global interval in Settings; make connector-specific overrides clear.
  Source: `website/src/ConnectorsView.jsx` and `website/src/SettingsView.jsx`.
- [x] <a id="pw-004"></a>**PW-004** Correct polling labels/help text: WhatsApp's interval covers connector
  intake, not only assistant chat; other chat connectors also default to fast
  polling. Document missing/default, explicit zero, and global background-off
  semantics accurately, including iMessage's misleading blank-value guidance.
  Source: `website/src/ConnectorsView.jsx`, `taskuary/server.py::_quick_due()`.
- [x] <a id="pw-005"></a>**PW-005** Add regression tests for slow triage/report execution versus chat intake,
  full-sync/quick-sync overlap and timestamp bookkeeping, failed-fetch retries,
  interval overrides, disabled polling, and the settings labels/defaults.

  Section 2.1: independent review cleared; combined-base regressions passed 2452
  backend tests plus 66 subtests, 281 frontend tests, packaged build and all seven
  real-browser scenarios. Delivery and exact-SHA CI are recorded in the
  [implementation evidence](processing-implementation-evidence.md#section-21--independent-poll-scheduling-and-settings).
  The email catch-up review corrections and final gates are recorded below.

## Email catch-up must not skip backlog

- [x] <a id="pw-006"></a>**PW-006** Outlook: `_mail_msgs()` reads newest-first and stops at its default 500
  cap, while `_poll_one()` subsequently advances the source watermark to now.
  Preserve continuation/progress until the backlog is exhausted; never advance
  past unfetched mail. Test more than 500 messages per folder and slow fetches.
- [x] <a id="pw-007"></a>**PW-007** Gmail/IMAP: Inbox and Sent polling select the last 25 qualifying UIDs and
  advance to their maximum, skipping lower pending UIDs. Drain oldest pending
  UIDs in bounded batches, preserving retryable failures and UID validity.
- [x] <a id="pw-008"></a>**PW-008** Gmail/IMAP: the date search window can exclude mail received during a long
  absence even when its UID exceeds the saved cursor. Make established-cursor
  catch-up cover the full gap; distinguish initial-import limits from catch-up.
  Test both Inbox and Sent with long absences and more than 25 new messages.

  Section 2.2: independently reviewed source `32d014b` passed 2,643 backend tests
  plus 71 subtests, 290 frontend tests, the packaged build, and all seven real
  browser scenarios. Earlier failures, their diagnoses, and the unchanged
  regression assertions are retained in the [implementation evidence](processing-implementation-evidence.md#section-22--email-catch-up-without-skipped-backlog),
  with delivery and exact-SHA CI tracked there. Historical messages, read state,
  and custom documents are checked through real Sync-now API tests on disposable data.

## Full email conversation context

Owner-approved requirement: assemble the full accessible email chain for every
email connector by merging newly fetched messages with stored history. Do not
download or duplicate the entire chain on every reply. Fetch only missing history.
This is pending implementation, not a claim that current intake does this.

- [x] <a id="pw-009"></a>**PW-009** Keep incremental polling for discovering new mail. Store each new message
  once and link it to existing thread records before context-dependent triage/task
  routing. For A -> B -> C already stored, receiving D must reuse A/B/C, not
  download their bodies again or copy their content into D.
- [ ] <a id="pw-010"></a>**PW-010** Track thread-history coverage and unresolved message references. Retrieve
  missing history when a thread is newly encountered or has gaps; listing provider
  thread IDs/metadata to discover gaps is distinct from re-fetching stored bodies.
  Include
  inbound and sent messages across accessible relevant folders, regardless of
  read status or the incremental polling window; follow pagination to completion.
- [ ] <a id="pw-011"></a>**PW-011** Apply the same contract to Outlook/Graph and Gmail/IMAP. Scope provider
  conversation/thread IDs to the mailbox/account; use Gmail native thread IDs
  where available and Message-ID/References/In-Reply-To relationships for generic
  IMAP. Preserve those headers for matching; do not merge unrelated mail merely
  because subjects match. Thread membership is not automatically task membership.
- [ ] <a id="pw-012"></a>**PW-012** Preserve individual messages, chronology, sender/recipient metadata, and
  attachment associations. Historical context must not create duplicate tasks,
  revive previously read items in unread, or retrigger old actions.
- [ ] <a id="pw-013"></a>**PW-013** Refresh the selected thread before assistant/agent context is assembled,
  reusing stored history and fetching missing/new messages. Make inaccessible or
  incomplete history explicit; do not silently present partial context as full.
- [ ] <a id="pw-014"></a>**PW-014** Test across email connectors: old roots outside the watermark, sent replies,
  archived messages, multi-page chains, attachments, duplicate fetches, unrelated
  same-subject mail, later replies, and retrieval failures. Verify triage and task
  context use the retrieved chain without altering historical read state.
- [x] <a id="pw-015"></a>**PW-015** Test incremental merging explicitly: D joins stored A/B/C without repeated
  body downloads or duplicate records; D referencing absent C retrieves the
  missing history. Repeated polls must remain idempotent, with complete context
  assembled from individual records rather than a copied chain per message.

Integration review keeps PW-010/PW-011 partial: provider listing completeness and
account/epoch-scoped coverage remain unresolved. PW-013 also needs its incomplete
history warning to survive context budgeting. The earlier authored Section 2.4
evidence is retained with these follow-up findings.

## Routing: email identity versus chat intent

Owner-approved change: remove fuzzy task matching for email. This is pending
implementation; current `routing.route()` still scores email subjects/senders/body.

- [x] <a id="pw-016"></a>**PW-016** Email: link new messages by actual conversation identity, merge missing
  chain records, and use the conversation's existing task association. Do not
  attach unrelated threads based on subject, sender, or body similarity. Missing
  thread identity must not fall back to fuzzy automatic attachment.
- [x] <a id="pw-017"></a>**PW-017** Keep chain storage separate from task lifecycle. A reply on a closed task's
  email thread is retained as conversation context without automatically reopening
  the task. Triage determines whether the new reply requires further work.
- [x] <a id="pw-018"></a>**PW-018** WhatsApp/Teams/Slack: use AI to determine whether a new message continues an
  existing ask or starts a different ask. A shared chat/room ID alone must not
  decide task membership. Preserve the conversation context for that decision.
- [x] <a id="pw-019"></a>**PW-019** Add regression tests: unrelated emails with identical subjects remain
  separate; genuine replies reuse their chain/task association; missing identity
  cannot force a similarity match; closed-task replies do not automatically reopen
  work; one chat can contain multiple asks while follow-ups join the correct ask.

## Fresh evaluation for each new message

Owner requirement: when a new message arrives, reevaluate using the updated full
chain. An old message/chain evaluation must not determine the new verdict.

- [x] <a id="pw-020"></a>**PW-020** Remove the automatic thread-dismissal veto through `ruled_on_thread()` /
  `store.owner_verdict_on_thread()` from both existing-task and new-task intake
  paths. An earlier owner `ignore` must not cause a new reply to be filed without
  fresh evaluation, whether or not an agent run is recorded as running.
- [ ] <a id="pw-021"></a>**PW-021** Merge the new message into its chain before evaluation. Evaluate the latest
  message in full conversation context, without carrying over an old FYI/ignore
  verdict or using that verdict as a presumption about the new message. Retain old
  decisions as history, not as an automatic suppression rule.
- [x] <a id="pw-022"></a>**PW-022** Preserve the separately approved explicit feed-only and standing-policy
  bypasses. A per-message dismissal must not implicitly become a standing policy.
- [x] <a id="pw-023"></a>**PW-023** Preserve old read/dismissed state: reevaluation of new activity must not
  resurrect each historical message as fresh unread work or automatically reopen
  a closed task. Fresh triage decides whether new activity needs action.
- [x] <a id="pw-024"></a>**PW-024** Test a previously ignored/FYI chain receiving a new actionable request and
  a non-actionable acknowledgement, on both open and closed tasks, with and
  without an agent run. Assert fresh evaluation and retained chain context;
  duplicate fetches of the same message must not trigger another evaluation.

## Clean, complete context for AI triage

- [x] <a id="pw-025"></a>**PW-025** Remove the historical-verdict prompt override in
  `triage.classify_intent()` (`_agreement`, "SETTLED BY YOUR OWNER", and the
  "Answer fyi - no exceptions" instruction). Repeated past evaluations must not
  force the verdict on new activity. Keep explicitly configured standing policies
  separate from historical message judgments.
- [x] <a id="pw-026"></a>**PW-026** Replace `exchange_lines()`'s 12-message/300-character excerpt dependency
  with the approved assembled email-chain context. Audit downstream payload cuts
  too: `classify_intent()` currently truncates the cleaned current body to 1500
  characters. Preserve substantive requests and replies throughout the chain;
  disclose context-budget limitations instead of silently claiming completeness.
- [x] <a id="pw-027"></a>**PW-027** Before sending email content to triage, remove signatures, automatic
  external-sender banners, confidentiality/legal notices, tracking/footer clutter,
  and other boilerplate. Keep original stored messages unchanged; cleaning creates
  a separate triage representation, not a destructive edit to source history.
- [x] <a id="pw-028"></a>**PW-028** Represent each message's substantive content once. Remove repeated quoted
  copies only when their content is retained elsewhere in the assembled chain;
  preserve unique forwarded/quoted context and inline replies. Keep sender,
  recipients, timestamp, message identity, and meaningful attachment references as
  structured context. Do not strip actual requests merely because they mention
  security, notices, or signatures.
- [x] <a id="pw-029"></a>**PW-029** Apply the same cleaning/context contract across email connectors. Extend
  existing `strip_boilerplate()` where appropriate rather than creating divergent
  per-connector cleaners.
- [x] <a id="pw-030"></a>**PW-030** Add regression tests for historical-verdict unanimity versus a new request,
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

- [x] <a id="pw-031"></a>**PW-031** Extend the single triage verdict for WhatsApp, Teams, Slack, and similar
  messaging connectors with `relationship` (`new`, `continues`, `answers`, or
  `uncertain`), `related_message_ids`, and optional `existing_task_id`. Related
  messages need not already belong to a task. Keep intent/kind classification and
  relationship judgment in the same call, replacing a separate potentially
  conflicting chat-association classifier.
- [x] <a id="pw-032"></a>**PW-032** Restrict automatic relationship candidates to the same chat/conversation
  and same local calendar date as the incoming message's timestamp. Use message
  dates, not processing dates, for delayed sync/backfill. Do not auto-attach to an
  older ask/task by bypassing the date restriction via a task ID or room match.
- [x] <a id="pw-033"></a>**PW-033** Validate returned message/task IDs against the eligible candidate context.
  `uncertain` must not cause an automatic join. Prior-day messages cannot receive
  `continues`/`answers` links through this automatic grouping path.
- [x] <a id="pw-034"></a>**PW-034** Keep this date restriction chat-only: email chains and structural identities
  of GitHub, Monday, Jira, and similar items are not reset at midnight. This rule
  controls chat grouping, not deletion of historical messages or forced creation
  of a task for every new informational message.
- [ ] <a id="pw-035"></a>**PW-035** Add tests for same-day continuations, answers before a task exists, multiple
  asks in one room, uncertain matches, invalid/cross-room IDs, yesterday/two-week-old
  candidates, midnight and timezone boundaries, delayed sync spanning dates, and
  unchanged cross-day email/tracker item association.

## Explicit triage errors and retry

Owner-approved requirement: failed triage is an error, not FYI/filed, and must have
a visible retry button. Pending implementation only.

- [x] <a id="pw-036"></a>**PW-036** Store failed triage as a distinct message `Status='error'`, including model
  call failures, unusable/degraded verdicts, and exceptions caught by the queue
  drain. Audit existing-task follow-up failures too; do not silently treat them
  as successfully classified work. Preserve message content, existing task links,
  and diagnostic route records.
- [x] <a id="pw-037"></a>**PW-037** Show a clear "Triage failed" state with a useful failure reason and a
  "Retry triage" button on the affected timeline item/message detail. Keep failed
  items discoverable; do not present them as successfully processed FYI.
- [x] <a id="pw-038"></a>**PW-038** Adapt the existing retriage endpoint and `claim_retriage()` to the error
  state, including linked messages. Retry the same message with refreshed context
  and attachments, atomically claiming error -> triaging. Prevent repeated clicks
  or concurrent requests from creating duplicate tasks, drafts, or agent starts.
- [x] <a id="pw-039"></a>**PW-039** On successful retry, apply the new verdict and clear the error indication;
  on another failure, return to error with the updated reason and retry available.
- [x] <a id="pw-040"></a>**PW-040** Define a safe upgrade for identifiable historical triage-failure records
  currently stored as filed. Do not bulk-convert genuine FYI or reset historical
  read state. Handle missing AI configuration explicitly rather than presenting it
  as a successful FYI evaluation.
- [ ] <a id="pw-041"></a>**PW-041** Test model exceptions, malformed verdicts, drain failures, linked-message
  failures, visible retry controls, concurrent/double retry, repeated failure,
  successful recovery, retained attachments/context, and unaffected genuine FYI.

## Reply-needed items always get drafts

Owner-approved behavior: always generate a draft for `reply_only`. Sending
capability controls sending, not whether the question is actionable or drafted.
Pending implementation only.

- [x] <a id="pw-042"></a>**PW-042** Remove the `reply_only` early filing path when `can_reply()` is false.
  Retain reply-needed work and create/reuse its pending review regardless of
  whether the connector supports sending or outgoing replies are enabled.
- [x] <a id="pw-043"></a>**PW-043** Always request draft generation for `reply_only`; do not gate this path on
  `auto_draft_enabled`. Reconcile the setting/help text for this scope. Apply the
  same behavior to fresh questions attached to existing tasks, reusing that task
  without creating duplicate pending reviews for the same message.
- [x] <a id="pw-044"></a>**PW-044** When sending is unavailable, omit the send/approve-and-send button and
  display the concrete reason beside the draft (for example, replies disabled,
  read-only connector, or missing send permission). Keep the draft readable and
  editable for manual use. Apply consistently across Review, task, and assistant
  draft surfaces; availability must reflect current capability/configuration.
- [x] <a id="pw-045"></a>**PW-045** Preserve server-side send checks; hiding a UI button is not authorization.
  Always drafting must not enable outgoing replies or automatically send anything.
- [x] <a id="pw-046"></a>**PW-046** Make draft-generation failures or missing AI configuration visible with a
  retry action; keep the item reply-needed rather than treating it as FYI or
  falsely claiming a draft exists.
- [ ] <a id="pw-047"></a>**PW-047** Test sending-disabled/read-only/missing-permission cases, enabled sending,
  auto-draft setting previously off, existing-task follow-ups, retry/deduplication,
  and capability changes. Verify a draft is attempted, blocked sends remain
  blocked, and all relevant UI surfaces hide sending with a clear reason.

## Mandatory freshness before surfacing or acting

Owner-approved requirement: record which messages each evaluation/draft used.
Before the assistant surfaces or acts on an item, refresh its source context;
new activity requires fresh triage before choosing the next action. This is a
pending change, not a guarantee provided by the current implementation.

- [ ] <a id="pw-048"></a>**PW-048** Capture the exact input message IDs/context revision at task evaluation
  and draft generation. In `draft_for_review()`, do not label the generated draft
  with a "latest" message queried after the model finishes: a message arriving
  during generation was not necessarily in its input. Save the version actually
  read and mark stale if context changes during the call.
- [ ] <a id="pw-049"></a>**PW-049** Apply a shared source-freshness check before assistant surfacing, discussion,
  draft generation, approval/send, and agent dispatch. Cover email connectors as
  well as chats; `_refresh_chat_context()` currently skips email. Use incremental
  source retrieval plus the approved thread-history merge, not repeated downloads
  of the entire chain.
- [ ] <a id="pw-050"></a>**PW-050** Select an item first, then validate its freshness, including automatic
  Next/Walk without an explicit key and every item in an FYI batch. Rebuilding the
  pipeline from the database alone is not a source refresh. Reconcile selection
  after fresh triage so Current/Next and the assistant refer to the same item.
- [ ] <a id="pw-051"></a>**PW-051** On newly relevant inbound or owner-sent activity, reevaluate the updated
  context and supersede stale drafts/verdicts. Route according to the fresh result:
  FYI, reply-needed, or work-needed. Do not blindly redraft or start another agent;
  respect chat same-day grouping and reuse existing tasks/sessions as appropriate.
- [ ] <a id="pw-052"></a>**PW-052** When new messages are detected on the item being discussed/surfaced, notify
  the owner as retriage starts, before waiting for its result: "New messages came
  in on this conversation. I'm sending it through triage again before we continue."
  Keep the item visibly pending reevaluation; do not present its stale draft or
  verdict as current. Emit this notice once per newly detected context revision,
  not repeatedly on every poll/render, and only claim retriage started when it did.
  Follow up with the fresh result, or a visible error/retry if evaluation fails.
- [ ] <a id="pw-053"></a>**PW-053** Tell the owner when new activity changes the item being discussed. If the
  owner already answered externally, suppress the obsolete reply and explain
  that it was answered; fresh triage must still consider any subsequent new ask.
- [ ] <a id="pw-054"></a>**PW-054** Use the assembled substantive chain for drafting as well as triage; remove
  the silent last-six-message/4000-character-per-message draft-context boundary.
  Reuse cleaned, deduplicated history and disclose any unavoidable context limits.
- [ ] <a id="pw-055"></a>**PW-055** Recheck the evaluated version before committing an action. Require renewed
  approval for a changed draft; never send obsolete wording or launch duplicate
  work because sync and user action raced. If source refresh fails, expose that
  failure rather than claim the context is current or proceed with stale actions.
- [ ] <a id="pw-056"></a>**PW-056** Add regression tests for email/chat refresh, Next without a key, FYI batches,
  new activity before surfacing or during model generation, external owner replies,
  subsequent asks, refresh failures, unchanged-context no-op, concurrent sync/action,
  stale approval, correct draft version markers, and no duplicate task/agent work.
- [ ] <a id="pw-057"></a>**PW-057** Test that the new-message/retriage notice arrives before the triage result,
  is not duplicated on polling/rerender, and does not claim successful reevaluation
  when the run fails.

## Separate triage learning from reply-writing preferences

Owner-approved requirement: general LEARNED.md injection belongs to triage, not
reply generation. This records a pending change; no document content is migrated
or removed during the walkthrough.

- [ ] <a id="pw-058"></a>**PW-058** Remove general `LEARNED.md` prompt injection from reply drafting and
  redrafting paths, including task-linked and message-only drafts. Keep relevant
  learned preferences available to triage, subject to the fresh-evaluation rules
  above; past judgments must not force a new message's verdict.
- [ ] <a id="pw-059"></a>**PW-059** Build replies using STYLE.md for voice, phrasing, greetings, and signatures;
  SOUL.md for identity/responsibilities; and the refreshed conversation, verified
  work result, and relevant factual context for what the reply says.
- [ ] <a id="pw-060"></a>**PW-060** Restrict separately retrieved standing memory notes to explicit,
  reply-relevant writing instructions. Do not reintroduce operational triage
  judgments (ignore, not my responsibility, task classification/routing) through
  another memory block after removing LEARNED.md.
- [ ] <a id="pw-061"></a>**PW-061** Route explicit writing-style feedback to STYLE.md rather than general
  triage learning. Keep scope clear and preserve existing document/history data;
  do not blindly migrate mixed historical notes into the style document.
- [ ] <a id="pw-062"></a>**PW-062** Add model-payload tests for initial drafts, redrafts, and message-only
  drafts: style/signature and verified context remain present; general learned
  triage judgments are absent. Test that writing feedback updates style while
  triage feedback remains available to triage without changing reply voice.

## Email reply recipients and signatures

Owner-approved during the resumed walkthrough on 2026-09-05: offer Reply all and
Reply to, default to Reply all, and apply the owner's email signature.

- [ ] <a id="pw-063"></a>**PW-063** Default email drafts to Reply all; offer Reply to (sender/reply address)
  and editable To/CC. Resolve the original Reply-To when present, preserve relevant
  original To/CC participants for Reply all, exclude the sending account's own
  addresses, deduplicate recipients, and never infer or expose hidden BCCs.
- [ ] <a id="pw-064"></a>**PW-064** Persist and display the selected recipient envelope with the draft so
  approval sends exactly the recipients the owner reviewed. Keep behavior
  consistent across email connectors and task/Review/assistant draft surfaces.
- [ ] <a id="pw-065"></a>**PW-065** Apply the appropriate owner's email signature once in the draft, visible
  before approval, including manual drafts and redrafts. Current automatic drafts
  merely instruct the model to use STYLE.md's signature (SOUL.md sign-off fallback);
  send functions do not independently apply one. Do not rely solely on model
  compliance, invent missing signature details, duplicate signatures, or silently
  change approved text at send time. Preserve intentional owner edits.
- [ ] <a id="pw-066"></a>**PW-066** Test default Reply all, Reply to selection, Reply-To headers, editable To/CC,
  owner exclusion, deduplication, exact approved envelope, and signature presence
  exactly once on initial drafts/redrafts/manual drafts without adding signatures
  to chat messages. Keep originals intact when cleaning triage context.

## Default task kind

- [x] <a id="pw-067"></a>**PW-067** Owner-approved on 2026-09-05: a task with missing/uncertain agent kind
  defaults to `general` (a general assistant-style agent), not coding. Align
  intake fallbacks and classifier instructions, including "Cannot tell? Say coding",
  with this default. Preserve explicit coding and owner-personal-task decisions.
  Automatic startup follows the owner-approved settings contract below.
- [x] <a id="pw-068"></a>**PW-068** Test missing/invalid kind and uncertain classification across the supported
  task-creation paths: default general, no unintended coding-session launch.

## Automatic agent startup for both work kinds

Owner-approved on 2026-09-05: both coding and general-agent tasks start their
respective worker automatically by default; the owner can change this in Settings.
Pending implementation, not authorization to launch sessions during this review.

- [ ] <a id="pw-069"></a>**PW-069** Extend automatic dispatch to general agents, using a per-task worker
  session rather than having the routing assistant perform the work inline. Route
  explicit coding work to coding sessions and general/default work to general
  sessions. Personal `kind=task` items remain owner to-dos, without auto-start.
- [ ] <a id="pw-070"></a>**PW-070** Expose clear auto-start controls for coding and general agents in Settings,
  default enabled for each. Preserve existing explicit opt-outs during upgrade;
  reconcile the existing `coder_auto_enabled` setting and related UI/help text.
  When disabled, keep work visible for manual dispatch.
- [ ] <a id="pw-071"></a>**PW-071** Apply appropriate shared safety/permission checks to both worker kinds,
  preserving connector auto-dispatch restrictions and sender authorization gates.
  Respect repo-choice requirements for coding and available worker configuration
  for general. A blocked launch remains visible with a concrete reason.
- [ ] <a id="pw-072"></a>**PW-072** Dispatch once per eligible work item, not per refresh or historical chain
  message. Reuse existing live sessions when handling fresh context; auto-start
  is not blanket authority for external sends or other restricted actions.
- [ ] <a id="pw-073"></a>**PW-073** Test both default auto-start paths, each settings opt-out, manual fallback,
  personal to-dos, missing worker/repo configuration, safety holds, concurrent
  ingest/retriage, and truthful pipeline state when launch fails or is blocked.

## Triage-generated task summary and checkable list

Owner marks this important: triage should produce a concise task summary and
GitHub-style Markdown checklist describing the actual requested work.

- [x] <a id="pw-074"></a>**PW-074** Extend the same triage verdict with a meaningful task title/summary and
  actionable checklist for `intent=task`; derive these from the cleaned, assembled
  message context rather than taking the first 1000 body characters. Capture each
  distinct requested outcome without inventing requirements or claiming work done.
- [x] <a id="pw-075"></a>**PW-075** Persist the checklist with the task and render interactive, saved checkboxes
  using GitHub Markdown task-list syntax (`- [ ]` / `- [x]`). Keep source messages
  separately accessible. Share the same task checklist across task/assistant views
  and include it in the assigned worker's context.
- [x] <a id="pw-076"></a>**PW-076** Give checklist items stable identity so edits, progress, and fresh-triage
  additions do not duplicate items or reset checked boxes. Preserve owner edits;
  surface substantive changes from new messages rather than overwriting silently.
- [x] <a id="pw-077"></a>**PW-077** Keep checklist progress separate from agent/session state and task completion;
  rendering or generating a checklist must not mark work done. Completion rules
  remain subject to the later lifecycle walkthrough.
- [ ] <a id="pw-078"></a>**PW-078** Add tests for multi-request chains, coding/general/personal tasks, meaningful
  summaries, interactive checkbox persistence, worker context, new-message merges,
  retained edits/progress, and no duplicate items or invented completed work.

## Configurable sender trust for automatic agent startup

Owner-approved on 2026-09-05: expose the auto-start sender rules in Settings.
Prior incoming mail is not trust evidence; prior sent mail is accepted evidence.
Pending implementation only.

- [ ] <a id="pw-079"></a>**PW-079** Remove `store.known_sender()` / "has written before" as an authorization
  path in the auto-start sender gate. Multiple incoming messages, historical
  imports, and retries must not turn an untrusted sender into an authorized one.
  Keep unrelated sender-history uses distinct from auto-dispatch authorization.
- [ ] <a id="pw-080"></a>**PW-080** Retain verified Sent Items evidence that the receiving mailbox previously
  wrote to the exact sender address as an accepted trust rule, configurable in
  Settings. Display the matched reason; a lookup failure is not proof of trust
  and should leave the task available for manual dispatch with an explanation.
- [ ] <a id="pw-081"></a>**PW-081** Expose same-domain trust and non-email-channel trust behavior explicitly in
  Settings rather than hiding these assumptions in code. Define scope and defaults
  visibly; prior incoming mail must not reappear as an enabled trust option.
- [ ] <a id="pw-082"></a>**PW-082** Apply the configured sender-trust contract consistently to coding and
  general auto-start, alongside their startup toggles and source restrictions.
  A hold affects unattended launch, not message intake, triage, or task visibility.
- [ ] <a id="pw-083"></a>**PW-083** Add tests for prior incoming-only history remaining untrusted, verified sent
  history allowing startup when enabled, disabled trust rules, same-domain and
  non-email settings, failed lookups, mailbox/address scoping, and both worker kinds.

## Agent capacity counting

- [ ] <a id="pw-084"></a>**PW-084** Owner-approved: count all live coding/general agent sessions toward the
  shared capacity limit, including sessions idle at a prompt or stopped waiting
  for user approval/input. Waiting for approval does not free a slot. Distinguish
  these live sessions from terminated sessions; do not implement an actively-
  computing-only limit. Test both worker kinds and approval-waiting transitions.

## Dispatch queue startup failure

- [ ] <a id="pw-085"></a>**PW-085** Owner-approved: allow at most two automatic retries after the initial
  startup attempt (three attempts total) for transient startup failures, with
  bounded backoff. Persist attempt count, last error, and next-attempt time so
  restarts or repeated queue checks cannot reset the budget or bypass backoff.
- [ ] <a id="pw-086"></a>**PW-086** Configuration, missing repository/worker, and permission failures should
  immediately become "Agent could not start - needs you" rather than consume
  blind automatic retries. Capacity waits and dependency waits are not failures
  and must not consume the retry budget.
- [ ] <a id="pw-087"></a>**PW-087** After retry exhaustion, retain the task and dispatch error visibly but stop
  automatic attempts. Offer "Retry" (an explicit new bounded attempt cycle) and
  "Cancel queued start" (remove pending dispatch without deleting/completing the
  task). Make the failure available to the owner's attention pipeline.
- [ ] <a id="pw-088"></a>**PW-088** Schedule due retries without depending solely on an unrelated session ending;
  use the shared capacity limits and dispatch guards, recheck live sessions before
  launch, and let other eligible tasks proceed. Distinguish an actual launch failure
  from bookkeeping failure after a session already started; never duplicate it.
- [ ] <a id="pw-089"></a>**PW-089** Test transient recovery, exactly three failed attempts, persisted backoff
  across restart, permanent errors, manual retry/cancel, waiting without consuming
  attempts, partial-start reconciliation, and other queued tasks continuing.

- [x] <a id="pw-090"></a>**PW-090** Move `clear_dispatch()` inside the startup `try`, after `start_on_task()`
  returns successfully, so a failed start preserves the queue entry. Implemented
  in `taskuary/blackboard.py` on 2026-09-05 before the owner clarified to record it
  in this TODO. No app restart performed.
- [x] <a id="pw-091"></a>**PW-091** Add a regression test proving a failed start remains queued and a later
  successful start removes the entry only after startup. Verification:
  `python -m pytest tests/test_blackboard.py tests/test_rank.py -q` — 20 passed.

## Project and repository selection in unified triage

Owner-approved: use the SOUL project/people map and structured learned project
relationships as evidence in the same AI triage evaluation that classifies work.
Pending implementation only.

- [x] <a id="pw-092"></a>**PW-092** Supply relevant known projects, repositories, and people associations with
  the cleaned request/context. Extend the verdict with project/repository selection,
  `needs_repo_choice`, and a concrete reason; persist the decision so startup uses
  it instead of independently guessing from word overlap.
- [x] <a id="pw-093"></a>**PW-093** An explicit owner-selected task repository wins. Treat sender/project
  relationships as supporting evidence, not proof that every message from that
  person concerns that project. Preserve authoritative source repository identity
  for repository-scoped items such as GitHub issues/PRs.
- [x] <a id="pw-094"></a>**PW-094** Validate returned project/repository IDs against the supplied known
  candidates and their associations. Ambiguous evidence or multiple plausible
  repositories must prompt the owner to choose; do not force a match merely
  because one checkout happens to be configured.
- [x] <a id="pw-095"></a>**PW-095** Before coding startup, validate/resolve the selected local checkout. Missing
  or invalid paths require a visible repository/path choice, not silent fallback
  to an unrelated working directory. General-agent work does not become coding
  merely because a project has a repository.
- [ ] <a id="pw-096"></a>**PW-096** Test explicit override precedence, mapped person with a matching request,
  same person asking about unrelated work, multi-repo projects, unknown model
  output IDs, source-repository identity, absent checkout, and persisted selection
  reaching startup without a contradictory second routing decision.

## Repository confirmation when manually sending to coding

Owner-approved: when correcting triage or manually sending an item to a coding
agent, offer repository selection before launch in every entry point, not only
after startup fails. Pending implementation only.

- [ ] <a id="pw-097"></a>**PW-097** Use a consistent pre-launch repository picker on the task page, timeline
  task actions, and assistant chat (including conversational dispatch). Preselect
  the existing explicit selection or triage suggestion, show why it is suggested,
  and let the owner confirm or change it before any coding session starts.
- [ ] <a id="pw-098"></a>**PW-098** Cover personal-task/general-to-coding corrections and manual coding dispatch;
  a confident guess or single configured repository must not bypass this manual
  confirmation step. Keep automatic dispatch governed by the separately approved
  triage-selection and uncertainty rules.
- [ ] <a id="pw-099"></a>**PW-099** Preserve the selected item, agent/model, and instructions while choosing;
  persist the confirmed repository on the task and validate its local path before
  launch. Cancelling the picker must not start a session. Reconcile any existing
  live session explicitly rather than silently launching a duplicate or replacing it.
- [ ] <a id="pw-100"></a>**PW-100** Add tests for all three UI entry points, conversational coding requests,
  incorrect-triage corrections, preselection/override, missing paths, cancel,
  duplicate clicks, and exact confirmed repository reaching startup. Inspect the
  conversational UX in the later assistant walkthrough before implementing it.

## All and Unread: one item set, different filter and order

Owner-approved on 2026-09-05: All is chronological; Unread is the same item set
filtered by shared unread state, ordered by status/priority. Unread must not be a
separately curated pipeline that loses arrivals visible in All. Pending change.

Section 1.1 foundation is CI-verified at `85c2e1b` (source `81981b8`, all ten jobs): durable
identity/aliases, full-content and view fingerprints, and versioned historical-read
evidence. All/Unread/assistant adoption and the final display-does-not-read cutover
are still pending, so PW-101 and PW-104 remain unchecked. See section evidence for
the cumulative tests, independent review and remote checkpoint status.

Section 1.3 adds internal uncapped inventory snapshots and tested All/priority
pagination mechanics (`b1ea30d`, `d696114`). It reports missing coverage and unknown
policy states explicitly; it does not switch All, Unread or assistant consumers.
Timezone, calendar and live attention adapters plus final read-policy adoption
remain pending. Related PW-101/102/103/106/109/110/111/112 remain unchecked until
their rendered/runtime requirements pass; see Section 1.3 implementation evidence.

Section 1.4 adds complete display revisions and same-identity Current/source/draft
refresh, including cleared fields and rejection of delayed older content. Its real
browser test preserves Current, durable history and unsaved owner edits during
external updates. PW-106 remains partial until shared selection and canonical
consumer adoption; see Section 1.4 evidence for final gates and delivery status.

Section 1.5 binds the displayed legacy Next and exact FYI members to the request,
rejects stale modern navigation before effects, and keeps tagged passive updates
from choosing Current or its interactive controls. Walk validation is cancelled
when its conversation changes. Legacy eligibility, canonical consumer adoption,
durable read/current cutover and historical untagged watcher provenance remain
pending; related requirements are still partial. See Section 1.5 evidence.

Section 1.6 integrates canonical All roots, source-member selection, compact frozen
pagination beyond 500 items, explicit coverage errors, and full detail via read-only
GETs for messages and standalone tasks/ideas/reviews. Its reconciliation and detail lifecycle
preserve legacy reads, documents and exact draft targets. Local gates and independent
review passed at `d75d45e`; delivery CI is pending in Section 1.6 evidence. Shared Unread/read/filter/priority and
Current/Next adoption remain pending, so PW-101/102/103/106/109 remain unchecked.

- [ ] <a id="pw-101"></a>**PW-101** Use one canonical item/identity/context representation for All, Unread,
  and assistant selection, including messages, reports, assistant posts/ideas,
  and agent work/attention items. Preserve legitimate task/thread grouping and
  prevent duplicate wrappers, but apply the same representation to both views.
- [ ] <a id="pw-102"></a>**PW-102** All sorts by time (newest first). Unread selects the unread subset and
  promotes by status/priority, with deterministic chronological tie-breaking.
  Sorting is derived from the single triage result plus current task/agent state,
  not a second AI classification. Exact status bands and read transitions remain
  subjects for the next walkthrough steps.
- [ ] <a id="pw-103"></a>**PW-103** Remove Unread-only age windows, category exclusions, and silent caps that
  hide otherwise unread All items. Paginate the shared dataset without treating
  unloaded rows as absent; any common source/history filters must apply equally.
  Catch-up arrivals must not disappear because provider SentAt is old. Do not
  confuse the approved same-day chat association rule with unread eligibility.
- [ ] <a id="pw-104"></a>**PW-104** Do not treat an FYI classification or merely surfacing an item as permission
  to silently settle it without an agreed read/handled action. Audit existing
  `surfaced`, ignored, closed-task, and age-based handling against explicit read
  semantics before implementing; preserve genuine historical read/dismissed state
  and existing deliberate skip/standing-policy choices. No blanket mark-read or
  mark-unread migration to make the lists look equal.
- [ ] <a id="pw-105"></a>**PW-105** Show newly persisted arrivals in both views immediately when eligible,
  including a pending-triage state. Do not wait for the whole sync/triage batch to
  finish before Unread updates. Keep unread active-agent status visible under the
  earlier contract, without making working items actionable in chat until needed.
- [ ] <a id="pw-106"></a>**PW-106** Replace the incomplete pipeline revision/update comparison: changes to
  relevant message/context IDs, previews, chain counts, drafts, status, read state,
  and priority must reach the UI even when key/lane/settling did not change.
  Reconcile counts, Current/Next, and assistant context from the shared revision.
- [ ] <a id="pw-107"></a>**PW-107** Superseding the earlier separate-filter proposal: remove the Needs me tab.
  The owner approved exactly two views: All (chronological, task/detail view only,
  no chat) and Unread (read-state filtered, importance/status sorted). Action-needed
  flags remain useful for promotion, not a third view. Apply live state before
  selection so an approval-waiting agent cannot be lost by an earlier SQL filter.
  Section 1.2 is CI-verified at `2557c94`: two-view controls and All detail-only behavior, with
  frontend and rendered desktop/narrow-screen coverage. This remains unchecked:
  live-state-before-selection and canonical read-filter adoption require the later
  Phase 1 inventory cutover. See the implementation evidence for delivery gates.
- [ ] <a id="pw-108"></a>**PW-108** Apply all common source/category/mute exclusions identically to All and
  Unread; remove funnel-only exclusions. Being classified as not-a-task/FYI is not
  itself a read receipt. An ignored-policy item visible in All must not be silently
  removed from Unread solely by a second funnel filter; resolve policy scope and
  read state consistently in the shared representation.
- [ ] <a id="pw-109"></a>**PW-109** Test All/Unread item parity (after read filtering), time versus status order,
  initial sync and long catch-up, FYI/assistant/report arrivals, pending triage,
  live working/waiting transitions, grouping, pagination beyond old caps, genuine
  historical read-state preservation, and updates with unchanged keys/lanes.

## Assistant selection: top eligible Unread item

Execution clarification approved 2026-09-06: use five bands: urgent requests/current
or starting-within-15-minutes calendar events; agent input/approval; other actionable
tasks and finished results; FYIs; working agents. Within each band use triage priority,
then oldest activity first. This resolves the historical middle-band/tie-break review
notes below; implementation remains pending its Phase 1 tests and CI evidence.

Ordering clarification approved during the detailed walkthrough:
- [ ] <a id="pw-110"></a>**PW-110** Put genuinely immediate/time-critical items first (a current calendar
  event or a request needed now); agent input/approval waits rank second behind
  those. A calendar item's mere existence does not make it immediately urgent.
- [ ] <a id="pw-111"></a>**PW-111** Put tasks actively worked by either coding or general agents in band 5,
  with a visible agent-working emoji/status. They remain visible in Unread but
  are not selected for owner action; waiting for owner input/approval is not
  Working and must move to band 2. Preserve Current during background reordering.
- [ ] <a id="pw-112"></a>**PW-112** Test coding/general working placement, transitions to owner-waiting, and
  time-critical precedence. Remaining band details/tie-breakers are still under review.

Owner-approved: the assistant picks the top eligible item in the same ordered
Unread list the owner sees. No separate ranking or already-shown eligibility
filter. Pending implementation.

- [ ] <a id="pw-113"></a>**PW-113** Preserve the existing funnel UI during this selection refactor: keep its
  layout, Current/Next indicators and navigation controls, and status/importance
  promotions. Remove duplicate selection logic, not these user-facing features.
  This does not undo the separately approved removal of the Needs me tab.
  Regression-test Current/Next visibility, navigation, and promoted ordering.
- [ ] <a id="pw-114"></a>**PW-114** Remove assistant-local filtering, ranking, and eligibility recalculation:
  consume the canonical Unread order and shared actionability state directly.
  The working/deferred/pending-triage rules below belong in that shared state,
  not another assistant-side funnel. Preserve shared read state and promotion.
- [ ] <a id="pw-115"></a>**PW-115** Clicking "Walk me through my tasks" resumes a valid Current item; only
  when there is no valid Current does it select the top eligible Unread item.
  Remove the unconditional Current-key exclusion from this start/resume path.
  Next is the owner's explicit request to move on, not a side effect of starting
  or resuming the walkthrough. Test repeat Walk clicks preserve Current.
- [ ] <a id="pw-116"></a>**PW-116** Replace next_item()'s surfaced-based exclusion and preference for unshown
  items with selection from the canonical ordered Unread dataset. Being shown in
  chat does not make an item read, handled, or ineligible for subsequent selection.
- [ ] <a id="pw-117"></a>**PW-117** Skip working agents, deferred items, and pending-triage items for automatic
  chat selection. Working agents remain visible in Unread and become eligible
  when input/approval or a finished result requires attention.
- [ ] <a id="pw-118"></a>**PW-118** Track Current explicitly: once selected, keep that item as the conversation
  subject until the owner acts or moves on. Derive Next from the same ordered
  eligible items and keep the visible Current/Next labels and chat context aligned.
  New arrivals must not silently replace the item being discussed. Moving on must
  not implicitly mark an item read; exact action/read transitions remain to review.
- [ ] <a id="pw-119"></a>**PW-119** Preserve the approved four-at-a-time FYI presentation for automatic walks;
  batching must follow shared ordering rather than introducing another ranking.
- [ ] <a id="pw-120"></a>**PW-120** Test displayed Unread versus assistant selection, already-shown but unread
  items, working/pending/deferred exclusions, Current stability during updates,
  Next labels, and absence of false all-done claims when eligible items remain.

## Assistant actions: AI interpretation, then explicit confirmation

Owner-approved: supersedes the earlier assistant per-message action menus and
immediate execution of typed commands. Requests are conversational; execution is
through a concrete confirmation box. Pending implementation, not a runtime change.

- [ ] <a id="pw-121"></a>**PW-121** Remove decide_words() and other phrase/regex-based intent dispatch from
  assistant messages. Use AI with Current, conversation, and verified task/source
  context to interpret the request. Ask for clarification when intent, target,
  scope, agent type, or repository is uncertain; do not guess a consequential action.
- [ ] <a id="pw-122"></a>**PW-122** Give every message the same conversational action interface. Replace the
  assistant's sprawling per-message action menus with bottom prompt examples such
  as Next, Done, Create task, Create agent, and Reply. Clicking a suggestion submits
  text through the same AI path as typing; it must not directly execute an action.
  Preserve the funnel layout, Current/Next indicators, and promotions approved above.
- [ ] <a id="pw-123"></a>**PW-123** Before executing a requested action (except draft preparation and Next navigation below), show a confirmation box describing
  exactly what will happen: action, target, and relevant parameters (for example,
  task, agent kind, repository, and instructions; or recipient and draft for a send).
  Offer a specifically labelled execution button and Cancel. Allow conversational
  corrections before confirmation; edits must update the proposal being confirmed.
- [ ] <a id="pw-124"></a>**PW-124** Except for the explicitly approved draft-preparation and Next-navigation exceptions below, no
  requested action executes merely because the AI interpreted it or the
  user submitted text. The confirmation button submits the structured action,
  not a phrase sent back through the interpreter. Explanation and clarification
  do not themselves mutate task, read, memory, or agent state.
- [ ] <a id="pw-125"></a>**PW-125** Use one validated action execution path shared with other app entry points.
  Code retains schemas, permissions, target/freshness checks, and safe execution;
  COUNSEL governs interpretation and conversation. Bind confirmation to the exact
  proposal and context revision, reject stale/changed proposals for review, and
  prevent duplicate execution from repeated clicks. Report actual success/error,
  never success before execution. Failed/cancelled actions must not settle Current
  or advance the walk.
- [ ] <a id="pw-126"></a>**PW-126** Preserve draft review/editing and explicit send approval within this model.
  Owner-approved exception: an explicit reply/draft request immediately generates
  the editable draft, without a preliminary Draft reply confirmation. Clarify an
  ambiguous target or instruction first. This uses the reply writer, not a worker
  agent dispatch, and sends nothing. Require explicit approval to send; agent
  dispatch still requires its confirmation. Draft preparation must not mark the
  item handled or advance Current. This exception does not authorize other actions.
  Selecting an FYI to act on targets only that entry, not its whole batch. The FYI
  actions described below are capabilities through this conversational proposal
  flow, not a requirement to retain separate immediate-action menus.
- [ ] <a id="pw-127"></a>**PW-127** Test typed/suggested-prompt parity, no phrase-dispatch bypass, clarification,
  exact target/parameter display, correction/cancel, no execution before clicking
  for confirmation-required actions, immediate drafting without send or dispatch,
  stale confirmation, duplicate clicks, failed execution, and per-FYI isolation.

- [ ] <a id="pw-128"></a>**PW-128** Owner-approved navigation exception: an unambiguous request to move Next
  immediately selects the next eligible shared-Unread item without confirmation,
  marking read, closing a task, or writing a deferral/memory. Interpret intent
  through AI, not keyword matching; bottom suggestions submit ordinary text.
  Questions such as "is the agent done?" must not trigger completion. Test Next
  navigation without mutation and context-sensitive questions versus commands.

## Action-driven triage correction memory and task discussion history

Owner-approved: successful action handlers automatically record owner changes
that differ from triage. The assistant does not independently write correction
memory from conversational interpretation. Pending implementation/verification.

- [x] <a id="pw-129"></a>**PW-129** After a confirmed owner action succeeds, compare its outcome with the
  relevant triage verdict and record any correction as learning evidence without
  a second memory confirmation. Use the same handler behavior across assistant
  confirmations, Tasks, and All timeline detail; do not depend on the UI entry point.
- [x] <a id="pw-130"></a>**PW-130** Record source/message or grouped-item identity, triage verdict/revision,
  relevant context, the owner's change, and the successful action identity.
  Cover FYI -> task, general -> coding, and reply-needed -> dismissed as unnecessary.
  Deferring until tomorrow or merely discussing an item is not by itself a triage
  correction. Cancelled/failed actions write no correction evidence; retries must
  not duplicate it. Make successful actions' correction recording recoverable
  if persistence fails, without repeating the underlying action.
- [x] <a id="pw-131"></a>**PW-131** Preserve the distinction between correction evidence, explicit learned
  preferences, and deterministic exclusions. A correction informs fresh triage;
  it must not force future verdicts or silently create a permanent sender rule.
  Explicit preference/rule requests use their own confirmed action handlers.
- [ ] <a id="pw-132"></a>**PW-132** Record evidence against source items even when an FYI has no task. Persist
  task-related assistant/user discussion, proposals, and action outcomes rather
  than relying on browser-only receipts. Keep history separate from learned memory:
  saving a conversation does not make every turn a standing preference.
- [x] <a id="pw-133"></a>**PW-133** When an FYI later becomes a task, link its earlier relevant discussion and
  correction history to that task. Show it in Assistant discussion/history in
  task/All detail. Preserve per-item attribution for FYI batches; do not copy
  unrelated sibling discussion onto every task or lose history before task creation.
- [ ] <a id="pw-134"></a>**PW-134** Test successful corrections from every entry point, unchanged verdicts,
  one-time deferrals, failed/cancelled actions, duplicate/retried events, evidence
  recovery, taskless FYIs later promoted to tasks, per-item discussion attribution,
  durable action receipts, and no automatic promotion of evidence into exclusions.

## Successful agent handoff: acknowledge and move on

Owner-approved walkthrough exception: after the owner confirms dispatch and the
worker actually starts, acknowledge the named agent/task, say "Moving on", and
present the next eligible shared-Unread item. This is a consequence of confirmed
handoff, not permission for background events to advance the conversation.

- [ ] <a id="pw-135"></a>**PW-135** Keep the delegated task visible in Unread as Working; do not settle it as
  done/read merely to advance chat. Failed starts, missing repository choices,
  and cancelled confirmations must keep the current item in place.
- [ ] <a id="pw-136"></a>**PW-136** Test successful handoff advances once, retains the working task in Unread,
  and failure/cancellation does not advance. Agent workspace inline presentation
  is still under review; do not infer a new display decision from this exception.

## Agent questions answered through the assistant

Owner-approved: keep worker UI in the task workspace, opened on request (coding
CLI or general-agent chat); do not automatically embed it in the routing chat.
The assistant should relay an agent's question and the owner's answer seamlessly.

- [ ] <a id="pw-137"></a>**PW-137** Receive structured input/approval-needed events from worker integrations,
  carrying task ID, run/session ID, stable request ID, exact question, and any
  choices. Show the named agent's question when the owner opens its attention
  item; unrelated arrivals notify through the bottom strip without stealing Current.
- [ ] <a id="pw-138"></a>**PW-138** Let the owner answer conversationally in the assistant. Clarify ambiguous
  targets/answers, then use the approved confirmation box to show the exact answer
  and destination before Send to agent. Keep ordinary input separate from tool
  permission/approval requests; approval must use the worker's supported mechanism.
- [ ] <a id="pw-139"></a>**PW-139** Bind delivery to the specific outstanding request and run, never merely the
  task's newest session. Reject resolved/stale requests and changed runs, prevent
  duplicate delivery, and never forward to a replacement worker silently.
- [ ] <a id="pw-140"></a>**PW-140** Use a supported reply/control path per worker integration; lifecycle hooks
  alone do not provide reliable answer delivery. Verify each integration's input
  and approval capabilities. Keep Open agent workspace as a fallback if direct
  delivery is unsupported, disconnected, or cannot be confirmed.
- [ ] <a id="pw-141"></a>**PW-141** Distinguish queued, delivered, and resumed/working states. Do not report
  "Told the agent" from HTTP success alone. Persist the question, confirmed answer,
  and delivery outcome in the task discussion; preserve recoverable pending state
  across reconnects without duplicate sends.
- [ ] <a id="pw-142"></a>**PW-142** Test general/coding question relay, multiple waiting agents, request/run
  identity, duplicate events/clicks, stale approval, disconnected workers, delivery
  failure, restart recovery, and visible confirmation of actual worker acceptance.

## Send outcomes and explicit closure when sending is unavailable

Owner-approved: distinguish confirmed sent, definitely failed, and uncertain
delivery. Missing send/write permission must not prevent explicit task closure.

- [ ] <a id="pw-143"></a>**PW-143** Check connector sending capability/permissions before offering send. Keep
  drafting and reading available; omit the send button when unsupported or not
  authorized and explain why. Do not depend solely on a failed send to discover
  known missing permissions.
- [ ] <a id="pw-144"></a>**PW-144** Confirmed send closes the task; definite failure preserves the draft and
  leaves the task open with an error and retry when sending is available. Treat
  timeouts/ambiguous provider responses as delivery unknown, not proof of NOT SENT.
  Reconcile with the provider before retrying; use supported idempotency and
  duplicate-click protection. If delivery cannot be verified, say so explicitly.
- [ ] <a id="pw-145"></a>**PW-145** When sending is unavailable, offer a separate confirmed Close without
  sending action. Warn that no reply will be sent and state the reason (such as
  missing write/send permission). Preserve the unsent draft/history, record the
  owner's explicit closure, and remove its pending actionable reply obligation.
  Never report Sent or treat this as proof of delivery. This is an explicit owner
  override, not automatic closure after a failed/blocked send.
- [ ] <a id="pw-146"></a>**PW-146** Test read-only/missing permissions, explicit close-without-send and cancel,
  confirmed success, definite failure, ambiguous timeout, provider reconciliation,
  duplicate approvals/retries, and no success-style advancement after failure.

## Successful reply closes its task

Owner-approved: once the reply is successfully sent, close the associated task.
This supersedes the proposed distinction that other unfinished TODOs would keep
the task open after replying. Pending implementation/verification.

- [ ] <a id="pw-147"></a>**PW-147** Apply successful reply -> task done consistently across assistant approval,
  task-view/Review sending, and reconciliation of a verified reply sent externally.
  Close only the task associated with that reply, not unrelated items in a batch.
- [ ] <a id="pw-148"></a>**PW-148** Drafting, editing, approving without confirmed send success, failed/blocked
  sends, and cancellation must not trigger this completion rule. Do not interpret
  an incoming message as proof that the owner replied.
- [ ] <a id="pw-149"></a>**PW-149** Refresh task, review, and canonical Unread state after confirmed send and
  closure so the old reply obligation does not remain actionable. Keep discussion
  and source history available in All. Automatic chat advancement remains a
  separate walkthrough decision; this rule does not authorize it.
- [ ] <a id="pw-150"></a>**PW-150** Test successful send closes even with unchecked task TODOs, failed sends
  leave the task open, external-reply matching, duplicate success events, and
  consistent results across send entry points.

## Assistant presentation: actionable FYI summaries and full task context

Owner-approved: COUNSEL governs the explanation; code supplies verified context,
card structure, and validated actions. Pending implementation.

- [ ] <a id="pw-151"></a>**PW-151** Present up to four FYIs together with a summary for each. Each entry is
  individually selectable and offers Make task, Send to agent, and Reply for that
  specific item. Use the shared action paths, including general/coding choice
  and repository selection when needed; never apply an individual action to the
  entire batch or mark the other FYIs read as a side effect.
- [ ] <a id="pw-152"></a>**PW-152** For a single task item, show the full message/context and the task summary
  in its card, not only a truncated preview. If triage grouped a chain, preserve
  access to the whole grouped context in that presentation rather than silently
  showing only the latest message. Include the approved task checklist summary.
- [ ] <a id="pw-153"></a>**PW-153** Generate the assistant's explanation according to COUNSEL, removing the
  normal-path hardcoded introductions and competing behavioral instructions.
  Keep card structure, action validation, and factual error handling in code.
- [ ] <a id="pw-154"></a>**PW-154** Presenting either kind of card does not mark it read or handled and does
  not automatically execute actions or advance the conversation.
- [ ] <a id="pw-155"></a>**PW-155** Test four-item FYI presentation, per-item action targeting, untouched sibling
  read state, full task/chain context, task summary/checklist display, and COUNSEL
  use in the normal presentation path.

## Chat archive and independent retention cleanup

Owner-approved: chats should eventually be automatically deleted, but retention
cleanup is independent of New chat and viewing history. Pending implementation;
retention duration is configurable in Settings, defaulting to 15 days. Cleanup
deletes expired chat archives, not task-linked history or learned state.

- [ ] <a id="pw-156"></a>**PW-156** New chat archives the current conversation, resets chat/Current, and opens
  a blank conversation awaiting owner input. It must not trigger retention
  deletion, change source/task read state, or automatically start a walkthrough.
- [ ] <a id="pw-157"></a>**PW-157** Listing/opening earlier chats is read-only and paginated. Remove the
  hardcoded CHATS_KEPT_DAYS cutoff/status mutation from concierge.chats(); do not
  hide or mark old conversations dropped as a side effect of a history request.
- [ ] <a id="pw-158"></a>**PW-158** Implement automatic retention cleanup as a separate scheduled lifecycle
  operation with a chat retention setting defaulting to 15 days, not the existing
  hardcoded 20-day cutoff.
- [ ] <a id="pw-159"></a>**PW-159** Preserve task-linked discussion, confirmed actions, agent results, and send
  outcomes for the life of the task, accessible in All/task history after the chat
  archive expires. FYI discussion linked when it becomes a task is task history
  too. Ensure retained records do not depend on a deleted archive for readability.
- [ ] <a id="pw-160"></a>**PW-160** Keep correction memory and saved rules on independent lifecycles. Chat
  deletion must not erase learning evidence, learned preferences, or exclusions.
- [ ] <a id="pw-161"></a>**PW-161** Test New chat archives without deletion or auto-walk, history reads do not
  mutate state, old retained chats remain accessible through pagination, and
  retention cleanup runs independently and only removes policy-eligible records.
  Test the 15-day default, configured overrides, and the retention cutoff boundary.
  Verify expired archive removal preserves task history (including promoted FYIs),
  agent results, send outcomes, correction evidence, and saved rules.

## Opening Assistant: restore without starting a walkthrough

Owner-approved: opening or returning to Assistant restores the existing
conversation and validated Current item; it must not initiate a walkthrough
merely because the tab was opened. Pending implementation.

- [ ] <a id="pw-162"></a>**PW-162** Persist Current explicitly and validate it against current canonical item
  state when restoring the conversation. Do not infer Current solely from the
  last historical card. Keep historical discussion readable without reviving
  handled items as current work. If Current is no longer valid, clear it without
  automatically selecting or discussing a replacement.
- [ ] <a id="pw-163"></a>**PW-163** Keep history/pipeline loading separate from initiating an assistant turn.
  Mounting, tab activation, remounting, reconnecting, or initial refresh must not
  itself call Next or start a walkthrough. Preserve the approved blank New chat
  behavior. Genuine live attention notifications remain a separate mechanism,
  whose interruption/auto-advance rules still need review.
- [ ] <a id="pw-164"></a>**PW-164** Test first visit, returning from another tab, page reload/remount, stale
  historical cards, completed Current items, and new/empty conversations. Verify
  restored history and valid Current without unsolicited turns or duplicate posts.

## Assistant background updates must not advance the conversation

Owner-approved: never move on by itself. Background updates may refresh the
current item and notify the owner, but must not switch the subject or initiate
Next. Pending implementation.

- [ ] <a id="pw-165"></a>**PW-165** Owner-approved notification placement: unsolicited updates use a single
  bottom strip, whether about Current or another item. Do not also append automatic
  chat messages/cards for the same event. This supersedes the earlier proposal
  to insert Current-item updates inline automatically; passive status/context
  refresh still occurs without changing the conversation subject.
- [ ] <a id="pw-166"></a>**PW-166** Keep the strip until Open, Later, or resolution; do not rely on a timed
  disappearing toast as the only notification. Open explicitly brings the
  relevant item/update into chat. Later acknowledges/dismisses the notification,
  not the underlying unread item or task. Neither arrival nor dismissal switches
  Current automatically. Multiple events must remain accessible without losing
  pending notifications or duplicating them across notification surfaces.
- [ ] <a id="pw-167"></a>**PW-167** Test no automatic chat insertion for Current and non-Current updates,
  strip persistence, Open/Later/resolution behavior, duplicate events, and retained
  unread state. Keep the separately approved approval-time material-change popup:
  that is an action-blocking validation dialog, not an unsolicited notification.

- [ ] <a id="pw-168"></a>**PW-168** Remove event-driven clearing/replacement of Current and scheduled surface()
  calls from AssistantView.loadPile(). A worker starting/finishing or another
  background event is not permission to advance. Keep relevant notifications
  separate from Current and offer a switch instead of silently switching.
- [ ] <a id="pw-169"></a>**PW-169** Only explicit owner navigation/actions may advance under their agreed
  behavior; do not infer an instruction to advance from polling, reconnects,
  newly merged historical cards, or model commentary. If Current becomes invalid,
  clear it without automatically discussing a replacement.
- [ ] <a id="pw-170"></a>**PW-170** Test updates on Current, unrelated urgent arrivals, delayed event delivery,
  tab activation, and reconnects: no unsolicited Next calls, subject replacement,
  or duplicate assistant turns.

## Similar coding work: inform agents, do not queue for overlap

Owner-approved: overlapping/similar work should produce a coordination briefing,
not a dependency queue. This replaces overlap-based blocking only; the approved
live-session capacity limit and startup-failure retry handling remain in effect.
Pending implementation only.

- [ ] <a id="pw-171"></a>**PW-171** Remove automatic deferral behind another task solely because of likely file
  overlap, in both immediate and ranked/queued dispatch paths. Treat any overlap
  assessment as advisory, not a launch veto. Existing overlap dependencies must
  no longer block dispatch, while retaining normal capacity checks.
- [ ] <a id="pw-172"></a>**PW-172** Before startup, give the agent current same-checkout peer task IDs, agent
  identities, task summaries, known touched files, and relevant live handoff notes.
  Clearly flag similar work and require coordination before changing shared files;
  preserve other agents' edits and stage/commit only the agent's own changes.
- [ ] <a id="pw-173"></a>**PW-173** Refresh coordination context as peers start, change work, or stop. Closed
  sessions' historical notes must not masquerade as current file ownership.
  Do not claim that a briefing provides enforced locking or isolated worktrees.
- [ ] <a id="pw-174"></a>**PW-174** If AI overlap assessment is absent, uncertain, or fails, still provide the
  factual live-peer briefing and proceed subject to capacity and other approved
  authorization/repository gates. Missing assessment is not proof of no overlap.
- [ ] <a id="pw-175"></a>**PW-175** Test similar tasks launching when capacity permits, both dispatch modes,
  advisory information reaching worker context, retained capacity queuing and
  retry limits, and removal of obsolete overlap blockers without duplicate starts.

## Wall notes: live coordination only

Owner-approved: agents should be able to check the wall for current coordination;
notes belong on the live wall only while their agent run is active. Pending
implementation, not a deletion of historical notes.

- [ ] <a id="pw-176"></a>**PW-176** Explicitly remove the deliberate closed-session wall-note injection from
  terminal startup (`terminal.py` seed context -> `blackboard.wall_text()`).
  Replace the unfiltered historical wall lookup with live-run notes only and
  remove the comment endorsing notes from agents that are no longer running.
  With no active runs' notes, inject no wall paragraph; do not fall back to
  historical notes. Keep this scoped to wall coordination, not saved task results.
- [ ] <a id="pw-177"></a>**PW-177** Apply the same removal explicitly to general-assistant context:
  `general._prompt()` -> `blackboard.chat_text()` / `house_wall()` must not inject
  closed runs' notes. Shared notes from general agents need run ownership and the
  same active-run filtering; no historical house-lane fallback when none are live.
- [ ] <a id="pw-178"></a>**PW-178** Associate coordination notes with a specific agent session/run, not merely
  a task ID. Include active coding, general, and headless workers, including live
  sessions waiting for approval/input. Remove notes from live surfaces when that
  run ends; restarting the same task must not revive the previous run's notes.
- [ ] <a id="pw-179"></a>**PW-179** Use the same live-note selection for the board UI, agent startup context,
  wall-reading commands/tools, and refreshed coordination context. Currently
  terminal startup uses unfiltered wall(), the UI filters by live task IDs, and
  general-agent context uses a separate unfiltered house lane.
- [ ] <a id="pw-180"></a>**PW-180** Retain ended-run notes in task/run history, explicitly historical and not
  presented as current file ownership. Taskless/house notes must not bypass the
  lifecycle rule; separate durable owner guidance from live agent coordination.
- [ ] <a id="pw-181"></a>**PW-181** Test active and approval-waiting runs, completed/stopped runs, same-task
  restarts, headless/general agents, and consistent wall contents across UI,
  prompts, and commands. An instruction to read the wall is not proof it was read.

## Simplified worker context: AGENT.md, CODER.md, and one task brief

Owner-approved: use the same concise context structure for general and coding
workers. Do not inject the full SOUL.md into every worker prompt. Pending
implementation only; preserve required context and authorization boundaries.

- [ ] <a id="pw-182"></a>**PW-182** Define shared AGENT.md operating rules for both worker kinds: task scope,
  honest tool/result reporting, asking when blocked, progress and completion
  reporting, and approval boundaries. CODER.md adds only coding-specific rules
  for repositories, editing, testing, and staging/committing changes.
- [ ] <a id="pw-183"></a>**PW-183** Build one authoritative task brief containing task ID, objective, triage
  checklist, explicit owner instructions, selected repository when applicable,
  latest complete substantive conversation context, and attachment references.
  Simplifying the prompt must not discard chain context or freshness checks.
- [ ] <a id="pw-184"></a>**PW-184** Stop injecting the full SOUL.md into coding and general-worker prompts.
  Keep SOUL available to triage for people/project understanding and routing;
  carry only relevant facts and owner preferences into the worker task brief.
  Audit existing SOUL safety/approval constraints and preserve them in shared
  rules or applicable task constraints before removing the blanket injection.
- [ ] <a id="pw-185"></a>**PW-185** Consolidate relevant source rules, playbook guidance, and saved preferences
  without duplicate or conflicting instruction blocks. Include writing style
  when the task requires it, not indiscriminately for every coding run. Keep
  lengthy supporting material accessible separately with clear references.
- [ ] <a id="pw-186"></a>**PW-186** Add live coordination only when relevant active peers/notes exist, using
  the approved run-scoped wall lifecycle. For a continuation, separately include
  this task's dated last result or pause handover; do not substitute historical
  shared wall notes or unrelated closed sessions.
- [ ] <a id="pw-187"></a>**PW-187** Test both worker kinds for shared rules, coding-only additions, absence of
  blanket SOUL injection, retained applicable approval constraints, complete
  fresh task context, and correctly scoped live/continuation information.

## Minimal onboarding and assistant-led Taskuary setup

Owner-approved: the initial onboarding box only establishes the user's name and
AI coding CLI setup, then hands off to assistant-led system setup. Pending work.

- [ ] <a id="pw-188"></a>**PW-188** Simplify initial onboarding to name, then AI coding CLI selection/setup
  and readiness validation. Clearly explain missing prerequisites; do not strand
  the user in a chat with no usable AI. Move the remaining setup walkthrough,
  including generating a draft reply-writing style, into the assistant.
- [ ] <a id="pw-189"></a>**PW-189** Add a discoverable system-setup walkthrough entry point at the top Assistant
  button/navigation area, available after onboarding as well as during first run.
  It starts an AI-led setup conversation, not a separate hardcoded wizard or
  keyword-dispatch path, and must not lose the user's existing conversation.
- [ ] <a id="pw-190"></a>**PW-190** Ship a Taskuary setup skill containing the product-specific setup procedure,
  prerequisites, supported configuration tools, and verification guidance. The AI
  uses that skill to inspect existing configuration, explain choices, ask relevant
  questions, and adapt the walkthrough. Keep procedure knowledge in the skill,
  not hardcoded dialogue/branching or a competing general assistant system prompt.
- [ ] <a id="pw-191"></a>**PW-191** Reuse direct report/connection setup and shared confirmed configuration
  actions. Draft style generation is a preview; show the proposed document and
  confirm before saving/replacing it. Preserve existing customized settings/docs
  and use secure credential/OAuth controls rather than collecting secrets in chat.
- [ ] <a id="pw-192"></a>**PW-192** Support resuming incomplete setup and revisiting individual setup areas
  without rerunning completed steps or creating duplicate resources. Display
  actual verified readiness and remaining work, not claimed completion from prose.
- [ ] <a id="pw-193"></a>**PW-193** Test first-run name/CLI handoff, missing CLI readiness, top-level setup entry,
  AI-guided clarification, skill use, draft-style preview/confirmation, preservation
  of user edits, resume/cancel, and no unintended worker dispatch or duplicate setup.

## Direct report and connection setup through the assistant

Owner-approved: straightforward report and connection setup happens in the
assistant conversation and creates the actual configured resource, not an empty
walkthrough task. Pending implementation.

- [ ] <a id="pw-194"></a>**PW-194** Interpret setup requests through AI, gather missing configuration, and show
  a structured confirmation box before saving. Use shared validated Reports and
  Connections operations, not a separate assistant-only creation path. Return the
  actual created resource and a link to its normal management screen.
- [ ] <a id="pw-195"></a>**PW-195** For reports, gather source/connection, query or inputs, summary instructions,
  schedule/timezone, and informational/promotion/triage behavior. Show enabled state
  explicitly; schedule activation must be covered by confirmation. Read-only preview
  may run without another confirmation, but must not send, write external data,
  activate schedules, or dispatch workers as a side effect.
- [ ] <a id="pw-196"></a>**PW-196** For connections, gather provider and non-secret configuration, show requested
  permissions/scopes, and use the existing secure credential/OAuth interface.
  Do not request or persist secrets in assistant conversation/history/memory.
  Distinguish configuration saved, authorization pending, connected, and validation
  failed; do not claim usable connectivity until verified. Make sync/start behavior
  explicit rather than silently enabling unrelated workflows or agents.
- [ ] <a id="pw-197"></a>**PW-197** If setup requires substantial investigation, propose a general-agent setup
  task with an explanation and confirmation. Use coding only for actual code work.
  Do not create a task or start a worker for every simple configuration request.
- [ ] <a id="pw-198"></a>**PW-198** Test conversational clarification/correction/cancel, exact configuration
  confirmation, real resource creation without placeholder tasks, duplicate-submit
  protection, permission/auth failure, secret redaction, safe preview, schedule
  activation, and shared behavior with Reports/Connections UI.

## Assistant ideas enter shared triage

Owner-approved: assistant-generated ideas propose new work and must pass through
the same triage as incoming messages, rather than receiving a separate automatic
forgotten/report lane. Pending implementation.

- [x] <a id="pw-199"></a>**PW-199** Replace assistant idea direct feed-route classification with shared triage
  using the idea, its source evidence, originating report context, and linked
  task/current worker state. Keep stable identity and legitimate grouping, show
  pending triage immediately, and reuse shared triage error/retry behavior.
- [x] <a id="pw-200"></a>**PW-200** Use the resulting classification and importance for canonical Unread order,
  task/draft creation, and configured agent startup rules. Do not create duplicate
  work where an idea refers to an already active task, or treat generated claims
  as verified evidence of completion. Do not add a second assistant-only ranking.
- [x] <a id="pw-201"></a>**PW-201** Preserve the existing opt-in report triage capability: configured reports
  can identify potential work and submit findings to triage for task/agent routing.
  Ordinary informational reports need not be triaged; use their configured
  informational/promotion behavior. Workflow triggers execute the configured job
  directly, and agent status/input/approval events remain explicit execution state,
  not requests for AI reclassification. All use the shared timeline representation.
- [ ] <a id="pw-202"></a>**PW-202** Test informational/actionable/urgent ideas, linked active work, duplicate
  report runs, pending/error states, report triage on/off, and no accidental
  retrigger loop from generated output. Verify normal workflow and worker-status
  paths remain independent of triage.

## Separate configured workflows from incoming-request procedures

Owner-approved: configured workflows are predefined jobs triggered by a schedule
or Run now, not incoming messages needing AI intent classification. Saved request
procedures (for example PTO handling) are a separate concept. Pending implementation.

- [ ] <a id="pw-203"></a>**PW-203** Separate scheduled/configured workflow definitions from reusable procedures
  for incoming requests. A workflow carries its objective, configured inputs,
  connections, steps, allowed actions, approval requirements, and completion
  criteria; a request procedure describes how to handle a matching incoming ask.
- [ ] <a id="pw-204"></a>**PW-204** Dispatch a triggered workflow directly to a general agent with the workflow
  definition and run-specific context. Do not send it through message triage to
  rediscover its intent or select its procedure; do not force a coding agent.
  Automatic dispatch remains subject to approved capacity and startup-retry
  handling, and does not bypass configured write permissions or approval gates.
- [x] <a id="pw-205"></a>**PW-205** Keep incoming-request procedure matching in unified triage (for example,
  recognizing a PTO request and attaching its saved handling instructions).
  Selecting a procedure must not itself classify the task as coding. Remove the
  current playbook-match override that assigns kind='coding'.
- [ ] <a id="pw-206"></a>**PW-206** Deliver the selected procedure to either worker kind through the shared
  task-brief structure, including general API agents. For direct workflow runs,
  deliver workflow context without requiring a playbook selection by triage.
- [ ] <a id="pw-207"></a>**PW-207** Preserve existing definitions when separating these concepts; explicitly
  distinguish reusable request procedures from configured scheduled jobs instead
  of blindly converting all existing playbooks into scheduled workflows.
- [ ] <a id="pw-208"></a>**PW-208** Test scheduled and manual workflow runs bypassing message triage and
  dispatching to general agents, workflow context delivery, retained approval
  boundaries, and PTO-style incoming requests selecting a procedure without
  forced coding or duplicate agent starts.

## Consistent worker startup and manual action surfaces

Owner-approved: dispatch submits the task brief, records the live worker, and
updates the timeline. Merely opening/viewing a workspace must not claim that an
agent is working. Pending implementation.

- [ ] <a id="pw-209"></a>**PW-209** Apply that startup contract to coding and general workers: distinguish
  workspace/session creation from accepted work submission, publish consistent
  live-state updates, and retain duplicate-start protection. Failures or pending
  repository selection must not be reported as successful starts.
- [ ] <a id="pw-210"></a>**PW-210** Verify equivalent Make task and Send to agent behavior across All timeline
  detail, Unread/chat cards, and Tasks. Make task creates/reuses an owner task
  without launching a worker; Send to agent uses explicit worker choice and the
  shared dispatch contract, including required repository confirmation.
- [ ] <a id="pw-211"></a>**PW-211** Audit finding: All detail's SendToAgent is hidden for unconverted
  FYI/reply_only rows by the codeless guard in FeedView.jsx. Resolve this mismatch
  with chat cards, which expose manual agent dispatch for those items.
- [ ] <a id="pw-212"></a>**PW-212** Audit finding: ui.jsx SendToAgent treats a successful HTTP response with
  dispatch='needs_repo' as a live start; unlike assistantCards.jsx, it has no
  repository-selection branch. Handle the decision state without success claims.
- [ ] <a id="pw-213"></a>**PW-213** Audit finding: TasksView.startGeneralAgent dispatches existing general
  tasks, but switching another kind only patches Kind/ask tags. Unify explicit
  dispatch instead of relying on workspace mount behavior to initiate work.
- [ ] <a id="pw-214"></a>**PW-214** Test the actual All-detail buttons and matching chat/Tasks actions: owner
  task creation without startup, coding/general launch, missing-repo handling,
  already-live sessions, errors, and consistent timeline refresh. Findings above
  are code-traced; live UI interactions have not been exercised in this review.

## Task-view buttons: accurate labels and shared execution

Owner-approved after the button code review: fix task-view inconsistencies; keep
the task-view controls. Assistant chat's removal of action menus does not remove
these controls. Findings are code-traced, not live-click verified. Pending work.

- [ ] <a id="pw-215"></a>**PW-215** Route task-view controls and assistant confirmation boxes through the same
  validated operations, with consistent targets, permissions, freshness checks,
  errors, and confirmed outcomes. Do not add phrase interpretation to button clicks.
- [ ] <a id="pw-216"></a>**PW-216** Unify coding startup (currently Kind PATCH plus openTerm) and general
  startup through shared dispatch. Fix Use non-coding agent changing Kind/ask
  tags without explicitly submitting work. Handle missing repository, failed
  launch, and already-live workers without false success or duplicate starts.
- [ ] <a id="pw-217"></a>**PW-217** Make task completion versus agent completion explicit in labels/help and
  behavior: Mark task done currently closes the live worker too; Reopen task
  changes task status without starting a worker. Preserve next-in-progress
  navigation after completion, including when opened from All/search.
- [ ] <a id="pw-218"></a>**PW-218** Reconcile Finish agent run and Save stopped run result with the approved
  save-result/completion/reply lifecycle. Current wrap(close=False) stops/saves
  but skips task completion and normal completion-to-reply processing; do not
  imply the full completion workflow happened when only a result was saved.
- [ ] <a id="pw-219"></a>**PW-219** Clarify Pause & save means end the session with saved continuation context,
  not suspend a live process. Keep Stop session distinct: stop without generating
  a wrap-up report, update worker/task state accurately, and preserve saved history.
- [ ] <a id="pw-220"></a>**PW-220** Verify Write reply, Generate reply, and Ask sender create/open the intended
  draft/review and never send immediately. Make clarification approval explicit.
  Review changes must remain a viewer, not imply approval or a commit.
- [ ] <a id="pw-221"></a>**PW-221** Add handler/backend tests plus actual UI interaction coverage for these
  controls: matching labels/outcomes, general/coding dispatch parity, repository
  cancellation/errors, task versus worker completion, pause/stop, saved results,
  reply/clarification approval, next-in-progress selection, and duplicate clicks.

## Event-driven worker status instead of terminal heuristics

Owner-approved: coding and general workers publish one shared status model using
explicit events. Pending implementation; no hooks or provider integration changed
during this walkthrough.

- [ ] <a id="pw-222"></a>**PW-222** Model Working, Input needed (with the unanswered question), Approval needed
  (with the specific pending action), and Finished (assigned work has a result
  ready for review). Finished does not itself close the task. Track failures,
  disconnections, and owner-stopped runs separately, never as successful completion.
  An idle/open workspace is not a user-facing work status or a reason to raise a hand.
- [ ] <a id="pw-223"></a>**PW-223** Integrate Claude Code lifecycle/tool hooks for prompt submission, permission
  requests, structured questions, and response termination. Validate supported
  hooks against the installed version. Stop means the response ended, not proof
  of task completion; observe approvals without automatically granting them.
- [ ] <a id="pw-224"></a>**PW-224** Integrate Codex App Server structured turn lifecycle, approval, and user-input
  requests. This is a provider integration change, not a passive subscription to
  the existing terminal. Validate the installed protocol/version and preserve
  interactive viewing, answering, interruption, and continuation capabilities.
- [ ] <a id="pw-225"></a>**PW-225** Emit regular API-agent lifecycle events directly from the execution loop.
  Provide explicit request_input and finish_work tools (or equivalent validated
  structured signals). Derive approval status from the actual approval gate,
  not generated prose. Apply equivalent semantic signals to coding workers.
- [ ] <a id="pw-226"></a>**PW-226** Separate response/turn completion from work completion. Require an explicit
  result or question to establish Finished or Input needed; a quiet terminal,
  bare prompt, end-of-response event, or process exit is not sufficient proof.
  Missing status signals should be identified as unknown/disconnected as appropriate,
  not guessed as a question, successful finish, or indefinitely active work.
- [ ] <a id="pw-227"></a>**PW-227** Persist and reconcile events by task/run/turn and request IDs. Deduplicate
  notifications, reject stale events from old runs, and handle reconnects and
  out-of-order delivery. All UI surfaces and the assistant consume the same state.
  Answering one request must not clear other outstanding approval/input requests.
- [ ] <a id="pw-228"></a>**PW-228** Keep Working visible in Unread without injecting it into chat. Promote
  actual input/approval requests with their content, and finished results as
  results rather than blocked work. Do not repeatedly announce the same event.
  Live approval/input-waiting sessions still count toward approved capacity.
- [ ] <a id="pw-229"></a>**PW-229** Test all providers: long silent work, terminal repaint noise, questions,
  approval allow/deny, response ending without task completion, explicit finish,
  errors/interruption, empty workspaces, duplicate/stale events, reconnection,
  and consistent timeline/chat state without duplicate hand raises.

Reference interfaces checked during review:
- Claude Code hooks: https://code.claude.com/docs/en/hooks
- Codex App Server: https://learn.chatgpt.com/docs/app-server

## Explicit completion: save the agent result, then close its run

Owner-approved: when an agent explicitly declares the assigned work finished,
automatically close its worker session after saving its result. Do not require
the owner to close the terminal manually just because they started it. Pending
implementation; task closure and outbound sending remain separate decisions.

- [ ] <a id="pw-230"></a>**PW-230** Capture the agent's actual final answer directly, rather than requiring a
  second AI to reconstruct it from terminal scrollback. Claude Stop provides
  last_assistant_message; Codex App Server completed agentMessage items provide
  the reply text; regular workers already receive the response directly.
  Match the answer to the correct run/turn and explicit work-finished signal:
  Stop, final_answer, and turn completion alone do not prove the task is finished.
- [ ] <a id="pw-231"></a>**PW-231** Persist the final Markdown result, evidence/artifact references, and reported
  completed/remaining checklist items on the task before closing the worker.
  Preserve item identities and do not blindly mark the entire checklist complete.
  Keep the original final answer even if an optional compact summary is generated.
- [ ] <a id="pw-232"></a>**PW-232** Replace the manual-start stay-open veto for explicit successful completion.
  Close only the completed run, release capacity, remove its live wall notes, and
  publish one result-ready event. Retain history and continuation identifiers for
  follow-up; never terminate a shared provider service or unrelated runs.
- [ ] <a id="pw-233"></a>**PW-233** If result persistence fails, do not discard the session or claim successful
  finalization. Make persistence/finalization retryable and idempotent; duplicate
  finish hooks must not duplicate artifacts, drafts, or completion notifications.
- [ ] <a id="pw-234"></a>**PW-234** Test automatic and manually started workers, matching final-answer capture,
  save-before-close ordering, incomplete checklist entries, pending approvals,
  duplicate events, persistence failures, and retained follow-up context.

## Completion-to-reply freshness and approval

Owner-approved: saved agent result -> refresh the source conversation -> reassess
whether a reply is still needed -> draft from the result and current context ->
owner approval. Pending implementation.

- [ ] <a id="pw-235"></a>**PW-235** Apply the approved freshness and unified reevaluation rules after work
  finishes, before generating its reply. Detect owner replies sent externally and
  changed requests; do not assume the original ask is still outstanding or draft
  a stale completion claim. If refresh fails, show the unresolved freshness state.
- [ ] <a id="pw-236"></a>**PW-236** Reuse the applicable held review rather than duplicating it. Generate the
  reply from the saved final result and verified current conversation, recording
  the context revision used. Preserve the completed worker result independently
  of draft generation success and keep a failed draft visibly retryable.
- [ ] <a id="pw-237"></a>**PW-237** Bring coder.finish() into line with the approved always-draft rule: when
  a reply is needed, unsupported/disabled sending must not suppress the draft.
  Hide Send and explain why it is unavailable; retain backend send restrictions.
  Outbound sending remains subject to owner approval, not agent completion.
- [ ] <a id="pw-238"></a>**PW-238** Test changed requests, already-sent external replies, unchanged chains,
  refresh/drafting failures, held-review reuse, unsupported send channels, and
  repeated completion events without duplicate drafts or automatic sending.

- [ ] <a id="pw-239"></a>**PW-239** Owner clarification: when new context materially changes the task/draft and
  triage updates it, interrupt approval with a popup: "A new message arrived.
  Review it before sending." Show the new message and relevant triage change,
  with actions to review the update or cancel. Do not send on the original click
  or silently substitute a revised draft; require fresh approval of the reviewed
  draft. Preserve owner edits for comparison rather than discarding them.
- [ ] <a id="pw-240"></a>**PW-240** Base approval invalidation on the draft's context/triage revision and
  material relevance, not every polling timestamp or unrelated arrival. Pending
  reevaluation must not be treated as proof that new context is harmless. Different
  email/chat polling cadences do not waive the approved source-freshness checks.
- [ ] <a id="pw-241"></a>**PW-241** Test material inbound changes, externally sent replies, relevant triage
  updates, non-material refreshes, changes while approval is open, and popup
  cancellation. Never apply the previous approval to a changed draft.

## Assistant instructions: remove the hardcoded behavioral prompt

### Separate main-chat instructions from report generation

Owner-approved, pending implementation:

- [ ] <a id="pw-242"></a>**PW-242** Remove shared COUNSEL injection from assistant.think() report-generation
  prompts. Preserve each report's configured instruction, configured data scope,
  valid output contract, and required safety constraints. The main chat's Current,
  walkthrough, and wait-for-owner rules must not govern scheduled idea generation.
- [ ] <a id="pw-243"></a>**PW-243** Audit other COUNSEL consumers, including suggestion discussions and general
  worker prompts, for role leakage before further changes. Review their appropriate
  instructions separately; do not silently remove required guidance.
- [ ] <a id="pw-244"></a>**PW-244** Test that changing chat COUNSEL does not alter the scheduled report prompt,
  report configuration remains intact, and report findings still enter the shared
  timeline. Existing live COUNSEL edits currently affect both consumers until
  this separation is implemented.

### Main-chat prompt cleanup

- [x] <a id="pw-245"></a>**PW-245** Implemented the owner-approved COUNSEL loader change in concierge._counsel:
  no 3,200-character slice and no hidden behavioral fallback. Missing/blank
  instructions restore the shipped document with an audit record and warning;
  an unreadable/empty shipped default raises an explicit error. Nonblank owner
  content is preserved. No arbitrary replacement length cap was introduced;
  provider-specific whole-prompt budget handling remains to review.
- [x] <a id="pw-246"></a>**PW-246** Added loader regressions for complete long instructions reaching _system,
  preserved owner content, missing/blank/comment-only recovery, rendered owner
  placeholders, and explicit failure when the default cannot be used.
  Verification: tests/test_concierge_counsel.py plus tests/test_concierge.py:
  46 passed. No live server restart performed; hardcoded SYSTEM removal remains
  pending and is not part of this loader change.

- [x] <a id="pw-247"></a>**PW-247** Applied approved consistency pass to shipped/live COUNSEL: shared Unread
  ordering instead of embedded priority bands; bottom-strip-only unsolicited
  notifications, explicit Open/Later behavior, and no automatic chat duplicates.
  Verified live content before and after writing. Actual UI/selection enforcement
  remains pending. Rendered COUNSEL now measures 3,927 characters; current loader
  still drops the final 727 characters until truncation is removed.
- [ ] <a id="pw-248"></a>**PW-248** Owner confirmed the boundary: retain the minimal machine action contract
  needed to render validated action buttons, but no competing hardcoded behavior.
  Removing behavioral prose must not remove action schemas or backend checks.

Owner-approved: remove the hardcoded assistant behavioral prompt and maintain
the reviewed instructions in editable COUNSEL.md. Review responsibilities and
action rules one at a time before implementing. Pending implementation only.

- [x] <a id="pw-249"></a>**PW-249** Applied approved Voice section to shipped and live saved COUNSEL: concise
  but expandable explanations, clear recommendations, verified facts versus
  inference, supported retrieval of missing context, no invented outcomes,
  no repetitive all-done announcements, and clarification of ambiguous scope or
  approvals. Removed document-level rigid word limits and obsolete post voice.
  Verified the live document before/after writing. Hardcoded prompt constraints,
  truncation, and the final ordering/notification consistency pass remain pending.

- [x] <a id="pw-250"></a>**PW-250** Replaced "The post" in shipped and live saved COUNSEL with the approved
  "My goal": help the owner complete work with minimal effort, walk Unread in
  displayed order, explain priorities/decisions, recommend actions, request needed
  approval/clarification, delegate execution, and follow confirmed outcomes without
  unsolicited advancement. Report-generated ideas are ordinary timeline items;
  the main chat needs no separate scheduled-post instruction. Verified saved
  content before and after the API update; report configuration was not changed.

- [x] <a id="pw-251"></a>**PW-251** Applied approved urgent-update wording to shipped and live saved COUNSEL:
  notify and offer to open, never automatically switch Current, avoid repeated
  notifications without changed facts, and explain updates to Current in place.
  Verified saved content before/after the update. Notification placement remains
  under review; no notification UI or backend event behavior changed here.

- [x] <a id="pw-252"></a>**PW-252** Applied the approved named-item rule to the shipped and live saved COUNSEL:
  identify the intended reference, clarify ambiguous matches, never substitute
  Current for an unresolved action target, preserve the previous place, and do
  not treat discussion as read/close/action authorization. Verified the live
  document was unchanged before writing and read back the saved result. Backend
  reference-resolution/read-state enforcement still needs implementation review.

- [x] <a id="pw-253"></a>**PW-253** Owner requested immediate implementation of the first responsibility in
  taskuary/templates/counsel.md: orchestrate validated actions, delegate to regular
  or coding workers/reply writer, use verified context, report confirmed outcomes,
  and never advance without owner action. Updated the adjacent work-handoff rule
  consistently. This changes the shipped template only; no live database document
  was overwritten. Hardcoded-prompt removal and runtime behavior remain pending.
- [x] <a id="pw-254"></a>**PW-254** Owner approved the walkthrough/FYI/overview rule: discuss Current and wait
  for owner action, batch up to four FYIs in Unread order, and summarize an overview
  on request without marking items read. Updated the shipped COUNSEL template.
- [x] <a id="pw-255"></a>**PW-255** At the owner's explicit request, applied both approved COUNSEL edits to the
  live saved document through PUT /api/doc/counsel. First verified its content
  exactly matched the stock HEAD template (UpdatedBy=template); checked again
  before writing and verified the saved result via GET. No restart or chat/read
  state changes. Hardcoded behavioral-prompt removal is still pending, so these
  document edits alone do not establish full runtime behavior compliance.

- [ ] <a id="pw-256"></a>**PW-256** Remove concierge.SYSTEM's competing behavioral/routing instructions and
  hidden behavioral fallback. Consolidate approved assistant behavior into the
  database-backed COUNSEL document and its shipped default, preserving existing
  owner edits through an explicit migration rather than overwriting them.
- [ ] <a id="pw-257"></a>**PW-257** Keep authorization, valid action/argument checks, target validation,
  freshness, and execution acknowledgment enforced in backend code. Removing
  prompt prose must not remove these safeguards or silently break DECIDE/OPTIONS
  parsing. Separate the machine action contract from editable behavioral policy;
  review its replacement before changing the execution interface.
- [ ] <a id="pw-258"></a>**PW-258** Remove silent 3,200-character truncation of COUNSEL; apply explicit size
  validation/budget handling so approved instructions are not silently dropped.
- [ ] <a id="pw-259"></a>**PW-259** Audit remaining inline prompts/action heuristics and canned receipts for
  contradictory behavior (including research-to-setup and skip-as-tomorrow).
  Resolve each through the walkthrough, not an unreviewed blanket rewrite.
- [ ] <a id="pw-260"></a>**PW-260** Test that editing the assistant document affects the actual loaded prompt,
  without a hidden competing behavioral block, while malformed actions and
  unapproved operations remain blocked by the backend.

## Orderly app shutdown: stop workers and wait for cleanup

Owner-approved: quitting Taskuary closes it, rather than leaving it running in
the background, and waits for cleanup. Pending implementation/verification.

- [ ] <a id="pw-261"></a>**PW-261** Fix desktop shutdown's daemon-thread race: signal backend shutdown and wait
  for completion before exiting the desktop process. Preserve available history,
  stop Taskuary-owned coding/general workers and CLI children, and finish durable
  task/run state updates. Do not terminate unrelated user processes.
- [ ] <a id="pw-262"></a>**PW-262** Leave unfinished work open and visibly interrupted, not Working or Done.
  Reopening offers explicit continuation rather than silently dispatching another
  worker. Tab navigation/browser disconnection must not act as backend shutdown.
- [ ] <a id="pw-263"></a>**PW-263** Handle stuck cleanup with visible progress/error and a bounded escalation
  strategy; do not silently exit before cleanup or claim all workers stopped when
  that is unverified. Reconcile interrupted runs after crashes as well as normal quit.
- [ ] <a id="pw-264"></a>**PW-264** Test native desktop quit waits for server cleanup, transcript/history
  persistence, general/coding/one-shot child cleanup, interrupted state on restart,
  and no unintended worker termination on tab navigation.

## Assistant browser control and its UI: review required

Owner clarification: browser control by the assistant and its UI have not been
walked through or approved as part of the direct setup design.

- [ ] <a id="pw-265"></a>**PW-265** Trace browser ownership/control and actual UI with the owner: which agent
  owns it, when it opens, visibility of actions, manual takeover, and its relation
  to the routing chat and task workspace.
- [ ] <a id="pw-266"></a>**PW-266** Review navigation versus consequential website actions, confirmation,
  credentials/session handling, cancellation, and recovery. Configuration setup
  approval does not imply permission for arbitrary browser actions.
- [ ] <a id="pw-267"></a>**PW-267** Agree the UI/interaction contract before redesigning browser control; then
  add scoped implementation tasks and behavioral tests. Current or proposed
  browser behavior must not be treated as already accepted.

## Review progress

- Walkthrough format requested by owner: show the actual relevant code excerpt
  and file/line link alongside each explanation. Distinguish current behavior
  from approved pending design; continue one step at a time for owner review.

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
- Reviewed: reply_only handling; approved always drafting with send controls
  omitted and the reason shown when sending is unavailable.
- Reviewed: draft generation/documents and freshness gaps; approved mandatory
  source checks, fresh triage, and exact draft-context version tracking.
- Reviewed: document responsibilities; approved separating triage learning from
  reply-writing preferences.
- Reviewed: reply approval entry point and destination selection; approved default
  Reply all/Reply to controls and reliable signature application. Delivery and
  completion internals still need review.
- Reviewed: task creation/category defaults and pipeline-ranking boundary;
  approved default general kind, configurable auto-start for coding/general workers,
  and a triage-generated summary with an interactive Markdown checklist.
- Reviewed: auto-start sender gate; approved configurable trust rules, removal of
  incoming-history authorization, and retained Sent Items evidence.
- Reviewed: dispatch capacity and startup-failure handling; approved counting
  approval-waiting live agents and bounded retry behavior.
- Reviewed: repository selection; approved project/people-map evidence and a
  validated project/repository decision in unified triage, with owner choice
  when uncertain.
- Reviewed: manual coding repository confirmation across task/timeline/chat.
- Reviewed: startup/action-surface consistency and worker attention detection;
  approved event-driven status for Claude, Codex, and general workers, separating
  input, approval, work completion, and technical failures.
- Reviewed: live wall lifecycle and worker prompt structure; approved shared
  AGENT.md plus coding-specific CODER.md, one task brief, and removal of blanket
  SOUL injection for both worker kinds.
- Reviewed: All versus Unread source/filter/render split; approved shared items
  and read state, All chronological, Unread ordered by status/priority.
- Reviewed: overlap coordination instead of overlap queuing; direct general-agent
  workflow dispatch versus triage-selected incoming-request procedures.
- Reviewed: explicit completion, save-before-close final result/checklist handling,
  and automatic worker closure including manually started runs. Result storage,
  worker termination, task closure, and outbound sending are distinct decisions.
- Reviewed: completion-to-reply freshness and the approval gate; material context
  changes require a popup and renewed approval, not a silent replacement/send.
- Reviewed: Walk resumes valid Current or selects the top eligible shared-Unread
  item; remove assistant-local filtering/ranking while preserving funnel layout,
  Current/Next controls, and promotions. Four FYIs have individually actionable
  summaries; task cards show full source context plus summary/checklist under COUNSEL.
- Reviewed: replace decide_words/phrase dispatch and assistant action menus with
  AI interpretation, clarification, bottom prompt suggestions, and structured
  confirmation boxes. Backend executes exact validated actions on confirmation.
  Draft generation and explicit Next navigation are immediate exceptions; neither
  closes tasks or marks items read. Task-view controls remain and need shared handlers.
- Reviewed: successful reply closes its task even with unfinished TODOs. Confirmed
  successful agent handoff says Moving on and advances once, keeping the worker
  visible as Working in Unread. Background events do not independently advance chat.
- Reviewed: keep worker UI in the task workspace, opened on request. Relay agent
  questions through the assistant with request/run-bound confirmed answers and
  verified delivery; hooks alone do not guarantee a reliable reply path.
- Reviewed: distinguish one-time actions, learned context, and deterministic
  exclusions. Successful action handlers automatically record deviations from
  triage as evidence, not permanent rules. Preserve discussion/action history for
  source items without tasks and link it when a task is created.
- Reviewed: New chat archives and starts blank; history reads do not mutate data.
  Independent configurable retention defaults to 15 days and preserves task-linked
  discussion/results/send history, correction evidence, and saved rules.
- Reviewed: confirmed/failed/unknown delivery states, reconciliation before retries,
  and explicit Close without sending when permissions/capability block sending.
- Reviewed: quitting the app stops its workers and waits for cleanup; preserve
  history and show unfinished work as interrupted on restart, not working/done.
- Walkthrough wrap-up: major flows are reviewed. Remaining policy details below
  must be distinguished from implementation/testing checks; resolve ambiguity
  before implementing the affected transition. No backlog implementation authorized
  merely by finishing this review.
- Still to review in detail: exact importance/status ordering; read versus handled
  transitions, FYI batch completion, deferral return timing, and chat advancement
  after actions other than the explicitly agreed handoff/Next cases. Clarify final
  skip/ignore scope and historical-item effects of standing exclusions.
- Reviewed since wrap-up: immediate calendar/urgent requests first, agent input/
  approval waits second, coding/general Working in band 5 with an emoji/status.
  Middle bands and exact tie-breaks remain to finalize. Assistant ideas enter shared
  triage; ordinary report triage is opt-in and configured workflow triggers bypass it.
- Reviewed since wrap-up: direct report/connection creation in the assistant;
  minimal name/CLI onboarding, then AI-led system setup using a shipped setup skill.
- Still to verify in code/tests: blank New chat, archives/15-day retention, duplicate
  response prevention, and context updates during an active conversation. The
  intended archive/retention behavior is approved, not an unresolved redesign.
- Still to verify in code/tests: actual outbound delivery, definite/uncertain failure
  and reconciliation, safe retries, alternate approvals, successful-send closure,
  and explicit close-without-send. Resolve clarification-send task state separately.
- Still to verify: initial CLI prompt submission acknowledgment; shutdown/restart,
  orphaned workers and continuation; workflow runs surviving navigation; runtime
  loading, terminal input/replay, and next-item navigation regressions.
- Documentation status: this file is the authoritative walkthrough/backlog record;
  the outdated processing-walkthrough-handoff.md was removed at the owner's request.
  Approved unchecked entries are pending, not implemented or tested. The checked
  dispatch-queue fix and regression test above are the implementation exception.
  Preserve the existing working tree and user data; no app restarts, read-state
  resets, or backlog implementation without the owner's direction.
