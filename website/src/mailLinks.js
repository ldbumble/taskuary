// A LINK IN A MAIL IS A DOOR, not a word (TQ-1192: "the email linking the google doc is not clickable here"). Two things
// shut it: a plain-text mail writes a link as `HERE <https://docs.google.com/...>`, and cleanText's tag strip read the
// address as a tag and erased it; and the body was drawn as plain text, so even an address that survived was dead ink.
const ADDR = /https?:\/\/[^\s<>"'`]+/gi;
const TAIL = /[.,;:!?)\]]+$/;   // the sentence's own punctuation after an address is not part of it
const count = (s, c) => s.split(c).length - 1;

// `<https://...>` -> ` https://... `, so the tag strip that follows leaves the address alone
export const keepAddresses = (s) => String(s || "").replace(/<(https?:\/\/[^\s<>]+)>/gi, " $1 ");

// A LINK BEHIND WORDS: an HTML mail's "View report" button kept its words and lost its address (the owner, 2026-11-03: "hyper links in
// fyi email like view report are not coming thru"). The server keeps them beside the text (message.Links, [[words, address]] -
// channels.mail_links) and the words become that link again here, each at its first mention after the one before. Web and mail
// addresses only, whatever the row says.
const SAFE = /^(https?:\/\/|mailto:)/i;
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const wordMarks = (text, links, taken) => {
  const out = [];
  let from = 0;
  for (const [w, href] of Array.isArray(links) ? links : []) {
    if (!String(w || "").trim() || !SAFE.test(String(href || ""))) continue;
    const re = new RegExp(String(w).trim().split(/\s+/).map(esc).join("\\s+"), "g");
    re.lastIndex = from;
    const m = re.exec(text);
    if (!m || [...taken, ...out].some((t) => m.index < t.at + t.text.length && t.at < m.index + m[0].length)) continue;
    out.push({ at: m.index, href, text: m[0] }); from = m.index + m[0].length;
  }
  return out;
};

// [{text}|{href, text}] in order: what the text says, the addresses in it marked as links - and the words `links` puts a link behind
export function linkParts(s, links = []) {
  const text = String(s || ""), out = [], marks = [];
  for (const m of text.matchAll(ADDR)) {
    let href = m[0].replace(TAIL, "");
    // ...but a ")" that closes a "(" inside the address is the address's own (a wiki page's "Foo_(bar)")
    if (m[0][href.length] === ")" && count(href, "(") > count(href, ")")) href += ")";
    marks.push({ at: m.index, href, text: href });
  }
  let at = 0;
  for (const k of [...marks, ...wordMarks(text, links, marks)].sort((a, b) => a.at - b.at)) {
    if (k.at > at) out.push({ text: text.slice(at, k.at) });
    out.push({ href: k.href, text: k.text });
    at = k.at + k.text.length;
  }
  if (at < text.length) out.push({ text: text.slice(at) });
  return out;
}

// A MAIL THAT IS ONLY A PICTURE (the owner, 2026-11-03: "entire email was a image it showed nothing"): the server writes its pictures as
// stand-ins (channels._picture) - "[image: ...]" carried with the mail and drawn from its attachments, "[remote image: ...]" on the
// sender's site, which nothing here loads (Attachments.ownImage). What a card's one line says for them, and the line the open message
// says when it has no words of its own.
export const STANDIN = /\[(?:remote image|image|cid|inline image)(?::\s*([^\]]*))?\]/gi;
export const pictureWords = (s) => String(s || "").replace(STANDIN, (_, name) => (name?.trim() ? `Picture: ${name.trim()}` : "A picture"));
export const wordsOnly = (s) => String(s || "").replace(STANDIN, "").replace(/\n{3,}/g, "\n\n").trim();
export const remotePicture =(s) => /\[remote image\b/i.test(String(s || ""));
export const bareLine = ({ drawn = 0, files = 0, remote = false } = {}) => drawn ? ""
  : remote ? "This message is a picture on the sender's site, and Taskuary does not load outside pictures - open the original to see it."
  : files ? "Nothing written in this message - only what is attached."
  : "Nothing written in this message, and nothing attached came through - open the original to see it.";
