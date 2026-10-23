// WHAT THE BRIDGE CAN SAY ABOUT ITSELF (2026-10-23). The card said "On - polling on schedule" from its switch, and /status said
// "connected" from an open socket, while the gate turned chats away, 1:1 chats addressed by LID vanished and the contact-name
// sync failed every ten minutes - all of it only in a log nobody reads. This keeps the few facts the card's one line needs.
// Dependency-free, like policy.mjs, so it is tested without a socket.
//
// Baileys reports app-state and decrypt failures only to its logger - resyncAppState swallows them - so `tap` listens there.

export const CONTACT_SYNC = "critical_unblock_low";      // the app-state collection that carries the owner's saved names

export function createHealth(now = () => Date.now()) {
  const sec = () => Math.floor(now() / 1000);
  let lastInboundAt = 0, lastFailure = null, keysAt = 0;
  const contactSync = { failures: 0, at: 0, ok: 0, why: "" };
  const fail = (kind, detail = "") => { lastFailure = { kind, at: sec(), detail: String(detail || "").split("\n")[0].slice(0, 160) }; };
  const inbound = () => { lastInboundAt = sec(); };

  const observe = (args) => {
    const [a, b] = args, msg = String(typeof a === "string" ? a : b || ""), obj = a && typeof a === "object" ? a : {};
    if (msg.startsWith("failed to sync state") && obj.name === CONTACT_SYNC) {
      contactSync.failures += 1; contactSync.at = sec();
      contactSync.why = /failed to find key/.test(String(obj.error || "")) ? "missing key" : String(obj.error || "").split("\n")[0].slice(0, 120);
      fail("contacts", contactSync.why);
    } else if (msg.startsWith(`restored state of ${CONTACT_SYNC}`) || msg.startsWith(`synced ${CONTACT_SYNC}`)) {
      Object.assign(contactSync, { failures: 0, ok: sec(), why: "" });
    } else if (msg.startsWith("injecting new app state sync keys")) keysAt = sec();
    else if (msg === "failed to decrypt message") fail("decrypt", obj.err?.message || obj.err || "");
  };

  // wraps the logger's own methods in place: Baileys keeps the object it was handed, so the wrap must be on that object
  // (pino re-assigns them when its level is set - tap after any level change)
  const tap = (logger) => {
    if (!logger) return logger;
    for (const lvl of ["info", "warn", "error"]) {
      const f = logger[lvl];
      if (typeof f !== "function") continue;
      logger[lvl] = function (...args) {
        try { observe(args); } catch { /* a log line never breaks the bridge */ }
        return f.apply(this, args);
      };
    }
    return logger;
  };

  const status = () => ({ lastInboundAt, lastFailure, contactSync: { ...contactSync, keysAt } });
  return { tap, observe, fail, inbound, status };
}
