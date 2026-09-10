# Processing state and migration contracts

Phase 0 design contract, 2026-09-06. These fields describe dependent implementation;
they are not claims that the baseline API already implements them. No live migration
is performed by Phase 0. Acceptance references use the permanent PW IDs in the ledger.

## Canonical inventory

One inventory service supplies All, Unread and assistant selection. `item_id` is
durable and independent of review/run/status. Existing `FunnelKey` is not suitable:
it changes among message, review and agent forms as state changes. Preserve aliases
and explicit member message IDs so historical actions resolve to the same source.
Provider identities include connector/account scope. Task linkage and source-chain
identity remain separate so later activity does not reopen a completed task by accident.

`context_revision` identifies the exact substantive inputs (message IDs and versions,
attachments, material task context). `view_revision` changes for any displayed state:
read/defer, priority, worker request, draft, preview, member count and source settings.
Each triage result, proposal and draft records the exact snapshot it consumed;
sequential outputs can consume newer revisions and must check compatibility before
execution. Failure to refresh cannot certify freshness. A selected item can remain
Current while its revision changes.

Read evidence (`read_at`, actor, revision, explicit operation/provenance) and deferral
(`defer_until`, reason, operation) are separate from triage and worker state. Display,
classification, Next and working status are not new read receipts. Store legacy state
verbatim, including the provenance of inferred historical reads. Owner decision on
2026-09-06: preserve existing historical read results (including display-only surfaced
records), while using display-does-not-read semantics for new activity going forward.
Capture the legacy result at the migration boundary without rewriting its evidence as
an explicit owner read receipt. Preserve explicit Done/skip records. Do not make
historical items unread again to enforce the new display behavior retroactively.
Preservation must keep temporary deferral separate: an active `later`/`skip` interval
cannot become a permanent read receipt merely because it currently suppresses Unread.
Preserve its expiry/return behavior and underlying read evidence. Unloaded pages and
cap/filter omissions are absence of inventory evidence, not historical read receipts.

Unread is the shared read-filtered inventory with shared exclusions and deterministic
ordering. Working items stay visible. Shared `actionable` and its reason exclude working,
deferred and pending-triage items from automatic selection. UI and assistant consume
the same ordered snapshot; neither adds private filters, limits or rankings. Pagination
returns snapshot revision, cursor and eligible counts; unloaded items are not absent.
A stale cursor requires an explicit snapshot restart/reconciliation with identity
deduplication; never silently combine pages from different revisions.
All remains chronological and detail-only. Preserve the funnel and Current/Next controls.

Owner-approved ordering (2026-09-06): (1) urgent requests and current or starting
within 15 minutes calendar events; (2) agent input/approval; (3) other actionable
tasks and finished results; (4) FYIs; (5) working agents. Within each band, sort by
triage priority, then oldest activity first, then stable item ID for deterministic ties.
Current persists by item identity, never advances from background reorder, and explicit
Next changes navigation without read/task mutation. FYI batches contain at most four
ordered members and preserve independent targeting. Exact batch Done and deferral
new-activity transitions remain pending owner answers.

## Actions and worker events

A proposed action carries owner, immutable proposal ID, type, exact target/parameters,
source/context revision, confirmation version, execution state and durable outcome.
Editing produces a new confirmation version. Shared handlers enforce authorization,
target scope, freshness and idempotency across assistant/task/timeline entry points.
Cancelled, stale and failed actions do not teach or advance. Successful correction
evidence is keyed to the operation and recoverable without repeating its external effect.
Draft preparation and explicit Next are immediate approved exceptions; automatic
triage/workflow authority is configured separately and still uses shared execution guards.

Worker events carry task/run/turn/request IDs, event ID/version, provider state and
question/approval payload. Reject stale-run replies and deduplicate replay. Workspace
creation, prompt acceptance, answer delivery, resumed work and explicit work completion
are distinct acknowledgments. Save final answer/checklist/artifacts before closing a run.
Unknown outbound delivery stays unknown until reconciled; do not retry a send blindly.

Task/source discussion, operation receipts and correction evidence have independent
lifetimes from chat archives. Chat cleanup defaults to 15 days; history reads never
perform cleanup. Preserve owner documents and confirmed rules without template overwrite.

## Migration and rollback gate

### Phase 1.1 foundation boundary

The first implementation section adds durable local identities, exact entity aliases,
explicit memberships, context/view fingerprints and an explicit historical-evidence
baseline operation. It does not yet switch the feed, assistant or UI consumers, and
does not activate display-does-not-read. PW-101 and PW-104 remain partial until those
consumers and the final semantics transition pass their own gates.

Baseline evidence is versioned and captured from uncapped raw records at one clock
and settings snapshot. Existing funnel-state rows remain verbatim, including keys
that cannot yet be resolved. A baseline must not become the final read boundary by
accident: capture/reconcile the final evidence atomically with the later semantics
switch. Never apply repeated legacy age or closure inference to post-cutover arrivals.

