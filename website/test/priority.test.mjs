// THREE PRIORITIES (the owner, 2026-10-25): regular / important / urgent, the same words the server keeps (processing_order.level),
// a task saved before the change read in them, and important never wearing urgent's shade or moving a row.
import test from "node:test";
import assert from "node:assert/strict";
import { PRIORITIES, level, isImportant } from "../src/priority.js";
import { isUrgent, attentionBand } from "../src/lanes.js";

test("exactly three, and every old word lands on one of them", () => {
  assert.deepEqual(PRIORITIES, ["regular", "important", "urgent"]);
  assert.deepEqual(["low", "normal", "high", "urgent", "", null, "Important", "whatever"].map(level),
    ["regular", "regular", "important", "urgent", "regular", "regular", "important", "regular"]);
});

test("important is a mark of its own: never urgent's shade, never a band, and urgent outranks it", () => {
  const ask = { key: "task:7", kind: "asked", lane: "asked", tid: 7, priority: "important" };
  assert.equal(isUrgent(ask), false, "important is not urgent");
  assert.equal(attentionBand(ask), attentionBand({ ...ask, priority: "regular" }), "importance never moves a row");
  assert.equal(isImportant(ask), true);
  assert.equal(isImportant({ ...ask, priority: "high" }), true, "a task saved as high reads important");
  assert.equal(isImportant(ask, true), false, "an urgent row wears urgent's shade alone");
  assert.equal(isImportant({ ...ask, settling: true }), false);
  assert.equal(isImportant({ ...ask, priority: "normal" }), false);
});

test("the three wear the app's own colours: sage, the brand's slate, the one oxblood - no new hues", async () => {
  const { readFileSync } = await import("node:fs");
  const theme = readFileSync(new URL("../src/theme.jsx", import.meta.url), "utf8");
  assert.match(theme, /PRIORITY_COLOR = \{ regular: PALETTE\.sage, important: PALETTE\.slate, urgent: PALETTE\.oxblood \}/);
  assert.match(theme, /slate: "#55697a"/);
});
