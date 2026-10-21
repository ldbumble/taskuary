// A document a message LINKS to (linkdocs.py) is drawn beside its files: its kind, its name, and a chip that opens it where it
// lives - never through our attachment door, which would hang the owner's token off a third party's address.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const src = fs.readFileSync(new URL("../src/Attachments.jsx", import.meta.url), "utf8");

test("a linked document opens at its own address, without the token", () => {
  assert.match(src, /const hrefOf = \(a\) => a\.link \? a\.external_url : a\.url \? attUrl\(a, true\) : undefined;/);
  assert.match(src, /rel=\{a\.link \? "noopener noreferrer" : "noopener"\}/);
});

test("its chip says its kind and, on hover, whether it was read and why not", () => {
  assert.match(src, /\["sheet", "SHEET"\]/);
  assert.match(src, /not read: \$\{a\.note\}/);
});

test("the task's counter counts linked documents beside its files", async () => {
  const { filesLine } = await import("../src/timeWords.js");
  assert.equal(filesLine(6, 2), "6 attachments · 2 links");
  assert.equal(filesLine(1, 0), "1 attachment");
  assert.equal(filesLine(0, 1), "1 link");
  assert.equal(filesLine(0, 0), "");
  const page = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /label=\{filesLine\(detail\.attachments\?\.length \|\| 0, detail\.links\?\.length \|\| 0\)\}/);
});
