import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { stepsOf } from "../src/agentSteps.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");


test("a turn that died shows its reason, with no answer of its own to hang it on", () => {
  const view = read("GeneralWorkspace.jsx");
  assert.deepEqual(stepsOf([{ type: "error", name: "assistant", detail: { result: "the CLI exited" } }]).map((s) => [s.kind, s.summary]), [["error", "⚠ the CLI exited"]]);   // the reason is built
  // ...and it reaches the page. The trail used to be folded into the newest ASSISTANT message,
  // so a turn that filed no answer folded it into nothing and the chat showed the question,
  // no reply, and no reason at all (TQ-0496).
  // ...the newest TURN's: a press made since (a stop) stays under it (the side-by-side walk, 2026-11-11)
  assert.match(view, /const at = out\.findLastIndex\(\(m\) => !m\.press\), tail = out\[at\];/);
  assert.match(view, /tail\?\.role === "assistant"[\s\S]{0,400}?out\.splice\(at \+ 1, 0, \{ id: `trace-/);
  assert.doesNotMatch(view, /for \(let i = out\.length - 1; i >= 0; i -= 1\)/);
});
