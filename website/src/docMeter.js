// HOW MUCH OF A DOCUMENT REACHES THE AGENT (the owner, 2026-11-02: "tell the user the max amount of characters that go into the
// instructions, with a bar/percentage showing if you are over"). The limit is the server's - GET /api/doc/{name} returns the very
// number its prompt cuts with (taskuary/doclimits.py) - and `flat` means it counts the text as a session receives it.

// terminal.flatten_rules, line for line: headings unmarked, blank lines dropped, one space between everything
export const flatten = (t) => String(t || "").split(/\r\n|\r|\n/).filter((l) => l.trim())
  .map((l) => (/^\s*#/.test(l) ? l.replace(/^[ #*-]+|[ #*-]+$/g, "").trim() : l.trim()))
  .join(" ").split(/\s+/).filter(Boolean).join(" ");

export const NEAR = 85;      // percent: past it the bar turns amber, past 100 red

// {n, of, pct, tone, over} for the editor's text against a limit; null when nothing cuts this document
export function meter(text, limit) {
  const of = Number(limit?.chars) || 0;
  if (of <= 0) return null;
  const n = (limit.flat ? flatten(text) : String(text || "")).length, pct = (n / of) * 100;
  return { n, of, pct, tone: pct > 100 ? "over" : pct >= NEAR ? "near" : "ok", over: Math.max(0, n - of) };
}
