// The ways past a failure the rebuilt walk found missing (2026-10-18): a send nobody can confirm offers Send anyway and Mark done on
// the card, a failed start on the task page draws its fix - every word read from the list. No way back is a Take it back (2026-10-19).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe } from "../src/proposalCard.js";
import { label } from "../src/buttons.js";

const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

// the owner, 2026-10-19: "no take it back button. hate that" - a card confirms with the act's own name, and no button is called Take it back
test("a card confirms with its act's own name, and nothing is called Take it back", () => {
  assert.equal(describe({ kind: "task.defer", label: "Remind me", params: { until: "2026-10-20" } }).confirm, "Remind me");
  assert.equal(label("take_back"), "", "no button by that name");
});
