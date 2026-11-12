// "Give an agent a job" offered "Just talk it through" - the assistant's own thread. The assistant does nothing itself; only agents do
// (the owner, 2026-10-15: "other option should not be just talk it through with assistant but general agent with all the correct
// buttons ... assistant itself does nothing. only research agents should do things"). The second door is a general agent: which role,
// which brain, which model - the task page's own hand-off - and it starts the moment you press the button.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const ns = readFileSync(new URL("../src/NewSheet.jsx", import.meta.url), "utf8");

test("an agent's job has no door to pick: no live-session-or-general fork (TQ-1397)", () => {
  assert.doesNotMatch(ns, /Just talk it through|Ask the assistant/);
  assert.doesNotMatch(ns, /title="A general agent"|title="A live session"/);
});

// THE AGENT CHAT'S OWN BOX (the owner, 2026-11-08): a general agent's job is typed into the shared PromptBox - no AI picker, no model picker, no
// Connect an AI; Settings decides the AI, and with none connected the box says so with the way to connect one
test("a general agent's job is typed into the chat's own box, with no pickers, and dispatched as general work", () => {
  assert.doesNotMatch(ns, /generalBrains=\{generalBrains\} brainsRead=\{agentsRead\} pick=\{pick\}/);
  assert.match(ns, /<PromptBox text=\{words\} setText=\{setText\} pics=\{pics\} busy=\{busy\} onSend=\{submit\}/);
  assert.match(ns, /const agentBox = \(kind === "agent" && how === "general"\) \|\| kind === "chat"/);
  assert.match(ns, /!agentBox && <Button size="small" variant="contained"/, "the box's own Send, no second one in the footer");
  assert.match(ns, /\(await capabilities\(\)\)\.ai === false/, "no AI is the one capability's answer - the demo's agents work");
  assert.ok(ns.includes('/dispatch`, { ...(general ? { kind: "general", agent: role || null } : {})'));
});

// NO KINDS TO PICK (TQ-1397): New is one box - the Assistant makes the words what they are - so there is no row of kinds to lose
test("New has no row of kinds", () => {
  assert.doesNotMatch(ns, /data-tq-new-kinds|KINDS\.map|role="tab"/);
});
