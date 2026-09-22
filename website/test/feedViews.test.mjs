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
  // The switch between the two rails is a SWITCH - a sunk track with a raised thumb - and not a
  // fourth pill of the same shape as the filters beside it; and the two pickers are one control
  // that says what it is filtering to (the owner, 2026-09-16: "the work/timeline vs all
  // kinds/all sources filters look weird").
  assert.match(source, /role="group" aria-label="Feed views"[^]*views\.map\(\(v\) =>[^]*onClick=\{\(\) => setView\(v\.key\)\}/);
  assert.match(source, /<FilterButton cat=\{cat\} pick=/);
  assert.doesNotMatch(source, /"aria-label": "Timeline category"/);
  assert.doesNotMatch(source, /"aria-label": "Timeline source"/);
  assert.match(source, /filterLabel\(cat, pick\)/);
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

test("the rail is a share of the window, not a number of pixels", () => {
  // A flat 500px was a third of a laptop and a quarter of a desktop monitor - the same rail in
  // two different shapes (the owner, 2026-09-22: "it should scale down... it's 20% of the screen
  // and should be the same on desktop"). The clamp is what a one-line row needs at either end.
  const source = feedSource();
  assert.match(source, /md: "minmax\(0, clamp\(380px, 25vw, 560px\)\) minmax\(0, 1fr\)"/,
    "the rail's width lives in one place, and it is proportional");
  assert.doesNotMatch(source, /md: "minmax\(0, \d+px\) minmax/,
    "a fixed pixel rail is the thing this replaced");
  // New belongs on the rail's right edge. It was moved beside the filter once and that was not
  // asked for; the width was (the owner, 2026-09-22: "put the new button where it was").
  const at = source.indexOf("onClick={() => setNewOpen(true)}");
  assert.notEqual(at, -1, "the New button is still in the rail's header");
  assert.match(source.slice(at, at + 400), /ml: "auto"/);
});
