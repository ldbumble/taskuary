// ONE SETTLE PER ITEM WHILE IT IS OUT (the overnight walk, 2026-10-26): a double-click on an FYI batch's "All read, next" posted
// /api/funnel/settle twice for the same batch - the second click landed before the batch folded. The guard is read from the source;
// browser/next-asks-once.test.mjs double-clicks the real button.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const src = fs.readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");

test("done() returns at once while the same item's settle is out, and lets go once it lands or fails", () => {
  assert.match(src, /const done = async \(pressed\) => \{\n\s+if \(current && doneFor\.current === current\) return;\n\s+doneFor\.current = current;\n\s+try \{ await settleDone\(pressed\); \} finally \{ doneFor\.current = null; \}/);
});
