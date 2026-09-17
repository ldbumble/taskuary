# The census reacts to the rows that changed

2026-09-17 · design · not yet built

## The problem, measured

`reconcile_membership` rebuilds every processing item from every row of six tables, on every
pass, to notice that one email arrived. On the owner's database (91 MB, 8,138 messages):

| | |
|---|---|
| settled pass, before today's filter | ~350 ms |
| settled pass, after it | ~177 ms |
| rows read per pass | 9,458 entity + 17,382 `processing_*` |
| `execute()` calls per pass | 36,721 |
| passes during one startup catch-up | 100+ (worker ticks at 0.25 s while writes arrive) |
| what the pass concludes, almost always | `created=0 moved=0 retired=0` |

It holds `store.lock` and `BEGIN IMMEDIATE` throughout, which is why `/api/funnel/pile` took
8.2 s and `/api/agents` 15.3 s during the 2026-09-17 catch-up.

**It is O(all history), and history is the thing that only grows.** At the measured rate of
100 kept messages a day, the census reads ~75,000 messages in two years to notice one arrival.
Today's `UNGROUPED_MESSAGE_STATUS` filter (49d0bc6d) removed the dominant term — 71% of arrivals
are flood mail — but it bought time rather than changing the shape.

## What the census is actually for

Not dedupe (`message_exists` on `ExternalId`, at ingest, 0.01 ms). Not "does this task exist"
(`identity_route`, at ingest, by conversation id). Both are settled before it runs.

It maintains one invariant: **every record belongs to the right durable item, and an item that
stopped being the answer forwards to the one that is.** Worked example from live data:

```
message 3071  "September Flyer"
  2026-09-06  arrives with no task → its own item pi_dad27…
  2026-09-15  gets TaskId=559      → belongs with task 559's item pi_5cd9c…

  census: retire member(3071 → pi_dad27…), create member(3071 → pi_5cd9c…),
          pi_dad27… now empty, and RedirectItemId → pi_5cd9c…
```

That redirect is the point. Read receipts, `funnel_state` keys, and open page cursors recorded
`pi_dad27…`; the arrow is what keeps them landing on the right row.

**How often that happens: 108 member moves and 78 item merges across the database's entire
life.** The full recount runs continuously to catch it.

## Why a partial pass is possible

Every grouping edge is a child naming its parent:

```
task                        → its own group
message.TaskId              → that task's group, else its own
review.MessageId (wins) / .TaskId → that group, else its own
idea  action.tid, or task.SourceRef == 'assistant:idea:<id>' → that task's group, else its own
attachment.MessageId        → that message's group
run.TaskId                  → that task's group
```

A new message names its task. It cannot change what any other message names. The information
needed to place it is already in its own row.

Two things are not purely local, and the design has to carry them:

1. **Adoption runs backwards.** A *new task* with `SourceRef='assistant:idea:42'` re-parents an
   *existing idea*. The changed row is the task, so the edge is still reachable from it — but
   only with an index that does not exist (`task` has no indexes at all today).
2. **Root election is ordered.** Which durable id a group keeps is decided over globally sorted
   groups with reservation and tie-breaks, so group N's outcome can depend on groups 1..N−1.

## Design

### 1. The trigger records what changed, not that something did

Today every trigger does `DirtyGeneration = DirtyGeneration + 1` and nothing else. That bare
counter is the reason a full re-read is the only thing the census *can* do.

```sql
CREATE TABLE processing_dirty (
  DirtyId    INTEGER PRIMARY KEY,
  EntityKind TEXT NOT NULL,   -- task | message | review | idea | attachment | run
  LocalId    TEXT NOT NULL,
  At         TEXT NOT NULL
);
```

The **six** membership tables enqueue a row *and* bump the generation. The **five**
display-only tables (`route`, `comment`, `funnel_state`, `task_artifact`, `transcript`) keep
bumping the generation and enqueue nothing — they cannot move an entity.

This is what `test_census_reads_only_what_it_needs.py` warns against removing, and the design
must not remove it. The chain that makes another process's write visible here is
trigger → census → `self._writes += 1` → display cache invalidated. It survives intact: a
generation bump with an empty queue becomes a pass that reconciles nothing, bumps `_writes`,
advances the generation, and returns — microseconds instead of 177 ms. The invariant is kept
and the cost of keeping it disappears.

### 2. Scope: load the small tables whole, the big ones by need

The volume is messages and attachments; everything else is small and slow-growing.

