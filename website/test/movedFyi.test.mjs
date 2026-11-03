import assert from "node:assert/strict";
import test from "node:test";
import { awayFromClear } from "../src/funnelPile.js";
import { dropHeld, ghostsOf, holds, keepHeld, movedEntry, refOf } from "../src/movedFyi.js";

/* SHOULD BE A TASK KEEPS THE FYI WHERE IT WAS (the owner, 2026-11-03): the line stays in FYI wearing where it went until the walk moves past
   the table it was pressed on - never on a clock. Invented Northwind world. */
const fyi = (k, t) => ({ key: k, kind: "fyi", lane: "fyi", order_band: 4, title: t, who: "Paula Vance", arrived_at: "2026-11-03 09:00:00" });
const batch = { key: "fyis:p:1,p:2,p:3", kind: "fyis", members: ["p:1", "p:2", "p:3"], items: [fyi("p:1", "Floor notice 1"), fyi("p:2", "Floor notice 2"), fyi("p:3", "Floor notice 3")] };

test("only an FYI line made a task is kept, by the row it was", () => {
  const m = movedEntry("p:2", 1290, null, [fyi("p:2", "Floor notice 2")], batch);
  assert.deepEqual([m.key, m.tid, m.ref, m.on, m.row.title], ["p:2", 1290, "TQ-1290", batch.key, "Floor notice 2"]);
  assert.equal(movedEntry("p:2", 7, null, [], batch).ref, "TQ-0007", "from the batch's own line when the rail has paged it out");
  assert.equal(movedEntry("t:9", 9, "TQ-0009", [{ key: "t:9", lane: "asked", tid: 9 }], null), null, "a task's own Put it on my list is no FYI");
  assert.equal(movedEntry("p:2", null, null, [fyi("p:2")], batch), null, "no task, nothing moved");
  assert.equal(refOf(12, "TQ-0012"), "TQ-0012");
});

test("it stays while the table holds it and goes when the walk moves past - a batch, or the task it became", () => {
  const m = { "p:2": movedEntry("p:2", 1290, "TQ-1290", [], batch) };
  assert.equal(keepHeld(m, { ...batch }), m, "the batch it was pressed in");
  assert.equal(keepHeld(m, { key: "p:2", tid: 1290, lane: "asked" }), m, "the task it became, at its place");
  assert.equal(keepHeld(m, { key: "task:1290", tid: 1290 }), m);
  assert.equal(keepHeld(m, null), m, "a move in flight lets nothing go");
  assert.deepEqual(keepHeld(m, { key: "fyis:p:4,p:5", kind: "fyis", members: ["p:4", "p:5"] }), {}, "the next batch");
  assert.deepEqual(keepHeld(m, { key: "t:3", tid: 3 }), {}, "another row opened");
  assert.deepEqual(dropHeld(m, batch), {}, "All read, next on its batch");
  assert.equal(dropHeld(m, { key: "t:3", tid: 3 }), m);
});

test("its ghost is its FYI row, wearing the task", () => {
  const [g] = ghostsOf({ "p:2": movedEntry("p:2", 1290, null, [fyi("p:2", "Floor notice 2")], batch) });
  assert.deepEqual([g.key, g.lane, g.title, g.moved], ["p:2", "fyi", "Floor notice 2", { tid: 1290, ref: "TQ-1290" }]);
  assert.ok(holds(batch, { key: "p:2", on: batch.key, tid: 1290 }));
  assert.equal(awayFromClear([{ level: "task", items: [{ key: "p:2", tid: 1290 }] }, { level: "fyi", items: [g, fyi("p:3")] }]), 2, "counted once, as the task");
});
