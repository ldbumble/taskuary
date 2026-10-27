// A DOUBLE-CLICK OPENS, IT DOES NOT OPEN AND SHUT (the overnight walk, 2026-10-27; the owner, 2026-10-26: "if you click a button twice it
// won't reload"). Ask sender, Hand it to a person, Find a time, Remind me, Share and every ▾ open a dialog or a menu over a backdrop, and
// a double-click's second click landed on that backdrop: it shut what the first had opened, and the press looked dead. A click on a
// backdrop within GRACE_MS of the last click anywhere else - the one that opened it, on the row or a menu's item - is that same press, and is swallowed before
// the page hears it. A later click on the backdrop shuts it as before.
export const GRACE_MS = 450;
// ...a dialog is shut by a click on its container (MUI Dialog), a menu or pop-over by one on its invisible backdrop
const BACKDROP = ".MuiBackdrop-root, .MuiModal-backdrop, .MuiDialog-container";
export const installSecondClick = (doc = globalThis.document, { grace = GRACE_MS } = {}) => {
  if (!doc || doc.__tqSecondClick) return () => {};
  doc.__tqSecondClick = true;
  let last = -Infinity;
  const click = (e) => {
    const el = e.target;
    if (el?.matches?.(BACKDROP)) {
      if (e.timeStamp - last < grace) { e.preventDefault(); e.stopImmediatePropagation(); }
      return;
    }
    last = e.timeStamp;
  };
  doc.addEventListener("click", click, true);
  return () => { doc.removeEventListener("click", click, true); doc.__tqSecondClick = false; };
};
