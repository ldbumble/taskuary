import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { feedInteraction, feedViews } from "../src/feedViews.js";

const feedSource = () => readFileSync(fileURLToPath(new URL("../src/FeedView.jsx", import.meta.url)), "utf8");

test("the Timeline exposes exactly All and Unread when the Assistant supplies its pipe", () => {
  assert.deepEqual(feedViews(true), [
    { key: "unread", label: "work" },
    { key: "", label: "timeline" },
  ]);
  assert.deepEqual(feedViews(false), [{ key: "", label: "timeline" }]);

  const source = feedSource();
  assert.doesNotMatch(source, /NeedsMe|pending_only|label:\s*["']needs me["']|view === ["']pending["']/);
  assert.match(source, /role="group" aria-label="Feed views"[^]*<FilterPills options=\{views\} value=\{view\} onChange=\{setView\} \/>/);
});

test("All rows can only open detail while Unread keeps the existing chat pull", () => {
  for (const rowMode of ["chat", "task"]) {
    assert.deepEqual(feedInteraction("", rowMode, true), {
      unread: false,
      showChatStage: false,
      pullRowIntoChat: false,
    });
  }
  assert.deepEqual(feedInteraction("unread", "chat", true), {
    unread: true,
    showChatStage: true,
    pullRowIntoChat: true,
  });
  assert.equal(feedInteraction("unread", "task", true).pullRowIntoChat, false);
  assert.equal(feedInteraction("unread", "chat", false).pullRowIntoChat, false);

  const source = feedSource();
  assert.match(source, /const visibleStage = interaction\.showChatStage \? stage : null/);
  assert.match(source, /const openRow = \(row\) => \(chatMode \? onPull\(row\) : drill\(row\)\)/);
  assert.doesNotMatch(source, /api\.(?:get|post)\(["'`]\/api\/(?:concierge|funnel\/settle)/);
});
