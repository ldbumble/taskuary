// A REPLY DRAFT'S CHOICES ARE CLOSE OUT, REDRAFT OR MARK DONE (the owner, 2026-10-01: "rejected is useless - it should be
// redraft or close task"). Reject threw the draft away and left the task open, which is neither. A proposal keeps its
// Dismiss and a close-out its Not yet - neither is a reply draft. The server still takes "reject" from an old caller.
import test from "node:test";
import assert from "node:assert/strict";


import { rowOf } from "../src/actionRow.js";


test("the row draws Mark done once: the decision's, with the task's own left out of More", () => {
  const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
  const r = rowOf({ ref: "TQ-1", list: [v("approve", "decide", { tone: "p" }), v("4:redraft", "decide"), v("4:done", "decide", { closes: true }), v("done", "more"), v("next", "next")] });
  assert.deepEqual(r.decide.map((x) => x.id), ["approve", "4:redraft", "4:done"]);
  assert.ok(!r.more.some((x) => x.id === "done"), "not twice");
  const plain = rowOf({ ref: "TQ-1", list: [v("approve", "decide", { tone: "p" }), v("done", "more"), v("next", "next")] });
  assert.deepEqual(plain.agent.map((x) => x.id), ["done"], "a decision with no close of its own: Mark done on the bar beside it (2026-10-06)");
  assert.ok(!r.agent.some((x) => x.id === "done"), "and still not twice beside the draft's own");
});
