// WHAT THE BRIDGE CAN SAY ABOUT ITSELF (2026-10-23). The card said "On - polling on schedule" from its switch, and /status said
// "connected" from an open socket, while the gate turned chats away, 1:1 chats addressed by LID vanished and the contact-name
// sync failed every ten minutes - all of it only in a log nobody reads. This keeps the few facts the card's one line needs.
// Dependency-free, like policy.mjs, so it is tested without a socket.
//
// Baileys reports app-state and decrypt failures only to its logger - resyncAppState swallows them - so `tap` listens there.

export const CONTACT_SYNC = "critical_unblock_low";      // the app-state collection that carries the owner's saved names
// libsignal's MessageCounterError (session_cipher.js doDecryptWhisperMessage): the message key for that counter is gone - spent
export const SPENT_KEY = "Key used already or never filled";

// A DECRYPT FAILURE IS NOT ONE THING (2026-11-10: a burst of "failed to decrypt message" on the owner's own @lid lines, then nothing
// came in at all). `known(key)` says the bridge already took that message, or would never take it (a chat nobody picked): WhatsApp
// handing a message over again after a dropped ack, which libsignal refuses because the key was spent on the first copy - expected,
// one debug line. Anything else is a message this computer did not get: `unreadable(key, spent)` asks for it again, and it counts
// until a readable message arrives. Many of them and nothing readable is a link that cannot read its messages (/status `unreadable`).
export function createHealth(now = () => Date.now(), { known = () => false, unreadable = () => {} } = {}) {
  const sec = () => Math.floor(now() / 1000);
  let lastInboundAt = 0, lastFailure = null, keysAt = 0;
  const contactSync = { failures: 0, at: 0, ok: 0, why: "" };
  const bad = { count: 0, since: 0, lastAt: 0 }, missed = new Set();
  const fail = (kind, detail = "") => { lastFailure = { kind, at: sec(), detail: String(detail || "").split("\n")[0].slice(0, 160) }; };
  const inbound = () => { lastInboundAt = sec(); };
  // a message read: one asked for again has come, and one with words or media ends the stretch of unreadable ones
  const arrived = (id, wrote = true) => { if (id) missed.delete(id); if (wrote) Object.assign(bad, { count: 0, since: 0 }); };

  // "quiet" when the line is a repeat of a message already taken - the caller logs it at debug instead
  const observe = (args) => {
    const [a, b] = args, msg = String(typeof a === "string" ? a : b || ""), obj = a && typeof a === "object" ? a : {};
    if (msg.startsWith("failed to sync state") && obj.name === CONTACT_SYNC) {
      contactSync.failures += 1; contactSync.at = sec();
      contactSync.why = /failed to find key/.test(String(obj.error || "")) ? "missing key" : String(obj.error || "").split("\n")[0].slice(0, 120);
      fail("contacts", contactSync.why);
    } else if (msg.startsWith(`restored state of ${CONTACT_SYNC}`) || msg.startsWith(`synced ${CONTACT_SYNC}`)) {
      Object.assign(contactSync, { failures: 0, ok: sec(), why: "" });
    } else if (msg.startsWith("injecting new app state sync keys")) keysAt = sec();
    else if (msg === "failed to decrypt message") {
      const key = obj.key || {}, why = String(obj.err?.message || obj.err || ""), spent = why.includes(SPENT_KEY);
      if (spent && known(key)) return "quiet";
      fail("decrypt", why);
      // ...counted once per message: Baileys may log one message twice (its sender-key part and its body)
      if (key.id && missed.has(key.id)) return "";
      if (key.id) { missed.add(key.id); if (missed.size > 500) missed.delete(missed.values().next().value); }
      Object.assign(bad, { count: bad.count + 1, since: bad.since || sec(), lastAt: sec() });
      try { unreadable(key, spent); } catch { /* asking again never breaks the bridge */ }
    }
    return "";
  };

  // wraps the logger's own methods in place: Baileys keeps the object it was handed, so the wrap must be on that object
  // (pino re-assigns them when its level is set - tap after any level change)
  const tap = (logger) => {
    if (!logger) return logger;
    const debug = typeof logger.debug === "function" ? logger.debug : () => {};
    for (const lvl of ["info", "warn", "error"]) {
      const f = logger[lvl];
      if (typeof f !== "function") continue;
      logger[lvl] = function (...args) {
        let said = "";
        try { said = observe(args); } catch { /* a log line never breaks the bridge */ }
        if (said === "quiet") return debug.call(this, args[0], "a message WhatsApp delivered again, already taken - its key was spent on the first copy");
        return f.apply(this, args);
      };
    }
    return logger;
  };

  const status = () => ({ lastInboundAt, lastFailure, contactSync: { ...contactSync, keysAt }, unreadable: { ...bad } });
  return { tap, observe, fail, inbound, arrived, status };
}
