// A metadata-only view of chats the paired account can currently reach. Message bodies never
// live here: the compose picker needs a JID, a useful name and recency, not a copy of WhatsApp.

const isChat = (jid) => String(jid || "").endsWith("@s.whatsapp.net")
  || String(jid || "").endsWith("@g.us");

const timestamp = (value) => {
  const n = Number(value?.toNumber ? value.toNumber() : value || 0);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
};

// `name` is what the owner saved them as in their address book - the name they search by. The others
// are what the person calls themselves, and only stand in until (or unless) a saved name arrives.
const savedName = (contact = {}) => String(contact.name || "").trim();
const ownName = (contact = {}) => String(contact.verifiedName || contact.notify || "").trim();

export function createChatRoster() {
  const chats = new Map();
  const names = new Map(), saved = new Map();
  const nameOf = (jid) => saved.get(jid) || names.get(jid) || "";

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
    for (const jid of [contact.id, contact.jid].filter(Boolean).map(String)) {
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
    const rows = new Map([...chats].map(([jid, row]) => [jid, { ...row }]));
    for (const item of extra || []) {
      const jid = String(item?.jid || "").trim();
      if (!isChat(jid)) continue;
      const row = rows.get(jid) || { jid, group: jid.endsWith("@g.us"), name: "", last: 0, n: 0 };
      row.last = Math.max(row.last, timestamp(item.last));
      if (!row.name) row.name = String(item.name || nameOf(jid)).trim();
      rows.set(jid, row);
    }
    return [...rows.values()].sort((a, b) => b.last - a.last || a.name.localeCompare(b.name)
      || a.jid.localeCompare(b.jid));
  };

  return { upsertContact, upsertChat, observeMessage, remove, replaceGroups, list };
}
