// The two facts the attachment row states, kept out of the component so they can be tested.
export const sizeText = (n) => {
  const b = Number(n) || 0;
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${Math.round(b / 1024)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
};

// A LINT, not a router. The owner may well mean "attached to my last mail", so this only ever puts
// a line on the card - the standing rule against word-matching governs what gets ROUTED, and
// nothing is routed here. It exists because a draft said "Attached are the PTO accrual files" while
// the envelope carried none, and the card looked identical either way (2026-09-14).
export const promisesFiles = (text) => /\b(attach(ed|ing|ment|ments)?|enclosed)\b/i.test(String(text || ""));
