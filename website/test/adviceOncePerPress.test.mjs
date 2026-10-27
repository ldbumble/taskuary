// ONE ADVISOR READ A PRESS OF NEXT (the overnight walk, 2026-10-26): every press read /api/advice three times - once about the item being
// put down (the after-a-press re-read, which Next is not), and twice about the one arriving (the table's new key, and the revision effect
// that fired on the same render). The wiring is read from the source; browser/next-asks-once.test.mjs counts the requests.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const src = fs.readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");

test("Next is no press that re-reads the item it puts down", () => {
  assert.match(src, /onPressed\(\(id\) => \{ if \(onTableRef\.current && !\/\(\^\|:\)next\$\/\.test\(String\(id \|\| ""\)\)\) readAdvice\(onTableRef\.current, true\); \}\)/);
});

test("...nor on a phone, whose view reads its own line (CanvasItem useItemAdvice)", () => {
  const item = fs.readFileSync(new URL("../src/CanvasItem.jsx", import.meta.url), "utf8");
  assert.match(item, /const after = onPressed\(\(id\) => \{ if \(!\/\(\^\|:\)next\$\/\.test\(String\(id \|\| ""\)\)\) read\(\); \}\);/);
});

test("a revision or lane move re-reads only the SAME item - a new key is read by the table's own effect", () => {
  assert.match(src, /const k = currentItem\?\.key \|\| null, was = revFor\.current; revFor\.current = k;\n\s+if \(onTable && k && k === was\) readAdvice\(onTable, true\);\n\s+\}, \[currentItem\?\.key, currentItem\?\.view_revision, currentItem\?\.lane\]\);/);
});
