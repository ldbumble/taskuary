// The two facts the attachment row states, kept out of the component so they can be tested.
export const sizeText = (n) => {
  const b = Number(n) || 0;
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${Math.round(b / 1024)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
};

// WHETHER THE DRAFT PROMISES A FILE is its writer's word, kept on the review (responder.FILES -> review.FilesPromised, JSON
// {"named": [...]}) - never a word list run over the text here (the owner, 2026-10-28). It only ever puts a line on the card: the
// owner may well mean "attached to my last mail". A draft said "Attached are the PTO accrual files" while the envelope carried none,
// and the card looked identical either way (2026-09-14).
export const filesPromised = (r) => {
  try { return !!JSON.parse(r?.FilesPromised || "null"); } catch { return false; }
};
