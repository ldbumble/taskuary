// WHAT THIS INSTALL CAN DO (GET /api/capabilities, computed by ONE function on the server - taskuary/capabilities.py):
//   {coding, ai, mail, send: {<channel>: bool}}
// coding exists only where a coding tool is connected (the owner, 2026-10-16: "if no cli tool like cloud api tools no coding"), the
// Advisor and the connect line ask `ai`, a reply's Send asks send[channel]. Every screen reads it here, never its own guess.
// Asked once; asked again when setup moves or the live feed says something changed (a connection made there brings its buttons
// back). Until the answer is in, everything shows - a coder never loses the button to a slow read.
import { useEffect, useState } from "react";
import api from "./api";
import { onLive } from "./live.js";
import { covers, seqOf } from "./liveSeq.js";

export const ASSUMED = { coding: true, ai: true, mail: true, send: {}, known: false };
let asked = null, last = ASSUMED, seen = null;      // seen: the write stamp the answer in hand was read at (liveSeq.js)
const subs = new Set();
const read = (data) => ({ ...ASSUMED, ...(data || {}), send: { ...(data?.send || {}) }, known: !!data });
export const capabilities = () => (asked ||= api.get("/api/capabilities").then((res) => { seen = seqOf(res); return (last = read(res.data)); })
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
// AN AGENT THAT CANNOT START IS GREYED, its reason in the hover (the owner, 2026-10-22: never pressable into a failure) - ONE check for
// both roads: general work needs an AI (this capability, or /api/agents' general_brains once read), coding a coding tool (R3,
// agents.coding_ready). '' when it can start; Connect an AI stays the lit move (the Advisor's strip)
export const NO_AI_WHY = "No AI is connected - connect one first";
export const NO_CODING_TOOL = "Pick a coding tool first";
// ...the coding road asks only its tool: a coding agent runs its own CLI with no AI connected, and greying it on `ai` left the
// owner nothing to press where the coding agent would have worked (the dead-end walk's nocli/badrepo faults, 2026-10-22)
export const cannotStart = (caps, { coding = false, read = false, brains = [], codingReady = true } = {}) =>
  coding ? (read && !codingReady ? NO_CODING_TOOL : "") : caps?.ai === false || (read && !brains.length) ? NO_AI_WHY : "";
export function refreshCapabilities() {
  asked = null;
  return capabilities().then((c) => { subs.forEach((f) => f(c)); return c; });
}
if (typeof window !== "undefined") {
  window.addEventListener?.("tq-setup-changed", () => { refreshCapabilities(); });
  // a connection made or dropped lands as feed/task events: one re-read after the burst, never one per row - nor one for a burst the
  // answer in hand was already read after (its write stamps, liveSeq.js: the start's own writes, the load-once pass 2026-10-27)
  try { onLive(["feed-changed", "task-changed"], (ev, meta) => { if (!covers(seen, meta)) refreshCapabilities(); }, { wait: 4000, max: 30000 }); }
  catch { /* no live socket here */ }
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
