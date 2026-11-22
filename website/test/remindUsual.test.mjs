// THE LEARNED DAY, PRE-CHOSEN (the owner's ruling 7, 2026-10-23): Remind me opens with the weekday the owner puts this sender's mail off
// to, filled and first, saying whose habit it is - and nothing at all while no day has held. Pressing it is what sets it.
import test from "node:test";
import assert from "node:assert/strict";

import { usualLabel, usualWhy } from "../src/taskFilter.js";

test("the usual day reads as a weekday and its date, with whose habit it is", () => {
  const u = { on: "2026-10-30", day: "Friday", by: "renewals@payworth.example", n: 2, of: 2 };
  assert.equal(usualLabel(u), "Friday 30");
  assert.equal(usualWhy(u), "your usual for renewals@payworth.example");
  for (const none of [{}, null, undefined, { day: "Friday" }]) assert.equal(usualLabel(none), "");
});
