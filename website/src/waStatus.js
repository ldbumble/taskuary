// THE WHATSAPP CARD TELLS THE TRUTH (2026-10-23). It said "On — polling on schedule and via Sync now." from its switch alone,
// while the bridge turned twelve chats away, never heard a 1:1 addressed by LID and failed its contact sync every ten minutes.
// This reads /wa/status (messengers.wa_status_line words the server already chose) into one short line and the one button that
// is the next step: "Connected · 2 chats · last message 40 min ago · 12 turned away", "Not connected — Restart bridge",
// "Logged out — Pair again". Pure, so the states are tested without a browser.
export const waLine = (st) => {
  if (!st || st.unreachable) return null;
  const phase = st.manager?.phase;
  if (st.bridge === false) return { parts: [phase === "installing" || phase === "starting" ? "Starting the bridge…" : "Not connected"], away: 0,
    fix: st.node && !["installing", "starting"].includes(phase) ? "restart" : "" };
  const parts = Array.isArray(st.parts) && st.parts.length ? st.parts : [st.connected ? "Connected" : "Not connected"];
  return { parts, away: st.connected ? Number(st.turned_away) || 0 : 0, fix: st.fix ?? (st.connected ? "" : "restart") };
};
