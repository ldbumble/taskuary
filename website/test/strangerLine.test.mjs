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
