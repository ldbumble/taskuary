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
