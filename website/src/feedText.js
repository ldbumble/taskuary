// What a timeline row says beyond who sent it. Pure string work, deliberately out of the
// view so it can be tested without a browser - the prefix rules are easy to get subtly wrong.

// Teams chats get a synthesized "<sender> in <source>" subject - redundant next to the
// sender + source we already show, so drop it. Reports stamp the title as from, source AND
// the start of the subject, which read "Morning digest · Morning digest — Morning digest — …".
// Chat is not mail. WhatsApp and Slack send no subject at all, and Teams synthesizes one from the
// people already named in the row ("Teams chat with Hindy Spiegel"), so the row read as a sender and
// nothing else while the work pill said "(no subject)". What was SAID is the title, one line, cut on
// a word to fit the pill (owner, 2026-09-07).
const CHAT_TITLE = /^((teams|slack|whatsapp|telegram)\s+)?(group\s+)?(chat|conversation)\s+with\b/i;
const PILL = 90;
export const said = (r) => {
  const line = String(r.Preview || r.BodyText || "").split("\n").map((l) => l.trim()).find(Boolean) || "";
  const one = line.replace(/\s+/g, " ");
  return one.length <= PILL ? one : one.slice(0, PILL).replace(/\s\S*$/, "") + "…";
};

export const subjectOf = (r) => {
  const s = r.Subject || "";
  if (!s || s === `${r.FromName} in ${r.SourceName}` || CHAT_TITLE.test(s)) return said(r);
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
