// WHAT THIS INSTALL CAN DO (GET /api/capabilities, computed by ONE function on the server - taskuary/capabilities.py):
//   {coding, ai, mail, send: {<channel>: bool}}
// coding exists only where a coding tool is connected (the owner, 2026-10-16: "if no cli tool like cloud api tools no coding"), the
// Advisor and the connect line ask `ai`, a reply's Send asks send[channel]. Every screen reads it here, never its own guess.
// Asked once; asked again when setup moves or the live feed says something changed (a connection made there brings its buttons
// back). Until the answer is in, everything shows - a coder never loses the button to a slow read.
import { useEffect, useState } from "react";
import api from "./api";
import { onLive } from "./live.js";

export const ASSUMED = { coding: true, ai: true, mail: true, send: {}, known: false };
let asked = null, last = ASSUMED;
const subs = new Set();
const read = (data) => ({ ...ASSUMED, ...(data || {}), send: { ...(data?.send || {}) }, known: !!data });
export const capabilities = () => (asked ||= api.get("/api/capabilities").then(({ data }) => (last = read(data)))
  .catch(() => { asked = null; return last; }));
// a channel the server has not named can send: only an explicit false hides a Send
export const canSend = (caps, channel) => !channel || caps?.send?.[String(channel).toLowerCase()] !== false;
// ...where a screen holds only a row's snapshot of that same channel answer: the live one once it is in, the row's until then
export const channelCanSend = (caps, channel, rowSays) => (caps?.known ? canSend(caps, channel) : rowSays !== false);
// ...and ONE DRAFT's: its channel asked here, AND the row's own CanSend, which knows more than the channel (a draft with nobody to
// go to; an invoice, which leaves by its own road and asks no channel)
export const draftCanSend = (caps, r) => {
  if (!r || r.CanSend === false) return false;
  let env = {};
  try { env = JSON.parse(r.Deliver || "{}") || {}; } catch { /* not an envelope */ }
  return env.kind === "zoho_invoice" || env.kind === "calendar" || canSend(caps, r.Channel || env.channel);   // outbound.OWN_ROAD
};
export function refreshCapabilities() {
  asked = null;
  return capabilities().then((c) => { subs.forEach((f) => f(c)); return c; });
}
if (typeof window !== "undefined") {
  window.addEventListener?.("tq-setup-changed", () => { refreshCapabilities(); });
  // a connection made or dropped lands as feed/task events: one re-read after the burst, never one per row
  try { onLive(["feed-changed", "task-changed"], () => { refreshCapabilities(); }, { wait: 4000, max: 30000 }); } catch { /* no live socket here */ }
}

export function useCapabilities() {
  const [caps, setCaps] = useState(last);
  useEffect(() => {
    let on = true;
    const set = (c) => on && setCaps(c);
    subs.add(set); capabilities().then(set);
    return () => { on = false; subs.delete(set); };
  }, []);
  return caps;
}
export const useCoding = () => useCapabilities().coding !== false;
