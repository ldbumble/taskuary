// The chat connectors' fast clock, described once for every chat card (PW-003/PW-004).
// Mirrors taskuary/server.py: CHAT_CONNECTORS default to CHAT_POLL_SECONDS; poll_seconds blank =
// that default, and 0 disables this recurring fast poll. Other explicit/startup fetch paths remain
// available; Background sync 0 in Settings turns both recurring clocks off.
export const CHAT_CONNECTORS = ["teams", "slack", "telegram", "whatsapp", "imessage", "discord"];
export const CHAT_POLL_SECONDS = 30;
export const POLL_KEY = "poll_seconds";

// ONE SHORT LINE (the setup sweep, 2026-10-28): the label was cut off on the card and its five-line hint led Credentials, before the
// token. The card draws it under Advanced, after the token (ConnectorsView, isPollField); Settings' Background sync help says the rest
export function pollSecondsField(type) {
  if (!CHAT_CONNECTORS.includes(type)) return null;
  return ["Check for new messages every (seconds)", POLL_KEY, String(CHAT_POLL_SECONDS),
    `Blank = ${CHAT_POLL_SECONDS}; 0 = no fast check (background sync and Sync now still read it).`];
}
export const isPollField = (f) => f?.[1] === POLL_KEY;
