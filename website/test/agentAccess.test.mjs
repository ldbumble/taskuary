// THE DESIGN WALK (2026-11-20): Agent permissions drew "Full authority (default)" in its picker beside an "Off for agents" button - two states on
// one row. One state per row now, from agentAccess: off, or one level, in one picker; picking saves it.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { ACCESS, accessOf, accessSave } from "../src/agentAccess.js";

const perms = readFileSync(new URL("../src/AgentPermissions.jsx", import.meta.url), "utf8");
const cv = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");

test("a connection's access to agents is one state: off, or the level it is at", () => {
  assert.equal(accessOf({ Roles: "inbound", Scope: "admin" }), "off");
  assert.equal(accessOf({ Roles: "inbound,tool", Scope: "", ScopeDefault: "admin" }), "admin");
  assert.equal(accessOf({ Roles: "tool", Scope: "WRITE" }), "write");
  assert.deepEqual(accessSave({ Roles: "inbound,tool", Scope: "admin" }, "off"), { Roles: "inbound" });
  assert.deepEqual(accessSave({ Roles: "inbound" }, "read"), { Roles: "inbound,tool", Scope: "read" });
  assert.deepEqual(Object.values(ACCESS), ["Off for agents", "Read only", "Read and write", "Full authority"]);
});

test("each row draws one picker and no second word of its state", () => {
  assert.match(perms, /value=\{accessOf\(c\)\}/);
  assert.doesNotMatch(perms, /\(default\)|<Button|off for agents</);
  assert.doesNotMatch(cv, /" — default"/, "the card's Authority row says no default beside the level it is at");
});
