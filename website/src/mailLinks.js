// A LINK IN A MAIL IS A DOOR, not a word (TQ-1192: "the email linking the google doc is not clickable here"). Two things
// shut it: a plain-text mail writes a link as `HERE <https://docs.google.com/...>`, and cleanText's tag strip read the
// address as a tag and erased it; and the body was drawn as plain text, so even an address that survived was dead ink.
const ADDR = /https?:\/\/[^\s<>"'`]+/gi;
const TAIL = /[.,;:!?)\]]+$/;   // the sentence's own punctuation after an address is not part of it
const count = (s, c) => s.split(c).length - 1;

// `<https://...>` -> ` https://... `, so the tag strip that follows leaves the address alone
export const keepAddresses = (s) => String(s || "").replace(/<(https?:\/\/[^\s<>]+)>/gi, " $1 ");

// [{text}|{href, text}] in order: what the text says, the addresses in it marked as links
export function linkParts(s) {
  const text = String(s || ""), out = [];
  let at = 0;
  for (const m of text.matchAll(ADDR)) {
    let href = m[0].replace(TAIL, "");
    // ...but a ")" that closes a "(" inside the address is the address's own (a wiki page's "Foo_(bar)")
    if (m[0][href.length] === ")" && count(href, "(") > count(href, ")")) href += ")";
    if (m.index > at) out.push({ text: text.slice(at, m.index) });
    out.push({ href, text: href });
    at = m.index + href.length;
  }
  if (at < text.length) out.push({ text: text.slice(at) });
  return out;
}
