// THE ADVISOR'S LINE DURING SETUP (the owner, 2026-10-15: "remember advisor is what tells you what to do next always. it's missing
// from here"): what setup says next is drawn where the Advisor always speaks - the bar over the row's buttons (AssistantView's dock),
// not as a line on the canvas. FirstRun writes it; the dock reads it.
import { useSyncExternalStore } from "react";

let line = "";
const subs = new Set();
export const writeSetupLine = (text) => { const t = String(text || ""); if (t === line) return; line = t; subs.forEach((f) => f()); };
export const useSetupLine = () => useSyncExternalStore((f) => { subs.add(f); return () => subs.delete(f); }, () => line);
