// THE ROWS A DASHBOARD DRAWS, SLICED (dashboards.py keeps them; this cuts them): the date range and the segment filter re-slice
// every component from the same rows, so the numbers on one screen always agree. Pure - test/dashboardSlice.test.mjs holds it -
// and the server's stat headline (dashboards.headline) reads a tile the same way: range, then where, then the aggregate.
export const RANGES = [7, 30, 90, 0];          // days back; 0 is every row the sources returned
export const MAX_SERIES = 6;                   // the palette's six validated slots; a seventh series folds into Other
export const OTHER = "\u0000other";            // a key no real value can be

const pad = (n) => String(n).padStart(2, "0");
export const dayOf = (v) => String(v ?? "").slice(0, 10);
export const isDay = (v) => /^\d{4}-\d{2}-\d{2}/.test(String(v ?? ""));
export const localDay = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const daysAgo = (n, now = new Date()) => { const d = new Date(now); d.setDate(d.getDate() - n); return localDay(d); };
export const num = (v) => (v === null || v === undefined || v === "" || Number.isNaN(Number(v)) ? null : Number(v));

export const sourceOf = (spec, key) => (spec?.sources || []).find((s) => s.key === key) || {};
export const rowsOf = (data, key) => data?.sources?.[key]?.rows || [];

// the range: rows dated inside the last `days` (today included); a source with no date column is never cut by it
export const inRange = (rows, date, days, now = new Date()) => {
  if (!date || !days) return rows;
  const cut = daysAgo(days - 1, now);              // the last 7 days are today and the six before it
  return rows.filter((r) => dayOf(r[date]) >= cut);
};
// the segment: only a row that HAS the column is cut by it - a source without it is not sliced, never emptied
export const inSegment = (rows, column, value) => !column || value === undefined || value === null || value === ""
  ? rows : rows.filter((r) => !(column in r) || String(r[column]) === String(value));
export const where = (rows, w) => !w ? rows : rows.filter((r) => Object.entries(w).every(([k, v]) => String(r[k]) === String(v)));

export const aggregate = (rows, agg = "count", y) => {
  if (!agg || agg === "count") return rows.length;
  const vals = rows.map((r) => num(r[y])).filter((v) => v !== null);
  if (!vals.length) return null;
  if (agg === "sum") return vals.reduce((a, b) => a + b, 0);
  if (agg === "avg") return vals.reduce((a, b) => a + b, 0) / vals.length;
  if (agg === "median") { const s = [...vals].sort((a, b) => a - b), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; }
  if (agg === "min") return Math.min(...vals);
  if (agg === "max") return Math.max(...vals);
  return null;
};

// the date a component is cut by: its source's - unless it counts what is true NOW ("range": false, open tasks), which no range cuts
export const dateOf = (spec, c) => (c?.range === false ? null : sourceOf(spec, c?.source).date || null);
// a component's own window: "range": 7 is always the last week (a weekly target), whatever range the page is on
export const spanOf = (c, days) => (typeof c?.range === "number" ? c.range : days);
// a component's rows: its source's, through the range, the segment and its own where - the one cut every component takes
export const componentRows = (spec, data, c, { days, segment, value, now } = {}) =>
  where(inSegment(inRange(rowsOf(data, c.source), dateOf(spec, c), spanOf(c, days), now), segment, value), c.where);

// ranked categories, the tail folded into Other so a bar chart never grows a ninth bar - or, given an `order` (a funnel's stages),
// those in that order, an empty stage drawn at zero rather than dropped
export const groupBy = (rows, x, agg, y, { limit = 8, order = null } = {}) => {
  const by = new Map();
  for (const r of rows) { const k = r[x] === null || r[x] === undefined || r[x] === "" ? "(blank)" : String(r[x]); if (!by.has(k)) by.set(k, []); by.get(k).push(r); }
  if (order?.length) return order.map(String).map((key) => ({ key, value: aggregate(by.get(key) || [], agg, y), rows: by.get(key) || [] }));
  const all = [...by].map(([key, rs]) => ({ key, value: aggregate(rs, agg, y), rows: rs })).sort((a, b) => (b.value ?? -Infinity) - (a.value ?? -Infinity) || a.key.localeCompare(b.key));
  if (all.length <= limit) return all;
  const rest = all.slice(limit - 1).flatMap((g) => g.rows);
  return [...all.slice(0, limit - 1), { key: OTHER, other: true, value: aggregate(rest, agg, y), rows: rest }];
};

// every day between two days, inclusive - a chart over time has no holes where nothing happened
export const daysBetween = (from, to) => {
  const out = [], d = new Date(`${from}T12:00:00`), end = new Date(`${to}T12:00:00`);
  if (Number.isNaN(d.getTime()) || Number.isNaN(end.getTime())) return out;
  for (let i = 0; d <= end && i < 400; i++) { out.push(localDay(d)); d.setDate(d.getDate() + 1); }
  return out;
};
const daySpan = (rows, x, days, now) => {
  const seen = rows.map((r) => dayOf(r[x])).filter(isDay).sort();
  const to = localDay(now), from = days ? daysAgo(days - 1, now) : seen[0] || to;
  return daysBetween(from < to ? from : to, seen.length && seen[seen.length - 1] > to ? seen[seen.length - 1] : to);
};

// a value per day: a count or a sum is 0 on a quiet day; an average has no value there, and the line breaks
export const timeSeries = (rows, x, agg, y, { days, now = new Date() } = {}) => {
  const by = new Map();
  for (const r of rows) { const k = dayOf(r[x]); if (!isDay(k)) continue; if (!by.has(k)) by.set(k, []); by.get(k).push(r); }
  const zero = !agg || agg === "count" || agg === "sum";
  return daySpan(rows, x, days, now).map((key) => { const rs = by.get(key) || []; return { key, value: rs.length ? aggregate(rs, agg, y) : zero ? 0 : null, rows: rs }; });
};

