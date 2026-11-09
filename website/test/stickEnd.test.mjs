// The owner, 2026-11-09: a coding task opened in the middle of its agent's transcript - placed once at the top of the newest turn's steps,
// then moved on by the steps drawing in. A chat opens at its end and is held there while it settles, until the owner moves in it.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { endTop, stickToEnd, OWN } from "../src/stickEnd.js";

const view = (h = 2000, ch = 400, top = 0) => {
  const on = {};
  return { scrollHeight: h, clientHeight: ch, scrollTop: top, children: [], on,
    getBoundingClientRect: () => ({ top: 100 }),
    addEventListener: (e, f) => { on[e] = f; }, removeEventListener: (e) => { delete on[e]; } };
};
const at = (top) => ({ getBoundingClientRect: () => ({ top }) });

test("the end is the bottom; a newest answer taller than the view shows from its first line instead", () => {
  assert.equal(endTop(view()), 1600);
  assert.equal(endTop(view(), at(100 + 1700)), 1600, "a short answer near the end: the bottom");
  assert.equal(endTop(view(), at(100 + 900)), 892, "a tall answer: its top, 8px under the view's top");
});

test("held at the end as it grows, until the owner's own move lets go", () => {
  const v = view(); stickToEnd(v, (x) => endTop(x), { settle: 50 });
  assert.equal(v.scrollTop, 1600);
  for (const e of OWN) assert.ok(v.on[e], `${e} lets go`);
  v.on.wheel();
  v.scrollHeight = 3000; assert.equal(v.scrollTop, 1600, "never yanked once they scrolled");
  assert.deepEqual(Object.keys(v.on), [], "and every listener goes");
});

test("the chat uses it on opening, and the answer's words are what it reads as the answer", () => {
  const src = readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(src, /return stickToEnd\(viewport\.current, \(v\) => endTop\(v,/);
  assert.match(src, /<div ref=\{box\} onClick=\{open\} data-tq-said="">/);
  assert.doesNotMatch(src, /\[350, 900, 1800\]/, "the one-time place at the turn's top is gone");
});
