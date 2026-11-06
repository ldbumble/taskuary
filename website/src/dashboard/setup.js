// A DASHBOARD'S SPEC, AS A PERSON EDITS IT (DashboardEditor.jsx): its sources' small conversions, and its tiles - each ONE sentence the
// owner writes (the owner, 2026-11-06: "maybe we should just use text to say what it shows"), turned into a tile by the AI on the
// server (POST /api/dashboards/tile, compose.compose_tile). Pure - test/dashboardSetup.test.mjs holds it.
export const MAX_SOURCES = 8, MAX_COMPONENTS = 18;                 // dashboards.MAX_SOURCES, MAX_COMPONENTS

// a value set to nothing is a key gone, so a saved spec carries only what was chosen
export const withField = (c, k, v) => {
  const { [k]: _, ...rest } = c;
  return v === "" || v === undefined || v === null || (Array.isArray(v) && !v.length) ? rest : { ...rest, [k]: v };
};

// ── a tile is its sentence: the server fills one in for a tile saved before (dashboards.with_said); its title stands in until then
export const saidOf = (c) => String(c?.said || c?.title || "").trim();
// Enter or leaving the line draws it - only when the words changed and say something (the same words are the same tile)
export const wantsDrawing = (text, c) => { const t = String(text || "").trim(); return !!t && t !== saidOf(c); };
// what the server is asked: the dashboard as it stands (its sources are what a sentence binds to), the words, the tile they rewrite
export const tileAsk = (spec, said, current) => ({ config: { type: "dashboard", title: spec?.title || "", sources: spec?.sources || [] },
  said: String(said || "").trim(), ...(current ? { current } : {}) });
// the answer lands on the tile that was asked about, wherever it has been dragged meanwhile - and on none if it was removed
export const swapTile = (comps, was, now) => comps.map((x) => (x === was ? now : x));
export const copyTile = (comps, i) => (comps.length >= MAX_COMPONENTS ? comps : [...comps.slice(0, i + 1), { ...comps[i] }, ...comps.slice(i + 1)]);
export const moveTile = (comps, from, to) => {
  if (from === to || from < 0 || to < 0 || from >= comps.length || to >= comps.length) return comps;
  const n = [...comps]; const [m] = n.splice(from, 1); n.splice(to, 0, m); return n;
};
// a new source's key: the first sN no other source wears (a component names its source by key, never by its place)
export const freshKey = (srcs) => { let n = srcs.length + 1; while (srcs.some((s) => s.key === `s${n}`)) n++; return `s${n}`; };
// A SOURCE'S `key` IS ITS OWN NAME here, and an S3 source's executor reads a `key` of its own (the object path): on a dashboard that
// field is `object_key` (dashboards.OWN_KEYS), and the card's field and its Test are pointed at it - a report's S3 card is untouched
export const OWN_KEYS = { s3_object: { key: "object_key" } };
const pathLike = (v) => /[/.]/.test(String(v || ""));
// what the executor is handed (dashboards.run_cfg): the name dropped, a renamed field put back - and a path an older save kept in `key`
export const runCfg = (s) => {
  const { key, ...out } = s, own = OWN_KEYS[s.type]?.key;
  if (!own) return out;
  const { [own]: path, ...rest } = out, p = path || (pathLike(key) ? key : "");
  return p ? { ...rest, key: p } : rest;
};
// what the server's check would refuse, said before Save: a component reading a source that is no longer there
export const orphans = (spec) => (spec?.components || []).filter((c) => !(spec.sources || []).some((s) => s.key === c.source));
// the sources a set of rows was read from: a component edit redraws those rows, a source edit reads them again
export const sigOf = (spec) => JSON.stringify(spec?.sources || []);
