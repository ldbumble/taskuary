import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { INPUT_ORIGINS, continues, eventOf, isInput, linkWords, originOf } from "../src/chatStream.js";
import { resultOf } from "../src/reviewProposal.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const URL_ = "https://github.com/northwind/ledger/pull/12#issuecomment-1";
const NOTE = "The owner approved it and Taskuary ran `gh pr comment 12 --body-file -` in C:\\work\\ledger. It said: " + URL_ + ". Tell the owner in a line what it did (with its link, if it gave one) and what comes next, then carry on.";

// THE OWNER'S RULE OF INPUTS (2026-11-09): "inputs are messages in the prompt box or from the input channel" - nothing else is a bubble
test("only what the owner typed or what came in on the thread is an input", () => {
  assert.deepEqual(INPUT_ORIGINS, ["typed", "thread", "fold"]);      // a task folded in is new work arriving: an input
  const cases = [
    [{ role: "user", content: [{ type: "text", text: "try now" }] }, "typed", true],
    [{ role: "user", brief: true, mail: [{ words: "Any news?" }] }, "thread", true],
    [{ role: "user", press: true, content: [{ type: "text", text: "You approved it - the held step ran." }] }, "press", false],
    [{ role: "user", brief: true, content: [{ type: "text", text: "Signed in to portal.example." }] }, "taskuary", false],
    [{ role: "user", metadata: { custom: { press: true } } }, "press", false],
    [{ role: "assistant" }, "agent", false],
  ];
  for (const [m, origin, input] of cases) { assert.equal(originOf(m), origin); assert.equal(isInput(m), input); }
});



test("in the general chat a turn after a press goes on under the same head", () => {
  const ms = [
    { id: "a", role: "user", content: [{ type: "text", text: "post it" }] },
    { id: "b", role: "assistant" },
    { id: "p", role: "user", press: true, content: [{ type: "text", text: "You approved it - the held step ran." }] },
    { id: "c", role: "assistant" },
    { id: "d", role: "user", content: [{ type: "text", text: "thanks, now the docs" }] },
    { id: "e", role: "assistant" },
  ];
  assert.deepEqual(ms.map((m, i) => (m.role === "assistant" ? continues(ms, i) : null)).filter((x) => x !== null), [false, true, false]);
  const ws = read("GeneralWorkspace.jsx");
  assert.match(ws, /\{!more && <div className="tq-aui-role">/);
});


test("an approved act's card turns into its result in place", () => {
  const p = { action: "shell_act", command: "gh pr comment 12 --body-file -", about: "Comment on the pull request", result: { performed: "public comment", said: URL_ } };
  assert.equal(resultOf({ Kind: "action", Status: "pending", DraftText: JSON.stringify(p) }), null);
  const r = resultOf({ Kind: "action", Status: "approved", FinalText: JSON.stringify(p) });
  assert.deepEqual(r, { said: "Approved · ran", what: "Comment on the pull request", url: URL_, command: p.command });
  assert.match(read("ReviewDecision.jsx"), /const done = resultOf\(r\);\n\s*if \(done\) return \(/);
});
