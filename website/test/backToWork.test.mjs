import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { backToWork, overChat, tableOf, workWords, workedOn } from "../src/tableState.js";

const view = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");
const item = { key: "task:12", tid: 12, ref: "TQ-0012", title: "Renew the vendor.example contract before the quarter ends" };

// the owner, 2026-11-09: "there should always be a button on top corner when you are in settings or reports to go back to the main task
// you were working on, or clear it with the pencil for new chat?"
// ...and 2026-11-09 again: "any task you are on then switch to settings is [the] task" - a link, the Board or an answer's Open as much as the walk
test("the task in view is the one being worked on, however it was opened", () => {
  const onIt = tableOf({ current: "task:12" });
  assert.deepEqual(workedOn(onIt, item), { key: "task:12", tid: 12, ref: "TQ-0012", title: item.title });
  assert.equal(workedOn.length, 2);                                                          // no by-name exclusion to pass
  assert.equal(workedOn(tableOf({ current: "task:12", browsing: "b1" }), item), null);       // a page over it
  assert.equal(workedOn(tableOf({ current: "task:12", foldedKey: "task:12" }), item), null); // put away by its X
  assert.equal(workedOn(tableOf({ current: "fyi:3" }), { key: "fyi:3" }), null);             // an FYI is no task
});

test("a browse page over a remembered task shows Back + the pencil; the task itself shows the pencil only", () => {
  const w = workedOn(tableOf({ current: "task:12" }), item);
  const settings = tableOf({ current: "task:12", browsing: "settings" });
  assert.equal(backToWork(settings, w, 12), true);                                    // Settings over the task
  assert.equal(backToWork(tableOf({ browsing: "reports" }), w, 0), true);             // Reports with nothing on the table
  assert.equal(backToWork(tableOf({ current: "task:40" }), w, 40), true);             // another task in front
  assert.equal(backToWork(tableOf({ current: "task:12" }), w, 12), false);            // on the task: no Back
  assert.equal(backToWork(tableOf({ browsing: "settings" }), null, 0), false);        // nothing worked on yet
  assert.equal(overChat(settings), true);                                             // ...where the pencil goes to the head
  assert.equal(workWords(w), "Back to TQ-0012 Renew the vendor.example co…");
  assert.equal(workWords({ ref: "TQ-0007", title: "" }), "Back to TQ-0007");
});

// THE RAIL WALK (2026-11-12): Next from TQ-0012 to TQ-0040 drew "Back to TQ-0012" in the corner for the frames before the effect that keeps the
// worked task caught up, then took it away - a flash on every Next and row click. The corner reads the task in view now, in the same render.
test("a task coming into view is the one worked on in the frame it is drawn - no Back to the task just left", () => {
  const was = workedOn(tableOf({ current: "task:12" }), item), next = tableOf({ current: "task:40" }), nextItem = { key: "task:40", tid: 40, ref: "TQ-0040" };
  assert.equal(backToWork(next, workedOn(next, nextItem) || was, 40), false);
  assert.equal(backToWork(tableOf({ browsing: "reports" }), workedOn(tableOf({ browsing: "reports" }), {}) || was, 0), true);   // a page in front keeps it
  assert.match(view, /backToWork\(table, \(inView && workedOn\(table, \{ \.\.\.currentItem, tid: litTable\.tid \}\)\) \|\| worked, litTable\.tid\)/);
});

// the owner, 2026-11-09: "drop pencil if it's a duplicate" - one pencil on screen: the head's corner or the pill's, never both
test("the head draws Back and New chat in its corner, the pill drops its own pencil then, and no way of opening a task is singled out", () => {
  assert.match(view, /\{backWork && <Tooltip[^]*?data-tq-back-work=\{worked\.tid\} onClick=\{toWork\}/);
  assert.match(view, /const headPencil = iconsInPill && !firstRun && !old;/);
  assert.match(view, /\{headPencil && newChatIcon\("data-tq-new-chat-head"\)\}\s*\{!iconsInPill && ownIcons\}/);
  assert.match(view, /\{!headPencil && newChatIcon\("data-tq-new-chat"\)\}<\/>;/);
  assert.equal(view.match(/newChatIcon\("/g).length, 2);
  assert.match(view, /const newChatIcon = \(attr\) => <Tooltip title="New chat — archives this one"><IconButton size="small" \{\.\.\.\{ \[attr\]: "" \}\} onClick=\{newChat\}/);
  assert.match(view, /if \(table\.place && table\.key === worked\.key\) unfoldTable\(\); else pull\(`task:\$\{worked\.tid\}`, null\);/);
  assert.doesNotMatch(view, /byNameTid/);
  assert.match(view, /openTaskRef\.current = openTaskCard;/);
});
