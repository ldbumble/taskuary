// The files an agent made for its task (taskuary/outputs.py: <home>/scratch/outputs/TQ-nnnn/), found where an answer names them.
// A Codex researcher's answer carried its own `:codex-file-citation{path="..."}` marker, printed raw, and asked to send the file it
// wrote a link to http://127.0.0.1:7787/outputs/TQ-0017/<file> - a route the server never had. Each of those - the marker, a link or
// a bare path into THIS task's folder - becomes a file the owner can preview and download, through /api/task-outputs. A path into
// anywhere else is left as plain text: never a link, never served.

const CITE = /:{1,2}codex-file-citation\{([^}]*)\}/g;
const LINK = /\[([^\]\n]*)\]\(\s*<?([^)\s>]+)>?(?:\s+"[^"]*")?\s*\)/g;
const STOP = "[^\\s`'\"<>()\\[\\]]";
const BARE = new RegExp(`(?:https?://(?:127\\.0\\.0\\.1|localhost|\\[::1\\])(?::\\d+)?/outputs/TQ-\\d+/${STOP}+`
  + `|(?:file:/+)?(?:[A-Za-z]:)?${STOP}*?[\\\\/]scratch[\\\\/]outputs[\\\\/]TQ-\\d+[\\\\/]${STOP}+)`, "gi");
const ADDRESS = /^(?:https?:\/\/(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?)?\/outputs\/TQ-0*(\d+)\/(.+)$/i;
const ON_DISK = /(?:^|\/)scratch\/outputs\/TQ-0*(\d+)\/(.+)$/i;

export const baseName = (p) => String(p || "").replace(/\\/g, "/").split("/").filter(Boolean).pop() || String(p || "");
export const outputUrl = (tid, rel) => `/api/task-outputs/${Number(tid)}/${String(rel).split("/").map(encodeURIComponent).join("/")}`;

// {tid, rel} for an address or a path into any task's outputs folder, or null. rel is a name inside the folder - no `..`, no drive
export function parseOutput(raw) {
  let s = String(raw || "").trim();
  try { s = decodeURIComponent(s); } catch { /* a stray % - read it as written */ }
  s = s.replace(/\\/g, "/").replace(/^file:\/+/i, "");
  let m = ADDRESS.exec(s);
  const rel = m ? m[2].replace(/[?#].*$/, "") : (m = ON_DISK.exec(s)) && m[2];
  if (!m || !rel || rel.split("/").some((p) => !p || p === "." || p === ".." || p.includes(":"))) return null;
  return { tid: Number(m[1]), rel };
}
export const outputOf = (raw, tid) => { const o = parseOutput(raw); return o && tid != null && o.tid === Number(tid) ? o.rel : null; };

const PREVIEW = { xlsx: "sheet", xlsm: "sheet", csv: "table", pdf: "pdf", png: "picture", jpg: "picture", jpeg: "picture", gif: "picture",
  webp: "picture", md: "text", txt: "text", json: "text", log: "text", tsv: "text", svg: "page", html: "page", htm: "page" };
const TYPES = { csv: "text/csv", md: "text/markdown", txt: "text/plain", json: "application/json", log: "text/plain", tsv: "text/plain",
  pdf: "application/pdf", png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif", webp: "image/webp",
  svg: "image/svg+xml", html: "text/html", htm: "text/html" };
const ext = (name) => (/\.([a-z0-9]+)$/i.exec(name || "")?.[1] || "").toLowerCase();

// the row the page draws for a file an answer named: the server's own row when the task's listing has it (outputs.row), else one
// built from the name, marked `missing` once the listing is known and the file is not in it
export function outputRow(tid, rel, listed) {
  const known = (listed || []).find((r) => r.path === rel);
  if (known) return known;
  const name = baseName(rel), e = ext(name);
  return { id: `output:${rel}`, name, path: rel, kind: "output", content_type: TYPES[e] || "", preview: PREVIEW[e] || null,
    url: outputUrl(tid, rel), missing: Array.isArray(listed) };
}

// a citation marker, wherever it is shown, as the file's name - the raw marker is Codex's plumbing, not words for the owner
export const plainCitations = (text) => String(text ?? "").replace(CITE, (_, attrs) => {
  const p = /path\s*=\s*"([^"]*)"/.exec(attrs)?.[1];
  return p ? `\`${baseName(p)}\`` : "";
});

// {text, files}: the answer with every reference to THIS task's outputs taken out of the words (its name stays where it was
// said), and the names inside the folder, in order, once each - for the chips drawn under it
export function outputRefs(text, tid) {
  const files = [], add = (rel) => { if (!files.includes(rel)) files.push(rel); };
  let out = String(text ?? "").replace(CITE, (_, attrs) => {
    const p = /path\s*=\s*"([^"]*)"/.exec(attrs)?.[1];
    const rel = p && outputOf(p, tid);
    if (rel) { add(rel); return ""; }
    return p ? `\`${p}\`` : "";
  });
  out = out.replace(LINK, (all, label, href) => {
    const at = parseOutput(href);
    if (!at) return all;
    if (at.tid === Number(tid)) add(at.rel);
    // ...and a link into another task's folder is no link at all: its words, nothing to click into a 404 or a neighbour's file
    return label.trim() || baseName(at.rel);
  });
  out = out.replace(BARE, (all) => {
    const tail = /[.,;:!?]+$/.exec(all)?.[0] || "", path = all.slice(0, all.length - tail.length);
    const at = parseOutput(path);
    if (!at) return all;
    if (at.tid === Number(tid)) { add(at.rel); return `\`${baseName(at.rel)}\`${tail}`; }
    return `\`${path}\`${tail}`;
  });
  // a marker on a line of its own leaves no empty line behind
  return { text: out.replace(/\n[ \t]*\n(?:[ \t]*\n)+/g, "\n\n").trim(), files };
}

