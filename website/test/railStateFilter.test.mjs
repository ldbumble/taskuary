// A row's state word is the rail's filter (the owner, 2026-09-28: "filter by waiting to start / on you / agent
// waiting on you ... as minimal as possible") - no new control: the word on the row is the button.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");

test("clicking a row's state word narrows its band to that word, and clicking again clears it", () => {
  assert.match(src, /const \[only, setOnly\] = useState\(null\);/);
  assert.match(src, /const rows = picked \? all\.filter\(\(i\) => rowMeta\(i\)\.word === picked \|\| i\.key === curKey\) : all;/);
  assert.match(src, /setOnly\(picked \? null : \{ level, word: w \}\)/);
});

test("both the loud pill and the quiet word are the filter, and the heading says what it is showing", () => {
  assert.equal((src.match(/onClick=\{\(e\) => pick\(e, meta\.word\)\}/g) || []).length, 2);
  assert.match(src, /className="tq-pile-only"/);
});
