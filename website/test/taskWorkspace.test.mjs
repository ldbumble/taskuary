import test from "node:test";
import assert from "node:assert/strict";

test("a general agent whose run ended under it offers Continue on its bar; one with its chat open does not", async () => {
  const { barContinues } = await import("../src/taskWorkspace.js");
  assert.equal(barContinues({ canContinue: true, isGeneral: true, ended: "failed" }), true);      // its CLI died part-way through
  assert.equal(barContinues({ canContinue: true, isGeneral: true, ended: "disconnected" }), true);   // cut off
  assert.equal(barContinues({ canContinue: true, isGeneral: true, ended: "stopped" }), true);        // the owner stopped it: always Continue (2026-11-03)
  assert.equal(barContinues({ canContinue: true, isGeneral: true, ended: null }), false);       // a saved chat: its composer continues
  assert.equal(barContinues({ canContinue: true, isGeneral: true, ended: "finished" }), false);
  assert.equal(barContinues({ canContinue: true, isGeneral: false }), true);
  assert.equal(barContinues({ canContinue: false, isGeneral: true, ended: "failed" }), false);
});
