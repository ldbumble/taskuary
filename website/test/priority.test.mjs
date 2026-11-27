// THREE PRIORITIES (the owner, 2026-10-25): regular / important / urgent, the same words the server keeps (processing_order.level),
// a task saved before the change read in them, and important never wearing urgent's shade or moving a row.
import test from "node:test";
import assert from "node:assert/strict";
import { PRIORITIES, level, isImportant, urgentMark } from "../src/priority.js";
import { railStatus } from "../src/railStatus.js";
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

// THE JUDGE'S LOOK (walk 25, 2026-11-26): "the red dot stays on tasks I already finished" - an urgent task whose reply had gone read "agent done"
// with the urgent dot beside it. Urgent is on him now: answered or done, the row wears none; still owed, it wears it whatever its band
test("the urgent dot goes once the row is answered or done, and stands while it is owed", () => {
  const owed = { lane: "approve", kind: "review", priority: "urgent", draft: true }, asked = { lane: "asked", kind: "asked", priority: "urgent", urgent_request: true };
  assert.equal(urgentMark(owed, false, railStatus(owed)), true, "a reply waiting for his Send: band 2, the dot by its priority");
  assert.equal(urgentMark(asked, isUrgent(asked), railStatus(asked)), true);
  const sent = { lane: "yours", kind: "wrapup", chat_done: true, priority: "urgent" };
  assert.equal(railStatus(sent).role, "done");
  assert.equal(urgentMark(sent, isUrgent(sent), railStatus(sent)), false, "his reply went: no dot");
  const answered = { lane: "yours", kind: "asked", priority: "urgent", answered: true, status: { key: "answered", word: "you answered" } };
  assert.equal(railStatus(answered).word, "you answered", "the server's word, never the lane's 'on you'");
  assert.equal(urgentMark(answered, isUrgent(answered), railStatus(answered)), false);
  const closed = { lane: "yours", kind: "agentdone", priority: "urgent", closed: true };
  assert.equal(urgentMark(closed, false, railStatus(closed)), false, "an agent closed it");
  assert.equal(urgentMark({ ...owed, settling: true }, false, null), false);
  assert.equal(urgentMark({ lane: "yours", kind: "todo", priority: "important" }, false, null), false);
});
