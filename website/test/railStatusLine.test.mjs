import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const feed = src("FeedView.jsx"), page = src("TaskHubPage.jsx");
// the rail's one status line, from its opening Box to the Sync now button's closing tag
const row = feed.slice(feed.indexOf('data-tq-sync-row=""'), feed.indexOf("</Button>", feed.indexOf('data-tq-sync-row=""')));

// The owner, 2026-10-23: "the text 'checked 12:58' is not centered on top of the rail" - the clock was flex:1 and right-aligned
test("the clock sits centred between two equal sides", () => {
  assert.ok(row.length > 0, "the sync row is marked");
  assert.match(row, /display: setupMode \? "none" : "grid"/);
  assert.match(row, /gridTemplateColumns: "minmax\(max-content, 1fr\) minmax\(0, max-content\) minmax\(max-content, 1fr\)"/);
  const line = row.slice(row.indexOf("data-tq-sync-line"));
  assert.match(line, /textAlign: "center"/);
  assert.doesNotMatch(line.slice(0, line.indexOf("</Typography>")), /flex: 1|textAlign: "right"/);
  assert.match(row, /width: 104, justifySelf: "end"/);
});

// "...it also says chatgpt is not connected. Let's not show errors there but in the errors notifications"
test("the line holds the count, the clock and Sync now - never a connection's failure", () => {
  assert.match(row, /stats\.slice\(0, 1\)/);
  assert.match(row, /syncFace\(\{/);
  assert.doesNotMatch(row, /failed|could not be read|not connected|syncFailed/);
  // the only red the line may carry is the sync's own refusal
  assert.match(row, /color: syncErr \? ALERT_INK : syncing \|\| bgSync \? ACCENT : FAINT/);
});

test("a failed connection reaches the bell, read again when a sync lands", () => {
  assert.match(page, /api\.get\("\/api\/problems"\); setItems\(data\.data \|\| \[\]\)/);
  assert.match(page, /onLive\("ingest-status", load, \{ wait: 1000, max: 5000 \}\)/);
  // one entry per problem, each with its own fix button ("Open the card" for a connection, problems.collect)
  assert.match(page, /items\.map\(\(p\) => \(\s*<Box key=\{p\.key\}/);
  assert.match(page, /onClick=\{\(\) => \{ setEl\(null\); onGo\(p\); \}\}>\{p\.fix \|\| "Fix"\} →<\/Button>/);
});
