// A DATE COSTS ONE FORMATTER, NOT ONE PER ROW (2026-10-19). toLocale*String with options builds a new ICU formatter every call;
// the rail ran localDay over every pile row on every key and poll, seconds on a large home. dates.js keeps them; this holds it.
import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";

const Real = Intl.DateTimeFormat;
let built = 0;
Intl.DateTimeFormat = function (...a) { built++; return new Real(...a); };
Intl.DateTimeFormat.prototype = Real.prototype;
const d = await import("../src/dates.js");
const { localDay, fmtTime12, fmtDateTime, fmtDate, fmtTime, fmtStamp, setTz, asUtc } = d;
Intl.DateTimeFormat = Real;

const stamps = Array.from({ length: 5000 }, (_, i) => new Date(Date.UTC(2026, 9, 19) - i * 4.1e6).toISOString().slice(0, 19).replace("T", " "));
for (const tz of ["", "America/New_York"]) test(`a 5,000-row rail builds a handful of formatters, not one per row (tz=${tz || "browser"})`, () => {
  Intl.DateTimeFormat = function (...a) { built++; return new Real(...a); }; Intl.DateTimeFormat.prototype = Real.prototype;
  try {
    setTz(tz); built = 0;
    stamps.forEach((s) => { localDay(s); fmtTime12(s); fmtDateTime(s); });
    assert.ok(built <= 5, `built ${built} Intl formatters for ${stamps.length} rows`);
  } finally { Intl.DateTimeFormat = Real; setTz(""); }
});

// the words are the built-ins' to the character: every helper against the per-call code it replaced
const ZONES = ["", "America/New_York", "Asia/Kolkata", "Australia/Lord_Howe", "Pacific/Chatham", "Europe/London", "America/St_Johns", "UTC"];
const OPTS = [undefined, {}, { month: "short", day: "numeric" }, { weekday: "short", day: "numeric", month: "short" }, { hour: "numeric", minute: "2-digit" },
  { hour: "2-digit", minute: "2-digit" }, { weekday: "short", hour: "numeric", minute: "2-digit" }, { timeZone: "Asia/Tokyo" }, { hour: "numeric" }, { year: "numeric" }];
const LOCS = [undefined, [], "en-US", "sv-SE", "de-DE", "he-IL", "ja-JP"];
test("fmtDate / fmtTime / fmtStamp say what toLocaleDateString / TimeString / String said", () => {
  const ds = [new Date(NaN), new Date(Date.UTC(2026, 2, 8, 6, 59)), new Date(Date.UTC(2026, 10, 1, 5, 30)), new Date(0), new Date(Date.UTC(2026, 9, 19, 23, 59, 59))];
  for (const loc of LOCS) for (const o of OPTS) for (const x of ds) {
    assert.equal(fmtDate(x, loc, o), x.toLocaleDateString(loc, o));
    assert.equal(fmtTime(x, loc, o), x.toLocaleTimeString(loc, o));
    assert.equal(fmtStamp(x, loc, o), x.toLocaleString(loc, o));
  }
});
// the ui.jsx helpers as they stood before the cache, kept here as the oracle
const old = (TZ) => {
  const off = (x) => { const p = new Intl.DateTimeFormat("en-US", { timeZone: TZ, timeZoneName: "shortOffset" }).formatToParts(x).find((p) => p.type === "timeZoneName")?.value || "GMT+0";
    const m = p.replace("GMT", "").match(/([+-]?)(\d+)(?::(\d+))?/) || [0, "+", "0"]; return (m[1] === "-" ? -1 : 1) * (parseInt(m[2] || 0) * 60 + parseInt(m[3] || 0)); };
  const asUtc = (s) => { const iso = String(s || "").replace(" ", "T"); if (!TZ) return new Date(iso);
    try { return new Date(Date.parse(iso + "Z") - off(new Date(iso + "Z")) * 60000); } catch { return new Date(iso); } };
  const label = () => { if (!TZ) return ""; try { return new Intl.DateTimeFormat("en-US", { timeZone: TZ, timeZoneName: "short" }).formatToParts(new Date()).find((p) => p.type === "timeZoneName")?.value || ""; } catch { return ""; } };
  const o = () => (TZ ? { timeZone: TZ } : {});
  return {
    asUtc: (s) => String(asUtc(s).getTime()),
    fmtTime12: (s) => { const d = s ? asUtc(s) : null; return d && Number.isFinite(d.getTime()) ? d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", ...o() }) : ""; },
    fmtDateTime: (s) => { if (!s) return ""; const d = asUtc(s); if (!Number.isFinite(d.getTime())) return "";
      const b = d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", ...o() }), z = label(); return z ? `${b} ${z}` : b; },
    localDay: (s) => { const d = s ? asUtc(s) : null; return d && Number.isFinite(d.getTime()) ? d.toLocaleDateString("sv-SE", o()) : ""; },
  };
};
const N = +(process.env.DATES_N || 300);   // two years of stamps; the proof run sets 20,000
test("asUtc, fmtTime12, fmtDateTime and localDay are unchanged in every zone, DST edges and bad stamps included", () => {
  const ss = ["", null, "garbage", "2026-03-08 02:30:00", "2026-11-01 01:30:00", "2026-10-05 02:15:00", "2026-04-05 02:45:00", "2026-03-29 01:30:00",
    ...Array.from({ length: N }, (_, i) => new Date(Date.UTC(2025, 0, 1) + (i * Math.floor(1051200 / N) + i % 60) * 60000).toISOString().slice(0, 19).replace("T", i % 2 ? " " : "T"))];
  try {
    for (const tz of [...ZONES, "Not/AZone"]) {
      setTz(tz); const o = old(tz);
      for (const s of ss) for (const k of ["asUtc", "fmtTime12", "fmtDateTime", "localDay"]) {
        const run = (f) => { try { return f(s); } catch (e) { return `throws ${e.name}`; } };
        assert.equal(run(k === "asUtc" ? (x) => String(asUtc(x).getTime()) : d[k]), run(o[k]), `${k}(${s}) in ${tz || "browser"}`);
      }
    }
  } finally { setTz(""); }
});

test("no source file formats a date with an options object outside dates.js", () => {
  const src = new URL("../src/", import.meta.url);
  // SemanticPanel formats a number, not a date: Number.toLocaleString with a locale is not the formatter this guards
  const bad = readdirSync(src).filter((f) => /\.jsx?$/.test(f) && f !== "dates.js").flatMap((f) => readFileSync(new URL(f, src), "utf8").split("\n")
    .map((l, i) => [f, i + 1, l]).filter(([, , l]) => /\.toLocale(Date|Time)?String\([^)]*,|new Intl\.DateTimeFormat/.test(l) && !/Number\(v\)\.toLocaleString/.test(l)))
    .map(([f, n]) => `${f}:${n}`);
  assert.deepEqual(bad, []);
});
