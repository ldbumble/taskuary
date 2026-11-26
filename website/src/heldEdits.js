// WHAT HE TYPED INTO A CARD IS KEPT BY THE CARD'S REVIEW, NOT BY WHERE THE CARD IS DRAWN (the owner, 2026-11-26: "things on chat don't go
// away" - a card set down under a later turn is drawn anew there, and the words he had typed into a post were gone with the old one; 10-27:
// a look at another row lost an edited reply). One store for every card that takes his words - a reply's text, CC, BCC and subject, a
// post's words and picks, a change's boxes - for as long as the page is open: the card drawn again, anywhere, reads its edit back.
// An edit is held against the words it was made over (`filed`): once the card is filed with other words, it is an edit of something else.
const edits = new Map(), heard = new Set();
export const heldEdit = (id, filed) => { const e = edits.get(id); return e && e.filed === filed ? e : null; };
// ...`part`: the fields he changed ({text}, {cc}, {vals}, ...) - null takes one back; with none left, nothing is held. Every card drawn on the
// same review hears it (onHeld), so two cards of one draft read the same
export const holdEdit = (id, filed, part) => {
  const { filed: _was, ...kept } = heldEdit(id, filed) || {}, e = { ...kept, ...part };
  if (Object.values(e).every((v) => v == null)) edits.delete(id); else edits.set(id, { ...e, filed });
  heard.forEach((f) => f(id));
};
export const onHeld = (f) => { heard.add(f); return () => { heard.delete(f); }; };
