import test from "node:test";
import assert from "node:assert/strict";
import { agentWorkspaceMode } from "../src/taskWorkspace.js";

test("a restarted live session replaces the prior session-closed card", () => {
  const oldResult = { report: "The previous run finished." };

  assert.equal(agentWorkspaceMode({ session: null, wrapped: oldResult }), "wrapped");
  assert.equal(agentWorkspaceMode({ session: { alive: true }, wrapped: oldResult }), "live");
});

test("the active wrap operation replaces the terminal until its result is ready", () => {
  assert.equal(agentWorkspaceMode({ session: { alive: true }, wrapping: "wrap" }), "wrapping");
});

test("a general task shows no assistant workspace until it was actually sent", () => {
  assert.equal(agentWorkspaceMode({ isGeneral: true, generalStarted: false }), "empty");
  assert.equal(agentWorkspaceMode({ isGeneral: true, generalStarted: true }), "general");
});

test("general-agent pause and finish states replace the conversation while they settle", () => {
  assert.equal(agentWorkspaceMode({ isGeneral: true, generalStarted: true, wrapping: "pause" }), "wrapping");
  assert.equal(agentWorkspaceMode({ isGeneral: true, generalStarted: true, wrapped: { note: "saved" } }), "wrapped");
  assert.equal(agentWorkspaceMode({
    isGeneral: true,
    generalStarted: true,
    session: { alive: true },
    wrapped: { note: "an older run" },
  }), "general");
});
