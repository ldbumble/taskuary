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

test("Done on the browser view is the owner's press, never words in their name", () => {
  const back = ws.slice(ws.indexOf("const handBack = "), ws.indexOf("const promptUsed"));
  assert.match(back, /worker\/answer`, \{ request_id: req\.request_id, text: "", press: true \}/);
  assert.doesNotMatch(back, /setOwnPrompt|answerAsk/, "no bubble, and no turn typed for them");
  // ...and the Done drawn as a chip under the ask, where no view is on screen, takes the same road
  assert.match(ws, /if \(isTurn\(req\) && \(req\.choices \|\| \[\]\)\.includes\(text\)\) return handBack\(\);/);
  assert.ok(isTurn({ request_id: "yourturn:press:abc" }) && isTurn({ request_id: "yourturn:1f" }) && !isTurn({ request_id: "ask:1" }));
  for (const f of readdirSync(SRC).filter((x) => /\.jsx?$/.test(x))) assert.doesNotMatch(read(f), /TURN_BACK/, `${f}: the words are nobody's to send`);
});

test("an act that still waits keeps its buttons on the turn that set it up", () => {
  assert.doesNotMatch(ws, /<ActionCard[^>]*live=/, "live is the review waiting, not which turn is newest");
  const row = { ReviewId: 4, Status: "pending", post: { type: "linkedin", action: "run_tool", text: "We shipped the export." } };
  assert.deepEqual(stateOf(row), { live: true });
  assert.equal(stateOf({ ...row, Status: "approved" }).done, true); assert.equal(stateOf({ ...row, Status: "rejected" }).done, false);
});

