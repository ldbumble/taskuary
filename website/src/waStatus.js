// THE WHATSAPP CARD TELLS THE TRUTH (2026-10-23). It said "On — polling on schedule and via Sync now." from its switch alone,
// while the bridge turned twelve chats away, never heard a 1:1 addressed by LID and failed its contact sync every ten minutes.
// This reads /wa/status (messengers.wa_status_line words the server already chose) into one short line and the one button that
// is the next step: "Connected · 2 chats · last message 40 min ago · 12 turned away", "Not connected — Restart bridge",
// "Logged out — Pair again". Pure, so the states are tested without a browser.
// ...AND THE PAIRING BOX READS THE SAME STATE (the design walk, 2026-11-20): it said "Starting the bridge..." beside "bridge not running ·
// idle", wrote step 2 in bold as "The bridge is running" while it was not, and lit Start and Restart together. waPair is the box's state,
// said once: the step it is on, the steps as things to do, one line and one button - and waLine says the same line where the card is.
export const waPair = (st) => {
  if (!st || st.unreachable) return null;
  const m = st.manager || {}, phase = m.phase || "";
  const step = st.connected ? 4 : st.bridge === false ? (st.node ? 2 : 1) : 3;
  const steps = [phase === "installing" && !st.node ? (m.detail || "Set up Node.js") : "Set up Node.js on this computer - Taskuary does it",
    phase === "installing" && st.node ? "Fetch the bridge - a minute or two, the first time only" : "Start the bridge",
    "Scan the QR from your phone"];
  if (st.bridge !== false) return { step, steps, busy: false, line: "", button: "" };
  const busy = phase === "installing" || phase === "starting";
  const line = phase === "installing" ? (st.node ? "Fetching the bridge" : m.detail || "Setting up Node.js")
    : phase === "starting" ? "Starting the bridge…"
    : phase === "failed" ? `The bridge could not start${m.detail ? `: ${m.detail}` : ""}`
    : m.held ? "The bridge is stopped and this computer is unpaired"
    : "The bridge is not running";
  // ...no button while it is busy, and none before Node is there: Taskuary sets Node up itself
  return { step, steps, busy, line, button: busy || (!st.node && phase !== "failed" && !m.held) ? "" : "start" };
};

export const waLine = (st) => {
  if (!st || st.unreachable) return null;
  if (st.bridge === false) { const p = waPair(st); return { parts: [p.line], away: 0, fix: p.button }; }
  const parts = Array.isArray(st.parts) && st.parts.length ? st.parts : [st.connected ? "Connected" : "Not connected"];
  return { parts, away: st.connected ? Number(st.turned_away) || 0 : 0, fix: st.fix ?? (st.connected ? "" : "restart") };
};
