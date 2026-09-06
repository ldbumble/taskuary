// The chat connectors' fast clock, described once for every chat card (PW-003/PW-004).
// Mirrors taskuary/server.py: CHAT_CONNECTORS default to CHAT_POLL_SECONDS; poll_seconds blank =
// that default, 0 (or anything that is not a whole number) = only the background sync, and
// Background sync 0 in Settings turns this clock off as well - see server._quick_due/quick_forever.
export const CHAT_CONNECTORS = ["teams", "slack", "telegram", "whatsapp", "imessage", "discord"];
export const CHAT_POLL_SECONDS = 30;

const COVERS = {
  whatsapp: "every chat this connector brings in - not only the assistant chat; notifications ride the same clock",
  imessage: "every chat Messages.app brings in",
};

export function pollSecondsField(type) {
  if (!CHAT_CONNECTORS.includes(type)) return null;
  const covers = COVERS[type] || "every chat this connector brings in";
  return [`Check for new messages every N seconds (blank = ${CHAT_POLL_SECONDS}, 0 = background sync only)`, "poll_seconds", String(CHAT_POLL_SECONDS),
    `Covers ${covers}. All chat connectors run on this fast clock, so a slow mail sync never holds a chat back; `
    + "mail and the other connections keep the background sync interval. 0 = this connector waits for the background sync alone; "
    + "Background sync 0 in Settings turns this clock off too."];
}

// What the server will actually do with a card's saved value - the one truth the labels above describe.
export function chatClock({ type, cfg, pollMinutes }) {
  const mins = Number(pollMinutes);
  if (!(mins > 0)) return { mode: "off", seconds: 0 };
  const saved = cfg && cfg.poll_seconds != null && String(cfg.poll_seconds).trim() !== "" ? String(cfg.poll_seconds).trim() : null;
  const raw = saved ?? (CHAT_CONNECTORS.includes(type) ? String(CHAT_POLL_SECONDS) : "0");
  const secs = /^\d+$/.test(raw) ? Number(raw) : 0;
  return secs > 0 ? { mode: "fast", seconds: secs } : { mode: "background", seconds: mins * 60 };
}
