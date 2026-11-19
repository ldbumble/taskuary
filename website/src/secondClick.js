// A DOUBLE-CLICK OPENS, IT DOES NOT OPEN AND SHUT (the overnight walk, 2026-10-27; the owner, 2026-10-26: "if you click a button twice it
// won't reload"). Hand it to a person, Find a time, Remind me, Share and every ▾ open a dialog or a menu over a backdrop, and
// a double-click's second click landed on that backdrop: it shut what the first had opened, and the press looked dead. A click on a
// backdrop within GRACE_MS of the last click anywhere else - the one that opened it, on the row or a menu's item - is that same press, and is swallowed before
// the page hears it. A later click on the backdrop shuts it as before.
// ...AND A SECOND CLICK NEVER PRESSES WHAT THE FIRST ONE DREW UNDER IT (the button stress, 2026-11-02): a triple-click on Not a task put the
// task down, the next one was drawn in its place, and the third click ticked a box of the next task's to-do; a double-click on Change ▾'s
// Priority opened the priority menu at the same spot and its second click picked a priority. A click at the same spot as the last one, within
// GRACE_MS, on another control than the one that click pressed - the page changed under a still pointer - is that click's repeat, swallowed.
// ...AND A CONTROL THAT CAME UNDER A STILL POINTER TAKES NO PRESS FOR ITS FIRST MOMENT (design round 4, 2026-11-19: two letters in a row - he
// pressed Send on the first, the second card drew where his press had landed, and his next press sent a letter he never read). Measured from
// when it came there, not from the last click: the next card draws when the agent has answered, seconds after the press. One rule for every
// button, card and row, wherever a press just landed - the pointer moving off the spot ends the watch.
export const GRACE_MS = 450, MOMENT_MS = 1000;
const SPOT_PX = 6;
// ...a dialog is shut by a click on its container (MUI Dialog), a menu or pop-over by one on its invisible backdrop
const BACKDROP = ".MuiBackdrop-root, .MuiModal-backdrop, .MuiDialog-container";
const CONTROL = "button, a[href], input, select, textarea, label, [role=button], [role=menuitem], [role=checkbox], [role=option], [role=tab], [role=switch]";
const controlOf = (el) => el?.closest?.(CONTROL) || null;
// ...one control still: a label and the box it clicks for the hand, a button and a control inside it
const same = (a, b) => a === b || (!!a && !!b && (a.contains?.(b) || b.contains?.(a) || a.control === b || b.control === a));
// `now`: the clock clicks are stamped on (performance.now); `watch(check)`: calls `check` whenever the page may have changed, returns its stop
const pageWatch = (doc) => (check) => {
  const MO = doc.defaultView?.MutationObserver;
  if (!MO || !doc.body) return () => {};
  const mo = new MO(check); mo.observe(doc.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled", "aria-disabled"] });
  return () => mo.disconnect();
};
export const installSecondClick = (doc = globalThis.document, { grace = GRACE_MS, moment = MOMENT_MS, now = () => globalThis.performance?.now() ?? Date.now(), watch = pageWatch(doc) } = {}) => {
  if (!doc || doc.__tqSecondClick) return () => {};
  doc.__tqSecondClick = true;
  let last = -Infinity, at = null, stop = () => {};
  const swallow = (e) => { e.preventDefault(); e.stopImmediatePropagation(); };
  // what is under the pressed spot, pressable, and since when: a control that comes there - or comes alive there - is new
  const live = (c) => !!c && !c.disabled && c.getAttribute?.("aria-disabled") !== "true";
  const look = () => {
    if (!at) return;
    const c = controlOf(doc.elementFromPoint?.(at.x, at.y));
    if (c !== at.under || live(c) !== at.alive) Object.assign(at, { under: c, alive: live(c), since: now() });
  };
  const leave = (e) => { if (at && (Math.abs(e.clientX - at.x) > SPOT_PX || Math.abs(e.clientY - at.y) > SPOT_PX)) { stop(); stop = () => {}; at = null; } };
  const click = (e) => {
    const el = e.target, soon = e.timeStamp - last < grace;
    if (el?.matches?.(BACKDROP)) {
      if (soon) swallow(e);
      return;
    }
    // ...the same spot, another control: what the first click drew under the pointer a moment ago, or what came there since and is still new
    if (at && e.isTrusted !== false && Math.abs(e.clientX - at.x) <= SPOT_PX && Math.abs(e.clientY - at.y) <= SPOT_PX) {
      const c = controlOf(el);
      if (c && !same(c, at.control) && (soon || (look(), same(c, at.under) && now() - at.since < moment))) { swallow(e); return; }
    }
    last = e.timeStamp;
    stop();
    const c = controlOf(el);
    at = { x: e.clientX, y: e.clientY, control: c, under: c, alive: live(c), since: -Infinity };
    stop = watch(look);
  };
  doc.addEventListener("click", click, true);
  doc.addEventListener("pointermove", leave, true);
  // ...and the page scrolled under the still pointer brings another control there as surely as a new one drawn
  doc.addEventListener("scroll", look, true);
  return () => { stop(); doc.removeEventListener("click", click, true); doc.removeEventListener("pointermove", leave, true); doc.removeEventListener("scroll", look, true); doc.__tqSecondClick = false; };
};
