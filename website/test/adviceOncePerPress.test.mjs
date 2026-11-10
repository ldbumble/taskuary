// ONE ADVISOR READ A PRESS OF NEXT (the overnight walk, 2026-10-26): every press read /api/advice three times - once about the item being
// put down (the after-a-press re-read, which Next is not), and twice about the one arriving (the table's new key, and the revision effect
// that fired on the same render). The wiring is read from the source; browser/next-asks-once.test.mjs counts the requests.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const src = fs.readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");

test("Next is no press that re-reads the item it puts down - nor Back, the other walk move", () => {
  assert.match(fs.readFileSync(new URL("../src/actionRow.js", import.meta.url), "utf8"), /export const walkMove = \(id\) => \/\(\^\|:\)next\$\/\.test\(String\(id \|\| ""\)\) \|\| id === BACK;/);
  assert.match(src, /if \(k && !walkMove\(id\) && leftKey\.current !== k && \(!on \|\| on === k\)\) readAdvice\(k, true\);/);
});

// ...and a narrow window's row asks nothing at all (2026-11-09): it read /api/advice for itself (useItemAdvice), a second ask for a second
// answer; it is handed the one the page already holds
test("...nor on a narrow window, whose row is handed the page's own read and asks nothing", () => {
  const item = fs.readFileSync(new URL("../src/CanvasItem.jsx", import.meta.url), "utf8");
  assert.match(item, /const read = phone && advice\?\.for === card\.key \? advice : null;/);
  assert.doesNotMatch(item, /useItemAdvice|onPressed|api\.get\(/);
});

test("a revision or lane move re-reads only the SAME item - a new key is read by the table's own effect", () => {
  assert.match(src, /const k = currentItem\?\.key \|\| null, was = revFor\.current; revFor\.current = k;\n\s+const sent = adviceSent\.current;\n\s+if \(onTable && k && k === was && !\(sent\.key === onTable && sent\.at > itemAt\.current\)\) readAdvice\(onTable, true\);\n\s+\}, \[currentItem\?\.key, currentItem\?\.view_revision, currentItem\?\.lane\]\);/);
});
