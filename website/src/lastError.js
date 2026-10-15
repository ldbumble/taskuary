// What the "Report this bug" popup knows about the client side: the last error and the last few writes.
// Pure (no DOM) so it can be tested; the app calls record/recordAction from its axios interceptors.
// Only the SHAPE of a call is kept (ids normalised, query dropped) - the server scrubs the rest again.
const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);
let err = null, acts = [];
// the popup's own calls: a refused draft recorded as "the last error" would be the next report's subject
const SELF = /\/api\/(bug-report\/|open-url)/;

// Ids, uuids, hashes and repo slugs identify someone's data; the verbs and nouns of the route are what a maintainer needs.
const ID = /^(\d+|[0-9a-f]{8,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i;
export function normPath(u) {
  let p = String(u || "").split(/[?#]/)[0]; const k = p.indexOf("/api/"); if (k > 0) p = p.slice(k);
  const s = p.split("/"), r = s.indexOf("repos");
  return s.map((x, i) => (ID.test(x) || (r >= 0 && (i === r + 1 || i === r + 2) && x) ? ":id" : x)).join("/");
}

export function recordAction(method, url) {
  const m = String(method || "").toUpperCase();
  if (!m || SAFE.has(m) || SELF.test(String(url || ""))) return;
  acts = [...acts, `${m} ${normPath(url)}`].slice(-5);
}

export function record(e) {
  const url = e?.config?.url;
  if (SELF.test(String(url || ""))) return;
  const status = e?.response?.status, d = e?.response?.data?.detail;
  let message = typeof e === "string" ? e : e?.message || String(e);
  if (d) message += ` (${status ? status + ": " : ""}${typeof d === "string" ? d : jsonOr(d)})`;
  else if (status) message += ` (${status})`;
  err = { message: message.slice(0, 2000), stack: String(e?.stack || "").slice(0, 4000), route: url ? normPath(url) : "", at: new Date().toISOString() };
}

const jsonOr = (d) => { try { return JSON.stringify(d); } catch { return String(d); } };
export const last = () => err;
export const reset = () => { err = null; acts = []; };
export const snapshot = (screen) => ({ screen, route: err?.route || "", error: err?.message || "", stack: err?.stack || "", actions: [...acts], at: err?.at || "" });
