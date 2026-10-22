// EVERY DATE THE UI DRAWS GOES THROUGH ONE CACHED FORMATTER PER (locale, options). `d.toLocale*String(loc, {opts})` and
// `new Intl.DateTimeFormat` build a fresh ICU formatter on every call (~0.15 ms against ~0.003 ms cached); the rail ran
// localDay over every pile row on every render, which on a large home was seconds per key press (owner 2026-10-19: "just
// make it feel snappy ... not how it works"). So the words are the built-ins' to the character - only the formatter is kept.
const cache = new Map();
export const dtf = (loc, o) => {
  const k = JSON.stringify([loc, o]);
  let f = cache.get(k);
  if (!f) cache.set(k, f = new Intl.DateTimeFormat(loc, o));   // a bad zone throws here as the built-ins did, and is not kept
  return f;
};
// d.toLocale{Date,Time,}String(loc, o), cached. The three differ from the constructor only in the fields they add when `o`
// names none (ECMA-402 ToDateTimeOptions: date / time / both), so `req` says which; an unreadable date says "Invalid Date"
// as they do instead of throwing.
const DF = ["weekday", "year", "month", "day"], TF = ["dayPeriod", "hour", "minute", "second", "fractionalSecondDigits"];
const withDefaults = (req, o) => {
  const has = (ks) => ks.some((k) => o?.[k] !== undefined);
  if ((req !== "time" && has(DF)) || (req !== "date" && has(TF)) || has(["dateStyle", "timeStyle"])) return o;
  return { ...o, ...(req !== "time" && { year: "numeric", month: "numeric", day: "numeric" }),
    ...(req !== "date" && { hour: "numeric", minute: "numeric", second: "numeric" }) };
};
const fmt = (kind) => (d, loc, o) => Number.isFinite(+d) ? dtf(loc, withDefaults(kind, o)).format(d) : "Invalid Date";
export const fmtDate = fmt("date"), fmtTime = fmt("time"), fmtStamp = fmt("any");

// Times are stamped in the SERVER's local time (store.norm_stamp makes every channel land there). The `timezone` setting
// names that zone: with it set, every time wears its short label (2:44 PM EDT) and a browser in another zone still reads
// the stamps correctly - naive local strings would otherwise be silently reinterpreted in the viewer's zone.
let TZ = "";
export const setTz = (z) => { TZ = z || ""; };
export const tzNow = () => TZ;
const tzOffsetMin = (d) => {
  // what the configured zone's UTC offset was AT that moment (DST-correct), via Intl
  const part = dtf("en-US", { timeZone: TZ, timeZoneName: "shortOffset" })
    .formatToParts(d).find((p) => p.type === "timeZoneName")?.value || "GMT+0";
  const m = part.replace("GMT", "").match(/([+-]?)(\d+)(?::(\d+))?/) || [0, "+", "0"];
  return (m[1] === "-" ? -1 : 1) * (parseInt(m[2] || 0) * 60 + parseInt(m[3] || 0));
};
export const asUtc = (s) => {
  const iso = String(s || "").replace(" ", "T");
  if (!TZ) return new Date(iso);                       // blank = this browser IS the server's zone
  try { return new Date(Date.parse(iso + "Z") - tzOffsetMin(new Date(iso + "Z")) * 60000); }
  catch { return new Date(iso); }
};
export const tzLabel = () => {
  if (!TZ) return "";
  try {
    return dtf("en-US", { timeZone: TZ, timeZoneName: "short" })
      .formatToParts(new Date()).find((p) => p.type === "timeZoneName")?.value || "";
  } catch { return ""; }
};
const tzOpt = () => (TZ ? { timeZone: TZ } : {});   // format in the configured zone, so digits match the label
export const fmtTime12 = (s) => {
  const d = s ? asUtc(s) : null;
  return d && Number.isFinite(d.getTime()) ? fmtTime(d, "en-US", { hour: "numeric", minute: "2-digit", ...tzOpt() }) : "";
};
export const tsMs = (s) => {
  const n = s ? asUtc(s).getTime() : 0;
  return Number.isFinite(n) ? n : 0;
};      // one clock for everything the Timeline orders (messages, meetings)
export const fmtDateTime = (s) => {
  if (!s) return "";
  const d = asUtc(s);
  if (!Number.isFinite(d.getTime())) return "";
  const base = fmtStamp(d, "en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", ...tzOpt() });
  const z = tzLabel();
  return z ? `${base} ${z}` : base;
};
export const localDay = (s) => {
  const d = s ? asUtc(s) : null;
  return d && Number.isFinite(d.getTime()) ? fmtDate(d, "sv-SE", tzOpt()) : "";
};   // YYYY-MM-DD in that zone
// THE DAY a stamp is from, as a heading says it: "Today", "Yesterday", then "Wed, Oct 21" - the chat thread's day chips and a report
// card's heading (an old End of day checkup read like today's, the owner 2026-10-22: "should say the day it's from")
export const dayLabel = (at, now = new Date()) => {
  const d = at ? asUtc(at) : null; if (!d || Number.isNaN(d.getTime())) return "";   // not tsMs: its 0 for no date would say Dec 31, 1969
  const today = new Date(now), yest = new Date(now); yest.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yest.toDateString()) return "Yesterday";
  return fmtDate(d, undefined, { weekday: "short", month: "short", day: "numeric" });
};
