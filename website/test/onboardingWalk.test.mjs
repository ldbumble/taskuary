import test from "node:test";
import assert from "node:assert/strict";


import { walkAdvances } from "../src/walkStep.js";


// The one real decision in this file: does a move land on a stop, or end the walk. `walk.go`
// clamps anything outside the list to 0 and returns THAT, so branching on the response instead of
// the request would make Finish silently reopen stop 1 - this executes the predicate rather than
// grepping for a string that happened to look right.
test("walkAdvances lands on every real stop and ends on Finish or past the end", () => {
  const total = 14;
  assert.equal(walkAdvances(0, total), true);     // first stop
  assert.equal(walkAdvances(7, total), true);     // a middle stop
  assert.equal(walkAdvances(total - 1, total), true);  // last stop
  assert.equal(walkAdvances(total, total), false);     // one past the end
  assert.equal(walkAdvances(-1, total), false);        // Finish
});
