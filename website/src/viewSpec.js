// A VIEW THE AGENT SHOWS IN ITS CHAT (agenttools `show`, viewspec.py): {title?, root, elements: {id: {type, props, children?}}} read off the
// call's trace and made safe to draw. The server already checked it against the catalog (taskuary/viewspec.json, read here too); this is the
// page's own guard, so a spec that reached the chat some other way - a call whose answer never came back, a log that kept only its arguments -
// still draws only what the catalog allows. Anything else is null, and ViewSpec.jsx shows the JSON as text. Pure: test/viewSpec.test.mjs.
import cat from "../../taskuary/viewspec.json" with { type: "json" };
import { VERBS, label } from "./buttons.js";

export const MARK = "TASKUARY-VIEW ";
const { caps: CAPS, every: EVERY } = cat;
const TYPES = Object.fromEntries(Object.entries(cat.types).map(([t, s]) => [t, { ...s, ...EVERY }]));     // every type also takes a title and a description
const FORMAT = cat.types.chart.format, DIR = "up|down|neutral";
// ...a button names a verb (or its row id) that has a button on the task page, as viewspec.ROW_VERBS
const ROW_OF = Object.fromEntries(Object.entries(VERBS).flatMap(([v, b]) => (b.row?.length ? [[v, v], ...b.row.map((r) => [r, v])] : [])));
export const verbOf = (v) => ROW_OF[v] || null;
const LINK = /^#[\w=&%.:/-]+$/;

const isObj = (o) => !!o && typeof o === "object" && !Array.isArray(o);
const text = (v, n = CAPS.short) => ((typeof v === "string" || (typeof v === "number" && Number.isFinite(v))) && String(v).trim().length <= n ? String(v).trim() : null);
const cell = (v) => (v === null || v === undefined ? null : typeof v === "boolean" || (typeof v === "number" && Number.isFinite(v)) ? v : text(v));
const list = (v, n = CAPS.items) => (Array.isArray(v) && v.length && v.length <= n ? v : null);
// every entry kept or the whole prop is bad: half a table drawn as if it were all of it would mislead
const TILE = new Set(["label", "value", "note", "trend", "format"]);
export const labels = (cols) => (cols || []).map((c) => (isObj(c) ? c.label : c));
const all = (xs, f) => { if (!xs) return null; const out = xs.map(f); return out.some((x) => x === null) ? null : out; };

const KIND = {
  str: (v) => text(v),
  md: (v) => text(v, CAPS.long),
  strs: (v, at) => all(list(v, at === "columns" ? CAPS.columns : CAPS.items), (x) => text(x)),
  // a column is its name, or {label, format} when its numbers are money, counts or percents
  cols: (v) => all(list(v, CAPS.columns), (c) => (!isObj(c) ? text(c) : Object.keys(c).every((k) => k === "label" || k === "format") && text(c.label)
    ? (c.format == null ? { label: text(c.label) } : oneOf(FORMAT, c.format) ? { label: text(c.label), format: c.format } : null) : null)),
  rows: (v, _, p) => all(list(v), (r) => {
    const cols = labels(p.columns), row = isObj(r) ? (Object.keys(r).every((k) => cols.includes(k)) ? cols.map((c) => r[c]) : null) : r;
    if (!Array.isArray(row) || row.length > cols.length) return null;
    const cells = [...row, ...Array(cols.length - row.length).fill(null)];
    return cells.some((c) => c != null && cell(c) === null) ? null : cells.map(cell);
  }),
  tiles: (v) => all(list(v, CAPS.columns), (o) => {
    if (!isObj(o) || !text(o.label) || cell(o.value) === null || Object.keys(o).some((k) => !TILE.has(k))) return null;
    const out = { label: text(o.label), value: cell(o.value) }, t = o.trend;
    if (o.note) { if (!text(o.note)) return null; out.note = text(o.note); }
    if (o.format != null) { if (!oneOf(FORMAT, o.format)) return null; out.format = o.format; }
    if (t != null) { if (!isObj(t) || !oneOf(DIR, t.dir) || (t.text != null && !text(t.text))) return null;
      out.trend = { dir: t.dir, ...(t.text ? { text: text(t.text) } : {}) }; }
    return out;
  }),
  checks: (v) => all(list(v), (o) => (typeof o === "string" ? (text(o) ? { text: text(o), done: false } : null)
    : isObj(o) && text(o.text) ? { text: text(o.text), done: o.done === true } : null)),
  points: (v) => all(list(v), (o) => (isObj(o) && text(o.label) && typeof o.value === "number" && Number.isFinite(o.value)
    ? { label: text(o.label), value: o.value, ...(o.highlight === true ? { highlight: true } : {}) } : null)),
  verb: (v) => verbOf(v),
  link: (v) => (typeof v === "string" && LINK.test(v) && v !== "#setup" ? v : null),
};
// one of the words; a count (a grid's columns) is a number, or its digits
const oneOf = (kind, v) => { const ws = kind.split("|");
  return ws.every((w) => /^\d+$/.test(w)) ? (typeof v !== "boolean" && ws.includes(String(v)) ? Number(v) : null) : ws.includes(v) ? v : null; };