An alias resolves to an exact entity and its current canonical item. Item merges
retain redirects and history; a review receipt does not become a blanket receipt for
all item members. Multiple ideas referenced by a digest retain independent identities.
Existing messages have no reliable account/source identifier, so ambiguous historical
provider keys remain locally scoped; source display names cannot establish identity.

Substantive context fingerprints cover complete bodies, explicit members, meaningful
attachment metadata and material task context. View fingerprints additionally cover
drafts, statuses, priority, read/defer and worker attention. Identity stays stable
across those changes. Additive storage initialization alone performs no historical
capture or owner-state rewrite; foundation backfill tests use disposable databases.

The implemented foundation stores full context/view snapshots once per canonical
item and baseline version in the same transaction as identity, receipts and the
completion marker. Current snapshot getters compute revisions from persisted inputs
inside one read transaction; cached item columns are not freshness certification.
Worker attention is caller-supplied snapshot data, copied deeply. An unavailable
worker snapshot is distinct from an explicitly observed empty worker set. Full email
chain expansion and worker/discussion context adapters remain later phase work.

### Section 1.3 internal inventory boundary

Raw inventory enumeration reads every reconciled canonical root, its current
projection and coverage in one transaction. It does not run backfill in a getter.
Uncatalogued message/task/review/idea rows are explicit coverage gaps, including new
arrivals after a completed baseline. Raw counts are not eligible or unread counts;
unsupported adapters, including calendar, prevent claiming complete inbox coverage.

Pagination operates on an immutable caller-held snapshot. Tokens bind snapshot,
order and ranking facts; an updated snapshot requires an explicit restart. Optional
ranking facts name exact current item view revisions. They cannot establish read,
exclusion or actionability policy. These interfaces remain internal until consumers
and their migration/read transitions pass the later acceptance gates.

Legacy `norm_stamp` stores local wall-clock timestamps without a timezone. The pure
ordering foundation must diagnose timestamps it cannot compare reliably, rather
than silently interpret them as UTC or use the integration machine's timezone.
Timezone-aware, revision-bound activity facts can supply comparable timestamps.
A timezone adapter is required before activating this ordering for legacy consumers.

1. Create a synthetic legacy database using the accepted pre-migration schema. Record
   identity/member, funnel-state, task/review/run/history, attachment and document/settings
   snapshots. Include explicit historical done/skip/later, custom COUNSEL and grouped mail.
2. Implement additive schema and an idempotent transaction/journal. Retain original rows,
   aliases and provenance; backfill only justified states. No blanket read reset or
   reinterpretation of timestamps. Reopen twice and compare preservation snapshots.
3. Test interrupted migration, retry, old/new client compatibility and incremental writes.
   A rollback must preserve data written after migration; prefer a corrective migration.
   Git revert alone is not a database rollback. Document any incompatible older client.
4. Any eventual live migration requires a consistent SQLite backup (including WAL state)
   and attachment manifest immediately beforehand. Never copy only an active database file
   or automatically restore a backup over newer owner work. No live migration or restart
   is part of the Phase 0 test section.

## Reconciliations and unresolved policy

The plan's newer approvals supersede historical action menus, 20-day history hiding,
overlap queuing, confirmation before drafting/Next, and a second correction-memory prompt.
COUNSEL loader/truncation and queued-start preservation fixes already exist at 2689679;
they must be retained and revalidated, not implemented twice. Historical checked
document edits do not imply corresponding runtime behavior is implemented.

Pending owner answers: grouped read/handled semantics; returning
deferred items on new activity; standing-exclusion history scope; advancement after
non-handoff actions; clarification-send versus every-successful-reply closure. The
first questions were sent during Phase 0; unanswered questions remain pending, not approval.
Historical inferred reads are resolved: preserve old results, apply new display semantics
going forward (owner response 2026-09-06).
Five ordering bands and oldest-first activity tie direction are resolved by the
owner's second response on 2026-09-06, as specified above.
Browser-control ownership and UI remain unreviewed and excluded from implementation.

## Section 1.6 All consumer boundary

All adopts canonical membership independently of canonical Unread/read migration.
One displayed root represents all exact task/message/review members; independent
ideas retain their own roots and explicit relations. A source filter selects any
matching displayed member and binds detail/reply actions to that exact member.
Standalone task/idea/review details are available; `assistant:dock` infrastructure
and message-only context/history/skipped roots do not create rail entries. Calendar
continues through the existing separate adapter, with prep shown once under its event.

This consumer explicitly retains stored local wall-clock newest-first display order,
unknown timestamps last and stable item IDs for ties. It does not activate the pure
priority ordering adapter or infer UTC for old naive timestamps. The current common
history interval uses local insertion time, preserving newly ingested old mail.
Counts are filtered presented roots, with canonical root/tombstone/not-presented
counts separate. Frozen compact leases bind the query and expire after 120 seconds;
expired or unavailable coverage is explicit, never a successfully empty response.

Membership reconciliation is an owned background lifecycle with atomic generations;
GETs remain read-only. Detail rejects pending membership and moved exact members,
hydrates full content only on selection, and preserves owner draft edits on refresh.
The only transcript payload is prior-session metadata, not terminal text. No read
receipts, exclusions, Current/Next selection or browser-control policy change here.
