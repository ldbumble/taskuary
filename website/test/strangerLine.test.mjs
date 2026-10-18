import test from "node:test";
import assert from "node:assert/strict";
import { strangerLine } from "../src/strangerLine.js";

test("a stranger's task gets the one line in plain words, with the reason for the tooltip", () => {
  const l = strangerLine({ origin: { origin: "stranger", why: "sent by someone not in your people" } });
  assert.equal(l.text, "From someone you haven't worked with here yet - anything risky waits for your OK");
  assert.equal(l.trust, "Trust them");
  assert.equal(l.why, "sent by someone not in your people");
  assert.doesNotMatch(l.text, /auto mode|stranger/i, "no coding-tool words for someone who never ran one");
});
test("words Taskuary wrote from what it read are not 'someone'", () => {
  const l = strangerLine({ origin: { origin: "stranger", why: "written by Taskuary's report from what it read" } });
  assert.match(l.text, /^Written by Taskuary from what it read/);
  assert.equal(l.trust, "Trust it");
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
