// Dependency-free policies used by bridge.mjs. Keeping these here makes the two safety
// boundaries testable without opening a WhatsApp socket: which chats Baileys may decrypt, and
// how many noisy reconnects it may attempt before a person deliberately restarts the bridge.

export const RECONNECT_DELAYS_MS = [5_000, 30_000, 2 * 60_000, 10 * 60_000];
export const STABLE_CONNECTION_MS = 5 * 60_000;

export function nextReconnect(attempt, openForMs = 0) {
  const from = openForMs >= STABLE_CONNECTION_MS ? 0 : Math.max(0, Number(attempt) || 0);
  if (from >= RECONNECT_DELAYS_MS.length) return { paused: true, attempt: from, delayMs: 0 };
  return { paused: false, attempt: from + 1, delayMs: RECONNECT_DELAYS_MS[from] };
}

// A DIRECT CHAT HAS TWO ADDRESSES (2026-10-23). WhatsApp now writes a 1:1 chat to its LID (<n>@lid) where it used to write the
// phone number (<n>@s.whatsapp.net). Only the phone form counted as a chat here, so a person written to by LID was not even
// listed as turned away - their messages vanished before decryption, and no switch in the picker could let them in.
// `user` drops the device suffix (<n>:12@...), which names one of the person's phones, not a different chat.
export const user = (jid) => {
  const [u, s] = String(jid || "").trim().split("@");
  return u && s ? `${u.split(":")[0]}@${s}` : "";
};
export const isDirect = (jid) => /@(s\.whatsapp\.net|lid)$/.test(String(jid || ""));
export const isChat = (jid) => isDirect(jid) || String(jid || "").endsWith("@g.us");
const isPn = (jid) => jid.endsWith("@s.whatsapp.net"), isLid = (jid) => jid.endsWith("@lid");

// PHONE <-> LID, as far as Baileys 6.7 tells us: contacts carrying both, group participants, a shared phone number, a message
// key's senderPn/senderLid, and onWhatsApp(number) asked outright. Memory only, rebuilt each connect - like the roster.
export function createLidMap(max = 5000) {
  const lid2pn = new Map(), pn2lid = new Map();
  const learn = (a, b) => {
    a = user(a); b = user(b);
    const [l, p] = isLid(a) ? [a, b] : [b, a];
    if (!isLid(l) || !isPn(p) || lid2pn.get(l) === p) return false;
    pn2lid.delete(lid2pn.get(l)); lid2pn.delete(pn2lid.get(p));
    lid2pn.set(l, p); pn2lid.set(p, l);
    while (lid2pn.size > max) { const [k, v] = lid2pn.entries().next().value; lid2pn.delete(k); pn2lid.delete(v); }
    return true;
  };
  const alt = (jid) => { const j = user(jid); return lid2pn.get(j) || pn2lid.get(j) || ""; };
  const pnOf = (jid) => { const j = user(jid); return isLid(j) ? lid2pn.get(j) || "" : isPn(j) ? j : ""; };
  return { learn, alt, pnOf, size: () => lid2pn.size };
}

export function createChatGate(now = () => Date.now(), lids = createLidMap()) {
  let ready = false, allDirect = false, allowed = new Set(), given = [];
  const self = new Set(), seenBlocked = new Map();

  const snapshot = () => ({ ready, allDirect, jids: [...given] });
  // the chat as the owner picked it: a person saved by phone is admitted when WhatsApp writes to their LID, and the other way round
  const allowedAs = (jid) => {
    const j = user(jid), a = lids.alt(j);
    return allowed.has(j) ? j : a && allowed.has(a) ? a : "";
  };
  const admits = (jid) => ready && (!!allowedAs(jid) || (allDirect && isDirect(user(jid))));
  // ...and what the chat is called everywhere past the gate: the picked form, else the phone number, else what WhatsApp wrote
  const canonical = (jid) => allowedAs(jid) || lids.pnOf(jid) || user(jid) || String(jid || "");
  const configure = ({ allDirect: direct = false, jids = [] } = {}) => {
    allDirect = !!direct;
    given = (Array.isArray(jids) ? jids : []).map((jid) => String(jid || "").trim()).filter(Boolean).slice(0, 500);
    allowed = new Set(given.map(user).filter(Boolean));
    ready = true;
    for (const jid of seenBlocked.keys()) if (admits(jid)) seenBlocked.delete(jid);
    return snapshot();
  };
  // THE OWNER'S OWN DEVICES ARE ALWAYS HEARD. Their phone sends the keys that decrypt the address book (app-state key shares)
  // and the other self-only protocol messages from the owner's own address - PN or, now, LID - and the gate turned those away
  // with everything else: "failed to find key ... to decode mutation" every ten minutes. What such a message says about any OTHER
  // chat - the owner typing to someone not picked - Baileys decrypts and the bridge drops (bridge.mjs onMessages: chatGate.admits).
  const setSelf = (jids = []) => {
    for (const j of jids.map(user).filter(Boolean)) { self.add(j); seenBlocked.delete(j); }
  };

  const shouldIgnore = (jid) => {
    jid = String(jid || "");
    // Baileys separately exempts this server address, but keeping it open here makes the policy
    // explicit and avoids blocking pairing/key traffic if that upstream implementation changes.
    if (!jid || jid === "@s.whatsapp.net") return false;
    const j = user(jid);
    const accepted = admits(jid) || self.has(j);
    if (!accepted && isChat(j)) {
      // Keep only routing metadata for the source picker. Baileys calls this before decrypting the
      // message, so an unapproved chat's name, text and media never enter Taskuary's bridge.
      seenBlocked.delete(j);
      seenBlocked.set(j, { jid: j, group: j.endsWith("@g.us"), last: Math.floor(now() / 1000) });
      while (seenBlocked.size > 500) seenBlocked.delete(seenBlocked.keys().next().value);
    }
    return !accepted;
  };

  // one row per chat, under the name the picker switches it on by: a LID whose number we know is that number
  const blockedChats = () => {
    const rows = new Map();
    for (const r of seenBlocked.values()) {
      if (admits(r.jid) || self.has(r.jid)) continue;
      const jid = canonical(r.jid);
      rows.set(jid, { ...r, jid, last: Math.max(r.last, rows.get(jid)?.last || 0) });
    }
    return [...rows.values()].sort((a, b) => b.last - a.last);
  };
  return { configure, shouldIgnore, snapshot, blockedChats, admits, canonical, setSelf, lids };
}

// WHICH MEDIA THE BRIDGE FETCHES. This was `if (!node || m.key.fromMe) return` inline in bridge.mjs,
// which read as "don't re-download our own outgoing media" but said "never download anything the
// owner sent" - including a voice note they left themselves. That message then reached messengers.py
// with no text and no audio and was dropped by the "one of text/audio/image/doc" rule: no task, and
// no thumbs-up, because the reaction rides on ingest (the owner, 2026-09-15: "i left voice note to
// create new task on the whatsapp channel myself but it was not picked up ... why not?").
//
// The echo it meant to skip is tracked exactly, by message id, in bridge.mjs's taskuarySent.
export const wantsMedia = (node, { echo = false } = {}) => !!node && !echo;
