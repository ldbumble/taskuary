// New → Meeting's form (meetingForm.js): the Assistant's prefill, the free times' address, a typed time, and whose calendars were read.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { canFind, formFrom, seenLine, slotsUrl, typedSlot } from "../src/meetingForm.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("the Assistant's prefill is the form's first state, defaults where it said nothing", () => {
  const f = formFrom({ to: ["gail@northwind.example"], unplaced: ["Zed"], about: "the Q3 budget", minutes: 45, within: "next_week", from: "", to_day: "" });
  assert.deepEqual(f, { to: ["gail@northwind.example"], unplaced: ["Zed"], subject: "the Q3 budget", minutes: 45, note: "", within: "next_week", from: "", until: "" });
  assert.deepEqual(formFrom({ minutes: 20, from: "2026-11-03" }), { to: [], unplaced: [], subject: "", minutes: 30, note: "", within: "range", from: "2026-11-03", until: "2026-11-03" });
});

test("the free times' address names each person once and the days asked", () => {
  const f = { to: ["erin@northwind.example", "gail@northwind.example"], minutes: 45, within: "next_week" };
  assert.equal(slotsUrl(f), "/api/meetings/slots?to=erin%40northwind.example&to=gail%40northwind.example&minutes=45&within=next_week");
  assert.equal(slotsUrl({ ...f, within: "range", from: "2026-11-02", until: "2026-11-04" }),
    "/api/meetings/slots?to=erin%40northwind.example&to=gail%40northwind.example&minutes=45&start=2026-11-02&end=2026-11-04");
  assert.doesNotMatch(slotsUrl(f), /to%5B%5D|to\[\]/);
});

test("Find times wants people, a subject and, for dates, a first day", () => {
  assert.equal(canFind({ to: [], subject: "x" }), false);
  assert.equal(canFind({ to: ["a@b.example"], subject: "  " }), false);
  assert.equal(canFind({ to: ["a@b.example"], subject: "x", within: "range", from: "" }), false);
  assert.equal(canFind({ to: ["a@b.example"], subject: "x", within: "" }), true);
});

test("a typed day and time is a slot of the meeting's length", () => {
  assert.deepEqual(typedSlot("2026-11-03", "16:45", 30), { start: "2026-11-03 16:45", end: "2026-11-03 17:15" });
  assert.deepEqual(typedSlot("2026-11-03", "23:30", 60), { start: "2026-11-03 23:30", end: "2026-11-04 00:30" });
  assert.equal(typedSlot("", "10:00", 30), null);
  assert.equal(typedSlot("2026-11-03", "", 30), null);
});

test("whose calendars the times were read against is said", () => {
  assert.equal(seenLine({ read: [], unread: [] }), "");
  assert.match(seenLine({ read: ["erin@northwind.example"], unread: [] }), /on erin@northwind\.example's/);
  assert.match(seenLine({ read: ["erin@northwind.example"], unread: ["gail@northwind.example"] }), /gail@northwind\.example does not share/);
  assert.match(seenLine({ read: [], unread: ["a@x.example", "b@x.example"] }), /^Free on your calendar - a@x\.example, b@x\.example do not share/);
});

test("New has a Meeting tab, and the Assistant's meeting opens it filled in", () => {
  assert.match(read("NewSheet.jsx"), /key: "meeting", mark: "📅", label: "Meeting"/);
  assert.match(read("NewSheet.jsx"), /<NewMeeting renderTo=\{\(p\) => <EmailRecipients \{\.\.\.p\} \/>\}/);
  assert.match(read("CanvasBrowse.jsx"), /initialMeeting=\{state\?\.meeting \|\| null\}/);
  // the pick is the only press, and it drafts: nothing in the form posts a send
  assert.doesNotMatch(read("NewMeeting.jsx"), /\/approve|\/send\b|\/decide/);
});
