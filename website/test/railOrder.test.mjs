import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";
import { arrivedAt, bandsOf, inOrder } from "../src/funnelPile.js";

// THE RAIL IS ONE FIXED ORDER (the owner, 2026-10-22: "set by time, oldest to newest and then never move ... on the table should
// never move them"): a row is placed by when it ARRIVED, and the row on the table is drawn in that place, never lifted to the top.
const at = (h) => new Date(Date.now() - h * 3600e3).toISOString().slice(0, 19).replace("T", " ");
const task = (key, h, extra = {}) => ({ key, kind: "todo", lane: "yours", order_band: 2, tid: Number(key.slice(5)), arrived_at: at(h), ...extra });

test("a task pulled onto the table from outside the pile is drawn in its place, not on top", () => {
  const rows = [task("task:1", 19), task("task:2", 17), task("task:3", 11)];
  const pulled = task("task:9", 12);
  assert.deepEqual(inOrder(rows, [pulled]).map((r) => r.key), ["task:1", "task:2", "task:9", "task:3"]);
  assert.deepEqual(inOrder(rows, [task("task:8", 1)]).map((r) => r.key), ["task:1", "task:2", "task:3", "task:8"]);
  const report = { key: "report:5", kind: "report", lane: "report", order_band: 3, arrived_at: at(2) };
  const drawn = bandsOf(inOrder(rows, [report]));
  assert.deepEqual(drawn.map((b) => b.level), ["task", "reports"]);
});

test("the gutter's age is the arrival the rows are ordered by, not the newest activity", () => {
  // the owner's screenshot: 19h, 17h, 11h, <30m and then 1h - the working task's age was its agent's start
  const working = task("task:4", 26, { lane: "working", since: at(1), when: at(0.2) });
  assert.equal(arrivedAt(working), working.arrived_at);
  assert.equal(arrivedAt({ since: "a", when: "b" }), "a");
});

test("the rail draws the pile in the server's order and the table row through inOrder", () => {
  const view = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");
  assert.match(view, /const drawn = inOrder\(/);
  assert.match(view, /band\(i\.kind === "meeting" \? i\.when : arrivedAt\(i\)\)/);
  assert.doesNotMatch(view, /\.\.\.\(curKey && !known \? \[pulledRow\(current\)\] : \[\]\),\s*\.\.\.onTable,\s*\.\.\.drawOrder/);
});