// the task's files no answer names: listed at the foot of the conversation, so every one is reachable and none is drawn twice
// ...and an older version of a file an answer names is that file's history, not one more file at the foot (deliverables)
export const uncited = (listed, answers, tid) => {
  const named = new Set((answers || []).flatMap((t) => outputRefs(t, tid).files)), fams = new Set([...named].map(family));
  return (listed || []).filter((r) => !named.has(r.path) && !fams.has(family(r.name || r.path)));
};

// ONE OF EACH THING IT MADE (the owner, 2026-10-28: "it looks like it created a million attachments. Agents should not create lists of
// lists of attachments unless specifically asked"). The same rule as outputs.deliverables - keep the two alike: a FAMILY is one name with
// its version marks off (v2, _final, (1), a timestamp) and only its newest is listed, the rest `earlier` on it; the agent's own working
// files (scripts, logs, temp and cache, anything under tmp/ or scratch/) are `working`, folded under one line. Never dropped: reachable.
const VER = /(?:[ _.-]+(?:v|ver|version|rev)[ _.-]?\d+|[ _.-]+(?:final|draft|copy|old|new|latest|updated|edited|revised)|[ _.-]*\(\d+\)|[ _.-]+\d{8}(?:[ _T-]?\d{4,6})?|[ _.-]+\d{4}-\d\d-\d\d(?:[ _T-]?\d\d[-.]?\d\d(?:[-.]?\d\d)?)?)+$/i;
const WORK_EXT = new Set(["log", "tmp", "temp", "bak", "pyc", "cache", "lock", "swp", "part", "crdownload",
  "py", "ps1", "sh", "bat", "cmd", "js", "mjs", "ts", "sql", "r", "ipynb"]);
const WORK_DIR = /(?:^|\/)(?:tmp|temp|scratch|cache|__pycache__|work|working|intermediate|drafts?)\//i;
const WORK_NAME = /^(?:tmp|temp|scratch|debug)(?:[ _.-]|$)/i;

export function family(name) {
  const b = baseName(name).toLowerCase(), i = b.lastIndexOf("."), stem = i > 0 ? b.slice(0, i) : b, x = i > 0 ? b.slice(i) : "";
  return (stem.replace(VER, "").replace(/^[ _.-]+|[ _.-]+$/g, "") || stem).replace(/[ _.-]+/g, " ") + x;
}
export const isWorking = (rel) => {
  const p = String(rel || "").replace(/\\/g, "/");
  return WORK_EXT.has(ext(baseName(p))) || WORK_DIR.test(p) || WORK_NAME.test(baseName(p));
};
// {made, working}, newest first; a shown or published page is never working - the agent chose to show it
export const deliverables = (rows) => {
  const by = new Map(), made = [], working = [], at = (r) => String(r?.at || r?.created_at || "");
  for (const r of [...(rows || [])].sort((a, b) => at(b).localeCompare(at(a)))) {
    if (r.kind === "output" && isWorking(r.path || r.name)) { working.push(r); continue; }
    const k = family(r.name || r.path), kept = by.get(k);
    if (kept) kept.earlier.push(r);
    else { const n = { ...r, earlier: [] }; by.set(k, n); made.push(n); }
  }
  return { made, working };
};
