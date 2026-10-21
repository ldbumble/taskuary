import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

// ROWS NEVER OVERLAP ON THE WAY (the 2026-10-19 UI walk, G8): only `top` glided, so the row taking the ring grew to its full height at
// once and the stack under it jumped, while the rows were still gliding - 8-14 frames of rows drawn over each other on every Next and
// rail click (measured 2026-10-20). Height, top and the stack's height move on one curve; a row joining a band comes in once the rows
// around it have moved; a row React moved in the page glides from where it stood; an arrival falls from its first frame.
test("rail rows move on one curve: height, top and the stack's height together", () => {
  const css = src("assistantView.css");
  assert.match(css, /\.tq-pile-stack \{ position: relative; transition: height \.55s cubic-bezier\(\.2,\.8,\.2,1\); \}/);
  assert.match(css, /transition: top \.55s cubic-bezier\(\.2,\.8,\.2,1\), height \.55s cubic-bezier\(\.2,\.8,\.2,1\),/);
  assert.match(css, /\.tq-pile-row\.entering \{ animation: tq-row-in/);
});

test("a row joining a band waits for the glide, a reordered row starts from where it stood, an arrival falls from its first frame", () => {
  const view = src("AssistantView.jsx");
  assert.match(view, /falls\(i\.key\) \? "landing" : entering\.has\(i\.key\) \? "entering" : ""/);
  assert.match(view, /style=\{\{ top: falls\(i\.key\) \? -ROW_H : top \}\}/);
  assert.match(view, /const d = was\.has\(k\) && drawn\?\.get\(k\);\n\s+if \(d\) return \[el, \.\.\.d\];/, "a moved node is sent back to where it was drawn");
  assert.match(view, /const arrivalsOf = \(was\) => \(was\?\.size \? arrivals\(was, items\) : new Set\(\)\);/, "after an empty rail nothing falls at once");
});

// ...AND A GLIDE THAT CHANGES COURSE (a close rings the next row at once, then the pile's answer lands mid-glide) restarts every row
// from where it is drawn, top and height together: the rows whose top changed again began a fresh glide while the ringed row's height
// kept its old one, and it grew into the row under it on CI's slow runner (the walk's SWAP, 2026-10-20)
test("a change of course mid-glide restarts every row's top and height from one frame", () => {
  const view = src("AssistantView.jsx");
  assert.match(view, /if \(!moved \|\| !was\.size\) return;/, "only when a row's rest changed - a re-render alone must not restart the glide");
  assert.match(view, /return \[el, parseFloat\(cs\.top\), parseFloat\(cs\.height\)\];/, "every row, read before any is written");
  assert.match(view, /el\.style\.transitionProperty = "opacity, transform"; el\.style\.top = `\$\{top\}px`; el\.style\.height = `\$\{h\}px`;/,
    "top and height held where drawn, a fade left running");
  assert.match(view, /el\.style\.transitionProperty = ""; el\.style\.top = `\$\{top\}px`; el\.style\.height = "";/);
});

// ...FROM WHERE IT IS DRAWN, read before React changes the page: read after, a row React moved had lost its glide and was sent back
// to where it was last going - a ringed row moved to the top of its band mid-glide came back full height over the row under it
// (CI, the walk's faults pass, 2026-10-21). getSnapshotBeforeUpdate is the one hook that runs before the change.
test("where every row is drawn is read before the commit changes the page", () => {
  const view = src("AssistantView.jsx");
  assert.match(view, /class BeforeCommit extends React\.Component \{\n\s+getSnapshotBeforeUpdate\(\) \{ this\.props\.take\(\); return null; \}/);
  assert.match(view, /<BeforeCommit take=\{takeDrawn\} \/>/);
  assert.match(view, /drawnAt\.current\.set\(`\$\{el\.closest\("\[data-tq-run\]"\)\?\.dataset\.tqRun\} \$\{el\.dataset\.tqKey\}`, \[parseFloat\(cs\.top\), parseFloat\(cs\.height\)\]\);/);
  // ...and only when a rest changes: a commit that moves nothing reads nothing
  assert.match(view, /now\.size === was\.size && \[\.\.\.now\]\.every\(/);
});
