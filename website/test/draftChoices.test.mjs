// A REPLY DRAFT'S CHOICES ARE CLOSE OUT, REDRAFT OR MARK DONE (the owner, 2026-10-01: "rejected is useless - it should be
// redraft or close task"). Reject threw the draft away and left the task open, which is neither. A proposal keeps its
// Dismiss and a close-out its Not yet - neither is a reply draft. The server still takes "reject" from an old caller.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { rowOf } from "../src/actionRow.js";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

test("the draft's decision is Close out, Redraft and Mark done - no Reject, in the row or on the card", () => {
  const src = read("ReviewDecision.jsx");
  assert.doesNotMatch(src, /"Reject"/, "no button says Reject");
  // only a proposal is dismissed; a close-out has Remind me instead (2026-10-02)
  assert.equal((src.match(/decide\("reject"\)/g) || []).length, 2);
  assert.match(src, /: proposal \? \[\{ id: no\("reject"\)[^\n]*decide\("reject"\)/);
  assert.match(src, /\{proposal && proposal\.kind !== "closeout" && <Button[^\n]*decide\("reject"\)/);
  assert.doesNotMatch(src, /decideBoth\("reject"\)/, "no Not yet: Next keeps it open, Remind me keeps it until a day");
  assert.match(src, /\{ id: no\("redraft"\), group: "decide"/, "Redraft stands beside Close out, not behind More");
  assert.match(src, /\{ id: no\("done"\), group: "decide", closes: true[^\n]*run: onMarkDone/, "Mark done is the task's own close");
  // the task view hands it ITS Mark done - put down at the press, a live session asked first (ac051beb)
  assert.match(read("TaskPage.jsx"), /<ReviewDecision review=\{pendingReview\} closeout=\{closeoutRv\} toRow=\{inRow\} onMarkDone=\{askFinish\} onSent=\{sent\} onRemind=\{\(e, a\) => setRemindAt\(a \|\| e\?\.currentTarget\)\}/);
});

test("the row draws Mark done once: the decision's, with the task's own left out of More", () => {
  const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
  const r = rowOf({ ref: "TQ-1", list: [v("approve", "decide", { tone: "p" }), v("4:redraft", "decide"), v("4:done", "decide", { closes: true }), v("done", "more"), v("next", "next")] });
  assert.deepEqual(r.decide.map((x) => x.id), ["approve", "4:redraft", "4:done"]);
  assert.ok(!r.more.some((x) => x.id === "done"), "not twice");
  const plain = rowOf({ ref: "TQ-1", list: [v("approve", "decide", { tone: "p" }), v("done", "more"), v("next", "next")] });
  assert.deepEqual(plain.agent.map((x) => x.id), ["done"], "a decision with no close of its own: Mark done on the bar beside it (2026-10-06)");
  assert.ok(!r.agent.some((x) => x.id === "done"), "and still not twice beside the draft's own");
});

test("the Timeline's reply box and the dock's reply are Send, Mark done and Redraft - no Reject", () => {
  const feed = read("FeedView.jsx");
  assert.doesNotMatch(feed, />Reject<\/Button>/);
  assert.match(feed, /decide\(reviewId, "no_reply"\)[^\n]*\n?[^\n]*>Mark done<\/Button>/);
  const dock = read("GeneralWorkspace.jsx");
  assert.match(dock, /decide\(review, "no_reply"\)\}>Mark done<\/Button>/, "the no-reply close says what it does");
  assert.match(dock, /decide\(review, "reject"\)\}>Dismiss<\/Button>/, "an agent's proposed action is still dismissed");
});

test("the walk's reply card offers Redraft over a draft it has", () => {
  const cards = read("assistantCards.jsx");
  const reply = cards.slice(cards.indexOf("export function ReplyCard"), cards.indexOf("export function MeetingCard"));
  assert.match(reply, /\{ verb: "redraft", label: busy === "redraft" \? "Drafting…" : "Redraft"/);
  assert.doesNotMatch(reply, /"Reject"/);
});
