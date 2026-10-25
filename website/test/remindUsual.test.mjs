// THE LEARNED DAY, PRE-CHOSEN (the owner's ruling 7, 2026-10-23): Remind me opens with the weekday the owner puts this sender's mail off
// to, filled and first, saying whose habit it is - and nothing at all while no day has held. Pressing it is what sets it.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { usualLabel, usualWhy } from "../src/taskFilter.js";

test("the usual day reads as a weekday and its date, with whose habit it is", () => {
  const u = { on: "2026-10-30", day: "Friday", by: "renewals@payworth.example", n: 2, of: 2 };
  assert.equal(usualLabel(u), "Friday 30");
  assert.equal(usualWhy(u), "your usual for renewals@payworth.example");
  for (const none of [{}, null, undefined, { day: "Friday" }]) assert.equal(usualLabel(none), "");
});

test("the picker leads with it, sets nothing until it is pressed, and holds its row while it is read", () => {
  const src = readFileSync(new URL("../src/RemindMe.jsx", import.meta.url), "utf8");
  assert.match(src, /api\.get\(`\/api\/tasks\/\$\{task\.TaskId\}\/remind\/usual`\)/);
  assert.match(src, /onClick=\{\(\) => set\(usual\.on\)\}/, "only a press sets the day");
  assert.match(src, /usual === null \|\| usualLabel\(usual\)/, "the row keeps its height while the day is read");
  assert.ok(src.indexOf("data-tq-remind-usual") < src.indexOf("QUICK.map("), "the learned day comes first");
});
