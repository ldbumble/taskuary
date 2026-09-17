# The rail ranks, the assistant takes — design (2026-09-17)

**Goal.** A Next press ("Next", "All read, Next") puts the next four on screen in **≤ 0.7 s**. The
assistant is the point guard: it marks read / done / hands to an agent. It never rebuilds or ranks
the rail — the work timeline (the rail) ranks, including urgency, and the assistant takes from it.

**Where the 4 s goes today** (live log, 15:53, quiet app, after the batch-key fix 18c62bc8):

| step | what | ms |
|---|---|---|
| settle | receipts on the four | 30 |
| reload 1 | client discards its capture and refetches the rail → **full rebuild** | 1,460 |
| turn | `_navigation_reservation` rebuilds the rail again to validate the pick (warm here); provider refresh **before** answering; writes | 540 |
| reload 2 | `landed()` refetches the rail → **full rebuild** (the turn wrote) | 2,030 |

A rebuild is `processing_inventory_snapshot(display_only=True)`: re-project every root in the
14-day window (~1,100 roots, ~20 queries each), `compact_inventory`, cards, then `present` stamps
every card by hashing its full backing. The display cache is keyed on the store's write counter
(`_writes - _processing_ignored_writes`), so **any** write — the press's own receipt, the
`surfaced` mark, a comment, a transcript line, a sync in another process — throws the whole
snapshot away. No model is called anywhere on this path.

Four changes, landed and measured one at a time.

---

## A. The rail updates incrementally

*Re-project the roots a write touched; reuse the rest.*

**Dirty rows, not only a counter.** The `processing_dirty_<table>_<insert|update|delete>` triggers
(store.py, `PROCESSING_DIRTY_TABLES`) keep bumping `DirtyGeneration` (the census reads it) and
**also** insert into a new table:

```
processing_dirty_row(Generation INTEGER, Kind TEXT, LocalId TEXT)
```

`Kind` is the entity the row belongs to, `LocalId` its id in that table, written by the trigger
from `NEW`/`OLD` (both on UPDATE when the key changes). It lives in the database, so a write from
the sync process or the membership worker is seen exactly as the counter is today
(`dirty-triggers-are-cross-process`). The setting triggers write `Kind='setting'` (meaning: all).

Tables added to the trigger set because the rail reads them and nothing marks them today:
`processing_read_receipt`, `processing_read_defer` (Kind = EntityKind, LocalId), `processing_member`
and `processing_relation` (Kind = `item`, LocalId = ItemId — both old and new on a move),
`processing_display_summary` (Kind = `state`, LocalId = Key), `report_run` (Kind = `message`).

**Mapping a dirty row to roots** (one query per kind, batched):
- `message/task/review/idea/attachment/comment/task_artifact/run/route/transcript` →
  `processing_member(EntityKind, LocalId)` → ItemId → follow redirects → root. A row with no
  member (not catalogued yet) is not a root's business until the census files it, which writes
  `processing_member` — itself dirty.
- `state` (`funnel_state` and `processing_display_summary`, LocalId = Key): `processing:<id>` → root; a legacy key →
  `processing_alias` → root.
- `item` (member/relation): the ItemId, followed to its root; a retired root drops out.
- `setting`: everything.

