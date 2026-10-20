// NOT READ YET IS NOT EMPTY (the owner, 2026-10-20): until the first pile read lands the opener says "Loading..." where it says
// "Nothing is waiting on you", and a Walk press made then is kept - queued, and run once the rows are in - not dropped on a
// disabled button. The browser check is scratch early.mjs; these hold the shape in the source.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const view = src("AssistantView.jsx");

test("unread is its own state, drawn in the empty line's place", () => {
  assert.match(view, /const pileLoading = pile === null && !pileRead;/);
  assert.match(view, /\{counting \? <span data-tq-pile-loading="">Loading\.\.\.<\/span>\s*: !items\.length && <span>Nothing is waiting on you/);
});

// STILL COUNTING IS NOT "NOTHING TO WALK" (an owner screenshot, 2026-10-20): the card said "Counting…" over On you rows while the line
// under it said "Nothing to walk through right now" and Walk was greyed - and pointed "on the left" at rows on the right
test("while the day is counted the opener says Loading..., and Nothing to walk only once it is counted and nothing is on you", () => {
  assert.match(view, /const counting = pileLoading \|\| mailReading \|\| \(!canAdvance && items\.some\(\(i\) => i\.settling\)\);/);
  assert.match(view, /const onYou = useMemo\(\(\) => onYouCount\(items\.length \? summarize\(items\)\.groups : \[\]\), \[items\]\);/);
  assert.match(view, /\{!counting && !!items\.length && !canAdvance && !onYou && !busy && !starting && <span className="tq-welcome-why" data-tq-nothing-to-walk="">/);
  assert.doesNotMatch(view, /on the left to open it/, "the rows are not on the left of this line");
  assert.match(view, /Click any row to open it\./);
  assert.match(src("assistantCards.jsx"), /const onYou = onYouCount\(groups\)/, "the card's headline and the line read one count");
});

test("the first read, landed or failed, ends the loading - a coverage retry does not", () => {
  assert.match(view, /setPile\(\(p\) => refreshPilePresentation\(p, data\)\); setPileRead\(true\);/);
  assert.match(view, /if \(isCoveragePending\(error\)\) setTimeout\([^\n]*\n\s*else setPileRead\(true\);/);
});

test("Walk is pressable while loading, and the press is kept until the rows are in", () => {
  assert.match(view, /disabled=\{walkQueued \|\| starting \|\| resetting \|\| !!handoff \|\| \(!counting && !canAdvance && !onYou\)\}/);   // walkGuard.test
  assert.match(view, /onPointerDown=\{counting \? \(\) => setWalkQueued\(true\) : undefined\}/);
  assert.match(view, /onClick=\{\(\) => \(counting \|\| walkOff \? setWalkQueued\(true\) : start\(null\)\)\}/);
  assert.match(view, /\{starting \|\| walkQueued \? "Getting your first one\.\.\." : "Walk me through my tasks"\}/);
});
