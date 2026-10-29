// The Agent work card says the result once (agentRecord.js): the step that IS the result points back to it, a chat's
// own turns are not listed again under the chat, and a report part equal to the result is not repeated.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { cardParts, hasMore, moreParts, plain, recordFacts, recordHead, recordSteps, runCost, splitFiles } from "../src/agentRecord.js";

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

// cost & time per run (the owner, 2026-10-22): one quiet addition to the facts; an unknown cost is said by saying nothing
test("a run's time, new tokens and priced cost join the facts, and nothing is said of what is unknown", () => {
  const run = { ...coding, took: 754, usage: { in: 1_250_000, cached: 1_200_000, out: 8_000, cost: 0.8412 } };
  assert.deepEqual(runCost(run), ["13m", "58K tokens", "$0.84"]);
  assert.deepEqual(recordFacts(run).slice(4), ["13m", "58K tokens", "$0.84"]);
  assert.deepEqual(runCost({ ...coding, took: 45, usage: { in: 900, cached: 0, out: 300 } }), ["45s", "1K tokens"]);   // no cost: no "$0"
  assert.deepEqual(runCost({ took: 3 * 3600 + 600, usage: { in: 2, out: 1, cost: 0.004 } }), ["3h 10m", "3 tokens", "<$0.01"]);
  assert.deepEqual(runCost(coding), []);
});

// THE ONE MORE (the owner, 2026-10-12: "main summary, then details behind more"): what happened is the card; everything
// else is behind one button that names what it holds.
const SAID = "Merged #41 as reviewed.\n\nYour local main is one commit behind origin; I left it alone.";
const ended = { report: { summary: "Merged #41; local main is behind." }, result: SAID, files: ["C:/work/portal/a.py"], cwd: "C:/work/portal",
  steps: [{ k: "tool", name: "Bash", text: "gh pr merge 41" }, { k: "said", text: SAID }] };

