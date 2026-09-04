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

const isDirect = (jid) => String(jid || "").endsWith("@s.whatsapp.net");
const isChat = (jid) => isDirect(jid) || String(jid || "").endsWith("@g.us");

export function createChatGate(now = () => Date.now()) {
  let ready = false, allDirect = false, allowed = new Set();
  const seenBlocked = new Map();

  const snapshot = () => ({ ready, allDirect, jids: [...allowed] });
  const configure = ({ allDirect: direct = false, jids = [] } = {}) => {
    allDirect = !!direct;
    allowed = new Set((Array.isArray(jids) ? jids : [])
      .map((jid) => String(jid || "").trim()).filter(Boolean).slice(0, 500));
    ready = true;
    for (const jid of seenBlocked.keys()) {
      if (allowed.has(jid) || (allDirect && isDirect(jid))) seenBlocked.delete(jid);
    }
    return snapshot();
  };

  const shouldIgnore = (jid) => {
    jid = String(jid || "");
    // Baileys separately exempts this server address, but keeping it open here makes the policy
    // explicit and avoids blocking pairing/key traffic if that upstream implementation changes.
    if (!jid || jid === "@s.whatsapp.net") return false;
    const accepted = ready && (allowed.has(jid) || (allDirect && isDirect(jid)));
    if (!accepted && isChat(jid)) {
      // Keep only routing metadata for the source picker. Baileys calls this before decrypting the
      // message, so an unapproved chat's name, text and media never enter Taskuary's bridge.
      seenBlocked.delete(jid);
      seenBlocked.set(jid, { jid, group: jid.endsWith("@g.us"), last: Math.floor(now() / 1000) });
      while (seenBlocked.size > 500) seenBlocked.delete(seenBlocked.keys().next().value);
    }
    return !accepted;
  };

  const blockedChats = () => [...seenBlocked.values()].sort((a, b) => b.last - a.last);
  return { configure, shouldIgnore, snapshot, blockedChats };
}
