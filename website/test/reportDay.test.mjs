// A REPORT SAYS THE DAY IT RAN (the owner, 2026-10-22: "end of day checkup should say the day it's from"): the card's heading read
// "End of day checkup — the last 8 hours of Inbox and Sent email" whichever day it was, so yesterday's read like today's.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { dayLabel, fmtDate } from "../src/dates.js";
import { nameAndRest } from "../src/reportRows.js";

const now = new Date("2026-10-22T18:00:00");

test("the day reads Today, Yesterday, then the weekday and date - the chat thread's own day words", () => {
  assert.equal(dayLabel("2026-10-22 09:15:00", now), "Today");
  assert.equal(dayLabel("2026-10-21 17:00:00", now), "Yesterday");
  const d = new Date("2026-10-19T17:00:00");
  assert.equal(dayLabel("2026-10-19 17:00:00", now), fmtDate(d, undefined, { weekday: "short", month: "short", day: "numeric" }));
  for (const x of [null, undefined, "", "not a date"]) assert.equal(dayLabel(x, now), "");
});

test("the heading splits after the report's name, whatever report it is", () => {
  assert.deepEqual(nameAndRest("End of day checkup — the last 8 hours of Inbox", "End of day checkup"),
    ["End of day checkup", " — the last 8 hours of Inbox"]);
  assert.deepEqual(nameAndRest("Morning digest — yesterday and today so far, distilled", "Taskuary"),
    ["Morning digest", " — yesterday and today so far, distilled"], "no sender match: the name is up to the last dash");
  assert.deepEqual(nameAndRest("Open invoices", ""), ["Open invoices", ""]);
});

test("the report card draws the day beside the name, and the chat thread reads the same helper", () => {
  const src = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
  const card = src("assistantCards.jsx"), body = card.slice(card.indexOf("export function ReportCard"), card.indexOf("export function IdeaCard"));
  assert.match(body, /nameAndRest\(card\.title, card\.who\), day = dayLabel\(card\.when\)/);
  assert.match(body, /<b>\{name\}<\/b>\{day && ` · \$\{day\}`\}\{rest\}/);
  assert.match(src("ChatThread.jsx"), /import \{ dayLabel, fmtTime \} from "\.\/dates\.js"/);
  assert.doesNotMatch(src("ChatThread.jsx"), /const dayLabel/);
});
