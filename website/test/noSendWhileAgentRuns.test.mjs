// NO "SEND TO AGENT" WHILE AN AGENT RUNS (the owner, 2026-10-01): a task with a live agent session is not offered to another
// agent - its own session is the way in (Continue session / the session's card). The server's dispatch door refuses it too.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { agentRuns } from "../src/taskFilter.js";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

test("an item an agent is working - or a live session holds - reads as running; a stopped or saved one does not", () => {
  assert.equal(agentRuns({ kind: "message", working: "coder" }), true);
  assert.equal(agentRuns({ kind: "agent", sid: "s1", lane: "working" }), true);
  assert.equal(agentRuns({ kind: "agent", sid: "s1", lane: "stopped" }), false);
  assert.equal(agentRuns({ kind: "agent", sid: "s1", paused: true }), false);
  assert.equal(agentRuns({ kind: "message", tid: 4 }), false);
  assert.equal(agentRuns(null), false);
});

test("the Assistant's message card and the Game do not offer the hand-off while an agent runs", () => {
  const cards = read("assistantCards.jsx");
  assert.match(cards, /const handIt = agentRuns\(card\) \? null : /);
  const game = read("gameItem.jsx");
  assert.match(game, /\{!agentRuns\(item\) && <Btn kind=\{m\.verb === "dispatch"/);
});
