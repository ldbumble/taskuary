import test from "node:test";
import assert from "node:assert/strict";
import { agentWorkspaceMode } from "../src/taskWorkspace.js";

// the ended session is the Agent work step's record; the workspace is only what is happening now (2026-10-12)
test("a saved session leaves no workspace of its own", () => {
  assert.equal(agentWorkspaceMode({ session: null, wrapped: { report: "done" } }), "empty");
  assert.equal(agentWorkspaceMode({ session: { alive: true }, wrapped: { report: "done" } }), "live");
});

test("the active wrap operation replaces the terminal until its result is ready", () => {
  assert.equal(agentWorkspaceMode({ session: { alive: true }, wrapping: "wrap" }), "wrapping");
});

test("a general task shows no assistant workspace until it was actually sent", () => {
  assert.equal(agentWorkspaceMode({ isGeneral: true, generalStarted: false }), "empty");
  assert.equal(agentWorkspaceMode({ isGeneral: true, generalStarted: true }), "general");
});

test("a general agent's pause replaces the conversation while it settles, and the conversation comes back after", () => {
  assert.equal(agentWorkspaceMode({ isGeneral: true, generalStarted: true, wrapping: "pause" }), "wrapping");
  assert.equal(agentWorkspaceMode({ isGeneral: true, generalStarted: true, wrapped: { note: "saved" } }), "general");
  assert.equal(agentWorkspaceMode({
    isGeneral: true,
    generalStarted: true,
    session: { alive: true },
    wrapped: { note: "an older run" },
  }), "general");
});
