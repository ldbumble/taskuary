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
