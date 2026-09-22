// What a timeline row says beyond who sent it. Pure string work, deliberately out of the
// view so it can be tested without a browser - the prefix rules are easy to get subtly wrong.

// Teams chats get a synthesized "<sender> in <source>" subject - redundant next to the
// sender + source we already show, so drop it. Reports stamp the title as from, source AND
// the start of the subject, which read "Morning digest · Morning digest — Morning digest — …".
// Chat is not mail. WhatsApp and Slack send no subject at all, and Teams synthesizes one from the
// people already named in the row ("Teams chat with Gail Moreno"), so the row read as a sender and
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

// A GENERATED body - a report's error summary, the assistant's own note - is written as structure:
// a lead, then a list. The Summary pane ran the whole thing through one flattening clamp, so the
// list arrived mashed into the sentence as a wall of run-on text. Split it so the pane can draw the
// list as a list. A body with NO list comes back untouched: a mail's "Hi Alex," followed by a blank
// line is a greeting, not a summary, and re-cutting on that would hide the actual question.
const BULLET = /^[-•*]\s+/;
export const structured = (body) => {
  const text = String(body || "");
  const lines = text.split("\n");
  const at = lines.findIndex((l) => BULLET.test(l.trim()));
  if (at < 0) return { lead: text, bullets: [] };
  return {
    lead: lines.slice(0, at).join("\n").trim(),
    bullets: lines.slice(at).map((l) => l.trim()).filter((l) => BULLET.test(l))
      .map((l) => l.replace(BULLET, "").trim()),
  };
};
