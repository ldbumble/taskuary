// The pure piece of the Advisor's line (website/src/advice.js): which live event is about the item on the table.
// A real function under test, not a source regex.
import test from "node:test";
import assert from "node:assert/strict";
import { adviceKeyFor } from "../src/advice.js";

test("an advice event is about the item on the table when it names its key or one of its aliases", () => {
  const cur = { key: "processing:pi_1", aliases: ["msg:3", "agent:1", "task:1"] };
  assert.equal(adviceKeyFor({ key: "task:1" }, cur), "processing:pi_1");          // the event carries the legacy key, the table the rail's
  assert.equal(adviceKeyFor({ key: "processing:pi_1" }, cur), "processing:pi_1");
  assert.equal(adviceKeyFor({ key: "task:2" }, cur), null);
  assert.equal(adviceKeyFor({ key: "task:1" }, "task:1"), "task:1");               // a bare key still works
  assert.equal(adviceKeyFor({ key: "task:1" }, null), null);
  assert.equal(adviceKeyFor({}, cur), null);
});
