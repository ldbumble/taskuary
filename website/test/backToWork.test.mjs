import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const view = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");

// ONE BACK ON A SCREEN (the design walk, 2026-11-20 - the owner's ruling that going to a page replaces the view): the head's arrow, its
// "Back to TQ-..." chip, the bar's Back and a page's "< Email" crumb were four ways back on one screen. The bar's Back is the one; it walks
// the one list of places (appLinks.navBack), and it is never greyed under a page of its own.
test("the chat head draws no Back of its own, and no page greys the bar's Back", () => {
  assert.doesNotMatch(view, /aria-label="Back" onClick=\{navBack\}|data-tq-back-work|backToWork|navOff/);
  assert.doesNotMatch(readFileSync(fileURLToPath(new URL("../src/actionRow.js", import.meta.url)), "utf8"), /navOff/);
  assert.doesNotMatch(readFileSync(fileURLToPath(new URL("../src/CanvasBrowse.jsx", import.meta.url)), "utf8"), /data-tq-browse-back/);
  assert.match(view, /useVerbs\("nav", \[\{ id: BACK, group: "back"/);
});

// the owner, 2026-11-09: "drop pencil if it's a duplicate" - one pencil on screen: the head's corner or the pill's, never both
test("the head draws New chat in its corner, the pill drops its own pencil then, and no way of opening a task is singled out", () => {
  assert.match(view, /const headPencil = iconsInPill && !firstRun && !old;/);
  assert.match(view, /\{headPencil && newChatIcon\("data-tq-new-chat-head"\)\}\s*\{!iconsInPill && ownIcons\}/);
  assert.match(view, /\{!headPencil && newChatIcon\("data-tq-new-chat"\)\}<\/>;/);
  assert.equal(view.match(/newChatIcon\("/g).length, 2);
  assert.match(view, /const newChatIcon = \(attr\) => <Tooltip title="New chat — archives this one"><IconButton size="small" \{\.\.\.\{ \[attr\]: "" \}\} onClick=\{newChat\}/);
  assert.doesNotMatch(view, /byNameTid/);
  assert.match(view, /openTaskRef\.current = openTaskCard;/);
});

