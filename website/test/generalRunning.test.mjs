import test from "node:test";
import assert from "node:assert/strict";
import { stepsOf } from "../src/agentSteps.js";


// A turn that filed no answer still says why it died (TQ-0496: the chat showed the question, no reply and no reason)
test("a turn that died shows its reason, with no answer of its own to hang it on", () => {
  assert.deepEqual(stepsOf([{ type: "error", name: "assistant", detail: { result: "the CLI exited" } }]).map((s) => [s.kind, s.summary]), [["error", "⚠ the CLI exited"]]);
});
