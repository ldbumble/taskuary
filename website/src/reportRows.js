// A data report's body is one JSON object per line (reports.rows_out) - read as a table, not as code.
export const jsonRows = (text) => {
  const lines = String(text || "").split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length || !lines.every((l) => l.startsWith("{") && l.endsWith("}"))) return null;
  try {
    const rows = lines.map((l) => JSON.parse(l));
    return rows.every((r) => r && typeof r === "object" && !Array.isArray(r) && Object.values(r).every((v) => v === null || typeof v !== "object")) ? rows : null;
  } catch { return null; }
};
// THE SHAPE OF A DATA REPORT, read off its rows the way the server picks its chart (artifacts.chart_columns): the first column that is a
// number in every row is the measure, the first that is not is the name, and a run of dates is one line over time rather than bars
export const numOf = (v) => (typeof v === "number" ? v : typeof v === "string" && /^\s*-?\$?[\d,]*\.?\d+\s*$/.test(v) ? Number(v.replace(/[$,\s]/g, "")) : null);
const DATED = /^\s*(\d{4}-\d{2}-\d{2}|\d{1,2}\/\d{1,2}(\/\d{2,4})?|\d{4}-\d{2}|[A-Z][a-z]{2} \d{1,2})/;
export const colWords = (c) => String(c || "").replace(/_/g, " ").trim();
export function reportShape(rows) {
  const cols = [...new Set((rows || []).flatMap((r) => Object.keys(r)))];
  const nums = cols.filter((c) => rows.every((r) => r[c] == null || numOf(r[c]) !== null) && rows.some((r) => numOf(r[c])));
  const lab = cols.find((c) => !nums.includes(c)) || null, val = nums[0] || null;
  const dated = !!lab && rows.length >= 5 && rows.every((r) => DATED.test(String(r[lab] ?? "")));
  return { cols, nums, lab, val, dated, chart: !val || rows.length < 2 ? null : dated ? "line" : "bars" };
}
// one column, one number of decimals (at most two): 9,310 and 18,420.55 in one column read as 9,310.00 and 18,420.55, so they align
export const places = (rows, c) => Math.min(2, Math.max(0, ...rows.map((r) => { const n = numOf(r[c]); return n === null ? 0 : (String(n).split(".")[1] || "").length; })));
const NF = [0, 1, 2].map((p) => new Intl.NumberFormat("en-US", { minimumFractionDigits: p, maximumFractionDigits: p }));
export const fmtNum = (n, p = 0) => (n === null || n === undefined ? "" : NF[Math.max(0, Math.min(2, p))].format(n));
// a report's day is the data, not a moment: said as it is written, never moved into a zone
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const day = (v) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(v || "")); return m ? `${MON[+m[2] - 1]} ${+m[3]}` : String(v ?? ""); };
// ...and WHAT IT FOUND, in one line from the rows themselves (no AI): how many, the total where a total means something, and the
// row that stands out - the peak of a run of days, the largest of a ranking
const NO_TOTAL = /avg|average|mean|median|rate|ratio|pct|percent|share|score|index|age_days|days_old/i;
export function reportSummary(rows, shape = reportShape(rows)) {
  const n = rows.length, { lab, val, dated } = shape;
  const count = dated ? `${n} days` : `${n} ${n === 1 ? "row" : "rows"}`;
  if (!val || !n) return count;
  const p = places(rows, val), vs = rows.map((r) => numOf(r[val]) ?? 0), top = Math.max(...vs), at = rows[vs.indexOf(top)];
  const sum = vs.reduce((a, b) => a + b, 0), what = colWords(val);
  const total = NO_TOTAL.test(val) ? "" : `${fmtNum(sum, p)} ${what} in all`;
  const stand = !lab ? "" : dated ? `peak ${fmtNum(top, p)} on ${day(at[lab])}${vs.length > 1 && vs.indexOf(top) !== vs.length - 1 ? `, latest ${fmtNum(vs[vs.length - 1], p)}` : ", the latest day"}`
    : `largest ${at[lab]} at ${fmtNum(top, p)}${total && sum > 0 && n > 1 ? ` (${Math.round((top / sum) * 100)}%)` : ""}`;
  return [count, total, stand].filter(Boolean).join(" · ");
}

// A report's heading split after its own NAME, so the day it ran can sit beside it: "End of day checkup · Yesterday — the last 8
// hours ..." (the owner, 2026-10-22). The row's sender is the report's title (funnel: who = SourceName) and its subject is
// "<title> — <head>" (reports.run_report_source), so the name is that prefix; failing that, up to the last " — " as reports.py reads it.
export const nameAndRest = (title, name) => {
  const t = String(title || "").trim(), n = String(name || "").trim();
  if (n && t.toLowerCase().startsWith(n.toLowerCase())) return [t.slice(0, n.length), t.slice(n.length)];
  const i = t.lastIndexOf(" — ");
  return i > 0 ? [t.slice(0, i), t.slice(i)] : [t, ""];
};
