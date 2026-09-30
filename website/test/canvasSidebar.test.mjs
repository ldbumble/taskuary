import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

// The canvas redesign's sidebar (docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md):
// buttons on top, then a full-width Work | Timeline selector with the filter as an icon beside it, then the counts line.
test("the sidebar's buttons are New, Reports, Connections, Hub, Settings, in that order", async () => {
  const { SIDE_NAV } = await import("../src/sideNav.js");
  assert.deepEqual(SIDE_NAV.map((n) => n.key), ["new", "reports", "connections", "hub", "settings"]);
  for (const n of SIDE_NAV) assert.ok(n.label && n.hint, n.key);
});

test("the stack sits above the selector, which is full width, and the filter is an icon with a tooltip", () => {
  const feed = src("FeedView.jsx");
  const nav = feed.indexOf("data-tq-sidenav"), views = feed.indexOf('aria-label="Feed views"'), sync = feed.indexOf("Sync now");
  assert.ok(nav > 0 && nav < views && views < sync, "buttons, then the selector, then the counts line");
  assert.match(feed.slice(views, views + 400), /flex: 1/, "the selector takes the row");
  const filter = src("FeedView.jsx").slice(feed.indexOf("function FilterButton"), feed.indexOf("function FilterButton") + 2500);
  assert.match(filter, /<IconButton/);
  assert.match(filter, /<Tooltip title=\{/);
});

test("a section heading walks that section; its chevron alone opens a capped band", () => {
  const view = src("AssistantView.jsx");
  assert.match(view, /data-tq-section-head=\{level\}/);
  assert.match(view, /onClick=\{\(\) => onSection\(level\)\}/);
  assert.match(view, /e\.stopPropagation\(\)/);
});

test("Next inside a section stays in it, then says the section is done and goes back to the walk", async () => {
  const { sectionNext } = await import("../src/funnelPile.js");
  const items = [
    { key: "a", lane: "fyi", order_band: 4 }, { key: "b", lane: "asked", order_band: 2 },
    { key: "c", lane: "fyi", order_band: 4 }, { key: "d", lane: "fyi", order_band: 4, settling: true },
  ];
  assert.equal(sectionNext(items, "fyi", new Set())?.key, "a");
  assert.equal(sectionNext(items, "fyi", new Set(["a"]))?.key, "c");
  assert.equal(sectionNext(items, "fyi", new Set(["a", "c"])), null);
  const view = src("AssistantView.jsx");
  assert.match(view, /sectionDone\(/);
});

// the owner, 2026-09-29: "make the full time fit ... hide the 8 in today while refreshing ... when it's not refreshing it
// should not have a ..." - swept at 1280-1920 and 390 against every sync string the server writes
test("the sync line fits: one count and the whole time at rest, no counts and what it is reading while it syncs", async () => {
  const feed = src("FeedView.jsx");
  assert.match(feed, /\{rows && !\(syncing \|\| bgSync\) && stats\.slice\(0, 1\)\.map\(\(s2\) => \(/);
  assert.match(feed, /title=\{stats\.map\(\(x\) => `\$\{x\.n\} \$\{x\.label\}`\)\.join\(" · "\)\}/);
  assert.match(feed, /terse: !\(syncing \|\| bgSync\)/);
  const { syncFace } = await import("../src/syncTiming.js");
  const at = new Date(2026, 8, 29, 22, 26);
  assert.equal(syncFace({ checked: true, started: true, lastAt: at, terse: true }), "started 10:26 PM");
  assert.equal(syncFace({ checked: true, lastAt: at, terse: true }), "checked 10:26 PM");
});
