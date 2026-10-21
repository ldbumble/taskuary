import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dueWord, levelOf, rowMeta } from "../src/funnelPile.js";

// a goal's gutter is its date, not its age: for a goal the date is the clock (spec 2026-10-12)
test("a goal's gutter says its date, short", () => {
  assert.equal(dueWord("2026-12-01"), "Dec 1");
  assert.equal(dueWord("2026-12-01 08:00:00"), "Dec 1");
  assert.equal(dueWord(""), "");
  assert.equal(dueWord(null), "");
});

test("a goal is under Tasks only while it has news you have not walked past", () => {
  assert.equal(levelOf({ kind: "goal_slipped", order_band: 2, news: true, surfaced: false }), "task");
  assert.equal(levelOf({ kind: "goal", order_band: 2, news: true, surfaced: true }), "later", "walked past: scheduled to come back");
});

// THE RAIL'S ROW (the owner, 2026-10-21): a goal reads "🎯 <title> · 2 of 5 steps" - no TQ number - with "slipped" in red when late;
// a task an agent is working wears a ring spinning round its icon, a still ring under reduced motion, and never the table's border
const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
test("a goal's row says its mark, its title and its steps, and slipped in red", () => {
  const view = src("AssistantView.jsx");
  assert.match(view, /goal \? <span className="goal">\{meta\.mark\}<\/span> : <SourceMark/, "the goal's mark where the source logo goes");
  assert.match(view, /<span className="tq-pile-steps">· \{i\.steps_done \|\| 0\} of \{i\.steps\} steps<\/span>/);
  assert.match(view, /!!i\.ref && isCur && !goal &&/, "no TQ number on a goal's row");
  assert.match(view, /goal \? \(i\.kind === "goal_slipped" \? meta\.word : ""\)/, "only slipped is said");
  assert.equal(rowMeta({ kind: "goal_slipped", lane: "yours" }).role, "bad", "slipped wears the bad ink - red");
  assert.equal(rowMeta({ kind: "goal_slipped", lane: "yours" }).word, "slipped");
});

test("an agent at work rings the row's icon, spinning, and still under reduced motion", () => {
  const view = src("AssistantView.jsx"), css = src("assistantView.css");
  assert.match(view, /spins = i\.lane === "working" && !i\.settling/);
  assert.match(view, /className=\{`logo\$\{spins \? " spins" : ""\}`\}/);
  assert.match(css, /\.tq-pile-row \.logo\.spins::after \{[^}]*animation: tq-agent-ring 1s linear infinite/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\) \{ \.tq-pile-row \.logo\.spins::after \{ animation: none;/);
  assert.doesNotMatch(css, /\.tq-pile-row\.working|\.spins[^{]*\{[^}]*border-color: [^;]*;[^}]*outline/, "the row's border is the table's alone");
});
