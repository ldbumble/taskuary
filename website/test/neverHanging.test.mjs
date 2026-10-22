// NEVER LEFT HANGING (the owner, 2026-10-08: "assistant is leaving user hanging. We need Next button on bottom at least and say hit next
// to continue"): a Next refused because the list moved said so in red, every card above had folded, and nothing was left to press.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const view = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");

test("with nothing on the table the row's floor is Next, and the chat says to press it", () => {
  // ...only over an EMPTY row: a task card registers its own Next, and the hint over it read as a bug (2026-10-08)
  assert.match(view, /const rowEmpty = !rowVerbs\.list\.some\(\(v\) => !String\(v\.id\)\.startsWith\("floor:"\)\)/);
  assert.match(view, /const hanging = [^\n]*rowEmpty[^\n]*\(canAdvance \|\| !!err \|\| proposing\)/);
  // ...a proposal waiting on its Confirm keeps Next on the row: the item folded away with its row (the walk's INLINE, 2026-10-17)
  assert.match(view, /proposing = !!asked && asked\.version != null && \(asked\.status \|\| "proposed"\) === "proposed"/);
  assert.match(view, /useVerbs\("floor", \[\{ id: "floor:next", group: "next", label: btn\("next"\)/);
  assert.doesNotMatch(view, /Press <b>Next<\/b> below to continue/, "the filled Next is enough - no line telling you to press it");
});

// ...but not while the next one is on its way (the owner, 2026-10-22: "when you hit all read & next button on fyi, a next button shows up
// for a second while the next 4 are loading why??"): the batch folded with its row at the press, and for the settle and the walk's grace
// - before surface() took `busy` - the row was empty and the walk could go on, so the floor put up its Next until the new batch drew its own
test("the floor's Next waits while the next one is coming: All read, next shows no Next of its own between batches", () => {
  assert.match(view, /const hanging = [^\n]*!busy[^\n]*!nextComing[^\n]*rowEmpty/);
  // the press itself says the next one is coming, in the same render that folds the batch...
  assert.match(view, /const done = async \(receipt\) => \{[\s\S]{0,600}?\.\.\.x, done: true[\s\S]{0,200}?setNextComing\(true\);/);
  // ...and the walk's own turn takes `busy` in the same tick it clears it, so there is no frame between the two
  assert.match(view, /deferredChat\.current\.delete\(timer\); setNextComing\(false\);\s*\n\s*if \(epoch === chatEpoch\.current && !resettingRef\.current\) fn\(\);/);
  // ...and a settle that fails lets go of it, its receipt offering Next
  assert.match(view, /setNextComing\(false\);\s*\n\s*setMsgs\(\(m\) => \[[^\n]*\n[^\n]*Not done - [^\n]*chips: \[\{ verb: "next"/);
});
