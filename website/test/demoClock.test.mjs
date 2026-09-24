import test from "node:test";
import assert from "node:assert/strict";
import { rebase, parseStamp } from "../src/demoClock.js";

test("the demo's moments move to the visitor's now; its dates-as-data do not", () => {
  const now = parseStamp("2026-10-20 12:00:00");
  const got = rebase({ at: "2026-09-03 10:23:00", before: ["2026-09-03 09:23:00"], day: "2026-08-18", n: 3, x: null },
    "2026-09-03 10:23:00", now);
  assert.equal(got.at, "2026-10-20 12:00:00");
  assert.equal(got.before[0], "2026-10-20 11:00:00");            // an hour before it is still an hour ago
  assert.equal(got.day, "2026-08-18");                             // a report's day column is data
  assert.equal(rebase({ a: "2026-09-03 10:23:00" }, "not a stamp", now).a, "2026-09-03 10:23:00");
});
