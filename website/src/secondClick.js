// A DOUBLE-CLICK OPENS, IT DOES NOT OPEN AND SHUT (the overnight walk, 2026-10-27; the owner, 2026-10-26: "if you click a button twice it
// won't reload"). Hand it to a person, Find a time, Remind me, Share and every ▾ open a dialog or a menu over a backdrop, and
// a double-click's second click landed on that backdrop: it shut what the first had opened, and the press looked dead. A click on a
// backdrop within GRACE_MS of the last click anywhere else - the one that opened it, on the row or a menu's item - is that same press, and is swallowed before
// the page hears it. A later click on the backdrop shuts it as before.
// ...AND A SECOND CLICK NEVER PRESSES WHAT THE FIRST ONE DREW UNDER IT (the button stress, 2026-11-02): a triple-click on Not a task put the
// task down, the next one was drawn in its place, and the third click ticked a box of the next task's to-do; a double-click on Change ▾'s
// Priority opened the priority menu at the same spot and its second click picked a priority. A click at the same spot as the last one, within
// GRACE_MS, on another control than the one that click pressed - the page changed under a still pointer - is that click's repeat, swallowed.
export const GRACE_MS = 450;
const SPOT_PX = 6;
// ...a dialog is shut by a click on its container (MUI Dialog), a menu or pop-over by one on its invisible backdrop
const BACKDROP = ".MuiBackdrop-root, .MuiModal-backdrop, .MuiDialog-container";
const CONTROL = "button, a[href], input, select, textarea, label, [role=button], [role=menuitem], [role=checkbox], [role=option], [role=tab], [role=switch]";
const controlOf = (el) => el?.closest?.(CONTROL) || null;
// ...one control still: a label and the box it clicks for the hand, a button and a control inside it
const same = (a, b) => a === b || (!!a && !!b && (a.contains?.(b) || b.contains?.(a) || a.control === b || b.control === a));
export const installSecondClick = (doc = globalThis.document, { grace = GRACE_MS } = {}) => {
  if (!doc || doc.__tqSecondClick) return () => {};
  doc.__tqSecondClick = true;
  let last = -Infinity, at = null;
  const swallow = (e) => { e.preventDefault(); e.stopImmediatePropagation(); };
  const click = (e) => {
    const el = e.target, soon = e.timeStamp - last < grace;
    if (el?.matches?.(BACKDROP)) {
      if (soon) swallow(e);
      return;
    }
    // ...the same spot, a moment later, another control: what the first click drew under the pointer, not what the hand meant
    if (soon && at && e.isTrusted !== false && Math.abs(e.clientX - at.x) <= SPOT_PX && Math.abs(e.clientY - at.y) <= SPOT_PX) {
      const now = controlOf(el);
      if (now && !same(now, at.control)) { swallow(e); return; }
    }
    last = e.timeStamp;
    at = { x: e.clientX, y: e.clientY, control: controlOf(el) };
  };
  doc.addEventListener("click", click, true);
  return () => { doc.removeEventListener("click", click, true); doc.__tqSecondClick = false; };
};
