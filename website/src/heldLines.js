// TALK WHILE IT WORKS (the owner's stress run, 2026-11-05): the box stays usable while the agent's turn runs. The chat's runtime takes no
// second message mid-run - Enter only put a newline in the box - so a line typed then is HELD: drawn at once as the owner's, and sent to the
// same session, which answers it as its next turn. It is drawn until the conversation the server keeps has it.
// ...the OWNER'S words only: a brief is Taskuary's (general.BRIEF_ACTOR - `brief` from the server, metadata.custom.brief in the thread), and counted as
// theirs it took a held line away before the server had it
// ...nor a PRESS drawn as their line (general.press_lines, "You set a reminder for ..."): no held line is it
const words = (m) => m?.brief || m?.metadata?.custom?.brief || m?.press || m?.metadata?.custom?.press ? "" : (m?.content || []).filter((p) => p?.type === "text").map((p) => p.text).join("").trim();

// the line Enter holds - the box's words - or null when this key is not that (Shift+Enter, an IME, an empty box, nothing running)
export function heldLine(e, text, running) {
  if (!running || e?.key !== "Enter" || e.shiftKey || e.nativeEvent?.isComposing) return null;
  const w = String(text || "").trim();
  return w || null;
}

// the same words however the server spelled them back: spacing, line breaks, curly quotes (the owner, 2026-11-05: a dictated line stood
// twice - once as the turn's own, once still "held" at the foot - because the copy the server kept differed only in its spacing)
const same = (w) => String(w || "").replace(/[\u2018\u2019]/g, "'").replace(/[\u201c\u201d]/g, '"').replace(/\s+/g, " ").trim();

// THE NAME THE PAGE GAVE A LINE IT SENT (the spine audit, 2026-11-09): sent with the line (`line_id`), kept on it and on the turn it becomes
// (general.wait_line), and echoed on both (`line`; metadata.custom.line in the thread). A line was known by its words and by counting, so
// one from another window or the phone retired a held line the server did not have yet, and "ok" sent twice stood once
const lineOf = (m) => m?.line || m?.metadata?.custom?.line || "";

// the held lines the conversation does not have yet. A line sent under its name (`named`) is the conversation's when the conversation has
// that name, and by nothing else. A road with no names - the coding CLI's, an answer to the agent's ask - reads as before, among the lines
// no page named: `after` is how many of the owner's lines the conversation had when the line was held, and each line it has since takes
// away one held line with the same words. A line the server has but spelled otherwise still goes: once the owner's unnamed lines since
// `after` are as many as the unnamed held lines up to this one, the conversation has them all.
// `at`: which count the line was held after - `after`, the server's conversation; `drawn`, the thread on screen (notShown)
export function stillHeld(held, messages, at = "after") {
  const all = (messages || []).filter((m) => m?.role === "user"), names = new Set(all.map(lineOf).filter(Boolean));
  const mine = all.map((m) => (lineOf(m) ? "" : words(m))), used = new Set(), from = (l) => l[at] || 0, loose = (held || []).filter((l) => !l.named);
  return (held || []).filter((l) => {
    if (l.named) return !names.has(l.id);
    const i = mine.findIndex((w, j) => j >= from(l) && !used.has(j) && same(w) === same(l.text));
    if (i >= 0) { used.add(i); return false; }
    const since = mine.filter((w, j) => j >= from(l) && w).length;
    return since < loose.slice(0, loose.indexOf(l) + 1).filter((x) => from(x) === from(l)).length;
  });
}

// ...AND NEVER BESIDE ITS OWN BUBBLE (the owner, 2026-11-06: one line, a "You" bubble and again under the agent's first step): a line typed while
// the agent asked takes the answer's road - appended to the thread, which draws it as the turn's own - and held, it stood at the foot as well
// until the server filed it. A held line is drawn only while the thread on screen does not draw it; `drawn`: its owner's lines at the hold
export const notShown = (held, thread) => stillHeld(held, thread, "drawn");

// THE LINES THE SERVER KEPT FOR THE AGENT (general.waiting_lines, the owner 2026-11-07): saved the moment they were sent, so every screen draws
// them - another tab's, the phone's, this page reloaded - with the time each was typed, until a turn takes them. Not where this screen draws the
// same words already: a line it held itself, or its thread's own copy of a line it streamed
// ...BY ITS NAME where it has one (lineOf): this page's own held line is the kept line that carries its name, and no other - two windows
// that each sent "ok" both draw both. A kept line with no name (the thread's own first line, streamed) is this screen's by its words, and
// each of this screen's copies stands for ONE kept line: the words were a set, so "ok" kept twice drew once, or not at all
// ...and a coding chat's held line (not `named`: its conversation never echoes the name) is sent under its id all the same: the kept copy that
// carries it is that line, and it stands for no other (the browser walk, 2026-11-10: a line typed after a coding session ended stood twice)
export function waitingShown(waiting, held, thread, messages) {
  const kept = (messages || []).filter((m) => m?.role === "user").length, ids = new Set((held || []).map((l) => l.id));
  const tagged = new Set((waiting || []).map((w) => w.line).filter(Boolean));
  const own = [...(held || []).filter((l) => !l.named && !tagged.has(l.id)).map((l) => same(l.text)), ...(thread || []).filter((m) => m?.role === "user").slice(kept).filter((m) => !lineOf(m)).map((m) => same(words(m)))];
  return (waiting || []).filter((w) => {
    if (w.line) return !ids.has(w.line);
    const i = own.indexOf(same(w.text));
    if (i >= 0) own.splice(i, 1);
    return i < 0;
  });
}
