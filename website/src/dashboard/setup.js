// A DASHBOARD'S SPEC, AS A PERSON EDITS IT (DashboardEditor.jsx): the bindings each preset asks for and the small conversions between
// what a field shows and what the spec keeps. Pure - test/dashboardSetup.test.mjs holds it - and kept to what dashboards.validate takes.

// what each kind binds, in the order it is set (dashboards.KINDS, compose.DASHBOARD_SYSTEM). Title, source, where, its own window and
// its width are every kind's; a y is asked only of an aggregate that adds one up
export const BINDS = { stat: ["agg", "y", "unit", "good"], progress: ["agg", "y", "target"], line: ["x", "agg", "y"], area: ["x", "agg", "y"],
  bar: ["x", "agg", "y", "limit"], stacked: ["x", "series", "agg", "y"], table: ["columns", "sort", "limit"], list: ["label", "meta", "sort", "limit"] };
export const MAX_SOURCES = 6, MAX_COMPONENTS = 12;                 // dashboards.MAX_SOURCES, MAX_COMPONENTS

// "state=open, kind=reply" <-> {state: "open", kind: "reply"}: a component's where, typed the way it reads
export const whereText = (w) => Object.entries(w || {}).map(([k, v]) => `${k}=${v}`).join(", ");
export const whereOf = (t) => {
  const o = Object.fromEntries(String(t || "").split(",").map((p) => p.split("=").map((x) => x.trim())).filter(([k, v]) => k && v));
  return Object.keys(o).length ? o : undefined;
};
// its own window: false counts what is true now, a number is a fixed window (a weekly target), nothing is the page's range
export const windowOf = (c) => (c.range === false ? "now" : c.range ? String(c.range) : "");
export const withWindow = (c, v) => { const { range: _, ...rest } = c; return v === "" ? rest : { ...rest, range: v === "now" ? false : Number(v) }; };
// a value set to nothing is a key gone, so a saved spec carries only what was chosen
export const withField = (c, k, v) => {
  const { [k]: _, ...rest } = c;
  return v === "" || v === undefined || v === null || (Array.isArray(v) && !v.length) ? rest : { ...rest, [k]: v };
};
// a preset changed keeps what every kind reads (title, source, where, window) and the aggregate when the new one takes one
export const withKind = (c, kind) => Object.fromEntries(Object.entries({ kind, title: c.title, source: c.source, where: c.where, range: c.range,
  ...(BINDS[kind]?.includes("agg") ? { agg: c.agg, y: c.y } : {}) }).filter(([, v]) => v !== undefined));
// a new source's key: the first sN no other source wears (a component names its source by key, never by its place)
export const freshKey = (srcs) => { let n = srcs.length + 1; while (srcs.some((s) => s.key === `s${n}`)) n++; return `s${n}`; };
// what the server's check would refuse, said before Save: a component reading a source that is no longer there
export const orphans = (spec) => (spec?.components || []).filter((c) => !(spec.sources || []).some((s) => s.key === c.source));
// the sources a set of rows was read from: a component edit redraws those rows, a source edit reads them again
export const sigOf = (spec) => JSON.stringify(spec?.sources || []);
