import test from "node:test";
import assert from "node:assert/strict";
import { dueWord, levelOf } from "../src/funnelPile.js";

// a goal's gutter is its date, not its age: for a goal the date is the clock (spec 2026-10-12)
test("a goal's gutter says its date, short", () => {
  assert.equal(dueWord("2026-12-01"), "Dec 1");
  assert.equal(dueWord("2026-12-01 08:00:00"), "Dec 1");
  assert.equal(dueWord(""), "");
  assert.equal(dueWord(null), "");
});

test("a goal is in Goals only while it has news you have not walked past", () => {
  assert.equal(levelOf({ kind: "goal_slipped", order_band: 2, news: true, surfaced: false }), "goals");
  assert.equal(levelOf({ kind: "goal", order_band: 2, news: true, surfaced: true }), "later");
});
