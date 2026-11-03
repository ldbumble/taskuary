// The digest's tag says when it was WRITTEN: one written at 22:12 wore "MORNING DIGEST" over meetings that
// had already happened (the owner, 2026-11-02). Unknown time (not written yet) reads by the clock now.
export function digestLabel(at, now = new Date()) {
  const d = at ? new Date(String(at).replace(" ", "T")) : now, h = isNaN(d) ? now.getHours() : d.getHours();
  return h < 12 ? "MORNING DIGEST" : h < 17 ? "AFTERNOON DIGEST" : "EVENING DIGEST";
}
