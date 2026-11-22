import test from "node:test";
import assert from "node:assert/strict";

import { agentAssignee, assignedAgent, assigneeLabel } from "../src/agentIdentity.js";

test("agent ownership storage syntax never leaks into the UI", () => {
  assert.equal(agentAssignee("Atlas"), "agent:Atlas");
  assert.equal(assignedAgent("agent:Atlas"), "Atlas");
  assert.equal(assigneeLabel("agent:Atlas"), "Agent", "the profile is instructions, never who works it");
  assert.equal(assigneeLabel("Erin Blake"), "Erin Blake", "a person keeps their name");
  assert.equal(assigneeLabel("owner"), "you");
  assert.equal(assigneeLabel(""), "unassigned");
});
