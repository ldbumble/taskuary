// HOW A TIME AND A COUNT ARE SAID, once (src/timeWords.js, its server twin taskuary/timewords.py): the words, and a guard that no page
// file grows its own "5m ago" again - the walk said "40 min" where the task list said "40m ago", "asked you 5m ago" was typed twice
// (the cleanup round, 2026-10-18). tests/test_timewords.py reads this file's ago() cases and holds the server to them.
import test from "node:test";
import assert from "node:assert/strict";


import { age, ago, agoMins, band, bandUntil, dur, durSince, minsSince, plural, span } from "../src/timeWords.js";
import { asUtc, setTz } from "../src/dates.js";

// ONE STAMP READER (dates.asUtc): a server stamp is the SERVER's local time. The rail's band and age read it in the BROWSER's zone while the
// task's "5m ago" (ui.timeAgo) and its date (fmtDateTime) read it in the server's - one stamp, two ages, whenever the zones differ.
test("a server stamp reads one age on the rail and on the task, whatever zone the browser is in", () => {
  const zone = "Pacific/Auckland";
  const parts = (d) => Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: zone, hourCycle: "h23", year: "numeric", month: "2-digit",
    day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }).formatToParts(d).map((p) => [p.type, p.value]));
  const p = parts(new Date(Date.now() - 5 * 60000)), stamp = `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second}`;
  setTz(zone);
  try {
    const task = agoMins((Date.now() - asUtc(stamp).getTime()) / 60000);     // the task's road: asUtc, then the one rule
    assert.equal(task, "5m ago");
    assert.deepEqual([ago(stamp), age(stamp), band(stamp)], [task, "5m", "< 15m"], "the rail read the stamp in the browser's zone");
    assert.equal(ago(new Date(Date.now() - 5 * 60000).toISOString()), "5m ago", "a stamp naming its own zone is read as written");
  } finally { setTz(""); }
});

const now = new Date("2026-10-18T09:00:00").getTime();
const at = (m) => new Date(now - m * 60000).toISOString();

test("ago: just now inside a minute either way, behind in whole units, ahead reads forward", () => {
  assert.equal(ago(at(0), now), "just now");
  assert.equal(ago(at(0.4), now), "just now");
  assert.equal(ago(at(1), now), "1m ago");
  assert.equal(ago(at(59), now), "59m ago");
  assert.equal(ago(at(60), now), "1h ago");
  assert.equal(ago(at(150), now), "2h ago");
  assert.equal(ago(at(1439), now), "23h ago");
  assert.equal(ago(at(1440), now), "1d ago");
  assert.equal(ago(at(47 * 60), now), "1d ago");
  assert.equal(ago(at(-5), now), "in 5m");
  assert.equal(ago(at(-3 * 1440), now), "in 3d");
  for (const x of [null, undefined, "", "not a date"]) assert.equal(ago(x, now), "");
  assert.equal(ago(new Date(now - 300000), now), "5m ago", "a Date in, as ui.asUtc hands one over");
  assert.equal(agoMins(0.2), "just now");
  assert.equal(minsSince("2026-10-18 08:00:00", now), 60, "a server stamp with a space is local time");
});

test("age is the bare distance, band the rail's gutter, bandUntil For later's countdown", () => {
  assert.deepEqual([age(at(0.4), now), age(at(40), now), age(at(240), now), age(at(-12), now), age("", now)], ["now", "40m", "4h", "in 12m", ""]);
  assert.deepEqual([band(at(10), now), band(at(45), now), band(at(185), now), band(at(-5), now)], ["< 15m", "< 1h", "3h", "in 5m"]);
  assert.deepEqual([bandUntil(at(-10), now), bandUntil(at(-45), now), bandUntil(at(-185), now), bandUntil(at(5), now)], ["in 30m", "in 1h", "in 3h", ""]);
});

// the owner, 2026-11-04: finer tiers for fresh rows. Whole minutes r (rounded): r<5 "< 5m", r<15 "< 15m", r<30 "< 30m", then as before
test("band: fresh rows get < 5m / < 15m / < 30m, the edges at 5, 15 and 30 whole minutes; later and future unchanged", () => {
  const b = (m) => band(at(m), now);
  assert.deepEqual([0, 2, 4.4].map(b), ["< 5m", "< 5m", "< 5m"]);
  assert.deepEqual([5, 12, 14.4].map(b), ["< 15m", "< 15m", "< 15m"]);
  assert.deepEqual([15, 16, 29, 29.4].map(b), ["< 30m", "< 30m", "< 30m", "< 30m"]);
  assert.deepEqual([30, 31, 59, 60, 1439, 1440].map(b), ["< 1h", "< 1h", "< 1h", "1h", "23h", "1d"]);
  assert.deepEqual([-60, -5].map(b), ["in 1h", "in 5m"]);
});

test("dur says how long something has run; span and plural say a count", () => {
  assert.deepEqual([dur(0), dur(89), dur(90), dur(5399), dur(5400), dur(null)], ["0s", "89s", "2m", "90m", "1.5h", ""]);
  assert.equal(durSince(at(-1), now), "0s", "a start a clock wrote ahead has run for nothing yet");
  assert.deepEqual([span(5), span(180), span(2 * 1440), span(2 * 1440, true), span(1, true)], ["5m", "3h", "2d", "2 days", "1 minute"]);
  assert.deepEqual([plural(1, "task"), plural(0, "task"), plural(3, "reply", "replies")], ["1 task", "0 tasks", "3 replies"]);
});

// THE WALK, 2026-11-21: Remind me > Next week keeps 7 days on at 7 AM; pressed in the evening, the rail counted 6.5 days down to "in 6d"
test("a return a week off by the calendar counts a week, whatever the hour it was set at", () => {
  const now = new Date(2026, 10, 21, 19, 20), back = new Date(2026, 10, 28, 7, 0);
  assert.equal(bandUntil(back, now), bandUntil(new Date(2026, 10, 28, 19, 20), now));
});
