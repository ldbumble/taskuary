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
// THE STATIC DEMO CARRIES ITS OWN BYTES (demo_fixtures.mjs): taskuary.com/demo has no server behind /api/task-outputs, so a picture or a PDF
// the recorded agent made rides in the recording as a data: address, put here by demoApi.js - its post's chart draws there too
export const STATIC_OUTPUTS = {};
export const outputUrl = (tid, rel) => STATIC_OUTPUTS[`${Number(tid)}/${rel}`]
  || `/api/task-outputs/${Number(tid)}/${String(rel).split("/").map(encodeURIComponent).join("/")}`;

// {tid, rel} for an address or a path into any task's outputs folder, or null. rel is a name inside the folder - no `..`, no drive
// ...and only an ADDRESS is decoded (a URL, or any markdown link's target: `link`), its query and fragment cut first. A path on disk
// is its name as written - "TQ-0012 % Collected v9.xlsx" or "Q3 #2.xlsx" is a real name, and decoding it, or cutting at its '#',
// named a file that is not there
const URLISH = /^(?:https?:|file:|\/outputs\/)/i;
export function parseOutput(raw, link = false) {
  let s = String(raw || "").trim();
  if (link || URLISH.test(s)) {
    s = s.replace(/^(https?:\/\/[^/]*)?(\/outputs\/[^?#]*)[?#].*$/i, "$1$2");
    try { s = decodeURIComponent(s); } catch { /* a stray % - read it as written */ }
  }
  s = s.replace(/\\/g, "/").replace(/^file:\/+/i, "");
  let m = ADDRESS.exec(s);
  const rel = m ? m[2] : (m = ON_DISK.exec(s)) && m[2];
  if (!m || !rel || rel.split("/").some((p) => !p || p === "." || p === ".." || p.includes(":"))) return null;
  return { tid: Number(m[1]), rel };
}
export const outputOf = (raw, tid) => { const o = parseOutput(raw); return o && tid != null && o.tid === Number(tid) ? o.rel : null; };

const PREVIEW = { xlsx: "sheet", xlsm: "sheet", csv: "table", pdf: "pdf", png: "picture", jpg: "picture", jpeg: "picture", gif: "picture",
  webp: "picture", md: "text", txt: "text", json: "text", log: "text", tsv: "text", svg: "page", html: "page", htm: "page", docx: "document" };
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
// run `f` on the words between code spans only: a path or a name already in backticks is left exactly as it is
const outsideCode = (s, f) => s.split(/(\x60[^\x60\n]*\x60)/).map((x, i) => (i % 2 ? x : f(x))).join("");

export function outputRefs(text, tid, listed) {
  const files = [], add = (rel) => { if (!files.includes(rel)) files.push(rel); };
  let out = String(text ?? "");
  // a name WITH SPACES ("Open tasks 2026-11-02.xlsx"), written as a bare path: BARE stops at the first space, so the page drew a file
  // called "Open" that was not there and left "tasks 2026-11-02.xlsx**" in the words (stress test 2026-11-02). The task's own listing
  // knows the whole name - those are found first, longest first, so a shorter name inside a longer one never takes its place
  const spaced = (listed || []).map((r) => r.path).filter((rel) => /\s/.test(rel || "")).sort((a, b) => b.length - a.length);
  for (const rel of spaced) {
    const name = rel.split("/").map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("[\\\\/]");
    const at = new RegExp(`(?:file:/+)?(?:[A-Za-z]:)?${STOP}*?[\\\\/]scratch[\\\\/]outputs[\\\\/]TQ-0*${Number(tid)}[\\\\/]${name}`, "gi");
    out = out.replace(at, (all) => { add(rel); return `${/^[*_]+/.exec(all)?.[0] || ""}\`${baseName(rel)}\``; });
  }
  out = out.replace(CITE, (_, attrs) => {
    const p = /path\s*=\s*"([^"]*)"/.exec(attrs)?.[1];
    const rel = p && outputOf(p, tid);
    if (rel) { add(rel); return ""; }
    return p ? `\`${p}\`` : "";
  });
  out = out.replace(LINK, (all, label, href) => {
    const at = parseOutput(href, true);
    if (!at) return all;
    if (at.tid === Number(tid)) add(at.rel);
    // ...and a link into another task's folder is no link at all: its words, nothing to click into a 404 or a neighbour's file
    return label.trim() || baseName(at.rel);
  });
  // ...and a path in bold or italics keeps its marks OUTSIDE it: "**C:\\...\\report.xlsx**" named a file "report.xlsx**" that was not there
  out = out.replace(BARE, (all, at0, whole) => {
    const lead = /^[*_]+/.exec(all)?.[0] || "", tail = /[.,;:!?*_]+$/.exec(all)?.[0] || "", path = all.slice(lead.length, all.length - tail.length);
    const at = parseOutput(path);
    if (!at) return all;
    // ...a path the agent put in backticks is its name in those backticks - wrapped again it read ```name``` (the product audit, 2026-11-08)
    const coded = whole[at0 - 1] === "\x60";
    if (at.tid === Number(tid)) { add(at.rel); return coded ? `${baseName(at.rel)}${tail}` : `${lead}\`${baseName(at.rel)}\`${tail}`; }
    return `${lead}\`${path}\`${tail}`;
  });
  // ...THE TASK'S FOLDER, named bare, is a code span too - the chat makes that one a link that opens it on this computer (the owner,
  // 2026-11-06: "clickable links in the agent to local desktop for where it saves items"); and a file of its own folder named bare in
  // the words ("- Private balance audit.xlsx") reads as that file, which the chat opens at a press. Only OUTSIDE code spans, and only
  // names the listing has, longest first
  const folder = new RegExp(`(?:[A-Za-z]:)?(?:[\\\\/]${STOP}*?)?[\\\\/]scratch[\\\\/]outputs[\\\\/]TQ-0*${Number(tid)}[\\\\/]?(?=$|[\\s.,;:!?)*_])`, "gim");
  const names = [...(listed || [])].sort((a, b) => baseName(b.path).length - baseName(a.path).length);
  out = outsideCode(out, (bit) => {
    bit = bit.replace(folder, (path) => `\x60${path}\x60`);
    for (const r of names) {
      const n = baseName(r.path).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      bit = outsideCode(bit, (b2) => b2.replace(new RegExp(`(^|[^\\w./\\\\-])(${n})(?![\\w])`, "gm"), (all, lead, name) => { add(r.path); return `${lead}\x60${name}\x60`; }));
    }
    return bit;
  });
  // ...and a line that is nothing but one of its files is that file's card, drawn under the answer - never its name again on a line of its
  // own (the product audit, 2026-11-08: the picture's whole path stood alone over the post card)
  const own = new Set(files.map(baseName));
  out = out.replace(/^[ \t]*[*_]*\x60([^\x60\n]+)\x60[*_]*[ \t.]*$/gm, (line, n) => (own.has(n) ? "" : line));
  // a marker on a line of its own leaves no empty line behind
  return { text: out.replace(/\n[ \t]*\n(?:[ \t]*\n)+/g, "\n\n").trim(), files };
}

// ONE FILE, ONE CARD: a file the answer names AND showed ([[TASKUARY-SHOW]]) is the same file twice - its output row from the path in
// the words, and the copy the turn kept - and the owner saw two cards for one picture ("why are there 2 of them? looks broken").
// The named row stays (Preview, Download, its size) and opens as the shown one did; the copy is drawn only when the words never named it.
export function shownOnce(cited, shown) {
  const names = new Set((cited || []).map(baseName)), seen = new Set((shown || []).map((p) => p.name));
  return { isShown: (rel) => seen.has(baseName(rel)), rest: (shown || []).filter((p) => !names.has(p.name)) };
}

// the task's files no answer names: listed at the foot of the conversation, so every one is reachable and none is drawn twice
// ...and an older version of a file an answer names is that file's history, not one more file at the foot (deliverables)
export const uncited = (listed, answers, tid) => {
  const named = new Set((answers || []).flatMap((t) => outputRefs(t, tid, listed).files)), fams = new Set([...named].map(family));
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

// EACH TURN SHOWS THE FILE AS IT MADE IT (the owner, 2026-11-07: "same file with revisions"): turn 1 named the table a later turn rewrote in
// place, and drew the newest one under words about the old. `versions` (outputs.turn_versions) are earlier turns' own copies, `turn` the
// answer each belongs to: that turn reads its own, every other turn - the newest among them - the file as it is now
export const forTurn = (listed, versions, id) => {
  const mine = new Map((versions || []).filter((v) => v.turn === id).map((v) => [v.path, v]));
  if (!mine.size) return listed || [];
  const out = (listed || []).map((r) => mine.get(r.path) || r);
  return [...out, ...[...mine.values()].filter((v) => !out.includes(v))];
};

// WHAT A TURN MADE, IN THE TURN (the owner, 2026-11-05: "the post and images are as artifacts separate not inline???"): the files placed on this
// answer by when they were made (the server's `after`, as a shown page's) and the ones its words or its summary name - each thing once, the
// newest of a family, never the agent's working files - less `skip` (a post's own picture, drawn on the post)
export const turnFiles = ({ listed = [], id, words = "", did = "", tid, skip = [] } = {}) => {
  const no = new Set((skip || []).map(baseName)), by = new Map();
  for (const r of (listed || []).filter((x) => x?.after != null && x.after === id)) by.set(r.path, r);
  for (const rel of outputRefs(`${words || ""}\n${did || ""}`, tid, listed).files) if (!by.has(rel)) by.set(rel, outputRow(tid, rel, listed));
  return deliverables([...by.values()].filter((r) => !no.has(baseName(r.path || r.name)) && !r.missing)).made;
};
