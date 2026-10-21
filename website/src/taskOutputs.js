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
export const uncited = (listed, answers, tid) => {
  const named = new Set((answers || []).flatMap((t) => outputRefs(t, tid).files));
  return (listed || []).filter((r) => !named.has(r.path));
};
