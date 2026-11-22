import test from "node:test";
import assert from "node:assert/strict";


import { replySource, sentElsewhere, unsentReplyReview, replyPhase } from "../src/taskLifecycle.js";


test("what went out elsewhere is your own outgoing messages, not a send from here", () => {
  const rows = [
    { MessageId: 1, Direction: "in", BodyText: "Fixes the export." },
    { MessageId: 2, Direction: "out", Channel: "github", BodyText: "Merged as reviewed - thanks!" },
    { MessageId: "review:9", Direction: "out", ReviewSent: true, BodyText: "Sent from Close out" },
    { MessageId: 3, Direction: "out", BodyText: "  " },
  ];
  assert.deepEqual(sentElsewhere(rows).map((m) => m.MessageId), [2]);
  assert.deepEqual(sentElsewhere(), []);
  // ...but the Sent copy of a reply approved HERE is that reply, however the provider re-spaced it (2026-10-13)
  const mine = [{ ReviewId: 9, Status: "edited", DraftText: "Yes, keep it.", FinalText: "Gail - any ideas?\n\nThanks,\nAlex" }];
  const copy = { MessageId: 7, Direction: "out", OwnText: "Gail - any ideas?\n\n\nThanks,\n\nAlex" };
  assert.deepEqual(sentElsewhere([copy, { MessageId: 8, Direction: "out", BodyText: "Something else" }], mine).map((m) => m.MessageId), [8]);
});
test("a reply answers the newest row somebody sent - never a report joined on after them (2026-10-13)", () => {
  const rows = [
    { MessageId: 1, Channel: "email", Direction: "in", Status: "routed", BodyText: "First" },
    { MessageId: 2, Channel: "email", Direction: "in", Status: "routed", BodyText: "Wrote again" },
    { MessageId: 3, Channel: "report", Direction: "in", Status: "routed", BodyText: "End of day checkup" },
  ];
  assert.equal(replySource(rows).MessageId, 2);
  assert.equal(replySource([rows[2]]).MessageId, 3);          // nobody behind any row: its newest, as before
});


test("a draft the close swept away stays readable, and a decided one reads not needed", () => {
  const swept = { ReviewId: 4, Kind: "draft_reply", Status: "superseded", DraftText: "Merged - thanks, Erin." };
  assert.equal(unsentReplyReview([swept]).ReviewId, 4);
  assert.equal(replyPhase([{ ...swept, Status: "no_reply" }]), "not needed");
});