**The cache.** `Store._root_cache = {root_id: projection}` plus `_root_cache_generation` and the
window it was built for (`history_days`, day). On a display read:
1. `dirty = SELECT Kind, LocalId FROM processing_dirty_row WHERE Generation > cached_generation`.
   Empty → nothing re-projects (this is #4 from the census work: a no-op reconcile writes nothing).
2. Resolve to roots; add new roots in the window; drop roots gone from `processing_item`.
3. `_processing_snapshot_cursor(...)` only for those; every other projection is **the same
   object** (they are treated as immutable; `apply_workers` builds new dicts only for the roots a
   worker row touches, as it already does per item).
4. `snapshot_revision` = hash over the roots' `(item_id, context_revision, view_revision)` plus
   coverage — not `json.dumps` of 12.8 MB. The cache-hit path stops deep-copying the snapshot; the
   reader gets the shared projections and the presentation layer copies what it mutates.

**Trimming.** `processing_dirty_row` older than `max(DirtyGeneration) - 10,000` rows is deleted at
the end of a reconcile pass. A cache whose generation is older than the oldest kept row rebuilds
fully (the safe fallback, and what a fresh process does).

**What must stay true (test matrix, all in `tests/processing/test_rail_incremental.py`):**
- For each dirty kind, one write that changes one item's card — task Status, a comment, a receipt,
  a defer, a run, a route, `funnel_state` surfaced, a transcript, a member move, a display summary,
  a setting — through (a) the store and (b) a second `sqlite3` connection (another process): the
  card changes on the next read, and every other root's projection is `is`-identical to before.
- A root that leaves the window (age) or is retired disappears; a new root appears.
- Trimmed log → full rebuild → same result as an untouched cold build (compare snapshots).
- `worker_attention` overlay still re-hashes only the owned root.
- The existing display-API tests keep passing unchanged (the contract of the snapshot is the same).

**Expected:** rail read after a press 1.5–2 s → **~0.3–0.5 s** (compact + cards + stamp remain).

## B. Next takes from the rail

*One build per press, and it is the rail's, not the assistant's.*

- The rail build already carries a generation (`funnel._CACHE['generation']`, surfaced to the
  client as `selection_revision`). The client **keeps** its capture between presses:
  `advance()` and `verb === 'next'` stop nulling `selectionRef`; `loadState()` keeps nulling it
  (a new chat is a new table).
- The turn validates against the **cached** rail: `_navigation_reservation` →
  `capture_selection(pile=funnel.pile(store))`. Same generation as the client's capture → take the
  four. Moved → take the fresh rail's four and say so in the answer; the 409 guard stays for the
  one case PW-050 protects — the item the client showed as next is not the one being taken.
- After `concierge.surface` writes, the turn reads the rail once more (incremental, A) and returns
  it in `done` as `pile`. `landed(data)` draws `data.pile` (`refreshPilePresentation`) and captures
  the selection from it; it no longer calls `loadPile(true)`. The live `feed-changed` after the
  turn is already suppressed by `coveredByReload`.
- Ensure-before-press disappears with the capture kept; `ensureNextSelection` remains as the
  fallback when there is no capture (first press after mount, after a filter change).

**Expected:** press = settle 30 ms + turn (take ~50 ms + writes + one incremental rail) ≈ **≤ 1 s**.

## C. The change-check follows the four

*Answer first; ask the provider after; update the card if it moved.*

Today `_refresh_next_selection` polls the provider for the picked item(s) **inside** the turn,
before the answer, and re-picks if the thread got newer mail. New: for `mode == 'next'` the turn
does not poll. After `done` is sent, the server runs `_refresh_items(members)` on a thread. If
mail arrived, ingest writes → dirty rows → `feed-changed` → the client's incremental reload →
`currentItemFromPile` sees `fresh.mid !== cur.mid` → the existing strip notice ("New message from …
arrived … The context is refreshed.") and the refreshed card. The item on the table is **not**
re-picked by the background refresh; it is updated in place. `open` and `say` keep their up-front
refresh (a typed question is about the words, and the day's open is not on a stopwatch).

**Expected:** the turn loses its network wait (100–1,000 ms live, provider-dependent).

## D. Stamp only what changed

`present` (funnel_presentation) fetches every card's backing tables and hashes them into
`presentation_revision` on every rail read (~300 ms for ~350 cards). Cache
`(key, context_revision, view_revision) → (presentation_revision, backing)` on the store; fetch and
hash only cards whose revisions changed. The proven `_backings` batching stays for those.

**Expected:** rail read **~0.2–0.3 s**; press **≈ 0.5–0.7 s**.

---

## Order, measurement, landing

A → B → C → D, each its own commit with the full suite, each remeasured on the live app: the
request log (`GET /api/funnel/pile`, `POST /api/concierge/stream`, `POST /api/funnel/settle`) and
the py-spy sampler including idle threads (recipe in memory `batch-key-full-history-build`). The
numbers above are the acceptance test; if a step does not deliver its number, stop and look before
the next.

## Out of scope

- Making the membership census itself incremental (separate design; A gives it the dirty rows it
  would need).
- The lock: a dedicated reader connection so rail reads do not queue other requests. Worth doing
  after D, when the reads are short enough that queueing is the larger cost.
- `stopped` as an owner-wait lane in the walk order (asked separately, not decided).
