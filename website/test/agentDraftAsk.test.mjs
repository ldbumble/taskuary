import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { alreadyAnswered, answeredLine } from "../src/agentDraftAsk.js";

// AN AGENT'S DRAFT IS A CARD IN THE ONE CHAT (the owner, 2026-11-06), and a draft the owner already answered says so. Invented people only.
const mine = { ReviewId: 7, Kind: "draft_reply", Status: "pending", DraftText: "Hi Erin - which week should the report cover?", DraftBy: "agent:Claude Code",
  MessageId: 40, FromName: "Erin Blake", FromEmail: "erin@northwind.example" };

test("already answered: a reply to that person newer than the message the draft answers - outside Taskuary or from here", () => {
  const against = { MessageId: 40, FromEmail: "erin@northwind.example", SentAt: "2026-11-02 09:00:00" };
  const outside = { at: "2026-11-02 09:30:00", text: "Hi Erin, the report covers the week of the 26th - all of it, night shift too.",
    msg: { RecipientsJson: JSON.stringify({ to: ["erin@northwind.example"] }) } };
  const a = alreadyAnswered({ draft: mine, sent: [outside], against });
  assert.equal(a.who, "Erin Blake");
  assert.equal(a.at, "2026-11-02 09:30:00");
  assert.ok(a.words.startsWith("Hi Erin, the report covers") && a.words.endsWith("...") && a.words.length < 70, a.words);
  assert.equal(answeredLine(a, () => "9:30 AM"), `You already answered Erin Blake at 9:30 AM: "${a.words}"`);
  const fromHere = { at: "2026-11-02 10:00:00", text: "Sent from Taskuary", review: { ReviewId: 3, FromEmail: "erin@northwind.example" } };
  assert.equal(alreadyAnswered({ draft: mine, sent: [outside, fromHere], against }).words, "Sent from Taskuary", "the newest one");
  // ...not: one older than the message the draft answers, one to someone else, the draft itself, or nothing at all
  assert.equal(alreadyAnswered({ draft: mine, sent: [{ ...outside, at: "2026-11-02 08:00:00" }], against }), null);
  assert.equal(alreadyAnswered({ draft: mine, sent: [{ ...outside, msg: { RecipientsJson: '["gail@northwind.example"]' } }], against }), null);
  assert.equal(alreadyAnswered({ draft: mine, sent: [{ ...fromHere, review: mine }], against }), null);
  assert.equal(alreadyAnswered({ draft: null, sent: [outside], against }), null);
  assert.equal(answeredLine(null), "");
});

test("the draft is one card, in the chat, its answered line on it - no notice pointing anywhere else", () => {
  const page = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.doesNotMatch(page, /AgentDraftNotice|noticeOn|askWhere/, "nowhere else to point at");
  assert.match(page, /<ReviewDecision review=\{pendingReview\}[^\n]*\n[^\n]*answered=\{answeredYet\}/);
  assert.equal(page.match(/<ReviewDecision review=\{pendingReview\}/g).length, 1, "one card for the draft: the chat's");
});

// AN EARLIER SESSION'S DRAFT IS NOT THE REPLY (the owner, 2026-11-03: "when you continue on general agent it shows the prior reply on bottom
// that the agent generated. Don't show that reply if it was based off another general session not the latest one")
test("a draft an earlier agent session wrote is not drawn while a newer session is live", async () => {
  const { latestDrafts, earlierSession } = await import("../src/agentDraftAsk.js");
  const old = { ...mine, DraftSid: "s-old" }, owned = { ...mine, ReviewId: 9, DraftSid: "owner" }, legacy = { ...mine, ReviewId: 10, DraftSid: null };
  assert.equal(earlierSession(old, "s-new"), true, "Continue opened a new session: the old one's words wait");
  assert.equal(earlierSession(old, "s-old"), false, "the same session, a new turn: still its latest");
  assert.equal(earlierSession(old, ""), false, "no session live: the draft is the task's, in the chat as ever");
  assert.equal(earlierSession(owned, "s-new"), false, "the owner edited it: theirs");
  assert.equal(earlierSession(legacy, "s-new"), false, "one written before drafts knew their session is the server's call (held there)");
  assert.equal(earlierSession({ ...old, DraftBy: "" }, "s-new"), false, "Taskuary's own draft belongs to no agent session");
  assert.equal(earlierSession({ ...old, Status: "approved" }, "s-new"), false, "what went is history, never hidden");
  const fresh = { ...mine, ReviewId: 11, DraftSid: "s-new" };
  assert.deepEqual(latestDrafts([old, fresh, owned], "s-new").map((r) => r.ReviewId), [11, 9]);
  const page = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /reviews = latestDrafts\(roundReviews\(allReviews, rounds\), liveSession \? term\?\.sid \|\| "" : ""\)/,
    "the page's reply, its Send and Mark done all read the reviews with it left out");
});
