import test from "node:test";
import assert from "node:assert/strict";
import { strangerLine } from "../src/strangerLine.js";

test("a stranger's task gets the one line, with the reason for the tooltip", () => {
  const l = strangerLine({ origin: { origin: "stranger", why: "sent by someone not in your people" } });
  assert.equal(l.text, "Stranger's words · runs in auto mode");
  assert.equal(l.why, "sent by someone not in your people");
});
test("owner, trusted and missing origin say nothing", () => {
  for (const o of ["owner", "trusted"]) assert.equal(strangerLine({ origin: { origin: o, why: "x" } }), null);
  assert.equal(strangerLine({}), null);
  assert.equal(strangerLine(null), null);
});
test("a stranger's task carries what its words read as trying to make an agent do, and only a stranger's", () => {
  assert.equal(strangerLine({ origin: { origin: "stranger", danger: "asks the agent to run a script from a link" } }).danger,
    "asks the agent to run a script from a link");
  assert.equal(strangerLine({ origin: { origin: "stranger" } }).danger, null);
  assert.equal(strangerLine({ origin: { origin: "trusted", danger: "x" } }), null);
});
