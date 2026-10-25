import test from "node:test";
import assert from "node:assert/strict";
import { bandsOf, inOrder, levelOf, placeId, placeOrder } from "../src/funnelPile.js";

// TWO ROWS IN THE SAME SECOND, ONE ORDER (2026-10-25): the page put a row back by its arrival alone - after every row of that second -
// while the server had it by a hashed key, and two dashboards filed by one run swapped as the rail moved (the dead-end walk's SWAP).
// The tie goes to the task number, then the first message, then the key: funnel.place_id, the same rows as
// tests/processing/test_same_second_tie.py. The keys here sort the other way round on purpose.
const at = "2026-10-25 06:00:00";
const report = (mid, hex) => ({ key: `processing:pi_${hex}`, lane: "report", kind: "report", member_ids: [`message:${mid}`], mid: null, arrived_at: at });
const rows = [report(11, "f0"), report(12, "c1"), report(13, "a2"), report(14, "07")];
const keys = (xs) => xs.map((x) => x.key);

test("a same-second tie goes to the first message, never the key or the order rows came in", () => {
  assert.deepEqual(keys([...rows].reverse().sort(placeOrder)), keys(rows));
  assert.deepEqual(keys([rows[2], rows[0], rows[3], rows[1]].sort(placeOrder)), keys(rows));
});

test("a row put back takes its place in the tie, and a pinned row keeps it", () => {
  for (const r of rows) assert.deepEqual(keys(inOrder(rows.filter((x) => x !== r), [r])), keys(rows), `${r.key} put back out of place`);
  for (const r of rows) {
    const band = bandsOf(rows.map((x) => (x === r ? { ...x, lane: "fyi" } : x)), { key: r.key, level: levelOf(r) }).find((b) => b.level === levelOf(r));
    assert.deepEqual(keys(band.items), keys(rows), `${r.key} pinned out of place`);
  }
});

test("the task number comes before the message, a known arrival before none, and the ids are read as the server reads them", () => {
  const goal = { key: "processing:pi_ff", tid: 40, lane: "asked", kind: "goal", arrived_at: at }, step = { ...goal, key: "processing:pi_00", tid: 41 };
  assert.deepEqual(keys([step, goal].sort(placeOrder)), [goal.key, step.key]);
  assert.deepEqual(keys([rows[0], { ...rows[1], tid: 99 }].sort(placeOrder)), [rows[1].key, rows[0].key], "a task row leads its second");
  assert.deepEqual(keys([{ ...rows[0], arrived_at: null }, rows[1]].sort(placeOrder)), [rows[1].key, rows[0].key]);
  assert.deepEqual(placeId({ key: "k", tid: "7", member_ids: ["task:7", "message:9", "message:3"] }), [0, 7, 1, 0, "k"]);
  assert.deepEqual(placeId({ key: "k", member_ids: ["message:9", "message:3"] }), [1, 0, 0, 3, "k"]);
  assert.deepEqual(placeId({ key: "k", tid: true, mid: "x" }), [1, 0, 1, 0, "k"]);
});
