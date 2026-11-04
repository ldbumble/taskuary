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
const json = (s) => { try { return JSON.parse(s || "null") || {}; } catch { return {}; } };

// THREE NAMED, TWO RIDE (2026-11-04): an agent's draft said "here are the three" and the card showed two chips and nothing more - the third,
// over the mailbox's cap, was refused in a comment under the agent's pane. Each file kept on the envelope as not attached (verdicts.refused)
// is said by name and why; with none kept, a draft that names more files than ride says the count. None attached at all is the card's own line.
export const filesShort = (r, files = []) => {
  const no = (json(r?.Deliver).not_attached || []).filter((f) => f && f.name);
  if (no.length) return no.map((f) => `Not attached: ${f.name} — ${String(f.why || "it could not be attached").replace(/\.$/, "")}.`);
  const named = json(r?.FilesPromised).named, n = Array.isArray(named) ? named.length : 0;
  return files.length && n > files.length ? [`The draft names ${n} files and ${files.length} ${files.length === 1 ? "is" : "are"} attached.`] : [];
};
