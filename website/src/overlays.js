// ONE OVERLAY AT A TIME, AND TYPING LANDS WHERE HE CAN SEE IT (the 2026-11-18 walks): the search box stayed open over a page that had moved
// under it and swallowed two instructions meant for the agents; "Report this bug" sat under Search and took every word; a picture's viewer
// took "Post them..." and dropped it. Every overlay goes through here: opening one shuts the one before it, the page moving under it
// (a link opened, a task brought up) shuts it, and one with no box of its own hands a typed key to the box beneath instead of eating it.
import { useEffect, useRef } from "react";
import { onStep } from "./appLinks.js";

const OPENED = "tq-overlay-opened";
let seq = 0;
// the box he types to on the page beneath: the task's agent box in sight, else the chat's own
const BOXES = [".tq-aui-input", ".tq-compose-field textarea", ".tq-compose-field input"];
const inSight = (el) => !!el && el.getClientRects().length > 0 && !el.disabled && !el.closest(".MuiModal-root");
export const boxBeneath = (doc = document) => BOXES.map((q) => [...doc.querySelectorAll(q)].find(inSight)).find(Boolean) || null;
// a key that writes a character - never a shortcut, an arrow or Esc
export const typesText = (e) => e.key?.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey;

// `open`, `close`: the overlay's own state. `typeThrough`: it holds no box of its own (a picture, a file), so a typed key shuts it and goes
// on into the box beneath
export function useOverlay(open, close, { typeThrough = false } = {}) {
  const shut = useRef(close); shut.current = close;
  useEffect(() => {
    if (!open || typeof window === "undefined") return undefined;
    const me = ++seq;
    window.dispatchEvent(new CustomEvent(OPENED, { detail: me }));
    const other = (e) => { if (e.detail !== me) shut.current?.(); };
    const moved = () => shut.current?.();
    const key = (e) => {
      if (!typeThrough || !typesText(e) || e.target?.closest?.("input, textarea, [contenteditable=true]")) return;
      const box = boxBeneath(); if (!box) return;
      // ...focused within the keydown, so the key's own character lands in it - and again once the dialog has let go, since a closing dialog
      // gives the focus back to what opened it
      shut.current?.(); box.focus(); setTimeout(() => { if (box.isConnected && document.activeElement !== box) box.focus(); }, 320);
    };
    window.addEventListener(OPENED, other); window.addEventListener("keydown", key, true);
    const off = onStep(moved);              // ...a link, Back, the canvas moving to another place (appLinks.onStep)
    return () => { window.removeEventListener(OPENED, other); window.removeEventListener("keydown", key, true); off(); };
  }, [open, typeThrough]);
}
