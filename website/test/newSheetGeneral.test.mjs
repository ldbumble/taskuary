// "Give an agent a job" offered "Just talk it through" - the assistant's own thread. The assistant does nothing itself; only agents do
// (the owner, 2026-10-15: "other option should not be just talk it through with assistant but general agent with all the correct
// buttons ... assistant itself does nothing. only research agents should do things"). The second door is a general agent: which role,
// which brain, which model - the task page's own hand-off - and it starts the moment you press the button.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const ns = readFileSync(new URL("../src/NewSheet.jsx", import.meta.url), "utf8");

test("the second door is a general agent, not the assistant's thread", () => {
  assert.doesNotMatch(ns, /Just talk it through|Ask the assistant/);
  assert.match(ns, /title="A general agent"/);
});

test("it asks the hand-off's three questions and dispatches them as general work", () => {
  assert.match(ns, /generalBrains=\{generalBrains\} brainsRead=\{agentsRead\} pick=\{pick\}/);
  assert.ok(ns.includes('/dispatch`, { ...(general\n            ? { kind: "general", agent: role || null, pick: pick || null, model: model || null }'));
});
