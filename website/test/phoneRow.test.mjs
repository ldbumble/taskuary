// THE ROW ON A PHONE (the owner, 2026-10-22): Next and the one lit move, every other group folded into ONE ▾ - and the chips in it wrap,
// never clip (the walk's end "Open TQ-..." chips had their starts cut off by a centred line that did not wrap).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { phoneRow, rowOf } from "../src/actionRow.js";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
const list = [v("reply", "decide"), v("approve", "decide"), v("continue", "agent"), v("save-end", "agent"), v("done", "more"), v("remind", "more"), v("next", "next")];

test("a phone's row is the one lit move with everything else behind one ▾ - and Next stays its own", () => {
  const lit = phoneRow(rowOf({ ref: "TQ-1", list }, { verb: "continue" }));
  // ...beside Mark done, never folded (the owner, 2026-10-28)
  assert.deepEqual(lit.shown.map((x) => x.id), ["done", "continue"], "the Advisor's pick is the one move");
  assert.equal(lit.rest.length, 4); assert.ok(!lit.rest.some((x) => x.id === "next"), "Next is never in the ▾");
  const quiet = phoneRow(rowOf({ ref: "TQ-1", list }));
  assert.deepEqual(quiet.shown.map((x) => x.id), ["done"], "no advice: what leads the bar - Mark done, with no decision of the card's own");
  assert.equal(new Set([...quiet.shown, ...quiet.rest].map((x) => x.id)).size, 6, "every button is still on the row, once");
  assert.deepEqual(phoneRow(rowOf({ ref: "", list: [v("next", "next")] })), { type: "move", label: "", shown: [], rest: [] });
});

// ...and a group's chips never wrap now (the owner, 2026-10-23: one line, always - rowOneLine.test.mjs): what does not fit folds into the ▾
test("the row draws the phone's one group under 600px, and a group's chips stay on its one line", () => {
  const row = read("ActionRow.jsx");
  assert.match(row, /const phone = useMediaQuery\("\(max-width:600px\)"\);/);
  assert.match(row, /const fit = fitRow\(row, m, avail, phone, extra\);/);
  assert.match(read("actionRow.js"), /const all = foldsOf\(row\), last = all\.length - 1/);
  assert.match(read("actionRow.js"), /export const phoneRow = \(row\) => foldsOf\(row\)\.at\(-1\)\?\.\[0\]/, "the narrowest layout is the phone's");
  assert.match(read("assistantView.css"), /\.tq-cl-b \{ display: flex; flex-wrap: nowrap; justify-content: center;/);
});
