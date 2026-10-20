// THE TIMELINE TAB IS GONE (the owner, 2026-10-15: "removing the timeline tab ... replace it with the filter being a
// little larger"). The Assistant's rail is Work alone: no Work | Timeline switch, no second view to switch to, and none
// of the code that only the Timeline ran - its paged loader, its date dock, its history rows.
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const src = (f) => fileURLToPath(new URL(`../src/${f}`, import.meta.url));
const feed = readFileSync(src("FeedView.jsx"), "utf8");

test("there is one view: no switch, no view state, no views module", () => {
  assert.doesNotMatch(feed, /aria-label="Feed views"/);
  assert.doesNotMatch(feed, /setView|useState\(top \? "unread" : ""\)/);
  assert.equal(existsSync(src("feedViews.js")), false, "the Work | Timeline view list is gone with the switch");
});

test("nothing the Timeline alone ran is left behind", () => {
  assert.doesNotMatch(feed, /\/api\/processing\/all|allPage|loadMore|"Timeline date"|ThreadFold|MeetingRow|ComingUp|FunnelBar/);
  for (const gone of ["threadGroups.js", "timelineDay.js", "rowLane.js"]) assert.equal(existsSync(src(gone)), false, gone);
  const all = readFileSync(src("processingAll.js"), "utf8");
  assert.doesNotMatch(all, /processingAllParams|firstProcessingPage|appendProcessingPage|isSnapshotExpired/);
});

test("the filter takes the freed row and says on its face what the rail is narrowed to", () => {
  const button = feed.slice(feed.indexOf("function FilterButton"), feed.indexOf("function FilterButton") + 2500);
  assert.match(button, /const label = filterLabel\(cat, pick\)/);
  assert.match(button, /flex: 1, minWidth: 0, height: 30/);
  assert.match(button, /\{label\}<\/Box>/);
});

test("a card's link to a message opens that message's card on the canvas even when no Work row holds it", () => {
  // it used to be left to the Timeline - a dead click once the Timeline was gone - and then to the rail's own row panel, which is gone too
  // (2026-10-20): the server answers msg:N for any message (funnel.item_for_key), so a pull lands it whatever the rail holds
  assert.doesNotMatch(feed, /drillRef|openHash/);
  assert.match(readFileSync(src("AssistantView.jsx"), "utf8"), /pull\(`msg:\$\{mid\}`\);/);
});
