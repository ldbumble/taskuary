import test from "node:test";
import assert from "node:assert/strict";
import { RUN_META, RUN_ORDER, runLabel, runOf, runsOf } from "../src/funnelPile.js";

// Unread is ranked, not chronological, so the heading over it names the RUN the rail is crossing.
// One run, one thing: open work and landed results are not merged into a single name (the owner,
// 2026-09-07: "why work and reports combined ... just make each one it's own thing").
test("every run has its own word and its own hint", () => {
  assert.deepEqual(RUN_ORDER, ["urgent", "needs", "work", "reports", "fyi", "agents"]);
  for (const run of RUN_ORDER) {
    assert.ok(runLabel(run).length, `${run} needs a word`);
    assert.ok(RUN_META[run].hint.length, `${run} needs a hint`);
  }
  assert.equal(new Set(RUN_ORDER.map(runLabel)).size, RUN_ORDER.length, "no two runs share a word");
  assert.equal(runLabel(""), "");
  assert.equal(runLabel("nonsense"), "");
});

test("no run name merges two things", () => {
  for (const run of RUN_ORDER) assert.ok(!/[&+]|and/.test(runLabel(run)), `${runLabel(run)} names two things`);
  assert.equal(runLabel("work"), "work");
  assert.equal(runLabel("reports"), "reports");
});

test("a landed result is its own run, below the work in the same band", () => {
  assert.equal(runOf({ lane: "asked", order_band: 3 }), "work");
  assert.equal(runOf({ lane: "queued", order_band: 3 }), "work");
  assert.equal(runOf({ lane: "broken", order_band: 3 }), "work");
  assert.equal(runOf({ lane: "forgotten", order_band: 3 }), "work");
  assert.equal(runOf({ lane: "report", order_band: 3 }), "reports");
  assert.ok(RUN_ORDER.indexOf("reports") > RUN_ORDER.indexOf("work"));
});

test("the other bands are one run each", () => {
  assert.equal(runOf({ lane: "time", order_band: 1 }), "urgent");
  assert.equal(runOf({ lane: "approve", order_band: 2 }), "needs");
  assert.equal(runOf({ lane: "blocked", order_band: 2 }), "needs");
  assert.equal(runOf({ lane: "fyi", order_band: 4 }), "fyi");
  assert.equal(runOf({ lane: "working", order_band: 5 }), "agents");
  assert.equal(runOf({}), "work", "a row with no band still lands in one, so the dock never reads empty");
});

test("the menu offers only the runs the pile holds, in the order the rail draws them", () => {
  const pile = [
    { lane: "fyi", order_band: 4 },
    { lane: "report", order_band: 3 },
    { lane: "approve", order_band: 2 },
    { lane: "asked", order_band: 3 },
  ];
  assert.deepEqual(runsOf(pile), ["needs", "work", "reports", "fyi"]);
  assert.deepEqual(runsOf([]), []);
  assert.deepEqual(runsOf(null), []);
});
