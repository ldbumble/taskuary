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

// A REPLY THAT WAITS FOR HIS SEND IS THE PAGE'S, WHICHEVER AGENT SESSION DRAFTED IT (the owner, 2026-11-11: "reply cards should survive
// untouched"): the page left one out while a newer session was live, so after a restart the card he was about to send had no Send
test("a draft an earlier agent session wrote keeps its card and its Send while a newer session is live", async () => {
  assert.equal(mine.Status, "pending");
  const page = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /reviews = roundReviews\(allReviews, rounds\);/, "the page's reply, its Send and Mark done read every review of the round");
  assert.doesNotMatch(page + readFileSync(new URL("../src/agentDraftAsk.js", import.meta.url), "utf8"), /latestDrafts|earlierSession/);
});
