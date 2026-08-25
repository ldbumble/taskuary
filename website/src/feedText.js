// What a timeline row says beyond who sent it. Pure string work, deliberately out of the
// view so it can be tested without a browser - the prefix rules are easy to get subtly wrong.

// Teams chats get a synthesized "<sender> in <source>" subject - redundant next to the
// sender + source we already show, so drop it. Reports stamp the title as from, source AND
// the start of the subject, which read "Morning digest · Morning digest — Morning digest — …".
export const subjectOf = (r) => {
  const s = r.Subject || "";
  if (s === `${r.FromName} in ${r.SourceName}`) return "";
  const who = String(r.FromName || "").trim();
  if (!who || !s.toLowerCase().startsWith(who.toLowerCase())) return s;
  // ONLY when a separator follows. Slicing on a bare prefix match ate real words: sender
  // "Bob" turned "Bobby's numbers" into "by's numbers", "CI" turned "CID lookup failing"
  // into "D lookup failing", and "Sam needs the invoice" lost its subject to a stray dash.
  const rest = s.slice(who.length);
  return /^\s*[—–:·-]/.test(rest) ? rest.replace(/^\s*[—–:·-]+\s*/, "") : s;
};

// The source earns a chip only when it says something the sender did not.
export const sourceOf = (r) => {
  const src = r.SourceName || "";
  const who = r.FromName || r.FromEmail || "";
  return src && src !== who ? src : "";
};
