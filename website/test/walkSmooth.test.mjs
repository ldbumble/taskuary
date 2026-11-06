import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// THE CARD HOLDS STILL WHILE THE NEXT ONE COMES (the owner, 2026-11-05: "try to smooth"): the walk's "…" is no line said after it, and a card
// put on the table is placed at once, never slid there
test("the walk dots never pull the body to its end, and the table card is placed without the smooth scroll", () => {
  const v = read("AssistantView.jsx");
  assert.match(v, /tq-pending\$\{\(nextComing \|\| walkDots\) && !\(busy && words\) \? " tq-walk-dots" : ""\}/);
  assert.match(v, /\.tq-msg:not\(\.tq-welcome-msg\):not\(\.receipt\):not\(\.tq-walk-dots\)/);
  assert.match(v, /const dots = el\.querySelector\("\.tq-walk-dots"\), slack = dots \? dots\.getBoundingClientRect\(\)\.height \+ 24 : 0;/);
  assert.match(v, /const placeAt = \(el, top\) => \{ el\.style\.scrollBehavior = "auto"; el\.scrollTop = top; el\.style\.scrollBehavior = ""; \};/);
});
