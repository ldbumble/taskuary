// The Agent work card says the result once (agentRecord.js): the step that IS the result points back to it, a chat's
// own turns are not listed again under the chat, and a report part equal to the result is not repeated.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { cardParts, hasMore, moreParts, plain, recordFacts, recordHead, recordSteps, splitFiles } from "../src/agentRecord.js";

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

// THE ONE MORE (the owner, 2026-10-12: "main summary, then details behind more"): what happened is the card; everything
// else is behind one button that names what it holds.
const SAID = "Merged #41 as reviewed.\n\nYour local main is one commit behind origin; I left it alone.";
const ended = { report: { summary: "Merged #41; local main is behind." }, result: SAID, files: ["C:/work/portal/a.py"], cwd: "C:/work/portal",
  steps: [{ k: "tool", name: "Bash", text: "gh pr merge 41" }, { k: "said", text: SAID }] };

test("More names everything past what happened: its last message, files, the run, since then, steps, earlier sessions", () => {
  assert.deepEqual(moreParts(ended, { timeline: [{ text: "Started" }], since: { text: "merged" }, earlier: 1 }),
    ["its last message", "1 file", "the timeline", "since then", "1 step", "1 earlier session"]);
  assert.deepEqual(moreParts({ result: "Done." }), [], "nothing past what happened, no More at all");
});

test("the last message is said once on the card - in What happened or behind More, never both", () => {
  const short = { result: "PR merged; ready to close.", steps: [{ k: "said", text: "PR merged; ready to close." }] };
  assert.equal(cardParts(short).lead, "PR merged; ready to close.");
  assert.deepEqual(moreParts(short), [], "it led, so More does not hold it again");
  assert.equal(recordSteps(short)[0].k, "result", "and its step points back to it");
  const p = cardParts(ended);
  assert.ok(p.lead !== p.message && p.message === SAID);
});

test("the head is the story's sentence; with none, what ended it upstream - which is then not repeated as since then", () => {
  const story = { kind: "left", line: "You ended the session." }, end = { text: "Merged on GitHub.", at: "2026-10-12 09:00" };
  assert.deepEqual(recordHead(story, end), { state: story, since: end });
  assert.deepEqual(recordHead(null, end), { state: { kind: "ended", line: "Merged on GitHub." }, since: null });
  assert.deepEqual(recordHead(null, null), { state: null, since: null });
});

test("the card has one More and no second section for the last message, files or steps", () => {
  const src = readFileSync(fileURLToPath(new URL("../src/AgentRecord.jsx", import.meta.url)), "utf8");
  const card = src.slice(src.indexOf("export const SessionRecord"), src.indexOf("export const AgentRecord"));
  assert.equal(card.match(/<Button /g).length, 1, "one control on the card");
  for (const h of ["Its last message", "Files it saved", "Every step", "Since then", "Earlier sessions", "<Timeline "])
    assert.ok(card.indexOf(h) > card.indexOf("{more && "), `${h} is behind More`);
  assert.doesNotMatch(src.slice(src.indexOf("export const AgentRecord")), /Since then|Earlier sessions/, "not repeated outside the card");
});

test("a folded line is plain text", () => assert.equal(plain("**Merged** `#41` as reviewed"), "Merged #41 as reviewed"));

// A regular agent's answers are the chat right under the card: the card over it said the answer a second time.
test("over a conversation the card holds only the working behind its answers", () => {
  const src = readFileSync(fileURLToPath(new URL("../src/AgentRecord.jsx", import.meta.url)), "utf8");
  assert.match(src, /const chat = inChat && now\?\.source === "conversation";\n  const s = chat \? \{ \.\.\.now, result: "", report: \{\} \}/);
  assert.match(src, /\{inChat \? null : lead \?/, "no What happened over the chat");
  const page = readFileSync(fileURLToPath(new URL("../src/TaskPage.jsx", import.meta.url)), "utf8");
  assert.match(page, /inChat=\{workspaceMode === "general"\}/);
});
