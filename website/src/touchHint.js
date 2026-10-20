// HINTS ON A LONG PRESS (owner-approved, 2026-10-20). A hint is a mouse's: on a touch screen a tap opened a tooltip over the drawer it
// had just opened (2026-10-19 UI walk), so the theme turned them off for touch - and with them every hint a phone had, the `title`s
// included, which a touch screen never shows. A finger held still on a control for HOLD_MS now shows that control's hint, and the
// press is a question, not a press: the click its release would fire is swallowed. A tap is a tap, exactly as before.
export const HOLD_MS = 500, SLOP = 10, SHOW_MS = 1800;
const NOT = "input, textarea, select, [contenteditable=''], [contenteditable='true'], .xterm";
// the words: a titled element's title, else a control's own name (MUI's Tooltip hands a string title to its child as aria-label)
export const hintOf = (el) => {
  if (!el?.closest || el.closest(NOT)) return "";
  const h = el.closest("[title]") || el.closest("button[aria-label], a[aria-label], [role='button'][aria-label], [role='option'][aria-label]");
  return h ? String(h.getAttribute("title") || h.getAttribute("aria-label") || "").trim() : "";
};
// where the bubble goes: above the finger, kept on the screen
export const placeHint = (at, w, h, vw) => {
  const left = Math.max(8, Math.min(vw - w - 8, at.x - w / 2)), above = at.y - h - 28;
  return { left, top: above >= 8 ? above : at.y + 28 };
};
export const installTouchHints = (doc = globalThis.document, { hold = HOLD_MS, timers = globalThis } = {}) => {
  if (!doc || doc.__tqTouchHints) return () => {};
  doc.__tqTouchHints = true;
  let timer = 0, gone = 0, at = null, shown = null, swallow = false;
  const hide = () => { timers.clearTimeout(gone); shown?.remove(); shown = null; };
  const cancel = () => { timers.clearTimeout(timer); timer = 0; at = null; };
  const show = (text, p) => {
    const el = doc.createElement("div");
    el.className = "tq-touch-hint"; el.setAttribute("role", "tooltip"); el.textContent = text;
    Object.assign(el.style, { position: "fixed", zIndex: "2000", maxWidth: "min(320px, calc(100vw - 16px))", background: "#262521", color: "#fff",
      font: "500 12px 'IBM Plex Sans', system-ui, sans-serif", lineHeight: "1.4", borderRadius: "6px", padding: "6px 10px", pointerEvents: "none" });
    doc.body.appendChild(el);
    const r = el.getBoundingClientRect?.() || { width: 0, height: 0 }, pos = placeHint(p, r.width, r.height, doc.defaultView?.innerWidth || 360);
    el.style.left = `${pos.left}px`; el.style.top = `${pos.top}px`;
    shown = el; swallow = true;
  };
  const on = {
    pointerdown: (e) => {
      hide(); cancel(); swallow = false;
      if (e.pointerType !== "touch") return;
      const text = hintOf(e.target);
      if (!text) return;
      const p = { x: e.clientX, y: e.clientY };
      at = p; timer = timers.setTimeout(() => { timer = 0; show(text, p); }, hold);
    },
    pointermove: (e) => { if (at && Math.hypot(e.clientX - at.x, e.clientY - at.y) > SLOP) cancel(); },
    pointerup: () => { cancel(); if (shown) gone = timers.setTimeout(hide, SHOW_MS); },
    pointercancel: () => { cancel(); if (shown) gone = timers.setTimeout(hide, SHOW_MS); },
    // ...the release of a held press fires no button, and the browser's own long-press menu does not open over the hint
    click: (e) => { if (!swallow) return; swallow = false; e.preventDefault(); e.stopPropagation(); },
    contextmenu: (e) => { if (shown || timer) e.preventDefault(); },
    scroll: () => { cancel(); hide(); },
  };
  for (const [k, f] of Object.entries(on)) doc.addEventListener(k, f, true);
  return () => { cancel(); hide(); doc.__tqTouchHints = false; for (const [k, f] of Object.entries(on)) doc.removeEventListener(k, f, true); };
};
