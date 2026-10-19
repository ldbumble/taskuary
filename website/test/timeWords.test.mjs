// HOW A TIME AND A COUNT ARE SAID, once (src/timeWords.js, its server twin taskuary/timewords.py): the words, and a guard that no page
// file grows its own "5m ago" again - the walk said "40 min" where the task list said "40m ago", "asked you 5m ago" was typed twice
// (the cleanup round, 2026-10-18). tests/test_timewords.py reads this file's ago() cases and holds the server to them.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { age, ago, agoMins, band, bandUntil, dur, durSince, minsSince, plural, span } from "../src/timeWords.js";

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
  assert.deepEqual([band(at(10), now), band(at(45), now), band(at(185), now), band(at(-5), now)], ["< 30m", "< 1h", "3h", "in 5m"]);
  assert.deepEqual([bandUntil(at(-10), now), bandUntil(at(-45), now), bandUntil(at(-185), now), bandUntil(at(5), now)], ["in 30m", "in 1h", "in 3h", ""]);
});

test("dur says how long something has run; span and plural say a count", () => {
  assert.deepEqual([dur(0), dur(89), dur(90), dur(5399), dur(5400), dur(null)], ["0s", "89s", "2m", "90m", "1.5h", ""]);
  assert.equal(durSince(at(-1), now), "0s", "a start a clock wrote ahead has run for nothing yet");
  assert.deepEqual([span(5), span(180), span(2 * 1440), span(2 * 1440, true), span(1, true)], ["5m", "3h", "2d", "2 days", "1 minute"]);
  assert.deepEqual([plural(1, "task"), plural(0, "task"), plural(3, "reply", "replies")], ["1 task", "0 tasks", "3 replies"]);
});

// what a person can read in a page file, comments gone (a comment reaches nobody) - the same strip buttons.test.mjs uses
const SRC = path.join(process.cwd(), "src");
const strip = (s) => s.replace(/(^[ \t]*|\{)\/\*[\s\S]*?\*\/\}?/gm, "").replace(/(^|\s)\/\/[^\n]*/g, "$1");
const files = fs.readdirSync(SRC).filter((f) => /\.(jsx?|mjs)$/.test(f) && f !== "timeWords.js");
// a hand-written age ("${m}m ago", "${n} min ago"), a typed "just now", or dur's own thresholds copied out
const OWN = [/\$\{[^}]*\}\s?(?:m|h|d|min|mins|minutes?|hours?|days?)?\s+ago\b/, /["'`]just now["'`]/, /\b5400\s*\?/];
test("no page file writes its own time formatter: every age is read from timeWords.js", () => {
  for (const re of OWN.slice(0, 2)) assert.match('`${Math.round(m)}m ago` "just now"', re, "the guard sees the shape it replaced");
  const hits = files.flatMap((f) => { const code = strip(fs.readFileSync(path.join(SRC, f), "utf8")); return OWN.filter((re) => re.test(code)).map((re) => `${f}: ${re}`); });
  assert.deepEqual(hits, []);
});

// ...and a count with its noun pluralised by hand - `${n} task${n === 1 ? "" : "s"}` - the shape that writes "1 tasks" wherever one is
// missed. Only where the count and the condition are the same expression: "Queue prompts" with no count is a different sentence.
const COUNTED = [/\$\{([^{}\n]+?)\} [\w/ -]{0,40}?\w\$\{([^{}\n]+?) === 1 \? "" : "s"\}/g, /\{([^{}\n]+?)\} [\w/ -]{0,40}?\w\{([^{}\n]+?) === 1 \? "" : "s"\}/g];
const byHand = (code) => COUNTED.some((re) => [...code.matchAll(re)].some((m) => m[1].trim() === m[2].trim()));
test("no page file pluralises a count by hand: plural() from timeWords.js says it", () => {
  assert.ok(byHand('`${n} task${n === 1 ? "" : "s"}`') && byHand('{n} file{n === 1 ? "" : "s"}'));
  assert.deepEqual(files.filter((f) => byHand(strip(fs.readFileSync(path.join(SRC, f), "utf8")))), []);
});
