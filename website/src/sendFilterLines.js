// THE SEND FILTER'S LINES (SendFilter.jsx): GET /api/sendfilter per CLI, turned into one line per server and tool, split into left out and kept.
export const NOT_CHECKED = "Not checked yet: left out";

// Claude and Codex can load the same server; the owner's word is per server and tool, so it is one line, naming both
export function linesOf(data) {
  const by = new Map();
  for (const cli of ["claude", "codex"]) for (const s of data?.[cli] || []) {
    const put = (tool, o) => {
      const k = `${s.server}/${tool || "*"}`, was = by.get(k);
      by.set(k, was ? { ...was, clis: [...was.clis, cli], blocked: was.blocked || o.blocked } : { server: s.server, tool, clis: [cli], ...o });
    };
    if (s.error) put("", { blocked: s.blocked, unchecked: !!s.unchecked, why: s.error, by: s.by || "" });
    for (const t of s.tools || []) put(t.name, { blocked: t.blocked, unchecked: !!t.unchecked, why: t.why || "", by: t.by || "" });
  }
  const all = [...by.values()];
  return { left: all.filter((l) => l.blocked), kept: all.filter((l) => !l.blocked) };
}
