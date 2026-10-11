// The Agent work card says the result once (agentRecord.js): the step that IS the result points back to it, a chat's
// own turns are not listed again under the chat, and a report part equal to the result is not repeated.
import test from "node:test";
import assert from "node:assert/strict";
import { cardParts, hasMore, recordFacts, recordSteps, splitFiles } from "../src/agentRecord.js";

const coding = { source: "Claude Code log", cli: "claude", at: "2026-10-10 09:00:03", result: "Fixed: the cursor reset.",
  counts: { thought: 2, tool: 1 }, files: ["ledger/importer.py"],
  report: { decided: "the cursor reset on retry", changed: "patched importer.py", summary: "Fixed: the cursor reset." },
  steps: [{ k: "you", text: "Why twice?" }, { k: "thought", text: "cursor" }, { k: "tool", name: "Edit", text: "importer.py" },
    { k: "said", text: "Fixed:  the cursor reset." }] };

test("the result step points back to the result instead of repeating it", () => {
  assert.deepEqual(recordSteps(coding).map((s) => s.k), ["you", "thought", "tool", "result"]);
});

test("what happened leads with the summary; a last message that only repeats it is not shown again", () => {
  const p = cardParts(coding);
  assert.equal(p.lead, "Fixed: the cursor reset.");
  assert.deepEqual(p.rows.map(([k]) => k), ["Decided", "Changed"]);
  assert.equal(p.message, "");
});

test("without a report its first paragraph is what happened and the rest is its last message", () => {
  const p = cardParts({ result: "Both invoices are paid.\n\nDetails: the second cleared on Monday." });
  assert.deepEqual([p.lead, p.message, p.rows.length], ["Both invoices are paid.", "Details: the second cleared on Monday.", 0]);
});

test("the last message is called the reply only when the draft on the task is in it", () => {
  const s = { report: { summary: "Fixed and deployed." }, result: "Hi Erin,\n\nAll seven are handled." };
  assert.equal(cardParts(s, "Hi Erin,\n\nAll seven are handled.").isReply, true);
  assert.equal(cardParts(s, "Hi Gail, the report is attached.").isReply, false);
  assert.equal(cardParts(s, "").isReply, false);
});

test("files in the project it worked in are named inside it; scratch files are counted apart", () => {
  const f = splitFiles(["C:\\work\\ledger\\src\\a.py", "C:\\Temp\\scratch\\gen.mjs", "c:/work/ledger/tests/t.py"], "C:\\work\\ledger");
  assert.deepEqual(f, { mine: ["src/a.py", "tests/t.py"], other: ["C:/Temp/scratch/gen.mjs"] });
});

test("a conversation lists only its working - its turns are the chat", () => {
  const chat = { source: "conversation", result: "August was up 8%.", steps: [{ k: "you", text: "How?" }, { k: "tool", name: "Read", text: "spend.csv" },
    { k: "said", text: "August was up 8%." }] };
  assert.deepEqual(recordSteps(chat).map((s) => s.k), ["tool"]);
  assert.equal(hasMore({ ...chat, steps: [{ k: "said", text: "August was up 8%." }] }), false);
});

test("facts name who, when and how much", () => {
  assert.deepEqual(recordFacts(coding), ["claude", "2026-10-10 09:00", "2 thoughts", "1 step"]);
});
