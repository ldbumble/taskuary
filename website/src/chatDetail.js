// HOW MUCH OF ITS WORK A CHAT SHOWS (the owner, 2026-11-06: "for coding default tool call backs are high and low for general agents, just summary
// though the settings can be changed" - "make it setting like slider we have in other places of see all tool calls vs see summary"). Three stops:
// - summary: the agent's words and results, and its cards; its steps behind one quiet "n steps" line
// - steps: one line a step, folded - as the general chat drew them
// - everything: every tool call, its command, output and diff a press away - as the coding chat drew them
// Settings holds the two defaults (coding work, other work); each chat can say its own, kept per task on this computer (a viewer's convenience).
import { useEffect, useState } from "react";

export const LEVELS = ["summary", "steps", "everything"];
export const LABELS = { summary: "Summary", steps: "Steps", everything: "Everything" };
export const SETTING = { coding: "chat_detail_coding", other: "chat_detail_other" };
export const SHIPPED = { coding: "everything", other: "summary" };
export const asLevel = (v) => (LEVELS.includes(v) ? v : null);
const side = (source) => (source === "coding" ? "coding" : "other");
export const defaultDetail = (source, settings = {}) => asLevel(settings[SETTING[side(source)]]) || SHIPPED[side(source)];
export const detailFor = ({ source, settings = {}, own = null }) => asLevel(own) || defaultDetail(source, settings);

// ...a chat's own choice, per task, in this browser - read and written so a private window or blocked storage only loses the memory
const key = (tid) => `tq-chat-detail:${tid}`;
export function ownDetail(tid) { try { return asLevel(window.localStorage.getItem(key(tid))); } catch { return null; } }
export function keepOwnDetail(tid, v) {
  try { if (asLevel(v)) window.localStorage.setItem(key(tid), v); else window.localStorage.removeItem(key(tid)); } catch { /* not kept: the default holds */ }
  window.dispatchEvent(new CustomEvent("tq-chat-detail", { detail: { tid, level: asLevel(v) } }));
}

// ...a task's own level, following what its chat corner sets
export function useOwnDetail(tid) {
  const [own, setOwn] = useState(() => ownDetail(tid));
  useEffect(() => { setOwn(ownDetail(tid)); const f = (e) => { if (String(e.detail?.tid) === String(tid)) setOwn(e.detail.level); };
    window.addEventListener("tq-chat-detail", f); return () => window.removeEventListener("tq-chat-detail", f); }, [tid]);
  return own;
}
