// TALK WHILE IT WORKS (the owner's stress run, 2026-11-05): the box stays usable while the agent's turn runs. The chat's runtime takes no
// second message mid-run - Enter only put a newline in the box - so a line typed then is HELD: drawn at once as the owner's, and sent to the
// same session, which answers it as its next turn. It is drawn until the conversation the server keeps has it.
const words = (m) => (m?.content || []).filter((p) => p?.type === "text").map((p) => p.text).join("").trim();

// the line Enter holds - the box's words - or null when this key is not that (Shift+Enter, an IME, an empty box, nothing running)
export function heldLine(e, text, running) {
  if (!running || e?.key !== "Enter" || e.shiftKey || e.nativeEvent?.isComposing) return null;
  const w = String(text || "").trim();
  return w || null;
}

// the same words however the server spelled them back: spacing, line breaks, curly quotes (the owner, 2026-11-05: a dictated line stood
// twice - once as the turn's own, once still "held" at the foot - because the copy the server kept differed only in its spacing)
const same = (w) => String(w || "").replace(/[\u2018\u2019]/g, "'").replace(/[\u201c\u201d]/g, '"').replace(/\s+/g, " ").trim();

// the held lines the conversation does not have yet: `after` is how many of the owner's lines it had when the line was held, and each
// line it has since takes away one held line with the same words. A line the server has but spelled otherwise still goes: once the
// owner's lines since `after` are as many as the held lines up to this one, the conversation has them all.
export function stillHeld(held, messages) {
  const mine = (messages || []).filter((m) => m?.role === "user").map(words), used = new Set();
  return (held || []).filter((l, k) => {
    const i = mine.findIndex((w, j) => j >= (l.after || 0) && !used.has(j) && same(w) === same(l.text));
    if (i >= 0) { used.add(i); return false; }
    const since = mine.filter((w, j) => j >= (l.after || 0) && w).length;
    return since < (held || []).slice(0, k + 1).filter((x) => (x.after || 0) === (l.after || 0)).length;
  });
}
