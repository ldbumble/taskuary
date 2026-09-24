// A reply closed without sending stays on its task - done or not (the owner, 2026-09-24: "draft should
// always stay on task even on done task"). The data always kept it; the page only ever looked for a
// pending or a sent one, so a closed task's draft was there and never shown.
import test from "node:test";
import assert from "node:assert/strict";

import { unsentReplyReview } from "../src/taskLifecycle.js";

test("the newest reply closed without sending is the one the task keeps", () => {
  const rows = [
    { ReviewId: 1, Kind: "draft", Status: "no_reply", DraftText: "older words" },
    { ReviewId: 3, Kind: "draft_reply", Status: "closed_unsent", DraftText: "the agent's reply" },
    { ReviewId: 2, Kind: "draft", Status: "rejected", DraftText: "middle" },
  ];
  assert.equal(unsentReplyReview(rows).ReviewId, 3);
});

test("a sent reply, an action, or a draft with no words is not an unsent reply", () => {
  assert.equal(unsentReplyReview([{ ReviewId: 1, Kind: "draft", Status: "sent", DraftText: "x" }]), undefined);
  assert.equal(unsentReplyReview([{ ReviewId: 1, Kind: "action", Status: "no_reply", DraftText: "x" }]), undefined);
  assert.equal(unsentReplyReview([{ ReviewId: 1, Kind: "draft", Status: "no_reply", DraftText: "  " }]), undefined);
  assert.equal(unsentReplyReview(), undefined);
});
