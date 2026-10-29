// Taskuary's own markers, out of what the owner reads (selfclose.for_screen on the server). A task that saved its progress before the
// server stripped them still drew the reply block, and the answer twice (2026-10-15).
const REPLY = /\[\[\s*TASKUARY[-_ ]?REPLY\s*\]\][\s\S]*?\[\[\s*\/\s*TASKUARY[-_ ]?REPLY\s*\]\]/gi;
const LINE = /^[ \t]*\[\[\s*TASKUARY[-_ ]?(?:ATTACH|ASK)\b[^\n]*\n?/gim;
// ...and the done line: its sentence is filed as a comment (or is the answer), and left in it kept dropEcho from seeing the echo (walk 2026-10-29)
const DONE = /[ \t]*\[\[\s*TASKUARY[-_ ]?DONE\s*\]\][^\n]*/gi;
export const forScreen = (text) => String(text || "").replace(REPLY, "").replace(LINE, "").replace(DONE, "").trim();

// ...and a progress line that only says what the answer says: a CLI's final text streams in as progress too, so the box repeated
// the answer under it (2026-10-15). A box with nothing left goes.
const flat = (s) => String(s || "").split(/\s+/).join(" ").trim();
export const dropEcho = (parts) => {
  const said = flat(parts.filter((p) => p.type === "text").map((p) => p.text).join(" "));
  if (!said) return parts;
  return parts.flatMap((p) => {
    if (p.type !== "reasoning") return [p];
    const keep = String(p.text || "").split(/\n{2,}/).filter((l) => { const f = flat(forScreen(l)); return f && !said.includes(f); });
    return keep.length ? [{ ...p, text: keep.join("\n\n") }] : [];
  });
};
