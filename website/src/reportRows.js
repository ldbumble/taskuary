// A data report's body is one JSON object per line (reports.rows_out) - read as a table, not as code.
export const jsonRows = (text) => {
  const lines = String(text || "").split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length || !lines.every((l) => l.startsWith("{") && l.endsWith("}"))) return null;
  try {
    const rows = lines.map((l) => JSON.parse(l));
    return rows.every((r) => r && typeof r === "object" && !Array.isArray(r) && Object.values(r).every((v) => v === null || typeof v !== "object")) ? rows : null;
  } catch { return null; }
};
// A report's heading split after its own NAME, so the day it ran can sit beside it: "End of day checkup · Yesterday — the last 8
// hours ..." (the owner, 2026-10-22). The row's sender is the report's title (funnel: who = SourceName) and its subject is
// "<title> — <head>" (reports.run_report_source), so the name is that prefix; failing that, up to the last " — " as reports.py reads it.
export const nameAndRest = (title, name) => {
  const t = String(title || "").trim(), n = String(name || "").trim();
  if (n && t.toLowerCase().startsWith(n.toLowerCase())) return [t.slice(0, n.length), t.slice(n.length)];
  const i = t.lastIndexOf(" — ");
  return i > 0 ? [t.slice(0, i), t.slice(i)] : [t, ""];
};
