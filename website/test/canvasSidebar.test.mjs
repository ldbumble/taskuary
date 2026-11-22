import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

// The canvas redesign's sidebar (docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md):
// buttons on top, then the filter taking the whole row (the Work | Timeline selector it sat beside is gone, the owner
// 2026-10-15: "replace it with the filter being a little larger"), then the counts line.
test("the sidebar's buttons are New, Reports, Connections, Hub, Settings, in that order", async () => {
  const { SIDE_NAV } = await import("../src/sideNav.js");
  assert.deepEqual(SIDE_NAV.map((n) => n.key), ["new", "reports", "connections", "hub", "settings"]);
  assert.ok(!SIDE_NAV.some((n) => n.key === "about"), "About you is the avatar in the top bar's corner (2026-11-06)");
  for (const n of SIDE_NAV) assert.ok(n.label && n.hint, n.key);
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
  assert.equal(syncFace({ checked: true, started: true, lastAt: at, terse: true }), "");   // "started 10:26 PM" said nothing (audit 2026-11-05)
  assert.equal(syncFace({ checked: true, lastAt: at, terse: true }), "checked 10:26 PM");
});
