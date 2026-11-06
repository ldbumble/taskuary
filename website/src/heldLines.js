// TALK WHILE IT WORKS (the owner's stress run, 2026-11-05): the box stays usable while the agent's turn runs. The chat's runtime takes no
// second message mid-run - Enter only put a newline in the box - so a line typed then is HELD: drawn at once as the owner's, and sent to the
// same session, which answers it as its next turn. It is drawn until the conversation the server keeps has it.
// ...the OWNER'S words only: a brief is Taskuary's (general.BRIEF_ACTOR - `brief` from the server, metadata.custom.brief in the thread), and counted as
// theirs it took a held line away before the server had it
const words = (m) => m?.brief || m?.metadata?.custom?.brief ? "" : (m?.content || []).filter((p) => p?.type === "text").map((p) => p.text).join("").trim();

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
// `at`: which count the line was held after - `after`, the server's conversation; `drawn`, the thread on screen (notShown)
export function stillHeld(held, messages, at = "after") {
  const mine = (messages || []).filter((m) => m?.role === "user").map(words), used = new Set(), from = (l) => l[at] || 0;
  return (held || []).filter((l, k) => {
    const i = mine.findIndex((w, j) => j >= from(l) && !used.has(j) && same(w) === same(l.text));
    if (i >= 0) { used.add(i); return false; }
    const since = mine.filter((w, j) => j >= from(l) && w).length;
    return since < (held || []).slice(0, k + 1).filter((x) => from(x) === from(l)).length;
  });
}

// ...AND NEVER BESIDE ITS OWN BUBBLE (the owner, 2026-11-06: one line, a "You" bubble and again under the agent's first step): a line typed while
// the agent asked takes the answer's road - appended to the thread, which draws it as the turn's own - and held, it stood at the foot as well
// until the server filed it. A held line is drawn only while the thread on screen does not draw it; `drawn`: its owner's lines at the hold
export const notShown = (held, thread) => stillHeld(held, thread, "drawn");