| table | rows today | growth | in scope |
|---|---|---|---|
| message | 8,138 | ~100/day | **only those affected** |
| attachment | 434 | slow | **only those affected** |
| task | 417 | ~3/day | load all |
| idea | 308 | slow | load all |
| review | 147 | slow | load all |
| run | 10 | slow | load all |

Loading tasks and ideas whole keeps the adoption rule (`spawned`) exactly as it is written
today — no reverse index needed, no new failure mode — at a cost that stays under a few
thousand rows for years. It removes the hardest part of the closure for almost none of the win.

Revisit only if `task` passes ~50k rows.

### 3. The affected set

For each entity in the queue, collect:

1. **Its current item**, via `processing_member WHERE EntityKind=? AND LocalId=? AND RetiredAt IS NULL`
   — this is the group it may be leaving.
2. **Its new parent's group**, by following its own foreign key.
3. **Every other member of both items**, so the group is whole.
4. For a changed or deleted **message**: its reviews (`idx_review_message`) and attachments
   (`idx_attachment_message`).
5. For a changed or deleted **task**: its messages (`idx_message_task`), reviews
   (`idx_review_task`), runs (`idx_run_task`).

Then close transitively over shared items until the set stops growing (depth 1–2 in practice).

**The invariant that makes the partial pass sound: the scope is closed under "shares an item".**
Root election can only contend between groups that currently hold the same item id, and any
group holding an in-scope item is itself in scope. So the ordered election runs over the
subgraph and reaches the same answer it would have reached globally.

This is the load-bearing claim of the design and it is what the verification in §5 exists to
falsify.

### 4. The partial pass

`reconcile_membership` keeps its rules and gains a scope. One mechanical change matters:

```python
raw_entities = {...}    # today: every row in the database
                        # becomes: every row IN SCOPE
```

The retire loop walks `current` and retires any member whose entity is absent from
`raw_entities`. Under a partial pass that would retire every member outside the scope. So the
retire loop must iterate **only over in-scope members** — absence outside the scope means "not
loaded", not "deleted".

Getting that one distinction wrong empties the Timeline, so it wants a test that asserts a
member outside the scope is untouched by a partial pass.

Queue rows are deleted in the same transaction that consumes them, so a failed pass replays.

### 5. Verification: shadow compare

The design is only worth building if we can show it agrees with the full census.

- **A `shadow` mode**: run the partial pass, then a full census on the same snapshot, and assert
  the resulting `processing_member` / `processing_item` state is byte-identical. Any divergence
  logs both and falls back to the full result.
- **Run it across the existing corpus**: `tests/processing/` is 40 files and there is a demo
  replay (`test_processing_demo_replay.py`) plus `fixtures.py`. Every one of them should pass
  with the partial pass forced on.
- **Then on real data**: the owner's database has 108 historical moves and 78 merges. Replay
  them against both algorithms and require identity.
- Ship behind a setting, shadow in production for a week, then make it the default.

### 6. Fallback, and staying honest

A full census remains the ground truth and runs when: the queue was lost or truncated, a pass
raises, a conflict appears, the schema version moves, or on an explicit
`POST /api/processing/reconcile?full=1`. Plus a scheduled full pass (daily, off-peak) as
self-heal, with `processing_reconcile_state` recording which mode last ran and when.

An install that never trusts the partial path still works — slowly, exactly as today.

## Out of scope

- The **debounce** (don't census per write; census when the burst pauses). Orthogonal, smaller,
  and worth doing independently — it cuts how *often*, this cuts how *much*.
- The three per-row query loops (`have_primary` 16,532, alias 10,134, redirect 9,239 — ~96 ms
  combined). They shrink on their own once the scope shrinks.
- Cleaning up the ~5,631 tombstone items left by 49d0bc6d. They still load each pass; a
  separate, easy job once this lands.
- Any change to what the grouping *rules* are. This changes how much is read, never the answer.

## Open decisions

1. **Shadow in production behind a setting, or tests only?** Recommend production shadow for a
   week — the interesting cases are in real data, and 108 moves is not many to learn from.
2. **How often should the self-heal full census run?** Recommend daily, off-peak.
3. **Is the "closed under shared item" invariant enough for root election?** Highest-risk claim
   in the document. It should be attacked deliberately before implementation — construct a case
   where two groups contend for an id and only one is in scope, and either exhibit it or prove
   it cannot happen.

## Expected result

The pass stops scaling with history and starts scaling with arrivals: a handful of rows per
changed entity instead of ~9,500 rows and 36,721 queries. A generation-only bump — about half
of all bumps during intake, because every message writes a `route` row — costs nothing at all.

The two-year projection stops mattering, which is the point.
