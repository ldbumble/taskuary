// What the "Report this bug" popup knows about the client side: the last error and the last few writes.
// Pure (no DOM) so it can be tested; the app calls record/recordAction from its axios interceptors.
// Only the SHAPE of a call is kept (ids normalised, query dropped) - the server scrubs the rest again.
const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);
let err = null, acts = [];

export const normPath = (u) => String(u || "").split(/[?#]/)[0].split("/").map((s) => (/^\d+$/.test(s) || /^[0-9a-f]{32}$/i.test(s) ? ":id" : s)).join("/");

export function recordAction(method, url) {
  const m = String(method || "").toUpperCase();
  if (!m || SAFE.has(m)) return;
  acts = [...acts, `${m} ${normPath(url)}`].slice(-5);
}

export function record(e) {
  const url = e?.config?.url, status = e?.response?.status, d = e?.response?.data?.detail;
  let message = typeof e === "string" ? e : e?.message || String(e);
  if (d) message += ` (${status ? status + ": " : ""}${typeof d === "string" ? d : JSON.stringify(d)})`;
  else if (status) message += ` (${status})`;
  err = { message: message.slice(0, 2000), stack: String(e?.stack || "").slice(0, 4000), route: url ? normPath(url) : "", at: new Date().toISOString() };
}

export const last = () => err;
export const reset = () => { err = null; acts = []; };
export const snapshot = (screen) => ({ screen, route: err?.route || "", error: err?.message || "", stack: err?.stack || "", actions: [...acts], at: err?.at || "" });
