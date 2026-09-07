import test from "node:test";
import assert from "node:assert/strict";
import { LEVEL_META, LEVEL_ORDER, levelLabel, levelOf, levelsOf } from "../src/funnelPile.js";

// Unread is ranked, not chronological, so the heading names the LEVEL the rail is crossing.
// One level per thing triage decided: open work and landed results are not merged into a single name (the owner,
// 2026-09-07: "why work and reports combined ... just make each one it's own thing").
test("every level has its own word and its own hint", () => {
  assert.deepEqual(LEVEL_ORDER, ["urgent", "task", "reports", "fyi", "agents"]);
  for (const level of LEVEL_ORDER) {
    assert.ok(levelLabel(level).length, `${level} needs a word`);
    assert.ok(LEVEL_META[level].hint.length, `${level} needs a hint`);
  }
  assert.equal(new Set(LEVEL_ORDER.map(levelLabel)).size, LEVEL_ORDER.length, "no two levels share a word");
  assert.equal(levelLabel(""), "");
  assert.equal(levelLabel("nonsense"), "");
});

test("no level name merges two things", () => {
  for (const level of LEVEL_ORDER) assert.ok(!/[&+]|and/.test(levelLabel(level)), `${levelLabel(level)} names two things`);
  assert.equal(levelLabel("task"), "your task");
  assert.equal(levelLabel("reports"), "reports");
});

// One level for the owner's work, whoever is waiting on it - triage never split those - and a
// landed result is not work at all (the owner, 2026-09-07).
test("everything triage called work is one level, and a result is not in it", () => {
  for (const lane of ["asked", "queued", "broken", "approve", "blocked"]) {
    assert.equal(levelOf({ lane, order_band: 2 }), "task", lane);
  }
  assert.equal(levelOf({ lane: "report", order_band: 3 }), "reports");
  assert.equal(levelOf({ lane: "forgotten", order_band: 4 }), "fyi", "an idea nobody judged is an fyi");
  assert.ok(LEVEL_ORDER.indexOf("reports") > LEVEL_ORDER.indexOf("task"));
  assert.ok(LEVEL_ORDER.indexOf("fyi") > LEVEL_ORDER.indexOf("reports"));
});

test("the ends of the list are one level each", () => {
  assert.equal(levelOf({ lane: "time", order_band: 1 }), "urgent");
  assert.equal(levelOf({ lane: "fyi", order_band: 4 }), "fyi");
  assert.equal(levelOf({ lane: "working", order_band: 5 }), "agents");
  assert.equal(levelOf({}), "task", "a row with no band still lands in one, so the dock never reads empty");
});

test("the menu offers only the runs the pile holds, in the order the rail draws them", () => {
  const pile = [
    { lane: "fyi", order_band: 4 },
    { lane: "report", order_band: 3 },
    { lane: "approve", order_band: 2 },
    { lane: "asked", order_band: 2 },
  ];
  assert.deepEqual(levelsOf(pile), ["task", "reports", "fyi"]);
  assert.deepEqual(levelsOf([]), []);
  assert.deepEqual(levelsOf(null), []);
});
