// NOT READ YET IS NOT EMPTY (the owner, 2026-10-20): until the first pile read lands the opener says "Loading..." where an empty
// day once had its line (gone 2026-10-22), and a Walk press made then is kept - queued, and run once the rows are in - not dropped on a
// disabled button. The browser check is scratch early.mjs; these hold the shape in the source.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const view = src("AssistantView.jsx");

test("unread is its own state, drawn in the empty line's place", () => {
  assert.match(view, /const pileLoading = pile === null && !pileRead;/);
  // ...said by the card's own "Counting…", not a stray "Loading..." line under it (the owner, 2026-10-28)
  assert.doesNotMatch(view, /data-tq-pile-loading|>Loading\.\.\.</);
  assert.match(view, /loading=\{mailReading \|\| pileLoading\} top=\{<SinceBlock/);
});

// BUTTONS DO THE TALKING (the owner, 2026-10-22: "what is this blank text?? buttons do the talking.."): an empty day draws no
// "Nothing is waiting on you - ask me anything, or set something up." line between the card and its buttons, nor on the brief card
test("an empty day says nothing between the card and the buttons", () => {
  for (const f of ["AssistantView.jsx", "assistantCards.jsx"]) assert.doesNotMatch(src(f), /ask me anything, or set something up/i, f);
});

// STILL COUNTING IS NOT "NOTHING TO WALK" (an owner screenshot, 2026-10-20): the card said "Counting…" over On you rows while the line
// under it said "Nothing to walk through right now" and Walk was greyed - and pointed "on the left" at rows on the right
test("while the day is counted the opener says Loading..., and a greyed Walk has no line of its own under it", () => {
  assert.match(view, /const counting = pileLoading \|\| mailReading \|\| \(!canAdvance && items\.some\(\(i\) => i\.settling\)\);/);
  // the owner, 2026-10-22: "yes remove that walk line too" - buttons do the talking
  assert.doesNotMatch(view, /data-tq-nothing-to-walk|Nothing to walk through right now|Click any row to open it/);
  // ...and the card's headline is the rail's Tasks count, every row under it (the owner, 2026-10-27: "they should match count of tasks")
  assert.match(src("assistantCards.jsx"), /const tasks = act\.reduce\(\(n, g\) => n \+ \(SECTION\[g\.key\]\?\.on_you \? g\.n \?\? g\.rows\.length : 0\), 0\);/);
  assert.match(src("assistantCards.jsx"), /tasks \? "Tasks" : "Nothing on you"/);
  // ...and said once: the heading carries no count of its own over the Tasks row that says it (2026-10-28)
  assert.doesNotMatch(src("assistantCards.jsx"), /plural\(tasks, "task"\)/);
});

test("the first read, landed or failed, ends the loading - a coverage retry does not", () => {
  assert.match(view, /setPile\(\(p\) => refreshPilePresentation\(p, data\)\); setPileRead\(true\);/);
  assert.match(view, /if \(isCoveragePending\(error\)\) setTimeout\([^\n]*\n\s*else setPileRead\(true\);/);
});

test("Walk is pressable while loading, and the press is kept until the rows are in", () => {
  assert.match(view, /disabled=\{walkQueued \|\| starting \|\| resetting \|\| \(!counting && !canAdvance && !onYou\)\}/);   // walkGuard.test
  assert.match(view, /onPointerDown=\{counting \? \(\) => setWalkQueued\(true\) : undefined\}/);
  assert.match(view, /onClick=\{\(\) => \(counting \|\| walkOff \? setWalkQueued\(true\) : start\(null\)\)\}/);
  assert.match(view, /\{starting \|\| walkQueued \? "Getting your first one\.\.\." : btn\("walk"\)\}/);
});
