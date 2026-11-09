// A meeting is a notification fifteen minutes before it, with Prepare (the owner, 2026-11-09: "just add a notification ... 15 minutes
// before the meeting, not two hours"). The poll rings each meeting once; Prepare posts the event as the server's MeetingPrepBody.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { LEAD_MIN, dueMeetings, meetingId, prepBody, rememberRung, rungBefore } from "../src/meetingAlert.js";

const at = (now, m) => { const d = new Date(now + m * 60000), p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`; };

test("only a timed meeting inside fifteen minutes, not begun and not rung before, is due", () => {
  const now = new Date(2026, 10, 9, 14, 0).getTime();
  const evs = [["Ops sync", 10], ["Budget check", LEAD_MIN], ["Vendor call", 60], ["Late review", 120], ["Started", -2]]
    .map(([subject, m]) => ({ subject, start: at(now, m), end: at(now, m + 30), all_day: false }));
  evs.push({ subject: "Holiday", start: at(now, 5), all_day: true });
  assert.deepEqual(dueMeetings(evs, now).map((e) => e.subject), ["Ops sync", "Budget check"]);
  assert.deepEqual(dueMeetings(evs, now, new Set([meetingId(evs[0])])).map((e) => e.subject), ["Budget check"]);
  assert.deepEqual(dueMeetings(null, now), []);
});

test("a meeting rung is remembered across reloads for a day, then let go", () => {
  const box = {}, st = { getItem: (k) => box[k] ?? null, setItem: (k, v) => { box[k] = v; } };
  rememberRung(st, ["2026-11-09 14:10|Ops sync"], 1000);
  assert.ok(rungBefore(st).has("2026-11-09 14:10|Ops sync"));
  rememberRung(st, ["2026-11-10 09:00|Standup"], 1000 + 86400000 + 1);
  assert.deepEqual([...rungBefore(st)], ["2026-11-10 09:00|Standup"]);
});

test("Prepare posts the event as the server reads it, and the hub draws the notice with its Prepare", () => {
  const b = prepBody({ subject: "Ops sync", start: "2026-11-09 14:10", end: "2026-11-09 14:40", who: ["Erin Blake", ""], mailbox: "x" });
  assert.deepEqual(b, { subject: "Ops sync", start: "2026-11-09 14:10", end: "2026-11-09 14:40", where: null, organizer: null,
    who: ["Erin Blake"], about: null, link: null, status: null, all_day: false });
  const hub = readFileSync(new URL("../src/TaskHubPage.jsx", import.meta.url), "utf8");
  assert.match(hub, /useMeetingAlerts\(onMeeting\)/);
  assert.match(hub, /api\.post\("\/api\/calendar\/prepare", prepBody\(meeting\)\)/);
  assert.match(hub, /data-tq-meeting-prepare/);
});
