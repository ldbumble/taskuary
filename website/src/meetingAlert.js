// A MEETING IS A NOTIFICATION FIFTEEN MINUTES BEFORE IT (the owner, 2026-11-09: "It should just be a notification ... a prepare button
// ... 15 minutes before the meeting, not two hours"). The page reads the calendar every minute; a meeting that comes inside LEAD_MIN of
// its start rings once - the hand raise's sound and desktop popup (handraise.js) - and a notice with Prepare (/api/calendar/prepare)
// stands until it is pressed, closed, or the meeting has begun. The rail's row comes at the same minute (funnel.from_calendar).
// Pure, so node's tests read it; the poll itself is handraise.js's useMeetingAlerts.
import { tsMs } from "./dates.js";

export const LEAD_MIN = 15;
const KEY = "tq-meeting-alerted";

export const meetingId = (e) => `${String(e?.start || "").slice(0, 16)}|${String(e?.subject || "")}`;

// the meetings to ring for at `now`: timed (never all-day), not yet begun, starting inside LEAD_MIN, and not rung before
export const dueMeetings = (events, now, seen = new Set()) => (Array.isArray(events) ? events : []).filter((e) => {
  if (!e || e.all_day || !e.start) return false;
  const left = tsMs(e.start) - now;
  return left > 0 && left <= LEAD_MIN * 60000 && !seen.has(meetingId(e));
});

// ...and a meeting rung is remembered for a day across reloads, so one meeting rings once
const load = (st) => { try { const o = JSON.parse(st?.getItem(KEY) || "{}"); return o && typeof o === "object" ? o : {}; } catch { return {}; } };
export const rememberRung = (st, ids, now) => {
  const o = Object.fromEntries(Object.entries(load(st)).filter(([, at]) => now - at < 86400000));
  for (const id of ids) o[id] = now;
  try { st?.setItem(KEY, JSON.stringify(o)); } catch { /* private mode: it may ring again after a reload */ }
  return new Set(Object.keys(o));
};
export const rungBefore = (st) => new Set(Object.keys(load(st)));

// what Prepare posts: the event as the page has it (server MeetingPrepBody)
export const prepBody = (e) => ({ subject: e.subject, start: e.start, end: e.end, where: e.where || null, organizer: e.organizer || null,
  who: (e.who || []).filter(Boolean), about: e.about || null, link: e.link || null, status: e.status || null, all_day: !!e.all_day });
