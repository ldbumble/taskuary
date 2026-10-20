// NOT READ YET IS NOT EMPTY (the owner, 2026-10-20): until the first pile read lands the opener says "Loading..." where it says
// "Nothing is waiting on you", and a Walk press made then is kept - queued, and run once the rows are in - not dropped on a
// disabled button. The browser check is scratch early.mjs; these hold the shape in the source.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const view = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");

test("unread is its own state, drawn in the empty line's place", () => {
  assert.match(view, /const pileLoading = pile === null && !pileRead;/);
  assert.match(view, /\{pileLoading \? <span data-tq-pile-loading="">Loading\.\.\.<\/span>\s*: !items\.length && <span>Nothing is waiting on you/);
});

test("the first read, landed or failed, ends the loading - a coverage retry does not", () => {
  assert.match(view, /setPile\(\(p\) => refreshPilePresentation\(p, data\)\); setPileRead\(true\);/);
  assert.match(view, /if \(isCoveragePending\(error\)\) setTimeout\([^\n]*\n\s*else setPileRead\(true\);/);
});

test("Walk is pressable while loading, and the press is kept until the rows are in", () => {
  assert.match(view, /disabled=\{walkOff \|\| walkQueued \|\| \(!pileLoading && !canAdvance\)\}/);   // walkOff: walkGuard.test
  assert.match(view, /onPointerDown=\{pileLoading \? \(\) => setWalkQueued\(true\) : undefined\}/);
  assert.match(view, /onClick=\{\(\) => \(pileLoading \? setWalkQueued\(true\) : start\(null\)\)\}/);
  assert.match(view, /if \(!walkQueued \|\| pileLoading \|\| walkOff\) return;\s*setWalkQueued\(false\);\s*if \(canAdvance\) start\(null\);/);
  assert.match(view, /\{starting \|\| walkQueued \? "Getting your first one\.\.\." : "Walk me through my tasks"\}/);
});
