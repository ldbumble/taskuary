// The chat connectors' fast clock, described once for every chat card (PW-003/PW-004).
// Mirrors taskuary/server.py: CHAT_CONNECTORS default to CHAT_POLL_SECONDS; poll_seconds blank =
// that default, and 0 disables this recurring fast poll. Other explicit/startup fetch paths remain
// available; Background sync 0 in Settings turns both recurring clocks off.
export const CHAT_CONNECTORS = ["teams", "slack", "telegram", "whatsapp", "imessage", "discord"];
export const CHAT_POLL_SECONDS = 30;

const COVERS = {
  whatsapp: "inbound messages from every chat this connector brings in - not only the assistant chat; replies in the notification chat are polled too, while sending notifications is event-driven",
  imessage: "every chat Messages.app brings in",
};

export function pollSecondsField(type) {
  if (!CHAT_CONNECTORS.includes(type)) return null;
  const covers = COVERS[type] || "every chat this connector brings in";
  return [`Check for new messages every N seconds (blank = ${CHAT_POLL_SECONDS}, 0 = no fast polling)`, "poll_seconds", String(CHAT_POLL_SECONDS),
    `Covers ${covers}. This recurring fast clock is separate from the full background-sync clock. `
    + `Blank uses ${CHAT_POLL_SECONDS} seconds. 0 disables this fast poll; recurring background sync can still poll the connector, `
    + "and manual Sync now, action-time freshness checks, and startup catch-up can still fetch it. "
    + "Background sync 0 in Settings disables both recurring clocks; explicit and startup fetches remain available."];
}
