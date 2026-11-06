import test from "node:test";
import assert from "node:assert/strict";
import { checkBackLine, checkBackOf, checkBackWhen } from "../src/checkBack.js";

test("a check-back reads as a short day and an hour", () => {
  const now = new Date(2026, 10, 6, 15, 0);                       // Fri Nov 6, 3 PM local
  assert.equal(checkBackWhen("2026-11-10 09:00:00", now), "Tue 9 AM");
  assert.equal(checkBackWhen("2026-11-07 14:30:00", now), "Sat 2:30 PM");
  assert.equal(checkBackLine("2026-11-10 09:00:00", now), "Checks back Tue 9 AM");
  assert.equal(checkBackWhen("2026-11-20 09:00:00", now), "Nov 20 9 AM");   // a week or more away names its date
  assert.equal(checkBackLine("", now), ""); assert.equal(checkBackLine("not a date", now), "");
});

test("only an open task with one waiting has a chip", () => {
  assert.deepEqual(checkBackOf({ CheckBackAt: "2026-11-10 09:00:00", CheckBackWhat: "the refund cleared", Status: "open" }),
    { at: "2026-11-10 09:00:00", what: "the refund cleared" });
  assert.equal(checkBackOf({ CheckBackAt: "", Status: "open" }), null);
  assert.equal(checkBackOf({ CheckBackAt: "2026-11-10 09:00:00", Status: "done" }), null);
  assert.equal(checkBackOf(null), null);
});
