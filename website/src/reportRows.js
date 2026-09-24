// A data report's body is one JSON object per line (reports.rows_out) - read as a table, not as code.
export const jsonRows = (text) => {
  const lines = String(text || "").split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length || !lines.every((l) => l.startsWith("{") && l.endsWith("}"))) return null;
  try {
    const rows = lines.map((l) => JSON.parse(l));
    return rows.every((r) => r && typeof r === "object" && !Array.isArray(r) && Object.values(r).every((v) => v === null || typeof v !== "object")) ? rows : null;
  } catch { return null; }
};
