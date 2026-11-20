// THE SPINE AUDIT, 2026-11-09, three places where a card or a press stood somewhere other than where it happened. The Done on the agent's
// browser view went in as words typed in the owner's name; an act that still waited lost its buttons when a line was typed after it; and the
// Assistant's dock showed an act as its proposal's JSON, and sent that back. Invented people.
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import test from "node:test";
import { stateOf } from "../src/actionCard.js";
import { isTurn } from "../src/browserSplit.js";
import { reviewText } from "../src/reviewProposal.js";

const SRC = new URL("../src/", import.meta.url), read = (f) => readFileSync(new URL(f, SRC), "utf8");
const ws = read("GeneralWorkspace.jsx");

test("an act that still waits keeps its buttons on the turn that set it up", () => {
  assert.doesNotMatch(ws, /<ActionCard[^>]*live=/, "live is the review waiting, not which turn is newest");
  const row = { ReviewId: 4, Status: "pending", post: { type: "linkedin", action: "run_tool", text: "We shipped the export." } };
  assert.deepEqual(stateOf(row), { live: true });
  assert.equal(stateOf({ ...row, Status: "approved" }).done, true); assert.equal(stateOf({ ...row, Status: "rejected" }).done, false);
});

