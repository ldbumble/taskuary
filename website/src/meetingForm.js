// NEW → MEETING's words and asks, kept out of the component so they are tested on their own (NewMeeting.jsx, calwrite.suggest / draft_new).
export const LENGTHS = [15, 30, 45, 60];
export const WITHIN = [
  { key: "", label: "Soon" },
  { key: "this_week", label: "This week" },
  { key: "next_week", label: "Next week" },
  { key: "range", label: "Pick dates" },
];

// what the Assistant wrote the screen up with (concierge.meeting_prefill), as the form's first state - anything missing is the default
export function formFrom(pre = {}) {
  const within = pre.within || (pre.from ? "range" : "");
  return { to: [...(pre.to || [])], unplaced: [...(pre.unplaced || [])], subject: pre.about || "", minutes: LENGTHS.includes(+pre.minutes) ? +pre.minutes : 30,
    note: "", within, from: pre.from || "", until: pre.to_day || pre.from || "" };
}

// the free times' address: `to` once per person (FastAPI's list), never axios's `to[]=`
export function slotsUrl(f) {
  const q = new URLSearchParams();
  for (const a of f.to || []) q.append("to", a);
  q.set("minutes", String(f.minutes || 30));
  if (f.within === "range") { if (f.from) q.set("start", f.from); if (f.until || f.from) q.set("end", f.until || f.from); }
  else if (f.within) q.set("within", f.within);
  return `/api/meetings/slots?${q}`;
}

export const canFind = (f) => !!(f.to?.length && String(f.subject || "").trim() && (f.within !== "range" || f.from));

const pad = (n) => String(n).padStart(2, "0");
// a day and a time typed: the slot it is, `minutes` long
export function typedSlot(day, time, minutes) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day || "") || !/^\d{2}:\d{2}/.test(time || "")) return null;
  const d = new Date(`${day}T${time.slice(0, 5)}`); if (Number.isNaN(+d)) return null;
  const e = new Date(+d + (minutes || 30) * 60000);
  const at = (x) => `${x.getFullYear()}-${pad(x.getMonth() + 1)}-${pad(x.getDate())} ${pad(x.getHours())}:${pad(x.getMinutes())}`;
  return { start: at(d), end: at(e) };
}

// whose calendars the times were read against - said, so a time clear on yours alone is not taken for one clear on theirs
export function seenLine(got) {
  const read = got?.read || [], unread = got?.unread || [];
  if (!read.length && !unread.length) return "";
  if (!unread.length) return `Free on your calendar and on ${read.length === 1 ? read[0] + "'s" : "everyone's"}.`;
  const who = unread.join(", ");
  return read.length ? `Free on yours and ${read.join(", ")}'s - ${who} ${unread.length === 1 ? "does" : "do"} not share a calendar with you, so check with them.`
    : `Free on your calendar - ${who} ${unread.length === 1 ? "does" : "do"} not share a calendar with you, so check with them.`;
}
