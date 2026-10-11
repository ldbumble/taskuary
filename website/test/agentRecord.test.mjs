// The Agent work card says the result once (agentRecord.js): the step that IS the result points back to it, a chat's
// own turns are not listed again under the chat, and a report part equal to the result is not repeated.
import test from "node:test";
import assert from "node:assert/strict";
import { hasMore, recordFacts, recordSteps, reportParts } from "../src/agentRecord.js";

const coding = { source: "Claude Code log", cli: "claude", at: "2026-10-10 09:00:03", result: "Fixed: the cursor reset.",
  counts: { thought: 2, tool: 1 }, files: ["ledger/importer.py"],
  report: { decided: "the cursor reset on retry", changed: "patched importer.py", summary: "Fixed: the cursor reset." },
  steps: [{ k: "you", text: "Why twice?" }, { k: "thought", text: "cursor" }, { k: "tool", name: "Edit", text: "importer.py" },
    { k: "said", text: "Fixed:  the cursor reset." }] };

test("the result step points back to the result instead of repeating it", () => {
  assert.deepEqual(recordSteps(coding).map((s) => s.k), ["you", "thought", "tool", "result"]);
});

test("a report part that is the result is not shown twice", () => {
  assert.deepEqual(reportParts(coding).map(([k]) => k), ["Decided", "Changed"]);
});

test("a conversation lists only its working - its turns are the chat", () => {
  const chat = { source: "conversation", result: "August was up 8%.", steps: [{ k: "you", text: "How?" }, { k: "tool", name: "Read", text: "spend.csv" },
    { k: "said", text: "August was up 8%." }] };
  assert.deepEqual(recordSteps(chat).map((s) => s.k), ["tool"]);
  assert.equal(hasMore({ ...chat, steps: [{ k: "said", text: "August was up 8%." }] }), false);
});

test("facts name who, when and how much", () => {
  assert.deepEqual(recordFacts(coding), ["claude", "2026-10-10 09:00", "2 thoughts", "1 step", "1 file"]);
});
