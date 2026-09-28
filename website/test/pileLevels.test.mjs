import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";
import { LEVEL_META, LEVEL_ORDER, levelLabel, levelOf, levelsOf } from "../src/funnelPile.js";

// Unread is ranked, not chronological, so the heading names the LEVEL the rail is crossing.
// One level per thing triage decided: open work and landed results are not merged into a single name (the owner,
// 2026-09-07: "why work and reports combined ... just make each one it's own thing").
test("every level has its own word and its own hint", () => {
  assert.deepEqual(LEVEL_ORDER, ["urgent", "task", "reports", "fyi", "passed", "agents"]);
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
  // work you pressed Next on waits at the bottom, beside the agents - still yours, not at the top
  assert.equal(levelOf({ lane: "stopped", order_band: 2, surfaced: true }), "passed");
  assert.equal(levelOf({ lane: "stopped", order_band: 2 }), "task");
  assert.equal(levelOf({ lane: "time", order_band: 1, surfaced: true }), "urgent", "a meeting about to start never moves down");
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

test("the card on the table keeps its band - it is passed only once Next moves you on", () => {
  const view = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");
  assert.match(view, /bandsOf\(drawn\.map\(\(i\) => \(i\.surfaced && atTable\(i\) \? \{ \.\.\.i, surfaced: false \} : i\)\)\)/);
});

// the owner, 2026-09-28: "the work rail still read agents working for a split second into your task, then goes back"
test("the card on the table never moves its row: the rail's lane and shown mark win", async () => {
  const { placed, levelOf } = await import("../src/funnelPile.js");
  const row = { key: "a", lane: "working", order_band: 5, kind: "agent", title: "Fix the export" };
  const stale = { key: "a", lane: "blocked", order_band: 2, surfaced: true, kind: "agent", why: "asked you" };
  const drawn = placed(row, stale);
  assert.equal(drawn.lane, "working");
  assert.equal(drawn.surfaced, undefined);
  assert.equal(drawn.why, "asked you", "the card still lends its words");
  assert.notEqual(levelOf(drawn), levelOf(stale));
});

test("an older rail answer never replaces a newer one", async () => {
  const { refreshPilePresentation } = await import("../src/funnelPile.js");
  const newer = { generated_at: 2000, items: [{ key: "a", lane: "working" }] };
  const older = { generated_at: 1000, items: [{ key: "a", lane: "blocked" }] };
  assert.equal(refreshPilePresentation(newer, older), newer);
  const newest = { generated_at: 3000, items: [] };
  assert.equal(refreshPilePresentation(newer, newest), newest);
});
