// A CLICK-ONLY BOX MADE A BUTTON FOR THE KEYBOARD (the UI audit, 2026-10-21): setup's cards, the catalogue's, the rail's and the task
// page's section heads and New's tabs were mouse-only - Tab skipped them, so setup could not be finished without a mouse. The setup
// shelf's More card was already this (FirstRun.jsx); this is that pattern once. Nothing drawn changes but the focus ring.
// `on` false (a planned card, nothing to press) gives nothing: it stays out of the Tab order.
export const pressKeys = (press) => (e) => {
  if (e.target !== e.currentTarget || !["Enter", " "].includes(e.key)) return;   // a field or button inside answers its own keys
  e.preventDefault(); press(e);
};
export const pressable = (press, on = true) => (on && press ? { role: "button", tabIndex: 0, onClick: press, onKeyDown: pressKeys(press) } : {});
export const FOCUS_RING = { "&:focus-visible": { outline: "2px solid #55697a", outlineOffset: 2 } };
