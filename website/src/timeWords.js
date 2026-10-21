// HOW A TIME AND A COUNT ARE SAID, once - "5m ago", "in 12m", "just now", "45s", "1 task" / "3 tasks". Every line the page writes
// about when, or how many, asks here; taskuary/timewords.py is the server's twin and a test holds the two to the same words. Each
// surface had grown its own: the walk said "40 min" where the task list said "40m ago", the Hub "47h ago" where the page said
// "2d ago", and "asked you 5m ago" was typed twice (2026-10-18).
const ms = (x) => (x instanceof Date ? x.getTime() : typeof x === "number" ? x : new Date(String(x).replace(" ", "T")).getTime());

export const plural = (n, one, many) => `${n} ${n === 1 ? one : many || `${one}s`}`;
// what came with a task: its files and the documents its messages link to - "6 attachments · 2 links", '' for neither
export const filesLine = (files, links) => [files && plural(files, "attachment"), links && plural(links, "link")].filter(Boolean).join(" · ");
// minutes from `at` to `now` - past is positive, ahead negative; null when it is no time at all. `at` may be a stamp, a Date (ui.asUtc
// hands one over in the server's zone) or epoch ms.
export const minsSince = (at, now = Date.now()) => {
  if (at == null || at === "") return null;
  const t = ms(at);
  return Number.isNaN(t) ? null : (ms(now) - t) / 60000;
};
// whole minutes as the clock reads them (a half minute past is not yet a minute: 11:59:30 is "now" at noon)
const whole = (m) => -Math.round(-m);
// how long `m` minutes is, in whole units: "5m" / "3h" / "2d" - or "5 minutes" / "3 hours" / "2 days" long
export const span = (m, long = false) => {
  m = Math.max(0, Math.floor(m));
  const [n, u] = m < 60 ? [m, "minute"] : m < 1440 ? [Math.floor(m / 60), "hour"] : [Math.floor(m / 1440), "day"];
  return long ? plural(n, u) : `${n}${u[0]}`;
};
// a SENTENCE's age: "just now" inside a minute either way, "5m ago" behind, "in 5m" ahead - a stamp the server clocked a moment
// ahead of the browser is not an age ("in 3 min ago", 2026-09-10 audit)
export const agoMins = (m) => { m = whole(m); return Math.abs(m) < 1 ? "just now" : m > 0 ? `${span(m)} ago` : `in ${span(-m)}`; };
export const ago = (at, now) => { const m = minsSince(at, now); return m == null ? "" : agoMins(m); };
// ...and the bare distance for a gutter or a kicker: "now", "40m", "4h", "in 12m" - "how far", so it never gets " ago" glued on
export const age = (at, now) => {
  const m = minsSince(at, now);
  if (m == null) return "";
  const r = whole(m);
  return Math.abs(r) < 1 ? "now" : r > 0 ? span(r) : `in ${span(-r)}`;
};
// THE WORK RAIL's gutter: ranked, not dated, so it only answers "has this sat too long" - an exact "22m" invites arithmetic. Inside the
// first half hour it is simply new, then hour by hour, then days (the owner, 2026-09-16: "within a half an hour say 30 min <, then per
// hour bands of time").
export const band = (at, now) => {
  const m = minsSince(at, now);
  if (m == null) return "";
  const r = whole(m);
  return r < 0 ? `in ${span(-r)}` : r < 30 ? "< 30m" : r < 60 ? "< 1h" : span(r);
};
// ...counting DOWN to a For later row's return, reading forward: "in 30m", "in 1h", "in 3h", "in 2d" - "< 30m" read as an age (the
// owner, 2026-09-30). "" once due: the row is on its way back. timewords.back_in is its server twin.
export const bandUntil = (at, now) => {
  const m = minsSince(at, now);
  if (m == null) return "";
  const r = Math.round(-m);
  return r <= 0 ? "" : r < 30 ? "in 30m" : r < 60 ? "in 1h" : `in ${span(r)}`;
};
// how long something has RUN, to the second while it is fresh: "45s", "12m", "1.5h" - an agent's turn, a step, a session
export const dur = (s) => (s == null || Number.isNaN(Number(s)) ? "" : s < 90 ? `${Math.round(s)}s` : s < 5400 ? `${Math.round(s / 60)}m` : `${(s / 3600).toFixed(1)}h`);
export const durSince = (at, now) => { const m = minsSince(at, now); return m == null ? "" : dur(Math.max(0, m * 60)); };