// ...and not the runs before it: those are a line each under the record (EarlierRuns, 2026-10-29), never inside one run's More
test("More names everything past what happened: its last message, files, the run, since then, steps", () => {
  assert.deepEqual(moreParts(ended, { timeline: [{ text: "Started" }], since: { text: "merged" }, earlier: 1 }),
    ["its last message", "1 file", "the timeline", "since then", "1 step"]);
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
  for (const h of ["Its last message", "Files it saved", "Every step", "Since then", "<Timeline "])
    assert.ok(card.indexOf(h) > card.indexOf("{more && "), `${h} is behind More`);
  assert.doesNotMatch(src.slice(src.indexOf("export const AgentRecord"), src.indexOf("const ResultView = ")), /Since then/, "not repeated outside the card");
  assert.doesNotMatch(card, /Earlier sessions|earlier=/, "earlier runs are listed under the record, not inside one run's More");
  // ...and the Result says Since then once: its replay's record is handed no `since` (the redesign, 2026-10-21)
  const result = src.slice(src.indexOf("const ResultView = "), src.indexOf("// EVERY RUN BY ITS LAST WORDS"));
  assert.match(result, /<SessionRecord s=\{s\} draft=\{draft\} startOpen timeline=\{story\?\.steps \|\| \[\]\} \/>/);
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

test("what the floor refused a stranger's session is behind More, named on it", () => {
  const s = { result: "Done.", refused: [{ text: "Read: refused", at: "2026-10-15 09:00" }] };
  assert.equal(hasMore(s), true);
  assert.deepEqual(moreParts(s), ["1 refusal"]);
});

// THE RESULT (the task page redesign, owner-approved 2026-10-21): when the agent has stopped and saved, the work column says what it
// found, how it resolved it and its write-up whole - each from the saved report, said once - and the session is one Replay line
test("the result reads the write-up's own parts, each once, and nothing it did not record", async () => {
  const { diffStat, resultParts } = await import("../src/agentRecord.js");
  const full = resultParts({ result: "Skipped the row with no manager; 9 passed. Not pushed - yours to approve.",
    report: { decided: "A site with no manager stopped the whole run", changed: "Skip that row and log it once; a test for it",
      summary: "Census sync no longer stops on a site with no manager." } });
  assert.deepEqual(full.rows.map(([k]) => k), ["What it found", "How it resolved it"]);
  assert.equal(full.summary, "Census sync no longer stops on a site with no manager.");
  assert.equal(full.writeup, "Skipped the row with no manager; 9 passed. Not pushed - yours to approve.");
  // the last words that only repeat the summary are not said twice; a write-up with no report parts is the whole of it
  assert.equal(resultParts({ result: "Fixed: the cursor reset.", report: { summary: "Fixed: the cursor reset." } }).writeup, "");
  assert.deepEqual(resultParts({ result: "Reran the nightly; it passed." }), { rows: [], summary: "", writeup: "Reran the nightly; it passed." });
  assert.deepEqual(resultParts({}), { rows: [], summary: "", writeup: "" }, "nothing recorded, nothing invented");
  // the run's own diff, counted
  const diff = ["diff --git a/app/census/sync.py b/app/census/sync.py", "--- a/app/census/sync.py", "+++ b/app/census/sync.py", "@@ -1,2 +1,4 @@",
    " def sync(site):", "+    if not site.manager:", "+        continue", "-    pass", "--- /dev/null", "+++ b/tests/test_census_sync.py", "+def test_no_manager(): pass"].join("\n");
  assert.deepEqual(diffStat(diff), { files: 2, added: 3, removed: 1 });
  assert.equal(diffStat(""), null);
  const src = readFileSync(fileURLToPath(new URL("../src/AgentRecord.jsx", import.meta.url)), "utf8");
  assert.match(src, /Replay the session/);
  assert.match(src, /api\.get\(`\/api\/task-outputs\/\$\{taskId\}`\)/, "the files it made for the task are listed with its work");
  const page = readFileSync(fileURLToPath(new URL("../src/TaskPage.jsx", import.meta.url)), "utf8");
  assert.match(page, /const resultShown = !term\?\.alive && hasRecord && !news && \[AGENT\.saved, AGENT\.stopped, AGENT\.finished\]\.includes\(agentState\);/);
  // ...and the heading tells the profile it runs under on hover only - the name on it is Taskuary (the owner, 2026-10-28)
  assert.match(page, /title=\{<span title=\{instructionsHint\(runRole\) \|\| undefined\}>\{!term\?\.alive \? \(resultShown \? "Result" : "Agent work"\)/);
  assert.match(page, /rowState === "agentdone" && \(\s*<Typography data-tq-handled="" [^>]*>Nothing to do\. It's handled\.<\/Typography>\)/);
});

// THE RESULT AT REST (the owner, 2026-10-27): what it did and what it based it on, and what it made listed once
test("the Result's summary: the write-up's summary and what it found, else its last message's first paragraph; a shown copy of an output once", async () => {
  const { resultLine, madeOnce } = await import("../src/agentRecord.js");
  assert.deepEqual(resultLine({ report: { summary: "Wrote a one-page plan.", decided: "Erin asked for one box per site." } }),
    { did: "Wrote a one-page plan.", found: "Erin asked for one box per site.", rest: "" });
  const s = { steps: [{ k: "said", text: "I've written the plan for Erin.\n\n**Steps:**\n1. Buy it." }] };
  assert.deepEqual(resultLine(s), { did: "I've written the plan for Erin.", found: "", rest: "**Steps:**\n1. Buy it." });  // the rest of its answer, whole (2026-10-28)
  assert.deepEqual(resultLine(null, "Only its last words."), { did: "Only its last words.", found: "", rest: "" });
  assert.equal(resultLine({ report: { summary: "Same.", decided: "Same." } }).found, "");
  const made = madeOnce([{ id: 1, name: "Pilot-plan.md", kind: "shown" }], [{ id: "o1", name: "pilot-plan.md", kind: "output" }, { id: "o2", name: "costs.xlsx", kind: "output" }]);
  assert.deepEqual(made.map((p) => p.id), [1, "o2"]);
});
