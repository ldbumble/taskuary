import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

// AN AGENT'S DRAFT IS A CARD IN THE ONE CHAT (the owner, 2026-11-06). One the owner answered themselves is retired, never bannered (2026-11-09).
// Invented people only.
const mine = { ReviewId: 7, Kind: "draft_reply", Status: "pending", DraftText: "Hi Erin - which week should the report cover?", DraftBy: "agent:Claude Code",
  MessageId: 40, FromName: "Erin Blake", FromEmail: "erin@northwind.example" };

test("the draft is one card, in the chat - no notice pointing anywhere else, no answered banner over it", () => {
  const page = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.doesNotMatch(page, /AgentDraftNotice|noticeOn|askWhere/, "nowhere else to point at");
  assert.doesNotMatch(page, /answeredYet|alreadyAnswered|answeredLine/, "the superseded draft is retired, never bannered");
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
