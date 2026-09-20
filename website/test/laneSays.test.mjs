import { test } from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { says, subState } from "../src/laneSays.js";
import { assistantFocus } from "../src/funnelPile.js";
import { handRaiseWhat } from "../src/handraiseState.js";
import { subline } from "../src/timelineState.js";

const lanes = JSON.parse(readFileSync(fileURLToPath(new URL("../../taskuary/lanes.json", import.meta.url)), "utf8"));

test("the request's kind picks the sub-state, the booleans are the fallback", () => {
  assert.equal(subState({ request: { kind: "stalled" }, asking: true }), "stalled");
  assert.equal(subState({ request_kind: "approval_needed" }), "approval");
  assert.equal(subState({ state: "stalled", asking: true }), "stalled");
  assert.equal(subState({ asking: true }), "asking");
  assert.equal(subState({}), "parked");
});

test("every sub-state has one sentence and the request's words ride on it", () => {
  for (const sub of Object.keys(lanes.lanes.find((l) => l.key === "blocked").says)) assert.ok(says(sub, "coder").startsWith("coder "), sub);
  assert.equal(says("stalled", "coder", "rate limit: resets at 3pm"), "coder is stuck - rate limit: resets at 3pm");
  assert.equal(says("asking", "codex", "Which  branch?"), "codex asked you: Which branch?");
  assert.equal(says("parked", "coder", "the screen said this"), "coder stopped and is waiting on you");
});

test("the walk's lead, the hand-raise and the Timeline read the same sentence", () => {
  const stuck = { kind: "agent", lane: "blocked", agent: "coder", request_kind: "stalled", why: "coder is stuck - rate limit" };
  assert.equal(assistantFocus(stuck).lead, "coder is stuck - rate limit.");
  assert.equal(handRaiseWhat({ agent: "coder", asking: false, line: "coder is stuck - rate limit" }), "coder is stuck - rate limit");
  assert.equal(handRaiseWhat({ agent: "coder", asking: true }), "coder asked you something");
  assert.match(subline({ TaskId: 4, Working: "coder", AgentWaiting: true, AgentLine: "coder is stuck - rate limit" }), /coder is stuck - rate limit/);
});
