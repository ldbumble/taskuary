// WHAT HE TYPED INTO A CARD IS KEPT BY THE CARD'S REVIEW, NOT BY WHERE THE CARD IS DRAWN (the owner, 2026-11-26: "things on chat don't go
// away" - a card set down under a later turn is drawn anew there, and the words he had typed into a post were gone with the old one; 10-27:
// a look at another row lost an edited reply). One store for every card that takes his words - a reply's text, CC, BCC and subject, a
// post's words and picks, a change's boxes, his answers - the card drawn again, anywhere, reads its edit back.
// ...AND NOTHING BUT HIS OWN HAND TAKES IT BACK (the owner, 2026-11-26: "never even overwrite an edit of a text for any card"): an edit was
// held against the words it was made over, so a draft written again under it - the thread moved, the agent filed other words - dropped it,
// and the box, and his Send, went back to generated words. It is held by the review alone now, and kept on the server as he types
// (POST /api/reviews/{id}/held): there no draft is written over it, and it is read back after a reload, a restart or on another screen.
const edits = new Map(), heard = new Set(), known = new Set(), timers = new Map();
let save = null;
export const heldEdit = (id) => edits.get(id) || null;
// ...the edit the server kept for a card this page has not typed into (the review row's OwnerEdit), read once: his later taking it back
// here is never undone by a row read before that was saved
export const seedEdit = (id, stored) => {
  if (id == null || known.has(id)) return heldEdit(id);
  let e = stored;
  if (typeof e === "string") { try { e = JSON.parse(e); } catch { e = null; } }
  if (e && typeof e === "object" && Object.values(e).some((v) => v != null)) { known.add(id); edits.set(id, e); }
  return heldEdit(id);
};
// his words on review `r`'s card where he has typed any - null for a card as filed. Every surface that sends a card reads it
export const hisText = (r) => seedEdit(r?.ReviewId, r?.OwnerEdit)?.text ?? null;
// ...`part`: the fields he changed ({text}, {cc}, {vals}, ...) - null takes one back; with none left, nothing is held. Every card drawn on the
// same review hears it (onHeld), so two cards of one draft read the same
export const holdEdit = (id, part) => {
  const e = { ...(edits.get(id) || {}), ...part };
  known.add(id);
  if (Object.values(e).every((v) => v == null)) edits.delete(id); else edits.set(id, e);
  heard.forEach((f) => f(id));
  if (save) { clearTimeout(timers.get(id)); timers.set(id, setTimeout(() => flushEdit(id), 400)); }
};
export const onHeld = (f) => { heard.add(f); return () => { heard.delete(f); }; };
// ...kept on the server a moment after he stops typing, and at once where something is about to read it there (flushEdit: his own Redraft)
export const keepEdits = (f) => { save = f; };
export const unsaved = (id) => timers.has(id);
// ...and before any press on it: one that carries no words of its own (the rail's, a list's one press) sends the ones kept there
export const savedEdit = (id) => (unsaved(id) ? flushEdit(id) : undefined);
export const flushEdit = async (id) => {
  clearTimeout(timers.get(id)); timers.delete(id);
  try { await save?.(id, heldEdit(id)); } catch { /* the page still holds it, and the press carries it */ }
};
