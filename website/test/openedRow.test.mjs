import { test } from "node:test";
import assert from "node:assert/strict";
import { withOpened } from "../src/funnelPile.js";

// THE TASK HE HAS OPEN STANDS ON THE RAIL (the owner, 2026-11-22; walk 5: a closed task opened from Search had no row and nothing ringed)
test("the task he has open stands on the rail in Tasks, as it now reads - never a stale copy, never twice", () => {
  const pile = { items: [{ key: "review:3", tid: 3, lane: "approve" }] };
  const done = { key: "task:7", tid: 7, lane: "done", title: "Find caterers" };
  const got = withOpened(pile, done).items.at(-1);
  assert.equal(got.tid, 7); assert.equal(got.order_band, 2); assert.ok(got.opened);
  assert.equal(withOpened(pile, { ...done, offRail: true }), pile, "a kept copy lends no row");
  assert.equal(withOpened(pile, { key: "review:3", tid: 3 }), pile, "one the rail holds is not drawn twice");
  assert.equal(withOpened(pile, null), pile);
});
