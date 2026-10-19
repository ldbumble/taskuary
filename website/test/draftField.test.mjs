// A LONG EMAIL IS READ IN THE BOX, not through an 8-line slot (the owner, 2026-10-19): every reply draft is the one DraftField,
// which grows with the text to 60% of the window and drags taller from its corner - the drag becomes autosize's floor.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the task page and the walk's reply card draw the same draft box", () => {
  for (const f of ["ReviewDecision.jsx", "assistantCards.jsx"]) {
    assert.match(read(f), /<DraftField value=\{value\}/, f);
    assert.doesNotMatch(read(f), /maxRows=\{(9|r\.Kind === "action" \? 24 : 8)\}/, f);
  }
});

test("the box grows to 60% of the window, resizes vertically, and a drag feeds minRows", () => {
  const ui = read("ui.jsx"), f = ui.slice(ui.indexOf("export const DraftField"), ui.indexOf("\n};", ui.indexOf("export const DraftField")));
  assert.match(f, /window\.innerHeight \* 0\.6/);
  assert.match(f, /resize: "vertical"/);
  assert.match(f, /minRows=\{Math\.max\(2, rows\)\} maxRows=\{Math\.max\(cap, rows\)\}/);
});
