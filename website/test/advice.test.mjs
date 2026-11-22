// The pure piece of the filled button (website/src/advice.js): what the strip lights for the item on the table.
// A real function under test, not a source regex.
import test from "node:test";
import assert from "node:assert/strict";
import { stripWord } from "../src/advice.js";

// C2 (the UI audit, 2026-10-21): the strip's word and the lit button are one decision (advice.stripWord)
test("a working agent lights Next and says nothing, and no missing AI lights a Connect (the owner, 2026-11-15)", () => {
  const w = stripWord({ speaks: true, key: "task:9", lane: "working" });
  assert.deepEqual(w, { pick: { verb: "next", line: "", for: "task:9" } });
  const s = { verb: "send_close", line: "x" };
  assert.equal(stripWord({ speaks: true, shown: s, key: "k", lane: "asked" }).pick, s, "a decision lights its verb");
  assert.deepEqual(stripWord({ speaks: true, advice: { none: "nothing", for: "k" }, key: "k", lane: "asked" }).pick, { verb: "next", line: "", for: "k" }, "any none: Next, silent");
});

// WHEN THE STRIP SPEAKS (the owner, 2026-10-13: "not while waiting or walking through things"): only the decision read for the
// item on the table now, only at rest; an agent at work is Next; and the OBVIOUS move is silent - lit, said by nothing (2026-10-23)
test("the strip speaks only for the item on the table, at rest, and an agent at work is Next", async () => {
  const { adviceShown } = await import("../src/advice.js");
  const a = { verb: "continue", line: "You usually continue it.", for: "processing:7" };
  const item = { key: "processing:7", lane: "blocked" };
  assert.equal(adviceShown(a, item, false), a);
  assert.equal(adviceShown(a, { key: "processing:8", lane: "blocked" }, false), null, "the last item's line over the next one");
  assert.equal(adviceShown(a, item, true), null, "an act in flight");
  assert.deepEqual(adviceShown(a, { ...item, lane: "working" }, false), { ...a, verb: "next", line: "", state: "working" }, "an agent continued and at work");
  assert.equal(adviceShown({ ...a, for: undefined }, item, false), null, "a line nobody read for this table");
  assert.equal(adviceShown(a, null, false), null);
  assert.deepEqual(adviceShown({ ...a, line: "" }, item, false), { ...a, line: "" }, "a silent decision still lights its button");
  assert.equal(adviceShown({ ...a, verb: null }, item, false), null, "a decision that lights nothing (an agent asking) is not shown");
});

