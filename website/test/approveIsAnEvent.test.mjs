import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { INPUT_ORIGINS, chatRows, continues, eventOf, isInput, linkWords, originOf, rowMessages, stepsFromAcp } from "../src/chatStream.js";
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

// THE SCREENSHOT'S BUG: an approved held command's note to the agent drew as "You · 4:43 PM" in a coding chat
test("an approved step's note to an ACP agent is never a You bubble, and the turn goes on", () => {
  const updates = [
    { sessionUpdate: "user_message_chunk", content: { type: "text", text: "post the review comment" }, _at: "2026-11-09 16:40:00" },
    { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "The comment is held for your yes." }, _at: "2026-11-09 16:41:00" },
    { sessionUpdate: "user_message_chunk", content: { type: "text", text: NOTE }, _meta: { taskuary: "brief" }, _at: "2026-11-09 16:43:00" },
    { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "Commented on PR #12. Next: wait for the review." }, _at: "2026-11-09 16:43:10" },
  ];
  const rows = chatRows({ sessions: [{ sid: "s1", source: "acp", updates }] });
  assert.deepEqual(rows.map((r) => r.kind), ["you", "turn"], "one input, ONE turn: the press let it go on, no new heading");
  assert.equal(rows[0].text, "post the review comment");
  assert.ok(!rows.some((r) => r.kind === "you" && /approved/.test(r.text)));
  assert.match(rows[1].answer, /Commented on PR #12/);
  assert.ok(rowMessages(rows).filter((m) => m.role === "user").every((m) => !/approved/.test(m.content[0].text)));
  // ...and its brief is read as Taskuary's at the source, never "you"
  assert.ok(stepsFromAcp(updates).some((s) => s.k === "brief" && s.text.startsWith("The owner approved")));
});

test("a typed line or a mail come in since the turn's last step opens a new turn", () => {
  const ups = (third) => [
    { sessionUpdate: "user_message_chunk", content: { type: "text", text: "go" }, _at: "2026-11-09 10:00:00" },
    { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "done one" }, _at: "2026-11-09 10:01:00" },
    third,
    { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "done two" }, _at: "2026-11-09 10:05:00" },
  ];
  const typed = chatRows({ sessions: [{ sid: "s1", source: "acp", updates: ups({ sessionUpdate: "user_message_chunk", content: { type: "text", text: "and the docs" }, _at: "2026-11-09 10:04:00" }) }] });
  assert.deepEqual(typed.map((r) => r.kind), ["you", "turn", "you", "turn"]);
  const brief = { sessionUpdate: "user_message_chunk", content: { type: "text", text: "THE THREAD CHANGED: a reply came in" }, _meta: { taskuary: "brief" }, _at: "2026-11-09 10:04:00" };
  const mail = chatRows({ sessions: [{ sid: "s1", source: "acp", updates: ups(brief) }], mails: [{ at: "2026-11-09 10:03:00", words: "Any news?" }] });
  assert.deepEqual(mail.map((r) => r.kind), ["you", "turn", "mail", "turn"]);
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

test("an approved step's event line carries its result, Taskuary's triggers are events too", () => {
  const ws = read("GeneralWorkspace.jsx"), um = ws.slice(ws.indexOf("const UserMessage = "), ws.indexOf("const ShownCtx"));
  assert.match(ws, /\.\.\.\(m\.press \? \{ press: true, \.\.\.\(m\.result \? \{ result: m\.result \} : \{\}\) \} : \{\}\)/);
  assert.match(um, /data-tq-press-link=""/); assert.match(um, /Show the command/);
  assert.equal(linkWords(URL_), "PR #12");
  assert.equal(eventOf("Signed in to portal.example."), "Signed in to portal.example.");
  assert.equal(eventOf("Folded in TQ-12: the invoice", "Folded in TQ-12: the invoice", [{ words: "x" }]), "", "a fold is an input, never an event line");
  assert.equal(originOf({ role: "user", metadata: { custom: { brief: true, fold: "Folded in TQ-12: the invoice" } } }), "fold");
  assert.equal(eventOf("x".repeat(400)), "", "Taskuary's long instructions are never drawn");
  assert.ok(!/tq-aui-arrived" data-tq-chat-trigger=""/.test(um), "no trigger card on the right");
});

test("an approved act's card turns into its result in place", () => {
  const p = { action: "shell_act", command: "gh pr comment 12 --body-file -", about: "Comment on the pull request", result: { performed: "public comment", said: URL_ } };
  assert.equal(resultOf({ Kind: "action", Status: "pending", DraftText: JSON.stringify(p) }), null);
  const r = resultOf({ Kind: "action", Status: "approved", FinalText: JSON.stringify(p) });
  assert.deepEqual(r, { said: "Approved · ran", what: "Comment on the pull request", url: URL_, command: p.command });
  assert.match(read("ReviewDecision.jsx"), /const done = resultOf\(r\);\n\s*if \(done\) return \(/);
});
