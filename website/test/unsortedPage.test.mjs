// AN ARRIVAL THE AI COULD NOT SORT SAYS SO ON ITS PAGE (walk 12, 2026-11-23): the AI's budget ran out, Alex Doyle's question to Erin Blake
// failed sorting, and its page read "FYI" / "✓ Sorted: FYI" / "Nothing to decide" with no reason - the reason stood only on the rail. The
// page says the lane's own words and the reason the row carries; its way past is Sort it again (RetryVerbs), as on every unsorted row.
import test from "node:test";
import assert from "node:assert/strict";
import { sortedSays } from "../src/fyiRow.js";
import { WORD } from "../src/lanes.js";

const WHY = "AI triage failed (the AI's monthly budget is used up - it answers again when the budget resets or is raised) - unclassified; fix the AI connector and retry";

test("an unsorted arrival's page names its state and the reason, never FYI", () => {
  const s = sortedSays({ kind: "fyi", lane: "unjudged", why: WHY, title: "Trainly seat count for the renewal" });
  assert.equal(s.label, WORD.unjudged);
  assert.ok(!/fyi|sorted:/i.test(s.foot), s.foot);
  assert.equal(s.note, WHY);
});

test("...with no reason kept, the lane's own hint says it and points at Sort it again", () => {
  assert.match(sortedSays({ kind: "fyi", lane: "unjudged" }).note, /Sort it again/);
});

test("a sorted FYI keeps its words", () => {
  assert.deepEqual(sortedSays({ kind: "fyi", lane: "fyi" }), { label: "FYI", foot: "✓ Sorted: FYI", note: null });
});
