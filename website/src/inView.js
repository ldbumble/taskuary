// A LIT MOVE IS ONE THE OWNER CAN SEE (the Advisor matrix's phone pass, 2026-10-20): scrollIntoView({block: "nearest"}) put a
// refused send's Redraft at the foot of a 390px screen - in view by its box, and under the phone's docked strip and row, so the line
// said "redraft it" over a button nobody could press. What covers the move is read off the screen (elementFromPoint), never assumed,
// and the scrollers around it move it clear: the card's own first, then the conversation's.

// the box over `el` that holds its place while the page scrolls under it (sticky or fixed), else the element that was hit
export const coverOf = (hit, el, style = (e) => getComputedStyle(e)) => {
  for (let e = hit; e && e !== el && e.nodeType === 1; e = e.parentElement) if (/sticky|fixed/.test(style(e).position)) return e;
  return hit;
};
// how far the content must scroll for `r` (the move) to clear `c` (what covers it), with a gap: up past a cover standing in the
// screen's lower half - a dock - (+), down from under one in its upper half - a pinned head - (-). Read off the screen, not off the
// move: a 275px dock's middle stood above the Redraft at its foot, and the move was sent down off the screen
export const shiftFor = (r, c, vh, gap = 8) => (c.top + c.height / 2 >= vh / 2 ? Math.ceil(r.bottom - c.top + gap) : -Math.ceil(c.bottom - r.top + gap));
// the lowest a held move may stand in a scroller: above the sticky dock a phone's view carries inside it (CanvasItem .tq-docked)
export const floorOf = (body, el) => {
  const b = body.getBoundingClientRect(), dock = el?.querySelector?.(".tq-docked")?.getBoundingClientRect();
  return dock && dock.height && dock.top < b.bottom ? Math.min(b.bottom, dock.top) : b.bottom;
};

export function bringIntoView(el) {
  if (!el?.getBoundingClientRect || typeof document === "undefined") return;
  el.scrollIntoView?.({ block: "nearest" });
  for (let i = 0; i < 3; i++) {                 // a dock below, a pinned head above - each read again after the last move
    const r = el.getBoundingClientRect(), hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    if (!hit || el.contains(hit)) return;
    let d = shiftFor(r, coverOf(hit, el).getBoundingClientRect(), window.innerHeight);
    // the nearest scroller takes what it can (a card scrolls 56px), the one around it the rest - instant, not the conversation's smooth
    // scroll, so what each took is read back at once (a smooth one read back nothing, and the rest went to boxes that do not scroll)
    for (let p = el.parentElement; p && Math.abs(d) >= 1; p = p.parentElement) {
      if (!/auto|scroll/.test(getComputedStyle(p).overflowY)) continue;
      const was = p.scrollTop; p.scrollTo({ top: was + d, behavior: "instant" }); d -= p.scrollTop - was;
    }
  }
}
// ...and HELD clear while the screen settles around it: the dock grows when its line and row fill in after the move lit, and a move
// scrolled clear a frame early stood 4px under it again (the matrix's phone pass, 2026-10-20). Each frame for `ms`, until the owner
// scrolls, types or presses - then where it stands is theirs (appLinks.focusPlace holds a named place the same way).
const OWNER = ["wheel", "touchmove", "keydown", "pointerdown"];
export function holdInView(el, ms = 1500) {
  if (!el || typeof window === "undefined" || !window.requestAnimationFrame) return () => {};
  const t0 = Date.now();
  let on = true, f = 0;
  const stop = () => { on = false; cancelAnimationFrame(f); OWNER.forEach((e) => window.removeEventListener(e, stop, true)); };
  OWNER.forEach((e) => window.addEventListener(e, stop, true));
  const tick = () => { if (!on || !el.isConnected || Date.now() - t0 > ms) return stop(); bringIntoView(el); f = requestAnimationFrame(tick); };
  f = requestAnimationFrame(tick);
  return stop;
}
