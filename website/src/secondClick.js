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
// ...AND A PRESS LANDS ON THE BUTTON THE POINTER WENT DOWN ON (the owner, 2026-11-26: "most buttons on our app you have to click twice for it to
// go?"). The browser gives a click only to what is under the pointer at BOTH ends of the press, and a page that moves in between - the Ask box
// opening at the pointer going down, its up-arrow rising a line; a box that shrinks as it loses the focus; the day filling in over a row of
// buttons - leaves the release on something else: no click reached the button, nothing happened, and he pressed again. A hand that went down
// on a button and came up where it went down pressed that button, wherever the page has since put it: the stray click is taken and the
// button is given it. A hand that moved off before letting go still cancels, and a button gone, greyed or hidden by then is not pressed.
export const GRACE_MS = 450, MOMENT_MS = 1000;
const SPOT_PX = 6;
// ...a dialog is shut by a click on its container (MUI Dialog), a menu or pop-over by one on its invisible backdrop
const BACKDROP = ".MuiBackdrop-root, .MuiModal-backdrop, .MuiDialog-container";
const CONTROL = "button, a[href], input, select, textarea, label, [role=button], [role=menuitem], [role=checkbox], [role=option], [role=tab], [role=switch]";
const controlOf = (el) => el?.closest?.(CONTROL) || null;
// ...and WHAT IT PRESSES: the card a control stands in (data-tq-review) - the next letter's card can be drawn in the same element as the one
// just sent (the Hydrogen walk, 2026-11-19: Send stayed one button, at 477,702 then 477,703, and his second press sent Erin's letter)
const cardOf = (c) => c?.closest?.("[data-tq-review]")?.getAttribute?.("data-tq-review") || "";
// ...one control still: a label and the box it clicks for the hand, a button and a control inside it
const same = (a, b) => a === b || (!!a && !!b && (a.contains?.(b) || b.contains?.(a) || a.control === b || b.control === a));
// `now`: the clock clicks are stamped on (performance.now); `watch(check)`: calls `check` whenever the page may have changed, returns its stop
const pageWatch = (doc) => (check) => {
  const MO = doc.defaultView?.MutationObserver;
  if (!MO || !doc.body) return () => {};
  const mo = new MO(check); mo.observe(doc.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled", "aria-disabled", "data-tq-review"] });
  return () => mo.disconnect();
};
export const installSecondClick = (doc = globalThis.document, { grace = GRACE_MS, moment = MOMENT_MS, now = () => globalThis.performance?.now() ?? Date.now(), watch = pageWatch(doc) } = {}) => {
  if (!doc || doc.__tqSecondClick) return () => {};
  doc.__tqSecondClick = true;
  let last = -Infinity, at = null, stop = () => {}, down = null;
  const ours = new WeakSet();
  const swallow = (e) => { e.preventDefault(); e.stopImmediatePropagation(); };
  // what is under the pressed spot, pressable, and since when: a control that comes there - or comes alive there - is new
  const live = (c) => !!c && !c.disabled && c.getAttribute?.("aria-disabled") !== "true";
  const look = () => {
    if (!at) return;
    const c = controlOf(doc.elementFromPoint?.(at.x, at.y));
    if (c !== at.under || live(c) !== at.alive || cardOf(c) !== at.card) Object.assign(at, { under: c, alive: live(c), card: cardOf(c), since: now() });
  };
  const near = (e, p) => Math.abs(e.clientX - p.x) <= SPOT_PX && Math.abs(e.clientY - p.y) <= SPOT_PX;
  const leave = (e) => { if (at && !near(e, at)) { stop(); stop = () => {}; at = null; } };
  const drawn = (c) => !c.getClientRects || c.getClientRects().length > 0;
  // ...`fresh`: it came under the pressed spot a moment ago - read as the pointer goes down, while it still stands there
  const press = (e) => {
    const c = e.isTrusted === false || e.button ? null : controlOf(e.target);
    down = c ? { control: c, x: e.clientX, y: e.clientY, fresh: !!at && near(e, at) && (look(), same(c, at.under) && now() - at.since < moment) } : null;
  };
  const click = (e) => {
    if (ours.has(e)) return;
    const d = down; down = null;
    // ...the button moved from under a still pointer: this click is the browser's, on whatever holds both ends of the press
    const moved = !!d && e.isTrusted !== false && !same(controlOf(e.target), d.control) && near(e, d) && d.control.isConnected !== false && live(d.control) && drawn(d.control);
    const el = moved ? d.control : e.target, soon = e.timeStamp - last < grace;
    if (el?.matches?.(BACKDROP)) {
      if (soon) swallow(e);
      return;
    }
    // ...the same spot, another control: what the first click drew under the pointer a moment ago, or what came there since and is still new
    if (at && e.isTrusted !== false && near(e, at)) {
      const c = controlOf(el);
      const other = c && (!same(c, at.control) || cardOf(c) !== at.pressed);
      if (other && (soon || (moved ? d.fresh : (look(), same(c, at.under) && now() - at.since < moment)))) { swallow(e); return; }
    }
    last = e.timeStamp;
    stop();
    const c = controlOf(el);
    at = { x: e.clientX, y: e.clientY, control: c, under: c, alive: live(c), card: cardOf(c), pressed: cardOf(c), since: -Infinity };
    stop = watch(look);
    if (!moved) return;
    // ...judged above as a press of that button; now given to it, where the hand made it
    swallow(e);
    const view = doc.defaultView || globalThis;
    const again = new view.MouseEvent("click", { bubbles: true, cancelable: true, composed: true, view: doc.defaultView || null, detail: 1, clientX: e.clientX, clientY: e.clientY,
      screenX: e.screenX, screenY: e.screenY, ctrlKey: e.ctrlKey, shiftKey: e.shiftKey, altKey: e.altKey, metaKey: e.metaKey });
    ours.add(again); d.control.dispatchEvent(again);
  };
  doc.addEventListener("pointerdown", press, true);
  doc.addEventListener("click", click, true);
  doc.addEventListener("pointermove", leave, true);
  // ...and the page scrolled under the still pointer brings another control there as surely as a new one drawn
  doc.addEventListener("scroll", look, true);
  return () => { stop(); doc.removeEventListener("pointerdown", press, true); doc.removeEventListener("click", click, true); doc.removeEventListener("pointermove", leave, true); doc.removeEventListener("scroll", look, true); doc.__tqSecondClick = false; };
};
