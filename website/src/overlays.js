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

// ...AND A MENU IS AN OVERLAY WITH NO BOX OF ITS OWN (the walks, 2026-11-18, recorded with a real mouse and keyboard): with the Change menu
// open he clicked into the agent's box and typed - the click only shut the menu, the focus went back to Change, his words were lost on it and
// the space in them pressed Change again, the menu back over the box; typed with the menu open, its type-ahead ate every key. One road for
// every menu: a character typed into an open menu, or a click past it, shuts it and his words go on - in order, none lost - into the box he
// clicked, else the box beneath
const BOX = "input, textarea, [contenteditable=true]";
// ...AND EVERY POP-OVER WITH NO BOX OF ITS OWN IS ONE (design round 4, 2026-11-19: a line typed while the task's Chat detail was open was lost,
// nothing started): a menu is a pop-over, so the one road is the pop-over's - one whose words are typed into a box of its own keeps them
const isBox = (el) => el?.closest?.(BOX) || null;
const POP = ".MuiPopover-root";
export const menuOf = (el) => { const p = isBox(el) ? null : el?.closest?.("[role=menu], .MuiMenu-paper, .MuiPopover-paper");
  return p && !p.querySelector?.(BOX) ? p : null; };
export const typeThroughMenus = (win) => {
  if (!win || win.__tqMenusTypeThrough) return;
  win.__tqMenusTypeThrough = true;
  const doc = win.document;
  // ...held while the menu lets go: a closing menu keeps the focus, then hands it back to the button that opened it
  let held = "", busy = false, tries = 0, at = null;
  const dest = () => (at && isBox(doc.elementFromPoint(at.x, at.y))) || boxBeneath(doc);
  const settle = () => {
    const b = dest();
    if (b && (doc.querySelector(POP) || (b.focus(), doc.activeElement !== b)) && ++tries < 120) { win.requestAnimationFrame(settle); return; }
    if (b && doc.activeElement === b && held) doc.execCommand("insertText", false, held);
    held = ""; busy = false; tries = 0; at = null;
  };
  win.addEventListener("pointerdown", (e) => {
    if (busy || !e.target?.closest?.(POP) || menuOf(e.target)) return;
    busy = true; at = { x: e.clientX, y: e.clientY }; win.requestAnimationFrame(settle);
  }, true);
  win.addEventListener("keydown", (e) => {
    const menu = menuOf(e.target);
    if (!(busy || menu) || !typesText(e) || !(busy || boxBeneath(doc))) return;
    e.preventDefault(); e.stopPropagation(); held += e.key;
    if (busy) return;
    busy = true; menu.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); win.requestAnimationFrame(settle);
  }, true);
};
if (typeof window !== "undefined") typeThroughMenus(window);
