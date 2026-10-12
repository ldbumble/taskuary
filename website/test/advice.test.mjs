// The two pure pieces of the Advisor's prompt box (website/src/advice.js): which live event is about the item on the
// table, and what the ghost text says. Real functions under test, not source regexes.
import test from "node:test";
import assert from "node:assert/strict";
import { adviceKeyFor, ghostText } from "../src/advice.js";

test("an advice event is about the item on the table when it names its key or one of its aliases", () => {
  const cur = { key: "processing:pi_1", aliases: ["msg:3", "agent:1", "task:1"] };
  assert.equal(adviceKeyFor({ key: "task:1" }, cur), "processing:pi_1");          // the event carries the legacy key, the table the rail's
  assert.equal(adviceKeyFor({ key: "processing:pi_1" }, cur), "processing:pi_1");
  assert.equal(adviceKeyFor({ key: "task:2" }, cur), null);
  assert.equal(adviceKeyFor({ key: "task:1" }, "task:1"), "task:1");               // a bare key still works
  assert.equal(adviceKeyFor({ key: "task:1" }, null), null);
  assert.equal(adviceKeyFor({}, cur), null);
});

test("the ghost text is the line, capped, then the way to answer; the phone keeps its own short hint", () => {
  assert.equal(ghostText("You usually merge it here.", false), "You usually merge it here. Tell me what to do with it, or press…");
  const long = "x".repeat(200);
  const g = ghostText(long, false);
  assert.ok(g.length < 140 && g.endsWith(" Tell me what to do with it, or press…") && g.includes("…"));
  assert.equal(ghostText("anything", true), null);
  assert.equal(ghostText("", false), null);
});
