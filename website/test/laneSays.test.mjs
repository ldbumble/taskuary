import { test } from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { says, starting, subState } from "../src/laneSays.js";
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
  for (const sub of Object.keys(lanes.lanes.find((l) => l.key === "blocked").says)) assert.ok(says(sub, "coding").startsWith("coding "), sub);
  assert.equal(says("stalled", "coding", "rate limit: resets at 3pm"), "coding is stuck - rate limit: resets at 3pm");
  assert.equal(says("asking", "codex", "Which  branch?"), "codex asked you: Which branch?");
  assert.equal(says("parked", "coding", "the screen said this"), "coding is waiting on you");
});

test("the walk's lead, the hand-raise and the Timeline read the same sentence", () => {
  const stuck = { kind: "agent", lane: "blocked", agent: "coding", request_kind: "stalled", why: "coding is stuck - rate limit" };
  assert.equal(assistantFocus(stuck).lead, "coding is stuck - rate limit.");
  assert.equal(handRaiseWhat({ agent: "coding", asking: false, line: "coding is stuck - rate limit" }), "coding is stuck - rate limit");
  assert.equal(handRaiseWhat({ agent: "coding", asking: true }), "coding asked you something");
  assert.match(subline({ TaskId: 4, Working: "coding", AgentWaiting: true, AgentLine: "coding is stuck - rate limit" }), /coding is stuck - rate limit/);
});

test("an agent started and silent is one sentence, from lanes.json", () => {
  // the agent goes by Taskuary, never the profile it runs under (the owner, 2026-10-28) - so no "the" before it
  assert.equal(starting("Taskuary", "Codex"), "Starting Taskuary on Codex…");
  assert.equal(starting("Taskuary"), "Starting Taskuary…");
  assert.equal(lanes.lanes.find((l) => l.key === "working").says.starting.line, "Starting {agent} on {text}…");
});
