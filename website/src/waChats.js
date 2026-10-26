// A WhatsApp chat is found by WHO it is - the person's name, their phone number, the group's name - never by its JID (the
// owner, 2026-10-23: "search should be by phone number, name or group name not id's. you can show id's in small under").
// The server's twin is taskuary/wanames.py; the rows arrive named and with `phone` from it.

// ...a LID (<n>@lid) too: WhatsApp addresses most 1:1 chats by one now, and it is no more searchable than any other id (2026-10-26)
export const isWaJid = (s) => /@(s\.whatsapp\.net|g\.us|lid)$/.test(String(s || ""));
export const isWaGroup = (s) => String(s || "").endsWith("@g.us");
const digits = (s) => String(s || "").replace(/\D/g, "");
const fold = (s) => String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLocaleLowerCase();

// the number in a person's JID - a group's id is not a number anyone has
export const waNumber = (jid) => /^(\d+)(?::\d+)?@s\.whatsapp\.net$/.exec(String(jid || ""))?.[1] || "";
export function fmtPhone(n) {
  const d = digits(n);
  if (!d) return "";
  return d.length === 11 && d[0] === "1" ? `+1 ${d.slice(1, 4)}-${d.slice(4, 7)}-${d.slice(7)}` : `+${d}`;
}
export const waPhone = (jid) => fmtPhone(waNumber(jid));

// no name, or the chat's own number/id standing in for one
export function bareName(name, jid) {
  const n = String(name || "").trim(), num = waNumber(jid);
  return !n || n === jid || n === String(jid || "").split("@")[0] || (!!num && digits(n) === num && !/[^\d\s+()\-.]/.test(n));
}

// what the chat is called on screen: its name, else its number, else a group nobody has named yet
export const waLabel = (jid, name = "") => (bareName(name, jid) ? waPhone(jid) || (isWaGroup(jid) ? "WhatsApp group" : String(jid || "")) : name);

export const isPhoneQuery = (q) => digits(q).length >= 3 && !/[^\d\s+()\-./]/.test(String(q || "").trim());

// The query against the name and the phone number - never the JID. Digits and punctuation are a phone number in whatever form
// it was typed: +1 (555) 010-0123, 0015550100123 and 555 0100 all find the same person.
export function waMatches(q, jid, name = "") {
  q = String(q || "").trim();
  if (!q) return true;
  const num = waNumber(jid);
  if (isPhoneQuery(q)) {
    const d = digits(q);
    return !!num && [d, d.startsWith("00") ? d.slice(2) : "", d.replace(/^0+/, "")].some((x) => x && num.includes(x));
  }
  const hay = fold(`${bareName(name, jid) ? "" : name} ${fmtPhone(num)}`);
  return q.split(/\s+/).every((w) => hay.includes(fold(w)));
}