const prop = (kind, v, at, p) => (kind.includes("|") ? oneOf(kind, v) : KIND[kind]?.(v, at, p) ?? null);

function element(e) {
  if (!isObj(e) || !TYPES[e.type] || (e.props != null && !isObj(e.props))) return null;
  const spec = TYPES[e.type], props = e.props || {}, out = {};
  if (Object.keys(props).some((k) => !spec[k])) return null;
  for (const [k, kind] of Object.entries(spec)) {
    const need = kind.endsWith("!"), v = props[k];
    if (v == null) { if (need) return null; continue; }
    const got = prop(kind.replace(/!$/, ""), v, k, out);
    if (got === null) return null;
    out[k] = got;
  }
  if (e.type === "button" && ("verb" in out) === ("open" in out)) return null;
  const kids = e.children ?? [];
  if (!Array.isArray(kids) || kids.length > CAPS.children || kids.some((k) => typeof k !== "string")) return null;
  return { type: e.type, props: out, children: kids };
}

// the spec made safe, or null. Only what the root reaches is kept; a child that is missing or contains itself is a bad spec
export function normalise(spec) {
  if (!isObj(spec) || !isObj(spec.elements)) return null;
  const els = spec.elements, ids = Object.keys(els);
  if (!ids.length || ids.length > CAPS.elements || typeof spec.root !== "string" || !(spec.root in els)) return null;
  const out = {}, path = new Set();
  const walk = (id) => {
    if (path.has(id) || !(id in els)) return false;
    if (out[id]) return true;
    const e = element(els[id]); if (!e) return false;
    out[id] = e; path.add(id);
    const ok = e.children.every(walk); path.delete(id); return ok;
  };
  if (!walk(spec.root)) return null;
  const title = spec.title == null ? "" : text(spec.title);
  return title === null ? null : { title, root: spec.root, elements: out };
}

// A NUMBER IN ITS FORMAT: money in dollars, a count grouped, a percent as written (12.5 -> 12.5%). `p` is the decimals, one count for a
// whole column so its figures line up; money has none or two, never one ($13.50, not $13.5)
export const placesOf = (ns, format) => { const frac = (n) => (String(n).split(".")[1] || "").length, p = Math.min(2, Math.max(0, ...ns.filter(Number.isFinite).map(frac)));
  return format === "currency" ? (p ? 2 : 0) : p; };
const NF = {};
export const fmtAs = (n, format, p = placesOf([n], format)) => {
  if (typeof n !== "number" || !Number.isFinite(n)) return n == null ? "" : String(n);
  const k = `${format}${p}`, nf = NF[k] ||= new Intl.NumberFormat("en-US", { minimumFractionDigits: p, maximumFractionDigits: p,
    ...(format === "currency" ? { style: "currency", currency: "USD" } : {}) });
  return `${nf.format(n)}${format === "percent" ? "%" : ""}`;
};

// the words a button says, and what it does: lights a task-page button (its label, buttons.json) or opens a page
export const buttonOf = (p) => ({ label: p.label, ...(p.verb ? { verb: p.verb, lights: label(p.verb) } : { open: p.open }) });

// ── a trace's `show` call -> the chat's view part ───────────────────────────────────────────────
const SHOW = /^(mcp__taskuary__)?show$/;
// its answer's spec, after MARK: the server's own check of it. A call with no answer yet (live) or none kept (a log) draws its arguments
export const specIn = (out) => { const s = String(out || ""), i = s.indexOf(MARK); if (i < 0) return undefined;
  try { return JSON.parse(s.slice(i + MARK.length).replace(/ ⏎ /g, "\n").trim()); } catch { return null; } };
export function viewOf(e, result) {
  if (e?.type !== "tool_call" || !SHOW.test(String(e.name || ""))) return null;
  const d = result?.detail;
  if (d?.is_error) return null;                       // refused: the agent was told why, and its step says it tried
  const got = specIn(d?.result ?? e.detail?.output);
  if (got === undefined && String(e.name) === "show") return null;       // a bare "show" is someone else's tool unless its answer is ours
  const raw = got === undefined ? e.detail?.args : got;
  // ...arguments cut down in the trace (a summary) or never kept (a CLI log's step): nothing to draw, so it stays a step
  if (raw == null || (got === undefined && !isObj(raw.elements))) return null;
  return { type: "view", spec: normalise(raw), raw };
}
