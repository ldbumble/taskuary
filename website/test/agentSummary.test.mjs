import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { answerShown, chatReplyShown, foldedSummaries, hasReply, lastAnswerSummed, nextSteps, oneLine } from "../src/agentSummary.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

// EACH TURN ENDS IN THREE PARTS (general.SUMMARY_TYPE, Task 3.5): the newest stays open, every earlier one folds
test("every summary but the newest folds", () => {
  const f = foldedSummaries([{ id: "a", summary: {} }, { id: "b" }, { id: "c", summary: {} }]);
  assert.ok(f.has("a"));
  assert.ok(!f.has("c"));
  assert.ok(!f.has("b"));
  assert.equal(foldedSummaries([]).size, 0);
  assert.equal(foldedSummaries(undefined).size, 0);
});
// ...but a newest answer with no summary of its own folds them all: its drafts follow it, not a turn up the chat (the owner, 2026-11-05)
test("a newest answer with no summary folds every summary, so the cards follow it", () => {
  const msgs = [{ id: "a", role: "assistant", summary: {} }, { id: "u", role: "user" }, { id: "b", role: "assistant" }];
  assert.deepEqual([...foldedSummaries(msgs)], ["a"]);
  assert.equal(lastAnswerSummed(msgs), false);
  assert.equal(lastAnswerSummed([...msgs, { id: "c", role: "assistant", summary: {} }]), true);
  // ...and anything after the answer (a mail, the owner's words) makes that turn history: it folds and its card goes (the owner, 2026-11-05:
  // "the draft card is part of the chat response ... next turn if i ask something or new input that turn is gone")
  assert.equal(lastAnswerSummed([{ id: "a", role: "assistant", summary: {} }, { id: "w", role: "user", brief: true }]), false);
  assert.deepEqual([...foldedSummaries([{ id: "a", role: "assistant", summary: {} }, { id: "w", role: "user", brief: true }])], ["a"]);
  assert.equal(lastAnswerSummed([{ id: "a", role: "assistant", summary: {} }, { id: "t", role: "user", content: [] }]), false);
});

// A NOTHING-NEW TURN IS ONE LINE (the owner, 2026-11-06): the agent's own judgement, filed as a summary with only `did`
test("a one-line turn is its line, and the real answer before it keeps its draft open", () => {
  assert.equal(oneLine({ did: "Ray thanked you." }), true);
  assert.equal(oneLine({ did: "Ray thanked you.", about: "" , on_you: [] }), true);
  assert.equal(oneLine({ about: "Ray wants the renewal term", did: "Drafted it." }), false);
  assert.equal(oneLine({ did: "Checked it.\nDrafted the reply." }), false);
  assert.equal(oneLine({ did: "Drafted it.", drafted: [{ review: 4 }] }), false);
  assert.equal(oneLine({ did: "" }), false); assert.equal(oneLine(null), false);
  const msgs = [{ id: "a", role: "assistant", summary: { about: "Ray asks", did: "Drafted Ray a reply." } }, { id: "w", role: "user", brief: true },
    { id: "b", role: "assistant", summary: { did: "Ray thanked you." } }];
  assert.deepEqual([...foldedSummaries(msgs)], []);
  // ...but a real answer after it folds both, as ever
  assert.deepEqual([...foldedSummaries([...msgs, { id: "c", role: "assistant", summary: { about: "x", did: "y" } }])], ["a", "b"]);
  const src = read("AgentSummary.jsx");
  assert.ok(src.indexOf("oneLine(summary)") < src.indexOf("if (folded)"), "a one-line turn draws before any heads or Next steps");
});

test("Next steps: nothing left only when no draft waits and no On you step is unticked", () => {
  assert.equal(nextSteps({ summary: { nothing_left: true } }).nothing, true);
  assert.equal(nextSteps({ summary: { nothing_left: false } }).nothing, false);
  assert.equal(nextSteps({ summary: null }).nothing, false);
  const steps = [{ id: "1", text: "Send Ray Colton the signed form", done: false, on_you: true },
                 { id: "2", text: "Already sent", done: true, on_you: true }, { id: "3", text: "Triage's box", done: false }];
  const s = nextSteps({ summary: { nothing_left: true }, checklist: steps });
  assert.equal(s.onYou.length, 1);
  assert.equal(s.onYou[0].text, "Send Ray Colton the signed form");
  assert.equal(s.nothing, false, "an unticked On you step is something left");
  // a pending reply waits: drafts count it, and it is something left; an action or a sent one is not a draft
  const reviews = [{ ReviewId: 1, Kind: "reply", Status: "pending" }, { ReviewId: 2, Kind: "action", Status: "pending" },
                   { ReviewId: 3, Kind: "reply", Status: "sent" }];
  const d = nextSteps({ summary: { nothing_left: true }, reviews });
  assert.deepEqual(d.drafts.map((r) => r.ReviewId), [1]);
  assert.equal(d.nothing, false);
  assert.deepEqual(nextSteps({ summary: { nothing_left: true }, reviews, cards: false }).drafts, []);
});

