// A REPLY NO LONGER NEEDED IS GONE (the owner, 2026-11-09, said ~40 times: "if we respond show on left side and then agent reevaluates if action
// still required"). The agent's re-think says so in one line and retires the draft (verdicts.not_needed: closed unsent, under Not sent). The card
// once kept it with "Not needed - <why>", and the page an orange "You already answered <who> at <time>" over it - both with Send under them.
// Invented people only.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { nextSteps, draftHome, freshNext } from "../src/agentSummary.js";
import { pendingReplyReview } from "../src/taskLifecycle.js";
import * as ask from "../src/agentDraftAsk.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
// the draft as the server hands it back once the owner answered Erin themselves and the agent re-thought: retired, its words kept
const retired = { ReviewId: 7, Kind: "draft_reply", Status: "closed_unsent", DraftText: "Hi Erin, yes - come over for the meeting.",
  NotNeeded: "Alex answered Erin on WhatsApp", DecideNote: "withdrawn - Alex answered Erin on WhatsApp", turn: "comment-2" };

test("(a) a review marked not needed renders no Send and no banner", () => {
  const rd = read("ReviewDecision.jsx");
  assert.doesNotMatch(rd, /NotNeeded|data-tq-not-needed|Not needed - /, "no Not needed line on a card");
  assert.doesNotMatch(rd, /data-tq-already-answered|answered = ""|as a second reply/, "no You-already-answered banner, no second-reply Send");
  assert.equal(ask.alreadyAnswered, undefined); assert.equal(ask.answeredLine, undefined);
  assert.doesNotMatch(read("TaskPage.jsx"), /answered=\{/);
  // ...and the retired draft is no card anywhere: not the page's pending reply, not a Next step, not a turn's card
  assert.equal(pendingReplyReview([retired]), undefined);
  assert.deepEqual(nextSteps({ reviews: [retired] }).drafts, []);
  assert.equal(draftHome([retired], [{ id: "comment-2", role: "assistant", createdAt: "2026-11-10 09:00:00" }]), null);
});

test("(c) the re-evaluated turn shows one line and no card", () => {
  const n = nextSteps({ summary: { did: "You answered Erin yourself - no new response needed.", nothing_left: true }, reviews: [retired] });
  assert.deepEqual([n.drafts, n.onYou, n.held, n.nothing], [[], [], [], true]);
  assert.equal(freshNext([retired]), true, "nothing stale waits either");
});

// (b) the owner's outside reply is an input entry on the LEFT: the server places it after the last agent turn (general.shown_history, pinned by
// tests/test_owner_input_on_canvas.py) as a brief whose mail is theirs; the page draws that brief in place, its own row on the left
test("(b) the owner's outside reply renders as a left-side input entry, in the stream's order", () => {
  const ws = read("GeneralWorkspace.jsx");
  assert.match(ws, /if \(brief && chat\) return mail\?\.length \? <><MessagePrimitive\.Root className="tq-aui-message tq-aui-brief"><Arrived mail=\{mail\} \/>/);
  assert.match(ws, /data-tq-chat-arrived=\{x\.own \? "own" : ""\}/);
  assert.match(ws, /const headOf = \(x\) => x\.own \? \["You", ON_WORD/);
  assert.match(read("generalWorkspace.css"), /\.tq-aui-chat \.tq-aui-arrived-own \{ justify-self: start;/);
});
