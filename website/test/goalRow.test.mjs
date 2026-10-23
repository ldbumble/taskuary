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
  assert.match(view, /goal \? \(i\.kind === "goal_slipped" \? meta\.word : ""\)/, "only slipped is said");
  assert.equal(rowMeta({ kind: "goal_slipped", lane: "yours" }).role, "bad", "slipped wears the bad ink - red");
  assert.equal(rowMeta({ kind: "goal_slipped", lane: "yours" }).word, "slipped");
});

test("an agent at work rings the row's icon, spinning, and still under reduced motion", () => {
  const view = src("AssistantView.jsx"), css = src("statusMark.css"), logo = src("StatusMark.jsx");
  assert.match(view, /const st = i\.settling \|\| goal \|\| i\.kind === "meeting" \? null : railStatus\(i, !canSend\(sendCaps, i\.channel\), page\);/);
  assert.match(view, /<StatusLogo status=\{shown\} agent=\{i\.working \|\| i\.agent\} className="logo">/);
  assert.match(logo, /className=\{\["tq-mark", className, spins \? "spins" : ""\]/);
  assert.match(css, /\.tq-mark\.spins::after \{[^}]*animation: tq-agent-ring 1s linear infinite/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\) \{\n\s+\.tq-mark\.spins::after \{ animation: none;/);
  assert.doesNotMatch(css + src("assistantView.css"), /\.tq-pile-row\.working|\.spins[^{]*\{[^}]*\bborder-color: [^;]*;[^}]*outline/, "the row's border is the table's alone");
});

// THE ROW'S STATE IS ON ITS ICON (owner-approved 2026-10-21): the lane's mark as a badge on the source's logo - waving, turning or
// still - and no status words or emoji on the row's right, so the title gets the room. The words are the icon's label.
test("a rail row carries its state in its icon and its label, and no status word on its right", () => {
  const view = src("AssistantView.jsx"), logo = src("StatusMark.jsx"), css = src("statusMark.css");
  assert.match(view, /const shown = st && \(st\.spins \|\| meta\.word !== BAND_SAYS\[level\]\) \? st : null;/);
  // the only words left on a row's right: a meeting's time and a goal's "slipped"
  assert.match(view, /: goal \? \(i\.kind === "goal_slipped" \? meta\.word : ""\) : "";/);
  assert.match(logo, /role=\{st \? "img" : undefined\} aria-label=\{st \? statusLabel\(st, agent\) : undefined\}/);
  assert.match(logo, /\{badge && <i className=\{`badge\$\{st\.anim \? ` \$\{st\.anim\}` : ""\}`\} aria-hidden="true">\{badge\}<\/i>\}/);
  assert.doesNotMatch(css, /badge\.turn|tq-badge-turn/, "no hourglass turns: waiting to start wears no badge");
  assert.match(css, /\.tq-mark \.badge\.wave \{/);
  assert.match(css, /\.tq-mark \.badge \{ animation: none !important; \}/, "no badge moves under reduced motion");
});

// no shaped ring is left (the owner, 2026-10-22): the working ring is the only one, and a goal is its mark and its step count
test("the only ring on a row is the working one; the hand and the flag are the only badges", () => {
  const view = src("AssistantView.jsx"), logo = src("StatusMark.jsx"), css = src("statusMark.css");
  assert.doesNotMatch(css + logo, /rg-|--ring|conic-gradient|data-tq-ring|progress/, "no shaped or progress ring");
  assert.equal((css.match(/::after \{ content:/g) || []).length, 1, "one ring: the working one");
  assert.match(logo, /badge = !spins && st\?\.badge \|\| "";/, "the badge is railStatus.BADGE's - never the lane's mark");
  assert.doesNotMatch(view, /progress=\{goal/, "a goal is its mark and its count, no ring");
});
