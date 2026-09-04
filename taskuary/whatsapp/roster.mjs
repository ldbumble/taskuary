// A metadata-only view of chats the paired account can currently reach. Message bodies never
// live here: the compose picker needs a JID, a useful name and recency, not a copy of WhatsApp.

const isChat = (jid) => String(jid || "").endsWith("@s.whatsapp.net")
  || String(jid || "").endsWith("@g.us");

const timestamp = (value) => {
  const n = Number(value?.toNumber ? value.toNumber() : value || 0);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
};

const contactName = (contact = {}) => String(
  contact.name || contact.verifiedName || contact.notify || ""
).trim();

export function createChatRoster() {
  const chats = new Map();
  const names = new Map();

  const ensure = (jid) => {
    jid = String(jid || "").trim();
    if (!isChat(jid)) return null;
    if (!chats.has(jid)) chats.set(jid, {
      jid, group: jid.endsWith("@g.us"), name: names.get(jid) || "", last: 0, n: 0
    });
    return chats.get(jid);
  };

  const upsertContact = (contact = {}) => {
    const name = contactName(contact);
    if (!name) return;
    for (const jid of [contact.id, contact.jid].filter(Boolean)) {
      names.set(String(jid), name);
      const row = chats.get(String(jid));
      if (row) row.name = name;
    }
  };

  const upsertChat = (chat = {}) => {
    const row = ensure(chat.id || chat.jid);
    if (!row) return;
    const name = String(chat.name || chat.subject || names.get(row.jid) || "").trim();
    if (name) row.name = name;
    row.last = Math.max(row.last, timestamp(chat.conversationTimestamp),
      timestamp(chat.lastMessageRecvTimestamp), timestamp(chat.last));
  };

  const observeMessage = (message = {}) => {
    const row = ensure(message.key?.remoteJid || message.jid);
    if (!row) return;
    const fromMe = !!(message.key?.fromMe ?? message.fromMe);
    if (!row.group && !fromMe && message.pushName) row.name = String(message.pushName).trim();
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
      if (!row.name && item.name) row.name = String(item.name).trim();
      rows.set(jid, row);
    }
    return [...rows.values()].sort((a, b) => b.last - a.last || a.name.localeCompare(b.name)
      || a.jid.localeCompare(b.jid));
  };

  return { upsertContact, upsertChat, observeMessage, remove, replaceGroups, list };
}
