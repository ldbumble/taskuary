import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { FIRST_DAYS, backChoices, broughtLine, syncFace, syncLine, syncStatusDelay } from "../src/syncTiming.js";

test("sync status checks quietly when the scheduled refresh is far away", () => {
  assert.equal(syncStatusDelay({ nextAt: 600_000, now: 0 }), 30_000);
});

test("sync status watches closely around the scheduled refresh", () => {
  assert.equal(syncStatusDelay({ nextAt: 20_000, now: 0 }), 500);
  assert.equal(syncStatusDelay({ nextAt: 10_000, now: 20_000 }), 500);
});

test("an observed running sync is followed every two seconds", () => {
  assert.equal(syncStatusDelay({ running: true, nextAt: 600_000, now: 0 }), 2000);
});

test("the sync clock reads the same on the Timeline and in the pipe", () => {
  const at = new Date(2026, 8, 3, 10, 42);
  const face = { every: 10, lastAt: at, nextIn: 271 };
  assert.equal(syncFace(face), "synced 10:42 AM · next in 4:31");
  assert.equal(syncFace({ ...face, terse: true }), "synced 10:42 AM");
  assert.equal(syncFace({ ...face, nextIn: 0 }), "synced 10:42 AM · next sync due now");
});

test("a running sync and a disabled one say so in both faces", () => {
  assert.equal(syncFace({ busy: true, what: "reading Outlook" }), "reading Outlook");
  assert.equal(syncFace({ busy: true, what: "reading Outlook", terse: true }), "syncing…");
  assert.equal(syncFace({ every: 0 }), "background sync off");
  assert.equal(syncFace({ every: 0, terse: true }), "sync off");
});

test("no poll yet never invents a time", () => {
  assert.equal(syncFace({ every: 10, lastAt: null, nextIn: null }), "synced —");
});

test("a first sync says how far back it goes and what it brings in, then what it brought (the owner, 2026-11-10)", () => {
  const run = { busy: true, phase: "fetching", what: "syncing · reading outlook" };
  assert.equal(syncLine({ ...run, back: 72 }), "going back 3 days…");                                     // starting
  assert.equal(syncLine({ ...run, back: 72, landed: 37 }), "going back 3 days · bringing in 37…");       // N so far
  assert.equal(syncLine({ ...run, phase: "triaging", what: "syncing · processing messages · 4 left", back: 72, landed: 212 }),
    "brought in 212 · processing messages · 4 left");                                                     // judging what came
  assert.equal(syncLine({ brought: { n: 212, hours: 72 } }), "brought in 212 from the last 3 days");     // done, for a moment
  assert.equal(syncLine({ brought: { n: 5, hours: 24 } }), "brought in 5 from the last day");
});

test("an ordinary sync says a count only when it has one, and nothing of its own otherwise", () => {
  const run = { busy: true, phase: "fetching", what: "syncing · reading outlook" };
  assert.equal(syncLine(run), "");                                       // the clock's own words stand
  assert.equal(syncLine({ ...run, landed: 3 }), "bringing in 3…");
  assert.equal(syncLine({ ...run, phase: "checking", what: "syncing" }), "");
  assert.equal(syncLine({ brought: { n: 3, hours: 0 } }), "brought in 3");
  assert.equal(syncLine({}), "");
  assert.equal(broughtLine(0, 0), "");
});

// HOW FAR BACK A NEW CONNECTION'S FIRST SYNC GOES (the owner, 2026-11-10: "first sync should be 3 days.. or you can make drop down"): a choice
// on its card while that sync is due, saved as it is picked; none on a reader not asked by date, nor once the first sync ran (ReadsBack 0)
test("a new connection's card offers how far back its first sync goes, in the period words, until that sync has run", () => {
  assert.deepEqual(backChoices(3), [[1, "1 day"], [3, "3 days"], [7, "7 days"], [14, "14 days"], [30, "30 days"]]);
  assert.deepEqual(backChoices(5).map(([d]) => d), [1, 3, 5, 7, 14, 30], "a catch-up window of its own is offered as it is");
  const py = fs.readFileSync(path.join(process.cwd(), "..", "taskuary", "channels.py"), "utf8");
  assert.ok(py.includes(`FIRST_DAYS, FIRST_DEFAULT = (${FIRST_DAYS.join(", ")}), 3`), "the server's list is the page's");
  const src = fs.readFileSync(path.join(process.cwd(), "src", "ConnectorsView.jsx"), "utf8");
  assert.match(src, /\{conn\.ReadsBack > 0 && !isAI && \(/, "shown only while the first sync is due, on a reader asked by date");
  assert.match(src, /label="How far back to bring in" value=\{String\(cfg\.first_days \|\| conn\.ReadsBack\)\}/, "unset, the window the server will use");
  assert.match(src, /onChange=\{\(e\) => setCfg\(\{ \.\.\.cfg, first_days: Number\(e\.target\.value\) \}\)\} InputProps=\{\{ endAdornment: boxes\.tick\("first_days"\) \}\}/, "saved as it is picked - no Save");
});
