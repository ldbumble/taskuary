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

// ── A VALUE WORKED OUT ON THE PAGE (viewspec.py names_in reads the same grammar): {$expr: "seats * 12"} or {$state: "/seats"}, evaluated
// against the view's state - and in a table's cell its row's columns - each time a control moves. Its own small parser, never eval: numbers,
// 'words', true/false, names, + - * / %, comparisons, && || !, c ? a : b, and the few functions below. A bad one is {error}, said in the view
export const exprOf = (v) => (isObj(v) && Object.keys(v).length === 1 ? (typeof v.$expr === "string" ? v.$expr.trim()
  : typeof v.$state === "string" ? v.$state.trim().replace(/^\//, "") : null) : null);
const FNS = { min: Math.min, max: Math.max, abs: Math.abs, floor: Math.floor, ceil: Math.ceil,
  round: (x, p = 0) => { const k = 10 ** p; return Math.round(x * k) / k; } };
const TOK = /\s*(?:(\d+(?:\.\d+)?|\.\d+)|('[^']*'|"[^"]*")|([A-Za-z_]\w*)|(==|!=|<=|>=|&&|\|\||[-+*/%<>!?:(),]))/y;
const OPS = { "+": [4, (a, b) => a + b], "-": [4, (a, b) => a - b], "*": [5, (a, b) => a * b], "/": [5, (a, b) => a / b], "%": [5, (a, b) => a % b],
  "==": [3, (a, b) => a === b], "!=": [3, (a, b) => a !== b], "<": [3, (a, b) => a < b], "<=": [3, (a, b) => a <= b], ">": [3, (a, b) => a > b],
  ">=": [3, (a, b) => a >= b], "&&": [2, (a, b) => a && b], "||": [1, (a, b) => a || b] };
const COMPILED = new Map();
function compile(src) {
  const toks = []; TOK.lastIndex = 0; const s = String(src).trimEnd();
  while (TOK.lastIndex < s.length) { const at = TOK.lastIndex, m = TOK.exec(s);
    if (!m) throw new Error(`cannot read "${s.slice(at).trim().slice(0, 20)}"`);
    toks.push(m[1] != null ? { n: Number(m[1]) } : m[2] != null ? { s: m[2].slice(1, -1) } : m[3] != null ? { id: m[3] } : { op: m[4] }); }
  let i = 0;
  const peek = () => toks[i]?.op, eat = (op) => { if (toks[i]?.op !== op) throw new Error(`expected "${op}"`); i++; };
  const atom = () => {
    const t = toks[i++]; if (!t) throw new Error("it ends too soon");
    if (t.op === "(") { const e = tern(); eat(")"); return e; }
    if (t.op === "-") { const e = atom(); return (sc) => -e(sc); }
    if (t.op === "!") { const e = atom(); return (sc) => !e(sc); }
    if ("n" in t) return () => t.n;
    if ("s" in t) return () => t.s;
    if (t.id === "true" || t.id === "false") return () => t.id === "true";
    if (!t.id) throw new Error(`"${t.op}" cannot start a value`);
    if (peek() === "(") {
      const f = Object.hasOwn(FNS, t.id) ? FNS[t.id] : null; if (!f) throw new Error(`${t.id}() is not one of ${Object.keys(FNS).join(", ")}`);
      eat("("); const args = []; if (peek() !== ")") { args.push(tern()); while (peek() === ",") { eat(","); args.push(tern()); } } eat(")");
      return (sc) => f(...args.map((a) => a(sc)));
    }
    return (sc) => { if (!Object.hasOwn(sc, t.id)) throw new Error(`no value named ${t.id}`); return sc[t.id]; };
  };
  const binary = (min) => { let l = atom();
    while (OPS[peek()] && OPS[peek()][0] >= min) { const [p, f] = OPS[toks[i++].op], r = binary(p + 1), a = l; l = (sc) => f(a(sc), r(sc)); }
    return l; };
  const tern = () => { const c = binary(1); if (peek() !== "?") return c; eat("?"); const a = tern(); eat(":"); const b = tern(); return (sc) => (c(sc) ? a(sc) : b(sc)); };
  if (!toks.length) throw new Error("it is empty");
  const e = tern(); if (i < toks.length) throw new Error(`"${toks[i].op ?? toks[i].id ?? toks[i].n}" was not expected`);
  return e;
}
// -> {value} or {error: plain words}. A number that is not one (1/0) is an error too: a tile never reads "Infinity"
export function evalExpr(src, scope = {}) {
  try {
    let f = COMPILED.get(src); if (!f) { f = compile(src); COMPILED.set(src, f); }
    const v = f(scope);
    if (typeof v === "number" && !Number.isFinite(v)) throw new Error("it does not come to a number");
    return { value: v };
  } catch (e) { return { error: `"${src}" - ${e.message}` }; }
}
// a column's name as a cell's expression reads it: lower case, _ for a space (viewspec.col_name)
export const colName = (l) => String(l).trim().toLowerCase().replace(/\W+/g, "_").replace(/^_+|_+$/g, "");
// words with {expr} in them, worked out now (a button's answer: "Order {seats} seats") -> {value} or {error}
export function fillIn(s, scope) {
  let error = null;
  const value = String(s).replace(/\{([^{}]+)\}/g, (_, src) => { const r = evalExpr(src, scope); if (r.error) error ||= r.error; return r.error ? "" : String(r.value); });
  return error ? { error } : { value };
}

const cell = (v) => (v === null || v === undefined ? null : typeof v === "boolean" || (typeof v === "number" && Number.isFinite(v)) ? v
  : exprOf(v) && exprOf(v).length <= CAPS.short ? { $expr: exprOf(v) } : text(v));
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
  points: (v) => all(list(v), (o) => (isObj(o) && text(o.label) && ((typeof o.value === "number" && Number.isFinite(o.value)) || exprOf(o.value))
    ? { label: text(o.label), value: exprOf(o.value) ? { $expr: exprOf(o.value) } : o.value, ...(o.highlight === true ? { highlight: true } : {}) } : null)),
  records: (v) => list(v),            // ...a chart's: made its points in element()
  num: (v) => (typeof v === "number" && Number.isFinite(v) ? v : null),
  // a control's value: the state name it moves - "seats", "/seats" or json-render's {$bindState: "/seats"}
  bind: (v) => { const n = isObj(v) ? v.$bindState : v; const s = typeof n === "string" ? n.trim().replace(/^\//, "") : "";
    return /^[A-Za-z_]\w{0,31}$/.test(s) ? s : null; },
  verb: (v) => verbOf(v),
  link: (v) => (typeof v === "string" && LINK.test(v) && v !== "#setup" ? v : null),
};
// one of the words; a count (a grid's columns) is a number, or its digits
const oneOf = (kind, v) => { const ws = kind.split("|");
  return ws.every((w) => /^\d+$/.test(w)) ? (typeof v !== "boolean" && ws.includes(String(v)) ? Number(v) : null) : ws.includes(v) ? v : null; };
const prop = (kind, v, at, p) => (kind.includes("|") ? oneOf(kind, v) : KIND[kind]?.(v, at, p) ?? null);

// a chart's records as its points, as viewspec._points: y the number column, x its label
const NUMS = (rs, c) => rs.every((r) => typeof r[c] === "number" && Number.isFinite(r[c]));
function pointsOf(p) {
  const rs = list(p.rows); if (!rs || !rs.every(isObj)) return null;
  const cols = [...new Set(rs.flatMap(Object.keys))], y = p.y ?? cols.find((c) => NUMS(rs, c));
  if (!cols.includes(y) || !NUMS(rs, y)) return null;
  const x = p.x ?? cols.find((c) => c !== y && !NUMS(rs, c));
  if (x != null && !cols.includes(x)) return null;
  return rs.map((r, i) => ({ label: x != null ? r[x] : `#${i + 1}`, value: r[y] }));
}
// a button's on.press (viewspec._on): answer {text} - his pick, to the agent - or setState {statePath, value} on the page; nothing else
function onOf(v) {
  const p = isObj(v) && Object.keys(v).length === 1 && isObj(v.press) ? v.press : null, ps = isObj(p?.params) ? p.params : {};
  if (p?.action === "answer" && text(ps.text)) return { press: { action: "answer", params: { text: text(ps.text) } } };
  if (p?.action === "setState" && KIND.bind(ps.statePath) && ps.value !== undefined && (ps.value === null || cell(ps.value) !== null))
    return { press: { action: "setState", params: { statePath: KIND.bind(ps.statePath), value: cell(ps.value) } } };
  return null;
}

function element(e) {
  if (!isObj(e) || !TYPES[e.type] || (e.props != null && !isObj(e.props))) return null;
  const spec = TYPES[e.type], out = {};
  let props = e.props || {};
  if (Object.keys(props).some((k) => !spec[k])) return null;
  // ...records stand as they come: a table's columns are their keys, a chart's points their label and number columns
  if (e.type === "table" && props.columns == null) {
    if (!Array.isArray(props.rows) || !props.rows.every(isObj)) return null;
    props = { ...props, columns: [...new Set(props.rows.flatMap(Object.keys))].slice(0, CAPS.columns) };
  }
  if (e.type === "chart") {
    if ((props.points == null) === (props.rows == null)) return null;
    if (props.rows != null) { const pts = pointsOf(props); if (!pts) return null;
      const { rows, x, y, ...rest } = props; props = { ...rest, points: pts }; }
  }
  for (const [k, kind] of Object.entries(spec)) {
    const need = kind.endsWith("!"), v = props[k];
    if (v == null) { if (need) return null; continue; }
    const got = prop(kind.replace(/!$/, ""), v, k, out);
    if (got === null) return null;
    out[k] = got;
  }
  const on = e.on == null ? null : onOf(e.on);
  if (e.on != null && (!on || e.type !== "button")) return null;
  if (e.type === "button" && ["verb" in out, "open" in out, !!on].filter(Boolean).length !== 1) return null;
  if (e.type === "slider" && !(out.min < out.max)) return null;
  const kids = e.children ?? [];
  if (!Array.isArray(kids) || kids.length > CAPS.children || kids.some((k) => typeof k !== "string")) return null;
  return { type: e.type, props: out, ...(on ? { on } : {}), children: kids };
}

// THE VIEW'S VALUES (viewspec._state): its `state` as given, and each bound name it lacks at its control's start
export const CONTROLS = new Set(["slider", "toggle", "select", "date"]);
function stateOf(st, els) {
  if (st != null && !isObj(st)) return null;
  const out = {};
  for (const [k, v] of Object.entries(st || {})) { if (!/^[A-Za-z_]\w{0,31}$/.test(k) || isObj(v) || Array.isArray(v)) return null; out[k] = cell(v); }
  if (Object.keys(out).length > CAPS.state) return null;
  for (const e of Object.values(els)) if (CONTROLS.has(e.type) && !(e.props.value in out))
    out[e.props.value] = { slider: e.props.min, toggle: false, select: e.props.options?.[0] ?? "", date: "" }[e.type];
  return out;
}
// ...and A VIEW HE CAN ANSWER (a choice, a button's answer): the server gave it an id of its own (viewspec.shown); one written in words
// has none, and is named by what it says - the same words drawn again are the same question
export const asks = (els) => Object.values(els).some((e) => e.type === "choice" || e.on?.press?.action === "answer");
const hash = (s) => { let h = 5381; for (let i = 0; i < s.length; i++) h = (h * 33 + s.charCodeAt(i)) >>> 0; return `w${h.toString(36)}`; };

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
  const title = spec.title == null ? "" : text(spec.title), state = stateOf(spec.state, out);
  if (title === null || state === null) return null;
  const id = !asks(out) ? "" : typeof spec.id === "string" && /^[\w-]{1,64}$/.test(spec.id) ? spec.id : hash(JSON.stringify({ title, root: spec.root, elements: out }));
  return { title, root: spec.root, elements: out, ...(Object.keys(state).length ? { state } : {}), ...(id ? { id } : {}) };
}

// A VIEW WRITTEN IN AN ANSWER (the owner, 2026-11-15: "of course chart should be in chat"): a fenced block in an agent's or the Assistant's
// words that parses as a spec this same check passes is drawn as a `show` call's is (md.jsx's Pre); anything else stays the code block it was
export const fencedView = (code) => { const s = String(code || "").trim(); if (!s.startsWith("{")) return null;
  try { return normalise(JSON.parse(s)); } catch { return null; } };

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

// A BAR CHART OF MANY SHORT LABELS STANDS AS COLUMNS (the owner, 2026-11-23: a view that "takes up the whole screen - you lose the flow"): twelve
// months as ranked bars were a row each, 538px in a 409px chat at 1366x768. Its marks ({key, value, on}) as the columns' series (charts.Stacked)
// - one series, the highlighted keys picked out - or null where ranked bars read better: a few, or names too long to stand under a column
const COLS = 6, SHORT = 8;
export const columnsOf = (marks) => (marks.length <= COLS || marks.some((m) => m.key.length > SHORT) ? null
  : { keys: marks.map((m) => m.key), series: ["value"], cells: Object.fromEntries(marks.map((m) => [m.key, { value: { value: m.value, rows: [] } }])),
      on: new Set(marks.filter((m) => m.on).map((m) => m.key)) });

// the words a button says, and what it does: lights a task-page button (its label, buttons.json) or opens a page
export const buttonOf = (p) => ({ label: p.label, ...(p.verb ? { verb: p.verb, lights: label(p.verb) } : { open: p.open }) });

// ── a trace's `show` call -> the chat's view part ───────────────────────────────────────────────
export const SHOW = /^(mcp__taskuary__)?show$/;
// its answer's spec, after MARK: the server's own check of it. Only a call with no answer yet (live) or none kept (a log) draws its arguments
export const specIn = (out) => { const s = String(out || ""), i = s.indexOf(MARK); if (i < 0) return undefined;
  try { return JSON.parse(s.slice(i + MARK.length).replace(/ ⏎ /g, "\n").trim()); } catch { return null; } };
// ...and the FILES it showed (agenttools.show_files, 2026-11-09): copies kept on the task, their rows after FILES_MARK and before any view's
// mark - drawn in the turn as the pictures and pages they are. Only rows the server wrote: a task artifact's own address, nothing else
export const FILES_MARK = "TASKUARY-FILES ";
const ARTIFACT = /^\/api\/task-artifacts\/\d+$/;
export function filesOf(e, result) {
  if (e?.type !== "tool_call" || !SHOW.test(String(e.name || "")) || result?.detail?.is_error) return null;
  const s = String(result?.detail?.result ?? e.detail?.output ?? ""), i = s.indexOf(FILES_MARK);
  if (i < 0) return null;
  // ...its rows end at their own last "]": a view's words and mark may follow them in the same answer
  const j = s.indexOf(MARK, i), upto = s.slice(i + FILES_MARK.length, j < 0 ? undefined : j), raw = upto.slice(0, upto.lastIndexOf("]") + 1).replace(/ ⏎ /g, "\n");
  let rows; try { rows = JSON.parse(raw); } catch { return null; }
  const files = (Array.isArray(rows) ? rows : []).filter((r) => isObj(r) && ARTIFACT.test(String(r.url || "")) && text(r.name))
    .map((r) => ({ id: r.id, name: text(r.name), path: `shown:${r.id}`, kind: "shown", content_type: String(r.content_type || ""), size: Number(r.size) || 0, url: r.url }));
  return files.length ? { type: "files", files } : null;
}
export function viewOf(e, result) {
  if (e?.type !== "tool_call" || !SHOW.test(String(e.name || ""))) return null;
  const d = result?.detail;
  if (d?.is_error) return null;                       // refused: the agent was told why, and its step says it tried
  const said = String(d?.result ?? e.detail?.output ?? "").trim(), got = specIn(said);
  if (got === undefined && String(e.name) === "show") return null;       // a bare "show" is someone else's tool unless its answer is ours
  // ...and an answer without the mark is the server's refusal (2026-11-17): it says why in words, not is_error, so drawing the arguments
  // put a table it refused above the one it then took - the server's check decides, the page draws only what it marked shown
  if (got === undefined && said) return null;
  const raw = got === undefined ? e.detail?.args : got;
  // ...arguments cut down in the trace (a summary) or never kept (a CLI log's step): nothing to draw, so it stays a step
  if (raw == null || (got === undefined && !isObj(raw.elements))) return null;
  // ...and one the page cannot draw is no view either (2026-11-15): it stays the step it was, never its JSON in the chat
  const spec = normalise(raw);
  return spec ? { type: "view", spec, raw } : null;
}
