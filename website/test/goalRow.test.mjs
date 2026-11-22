import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dueWord, levelOf, rowMeta } from "../src/funnelPile.js";

// a goal's date, short - said in its words as "due Dec 1"; its gutter is its age like every row's (the owner, 2026-10-28)
test("a goal's due date reads short", () => {
  assert.equal(dueWord("2026-12-01"), "Dec 1");
  assert.equal(dueWord("2026-12-01 08:00:00"), "Dec 1");
  assert.equal(dueWord(""), "");
  assert.equal(dueWord(null), "");
});

// GOALS STAY IN TASKS (the owner, 2026-10-22): walked past or quiet, a goal is not moved - only Remind me puts it For later
test("a goal stays under Tasks when Next walks past it, and goes For later only by Remind me", () => {
  assert.equal(levelOf({ kind: "goal_slipped", order_band: 2, news: true, surfaced: false }), "task");
  assert.equal(levelOf({ kind: "goal", order_band: 2, news: true, surfaced: true }), "task", "walked past: still in Tasks");
  assert.equal(levelOf({ kind: "goal_fresh", order_band: 2 }), "task", "quiet: still in Tasks");
  assert.equal(levelOf({ kind: "goal", order_band: 2, deferred: true }), "later", "Remind me");
});

// THE RAIL'S ROW (the owner, 2026-10-21): a goal reads "🎯 <title> · 2 of 5 steps" - no TQ number - with "slipped" in red when late;
// a task an agent is working wears a ring spinning round its icon, a still ring under reduced motion, and never the table's border
const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
test("a goal's row says its mark, its title and its steps, and slipped in red", () => {
  const view = src("AssistantView.jsx");
  assert.match(view, /goal \? <span className="goal">\{meta\.mark\}<\/span> : <SourceMark/, "the goal's mark where the source logo goes");
  assert.match(view, /<span className="tq-pile-steps">· \{i\.steps_done \|\| 0\} of \{i\.steps\} steps<\/span>/);
  assert.match(view, /!!i\.ref && isCur && !goal &&/, "no TQ number on a goal's row");
  assert.match(view, /goal \? \(i\.kind === "goal_slipped" \? \[meta\.word, dueWord\(i\.slipped_at \|\| i\.due\)\]\.filter\(Boolean\)\.join\(" "\) : ""\)/,
    "slipped says the day it slipped past - its late step's while its own date is ahead (slipped_at, 2026-11-08)");
  assert.match(view, /\{goal && i\.kind !== "goal_slipped" && !!dueWord\(i\.due\) && <span className="tq-pile-due" title=\{`due \$\{dueWord\(i\.due\)\}`\}>· due \{dueWord\(i\.due\)\}<\/span>/, "its due date in its words");
  assert.match(src("assistantView.css"), /\.tq-pile-due \{ flex: 0 0 auto;/, "...and the title gives way to it, as to its count and its word");
  assert.doesNotMatch(view, /\{goal \? dueWord\(i\.due\)/, "the age column is a goal's age, not its date");
  assert.equal(rowMeta({ kind: "goal_slipped", lane: "yours" }).role, "bad", "slipped wears the bad ink - red");
  assert.equal(rowMeta({ kind: "goal_slipped", lane: "yours" }).word, "slipped");
});
