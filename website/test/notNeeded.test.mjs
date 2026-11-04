// A REPLY NO LONGER NEEDED IS SAID ON ITS CARD, NOT DELETED (Task 4.5, 2026-11-04): the agent re-planned on a change on the thread and
// marked the draft not needed - the card says "Not needed - <why>" and the Send under it stays the owner's.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../src/ReviewDecision.jsx", import.meta.url), "utf8");

test("the card says Not needed with the agent's reason", () => {
  assert.match(src, /\{!!r\.NotNeeded && \(\s*<Typography[^>]*data-tq-not-needed=""[^>]*>Not needed - \{r\.NotNeeded\}<\/Typography>/);
});

test("the mark hides nothing: no Send or draft is gated on it", () => {
  assert.equal(src.match(/NotNeeded/g).length, 2);
});
