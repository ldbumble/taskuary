import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { NEAR, flatten, meter } from "../src/docMeter.js";

const docs = readFileSync(fileURLToPath(new URL("../src/DocsView.jsx", import.meta.url)), "utf8");
const lim = (chars, flat = false) => ({ chars, flat, reader: "the agent", past: "the end is cut off" });

test("flatten counts what a session receives, as terminal.flatten_rules does", () => {
  assert.equal(flatten("# CODING.md - rules\n\n## Ask first\n- Read  before\twrite.\r\n  Then test.\n"),
    "CODING.md - rules Ask first - Read before write. Then test.");
  assert.equal(flatten(""), ""); assert.equal(flatten(null), "");
});

test("calm under 85%, amber from 85 to 100, red past the limit with what is over", () => {
  assert.equal(NEAR, 85);
  assert.deepEqual(meter("x".repeat(840), lim(1000)), { n: 840, of: 1000, pct: 84, tone: "ok", over: 0 });
  assert.equal(meter("x".repeat(850), lim(1000)).tone, "near");
  assert.equal(meter("x".repeat(1000), lim(1000)).tone, "near");                 // exactly at the limit: nothing cut yet
  const m = meter("x".repeat(1204), lim(1000));
  assert.equal(m.tone, "over"); assert.equal(m.over, 204); assert.equal(Math.round(m.pct), 120);
  assert.equal(meter("# H\n\n\nab   cd", lim(10, true)).n, 7);                     // a flat limit counts the flattened text
});

test("no limit, no meter", () => {
  for (const l of [null, undefined, {}, { chars: 0 }]) assert.equal(meter("words", l), null);
});

test("the editor draws the meter above the words, from the server's limit, live as you type", () => {
  assert.match(docs, /<DocMeter text=\{docs\[docName\]\} limit=\{limits\[docName\]\} \/>\s*<TextField fullWidth multiline/);
  assert.match(docs, /\[n, res\[i\]\.data\.limit \|\| null\]/);                    // the operator documents
  assert.match(docs, /\[key\]: data\.limit \|\| null/);                           // ...and every profile's
  assert.match(docs, /characters reach \{limit\.reader \|\| "the agent"\}/);
  assert.match(docs, /over by \{m\.over\.toLocaleString\(\)\} - \{limit\.past \|\| "the end is cut off"\}/);
  assert.match(docs, /role="meter"/);
  assert.match(docs, /const TONE = \{ ok: ACCENT2, near: PALETTE\.brass, over: PALETTE\.oxblood \}/);
});
