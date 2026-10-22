import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dueWord, levelOf, rowMeta } from "../src/funnelPile.js";
import { MOVES, RINGS } from "../src/railStatus.js";

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
  const view = src("AssistantView.jsx"), css = src("statusMark.css"), logo = src("StatusMark.jsx");
  assert.match(view, /const st = i\.settling \|\| goal \|\| i\.kind === "meeting" \? null : railStatus\(i\);/);
  assert.match(view, /<StatusLogo status=\{goal \? \(i\.kind === "goal_slipped" \? \{ key: i\.kind, role: "bad" \} : null\) : shown\}/);
  // ONLY THE RING SPINS, at its own speed, as it always did - the logo inside it never turns (the owner, 2026-10-22)
  assert.match(css, /\.tq-mark\.spins::after \{[^}]*animation: tq-agent-ring 1s linear infinite/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\) \{\n\s+\.tq-mark\.spins::after \{ animation: none;/);
  assert.doesNotMatch(css.replace(/::after \{[^}]*\}/g, "").replace(/^@keyframes.*$/gm, ""), /\.tq-mark[^{]*\{[^}]*(animation|transform|opacity|filter)/, "nothing on the logo itself moves, fades or recolours");
  // the header pill keeps the ring alone (wears={false})
  assert.match(logo, /<StatusLogo status=\{status\} agent=\{agent\} wears=\{false\}>\{logo\}<\/StatusLogo>/);
  assert.doesNotMatch(css + src("assistantView.css"), /\.tq-pile-row\.working|\.spins[^{]*\{[^}]*\bborder-color: [^;]*;[^}]*outline/, "the row's border is the table's alone");
});

// THE ROW'S STATE IS ON ITS ICON (owner-approved 2026-10-21): a RING round the source's logo, one shape per state (the owner, 2026-10-22:
// "Don't spin the whole thing, just the circle around it") - nothing laid over the logo, which never changes - and no status words or
// emoji on the row's right, so the title gets the room. The words are the icon's label.
test("a rail row carries its state in the ring round its logo and its label, with no badge and no status word on its right", () => {
  const view = src("AssistantView.jsx"), logo = src("StatusMark.jsx"), css = src("statusMark.css");
  assert.match(view, /const shown = st && \(st\.spins \|\| meta\.word !== BAND_SAYS\[level\]\) \? st : null;/);
  // the only words left on a row's right: a meeting's time and a goal's "slipped"
  assert.match(view, /: goal \? \(i\.kind === "goal_slipped" \? meta\.word : ""\) : "";/);
  assert.match(logo, /role=\{said \? "img" : undefined\} aria-label=\{said\} title=\{said\}/);
  assert.match(logo, /const said = st && !goal \? statusLabel\(st, agent\) : undefined;/);
  assert.doesNotMatch(logo + css, /badge|lk-|tq-tint|grayscale|filter:/, "no badge, no look on the logo, no colour filter");
  assert.match(logo, /\{children\}\n\s+<\/span>/, "the logo is the mark's only child");
  // a working row names its ring "spin" too, but draws the old ring (.spins), never a masked one
  assert.match(logo, /const ring = goal \? "progress" : wears && st \? st\.ring \|\| "none" : "";/);
  assert.match(logo, /ring && !\["none", "spin"\]\.includes\(ring\) \? `rg-\$\{ring\}` : ""/);
  // every ring but spin (the old ring) and none is drawn, round the logo, in the pill's colour for its role
  for (const r of RINGS.filter((x) => !["spin", "none"].includes(x))) assert.match(css, new RegExp(`\\.tq-mark\\.rg-${r}::after \\{`), r);
  for (const r of ["you", "working", "done", "muted", "bad"]) assert.match(css, new RegExp(`\\.tq-mark\\.rl-${r} \\{ --ring: #[0-9a-f]{6}; \\}`), r);
  // shapes, not colours, tell them apart: half a ring, a ring broken in four, eight dots
  assert.match(css, /\.rg-half::after \{ background: conic-gradient\(var\(--ring\) 0 50%, transparent 0\); \}/);
  assert.match(css, /\.rg-broken::after \{ background: repeating-conic-gradient\(from 12deg, var\(--ring\) 0 64deg, transparent 0 90deg\); \}/);
  assert.equal((css.match(/\.rg-dots::after \{[^}]*\}/)[0].match(/0 \d+deg, transparent/g) || []).length, 8, "eight dots");
  // only the spin, the breath and the dots' tick move - and under reduced motion none of them does
  assert.deepEqual(MOVES, ["spin", "breathe", "dots"]);
  for (const r of ["breathe", "dots"]) assert.match(css, new RegExp(`\\.rg-${r}::after \\{[^}]*animation:`), r);
  for (const r of ["full", "half", "broken", "faint", "progress"]) assert.doesNotMatch(css, new RegExp(`\\.rg-${r}::after \\{[^}]*animation:`), r);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\) \{[^@]*\.tq-mark\[class\*="rg-"\]::after \{ animation: none !important; \}/);
  // a goal's ring is its progress: steps done of its steps
  assert.match(view, /progress=\{goal && Number\.isInteger\(i\.steps\) && i\.steps > 0 \? \(i\.steps_done \|\| 0\) \/ i\.steps : null\}/);
  assert.match(css, /\.rg-progress::after \{ background: conic-gradient\(var\(--ring\) 0 calc\(var\(--p, 0\) \* 1%\)/);

});
