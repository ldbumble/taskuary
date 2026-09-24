// The demo's clock. Its data was written at two moments - the recording (demoFixtures.json, stamped when it
// was dumped) and the scripted assistant (pinned to one September morning) - and read on any day after
// that, where every row said "21d ago" and the morning's work looked a month old (2026-09-23). Each set is
// moved so its own "now" is the visitor's now; what happened an hour before it still happened an hour ago.
const STAMP = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/;
const pad = (n) => String(n).padStart(2, "0");
export const parseStamp = (s) => {
  const m = STAMP.exec(String(s || ""));
  return m ? new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]).getTime() : null;
};
export const fmtStamp = (t) => {
  const d = new Date(t);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
};

// every "YYYY-MM-DD HH:MM:SS" string inside `obj`, moved by (now - anchor); a date alone is data (a report's
// day column), not a moment, and is left as it is. Mutates and returns `obj`.
export function rebase(obj, anchor, now = Date.now()) {
  const from = parseStamp(anchor);
  if (from == null) return obj;
  const delta = now - from;
  const walk = (v) => {
    if (typeof v === "string") { const t = parseStamp(v); return t == null ? v : fmtStamp(t + delta); }
    if (Array.isArray(v)) { for (let i = 0; i < v.length; i++) v[i] = walk(v[i]); return v; }
    if (v && typeof v === "object") { for (const k of Object.keys(v)) v[k] = walk(v[k]); return v; }
    return v;
  };
  return walk(obj);
}
