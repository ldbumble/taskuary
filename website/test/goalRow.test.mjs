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
  // the only words left on a row's right: a meeting's time and a goal's "slipped" (with its day, 2026-10-28)
  assert.match(view, /: goal \? \(i\.kind === "goal_slipped" \? \[meta\.word, dueWord\(i\.slipped_at \|\| i\.due\)\]\.filter\(Boolean\)\.join\(" "\) : ""\) : "";/);
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

// A GOAL'S TITLE KEEPS ITS ROOM ON THE RAIL (the owner, 2026-11-15): at every desktop width its row read "Migra… · 1 of 5 steps slipped Nov 1" -
// the count and the word whole, the title five letters, the date cut at the card's edge. The title holds its half as every row's does; the
// count and the due date give way first, then the word shortens - "slipped" itself stays
test("a goal's title holds its half of the row; its count, its due date and then its word give way", () => {
  const css = src("assistantView.css");
  assert.match(css, /^\.tq-pile-row \.t b \{ flex: 1 1 auto; min-width: 50%;/m, "every row's title");
  assert.doesNotMatch(css, /b\.goal-t \{ min-width: 20%/, "a goal's is no exception any more");
  assert.match(css, /^\.tq-pile-row \.t b\.goal-t \{ flex-shrink: 3; \}$/m, "it gives up its long tail before the word gives up a letter");
  assert.match(css, /^\.tq-pile-steps, \.tq-pile-due \{ flex: 0 1000 auto; min-width: 0; overflow: hidden; \}$/m, "the count and the date go first");
  assert.match(css, /^\.tq-pile-word\.keep \{ flex: 0 1 auto; min-width: 46px; overflow: hidden; text-overflow: ellipsis; \}$/m, "then the word, down to slipped");
  assert.match(css, /^\.tq-pile-word\.keep \.w \{ display: inline !important; \}$/m, "never down to its mark (2026-10-21)");
});