// COLOUR FOLLOWS THE ENTITY, NEVER ITS RANK: slots are dealt by each value's share of ALL the source's rows, before any filter,
// so a range or a segment that drops a series never repaints the ones left. Past the six slots a value is Other.
export const seriesSlots = (rows, column) => {
  const n = new Map();
  for (const r of rows) { const k = String(r[column] ?? "(blank)"); n.set(k, (n.get(k) || 0) + 1); }
  const order = [...n].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([k]) => k);
  const keep = order.length <= MAX_SERIES ? order : order.slice(0, MAX_SERIES - 1);
  return Object.fromEntries(keep.map((k, i) => [k, i]));
};

// categories split by a second column: {keys, series, cells[key][series] = {value, rows}} - a date x keeps every day
export const stacked = (rows, x, series, agg, y, { slots, days, now = new Date(), limit = 12 } = {}) => {
  const dated = rows.some((r) => isDay(r[x]));
  const sk = (r) => { const k = String(r[series] ?? "(blank)"); return slots && !(k in slots) ? OTHER : k; };
  const keys = dated ? daySpan(rows, x, days, now) : groupBy(rows, x, agg, y, { limit }).map((g) => g.key);
  const xk = (r) => { const k = dated ? dayOf(r[x]) : String(r[x] ?? "(blank)"); return dated || keys.includes(k) ? k : OTHER; };
  const cells = Object.fromEntries(keys.map((k) => [k, {}]));
  const seen = new Set();
  for (const r of rows) {
    const k = xk(r), s = sk(r); if (!cells[k]) continue;
    seen.add(s); (cells[k][s] ||= { rows: [] }).rows.push(r);
  }
  for (const k of keys) for (const s of Object.keys(cells[k])) cells[k][s].value = aggregate(cells[k][s].rows, agg, y);
  const rank = (s) => s === OTHER ? Infinity : slots?.[s] ?? 99;
  return { keys, dated, series: [...seen].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b)), cells };
};

// a tile's delta: this range against the one before it, the same length - only when the rows are dated and a range is chosen
export const delta = (rows, date, days, agg, y, now = new Date()) => {
  if (!date || !days) return null;
  const cut = daysAgo(days - 1, now), prevCut = daysAgo(days * 2 - 1, now);
  const cur = rows.filter((r) => dayOf(r[date]) >= cut), prev = rows.filter((r) => { const d = dayOf(r[date]); return d >= prevCut && d < cut; });
  const a = aggregate(cur, agg, y), b = aggregate(prev, agg, y);
  if (a === null || b === null) return null;
  return { now: a, prev: b, change: a - b, pct: b ? (a - b) / Math.abs(b) : null };
};

export const sortRows = (rows, sort) => {
  if (!sort) return rows;
  const desc = sort.startsWith("-"), col = desc ? sort.slice(1) : sort;
  return [...rows].sort((a, b) => {
    const x = a[col], z = b[col], nx = num(x), nz = num(z);
    const c = nx !== null && nz !== null ? nx - nz : String(x ?? "").localeCompare(String(z ?? ""));
    return desc ? -c : c;
  });
};

// compact from ten thousand up (12.9K, 4.2M); a whole number with its commas; one decimal otherwise
export const fmt = (v) => {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  const a = Math.abs(v);
  if (a >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (a >= 1e4) return `${(v / 1e3).toFixed(1)}K`;
  return Number.isInteger(v) ? v.toLocaleString("en-US") : v.toLocaleString("en-US", { maximumFractionDigits: 1 });
};
export const signed = (v) => (v > 0 ? `+${fmt(v)}` : v < 0 ? `−${fmt(-v)}` : "±0");

// the segment filter's choices: every value the column takes, across the sources that carry it
export const segmentValues = (data, column) => {
  if (!column) return [];
  const out = new Set();
  for (const s of Object.values(data?.sources || {})) for (const r of s.rows || []) if (column in r && r[column] !== null && r[column] !== "") out.add(String(r[column]));
  return [...out].sort((a, b) => a.localeCompare(b));
};

// a row that IS an item opens it: a task by its id, else a message
export const itemLink = (r) => r?.task_id ? `task=${r.task_id}` : r?.message_id ? `msg=${r.message_id}` : null;

// the grid: four columns at full width, two on a tablet, one on a phone - a stat is a quarter, a chart half, a table the row
export const spanOf4 = (c) => Math.max(1, Math.min(4, Number(c.w) || (c.kind === "stat" || c.kind === "progress" ? 1 : c.kind === "table" ? 4 : 2)));

// WHAT A SHARED DASHBOARD CARRIES (Share.jsx's useShare): its stat tiles as lines, over the spec's own range, and the rows it drew -
// one source's rows as they are, several sources' each marked with its label so one table still says which read a row came from.
// The share is frozen when pressed, so a filter the owner set on the page is not the dashboard; the spec's default range is.
export const snapshotOf = (spec, data, now = new Date()) => {
  const days = Number(spec?.filters?.range) || 0, srcs = Object.entries(data?.sources || {}).filter(([, s]) => (s?.rows || []).length);
  const text = (spec?.components || []).filter((c) => c.kind === "stat")
    .map((c) => { const v = aggregate(componentRows(spec, data, c, { days, now }), c.agg, c.y); return `${c.title || "value"}: ${fmt(v)}${c.unit && v !== null ? ` ${c.unit}` : ""}`; })
    .join("\n");
  const rows = srcs.length === 1 ? srcs[0][1].rows : srcs.flatMap(([k, s]) => s.rows.map((r) => ({ source: s.label || k, ...r })));
  return { text, data: rows };
};