// ...and a held browser act or a playbook waiting on Approve is something left too (review, Task 3.6)
test("Next steps: an Approve still pending is never Nothing left to do here", () => {
  const held = [{ ReviewId: 7, Kind: "action", Status: "pending" }];
  const a = nextSteps({ summary: { nothing_left: true }, reviews: held });
  assert.deepEqual(a.held.map((r) => r.ReviewId), [7]);
  assert.equal(a.nothing, false);
  const b = nextSteps({ summary: { nothing_left: true }, acts: [{ ReviewId: 8, Kind: "action", Status: "pending" }], reviews: held });
  assert.deepEqual(b.held.map((r) => r.ReviewId), [7, 8], "the chat's own acts and the task's reviews, each once");
  assert.equal(b.nothing, false);
  assert.deepEqual(nextSteps({ summary: { nothing_left: true }, reviews: [{ ReviewId: 9, Kind: "action", Status: "approved" }] }).held, []);
  assert.equal(nextSteps({ summary: { nothing_left: true }, reviews: [{ ReviewId: 9, Kind: "action", Status: "approved" }] }).nothing, true);
});

test("the chat draws the summary, and the turn's working is one line with its steps folded under it", () => {
  const view = read("GeneralWorkspace.jsx");
  assert.match(view, /import AgentSummary, \{ OneBox, StaleDrafts \} from "\.\/AgentSummary\.jsx";/);
  assert.match(view, /foldedSummaries\(/);
  assert.match(view, /data-tq-working=""/);
  assert.match(view, /Working on this…/);
  const card = read("AgentSummary.jsx");
  for (const h of ["What this is about", "What I did", "Next steps", "Nothing left to do here", "data-tq-summary", "data-tq-on-you"])
    assert.ok(card.includes(h), h);
  assert.doesNotMatch(card.slice(0, card.indexOf("export function NoAgentChat")), /<Button|onClick/, "the summary draws no press of its own yet (Task 4.2 brings the cards)");
  assert.doesNotMatch(card + view.slice(view.indexOf("<AgentSummary")), /onChanged=\{work/, "no prop nothing reads yet (Task 4.2 adds it with the cards)");
});

// Review Focus 4 (Task 4.1): until the cards live in the summary (4.2), a pending draft is not counted where no cards are drawn - Close out still draws it
test("a pending draft is no Next step where the summary draws no cards", () => {
  const reviews = [{ ReviewId: 1, Kind: "reply", Status: "pending", DraftText: "Thanks, Erin" }];
  assert.equal(nextSteps({ summary: { nothing_left: false }, reviews, cards: false }).drafts.length, 0);
  assert.equal(nextSteps({ summary: { nothing_left: false }, reviews }).drafts.length, 1);
});

test("the chat's Suggested reply stands only once a reply is in it, never over a bare To line", () => {
  const replyMessage = { MessageId: 1, FromName: "Ray Colton" };
  assert.equal(chatReplyShown({ replyMessage }), false);
  assert.equal(chatReplyShown({ replyMessage, pendingReview: { ReviewId: 3 } }), true);
  assert.equal(chatReplyShown({ replyMessage, sentReview: { ReviewId: 3 } }), true);
  assert.equal(chatReplyShown({ pendingReview: { ReviewId: 3 } }), false);
});

test("a chat task's chat keeps its height while its agent starts: the box sits at the card's foot", () => {
  // the stress run (2026-11-05): while the agent started, the chat shrank to its content and left ~485px of empty card under the box
  const page = read("TaskPage.jsx"), at = page.indexOf('"&:has([data-tq-starting])"');
  assert.ok(at > 0);
  assert.match(page.slice(at - 80, at), /!chatPane/, "the one-line starting room is for a pane that is not the task's chat");
});

test("Suggested reply heads only a reply, never a closed task's Mark done line or a proposal", () => {
  assert.equal(hasReply([]), false);
  assert.equal(hasReply([{ Kind: "action", Status: "pending" }]), false);
  assert.equal(hasReply([{ Kind: "draft_reply", Status: "pending" }]), true);
  assert.equal(hasReply([{ Kind: "draft", Status: "approved" }]), true);
  assert.match(read("AgentSummary.jsx"), /hasReply\(reviews\)/);
});

test("a chat task's chat carries no agent picker, model box or Full screen - only actions", () => {
  // the owner's ruling on the stress run (2026-11-05): "remove as much as possible ui components in the chat unless it's actions"
  const view = read("GeneralWorkspace.jsx");
  assert.match(view, /!dock && !noTools && !chat && toolsAt && !full && <>\{createPortal\(tools, toolsAt\)\}<\/>/);
  assert.match(view, /!dock && !noTools && !chat && !\(toolsAt && !full\) && <Box/);
});

// THE AGENT SAYS WHETHER ITS PROSE IS THE RESULT (the owner, 2026-11-05: "no hardcoded words"): its own `answer_is_result` decides; a turn
// that never said - every turn filed before - keeps the length-or-link rule, so history draws as it did
test("the agent's answer_is_result decides whether its prose shows beside the summary", () => {
  const long = "Here is what I found. ".repeat(40);
  assert.equal(answerShown({ answer_is_result: true }, long), true);
  assert.equal(answerShown({ answer_is_result: false }, "Short and done."), false);
  assert.equal(answerShown({}, "Short and done."), true);
  assert.equal(answerShown({}, long), false);
  assert.equal(answerShown({}, long + " https://northwind.example/brief"), true);
  assert.equal(answerShown({ answer_is_result: true }, "  "), false);
  assert.doesNotMatch(read("GeneralWorkspace.jsx"), /answerWords/, "the pane asks the agent's say, never its own rule");
});

// NEVER TWICE IN A TURN (the owner, 2026-11-08): the post text, "Before you post" and the to-do were drawn in the agent's words and again in
// What I did / Next steps under them. The words are the turn; the summary's prose is drawn only for a turn with none, its cards either way
test("a turn with words of its own draws them once, and the summary keeps only its cards", async () => {
  const { turnAnswered } = await import("../src/agentSummary.js");
  const { readFileSync } = await import("node:fs");
  assert.equal(turnAnswered("Posted text below - press Post."), true);
  assert.equal(turnAnswered("   "), false); assert.equal(turnAnswered(undefined), false);
  const ws = readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  const sum = readFileSync(new URL("../src/AgentSummary.jsx", import.meta.url), "utf8");
  assert.match(ws, /components=\{\{ Text: AssistantText,/, "the words are always drawn");
  const text = ws.slice(ws.indexOf("const AssistantText"), ws.indexOf("const CameIn"));
  assert.doesNotMatch(text, /return null/, "words equal to the summary's did are still drawn - the summary prose is out, so hiding them emptied the turn");
  assert.match(ws, /answered=\{answered\} \/>/);
  const cardsOnly = sum.slice(sum.indexOf("if (answered)"), sum.indexOf("// ...a nothing-new turn"));
  assert.ok(cardsOnly.length > 0, "an answered turn returns before the prose");
  assert.doesNotMatch(cardsOnly, /about|What I did|OnYou|did\b/, "no About, What I did or On you beside the words");
});

// THE TO DO HOLDS ONLY WORK (the owner, 2026-11-09: one task reached 11 lines for 4 pieces of work): an email owed is its Send card, and the
// steps left on the owner are one quiet "On you:" line under the list - never boxes
test("the To do is the work alone, and what is left on the owner is one On you line", async () => {
  const { onYouLine } = await import("../src/checklist.js");
  const items = [{ id: "1", text: "Fix the export column order", done: false }, { id: "2", text: "Email Erin Blake - the new file", done: false, out: { to: "erin@vendor.example" } },
    { id: "3", text: "Press Send on the draft.", done: false, on_you: true }, { id: "4", text: "Connect a calendar", done: false, on_you: true },
    { id: "5", text: "Ticked already", done: true, on_you: true }];
  assert.equal(onYouLine(items), "On you: Press Send on the draft; Connect a calendar.");
  assert.equal(onYouLine(items.slice(0, 2)), "");
  const page = (await import("node:fs")).readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /const todo = checklist\.filter\(\(i\) => !i\.out && !i\.on_you\);/);
  assert.match(page, /\{onYouLeft && <Typography data-tq-on-you-line="" sx=\{\{ \.\.\.ON_YOU_SX, mt: 0\.6 \}\}>\{onYouLeft\}<\/Typography>\}/);
});
