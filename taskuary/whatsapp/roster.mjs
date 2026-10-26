// A metadata-only view of chats the paired account can currently reach. Message bodies never
// live here: the compose picker needs a JID, a useful name and recency, not a copy of WhatsApp.

import { isChat } from "./policy.mjs";      // a LID (<n>@lid) is a direct chat too

const timestamp = (value) => {
  const n = Number(value?.toNumber ? value.toNumber() : value || 0);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
};

// `name` is what the owner saved them as in their address book - the name they search by. The others
// are what the person calls themselves, and only stand in until (or unless) a saved name arrives.
const savedName = (contact = {}) => String(contact.name || "").trim();
const ownName = (contact = {}) => String(contact.verifiedName || contact.notify || "").trim();

// `canon` and `alt` come from the bridge's phone<->LID map (policy.mjs createLidMap): one person written to by LID and saved by
// number is ONE row under the number - the form a person source is saved by - and carries the name saved under either.
export function createChatRoster({ canon = (jid) => jid, alt = () => "" } = {}) {
  const chats = new Map();
  const names = new Map(), saved = new Map();
  const nameOf = (jid) => saved.get(jid) || saved.get(alt(jid)) || names.get(jid) || names.get(alt(jid)) || "";

  const ensure = (jid) => {
    jid = String(jid || "").trim();
    if (!isChat(jid)) return null;
    if (!chats.has(jid)) chats.set(jid, {
      jid, group: jid.endsWith("@g.us"), name: nameOf(jid), last: 0, n: 0
    });
    return chats.get(jid);
  };

  // A SAVED CONTACT IS A CHAT YOU CAN PICK, whether or not it has written since the bridge started:
  // with no history downloaded, a person used to appear only once they wrote, and then as a bare
  // number - so search by their name found nobody and only the phone number did (2026-10-21).
  // A profile name alone never adds a row: every participant of every group carries one.
  const upsertContact = (contact = {}) => {
    const name = savedName(contact), own = ownName(contact);
    for (const jid of [...new Set([contact.id, contact.jid, contact.lid].filter(Boolean).map(String))]) {
      if (name) saved.set(jid, name);
      else if (own) names.set(jid, own);
      else continue;
      const row = name && !jid.endsWith("@g.us") ? ensure(jid) : chats.get(jid);
      if (row) row.name = nameOf(jid);
    }
  };

  const upsertChat = (chat = {}) => {
    const row = ensure(chat.id || chat.jid);
    if (!row) return;
    // HOW MANY PEOPLE ARE IN IT. WhatsApp gives the owner's own "Message yourself" thread a legacy
    // GROUP jid - <their number>-<when it was made>@g.us - and gives every group they CREATED the
    // same shape, so the number prefix cannot tell the two apart. A real group called "Jogging" was
    // being offered as the assistant's private chat (2026-09-17). groupFetchAllParticipating already
    // hands us the participant list; it was simply thrown away here. Absent stays absent, so an
    // older roster reads as "unknown" rather than as "nobody".
    if (Array.isArray(chat.participants)) row.people = chat.participants.length;
    const name = String((!row.group && saved.get(row.jid)) || chat.name || chat.subject || names.get(row.jid) || "").trim();
    if (name) row.name = name;
    row.last = Math.max(row.last, timestamp(chat.conversationTimestamp),
      timestamp(chat.lastMessageRecvTimestamp), timestamp(chat.last));
  };

  const observeMessage = (message = {}) => {
    const row = ensure(message.key?.remoteJid || message.jid);
    if (!row) return;
    const fromMe = !!(message.key?.fromMe ?? message.fromMe);
    if (!row.group && !fromMe && message.pushName && !saved.has(row.jid)) row.name = String(message.pushName).trim();
    row.last = Math.max(row.last, timestamp(message.messageTimestamp || message.ts));
    row.n += 1;
  };

  // THE NAME ON THE ENVELOPE (2026-10-26). The owner: "the whatsapp contacts people tab are still not searchable by name as
  // well". The address book never arrives on an account whose app-state key went missing (contact sync failing every ten
  // minutes, a name on 1 person row of 78), and a chat the owner has not picked is turned away before decryption - so its
  // messages' push names were never seen either, and every person row was a bare number. WhatsApp writes the sender's own
  // push name in clear on the message stanza (`notify`), beside who sent it; that name - only the name, never a body - names
  // the person's row, the way a saved contact would. Like a profile name it never adds a row, and the owner's own is skipped.
  const observeStanza = (attrs = {}, isSelf = () => false) => {
    const from = String(attrs.from || ""), notify = String(attrs.notify || "").trim();
    const who = String((from.endsWith("@g.us") ? attrs.participant : from) || "");
    if (!notify || !isChat(who) || who.endsWith("@g.us") || isSelf(who)) return;
    upsertContact({ id: who, jid: attrs.participant_pn || attrs.sender_pn, lid: attrs.participant_lid || attrs.sender_lid, notify });
  };

  const remove = (jids = []) => {
    for (const jid of jids || []) chats.delete(String(jid || ""));
  };

  const replaceGroups = (groups = []) => {
    const current = new Set((groups || []).map((group) => String(group?.id || group?.jid || ""))
      .filter((jid) => jid.endsWith("@g.us")));
    for (const jid of chats.keys()) if (jid.endsWith("@g.us") && !current.has(jid)) chats.delete(jid);
    for (const group of groups || []) upsertChat(group);
  };

  const list = (extra = []) => {
    const rows = new Map();
    const into = (raw, item) => {
      const jid = canon(raw) || raw, had = rows.get(jid);
      const row = had || { ...item, jid, group: jid.endsWith("@g.us"), name: String(item.name || "").trim(), last: 0, n: 0 };
      row.last = Math.max(row.last, timestamp(item.last));
      row.n += Number(item.n) || 0;
      if (!row.name) row.name = String(item.name || nameOf(raw) || nameOf(jid)).trim();
      rows.set(jid, row);
    };
    for (const [jid, row] of chats) into(jid, row);
    for (const item of extra || []) {
      const jid = String(item?.jid || "").trim();
      if (isChat(jid)) into(jid, { last: item.last, name: item.name });
    }
    // two rows made one: the name the owner saved wins over the one a LID row carried in from a push name
    for (const r of rows.values()) if (!r.group && (saved.get(r.jid) || saved.get(alt(r.jid)))) r.name = saved.get(r.jid) || saved.get(alt(r.jid));
    return [...rows.values()].sort((a, b) => b.last - a.last || a.name.localeCompare(b.name)
      || a.jid.localeCompare(b.jid));
  };

  return { upsertContact, upsertChat, observeMessage, observeStanza, remove, replaceGroups, list };
}
