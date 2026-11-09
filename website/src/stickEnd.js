// A CHAT OPENS AT ITS END AND STAYS THERE WHILE IT SETTLES (the owner, 2026-11-09: a coding task opened in the middle of its agent's
// transcript). It was placed once at the top of the newest turn - for a coding turn that is the top of its long list of steps ("Read 3 files",
// "Searched files for ...") - and the steps, loading in above, moved it on. Now: the end, held through every growth of what is drawn, until the
// owner scrolls, presses or types in it, or nothing has moved for `settle` ms. The newest ANSWER still shows from its first line when it is
// taller than the view (the owner, 2026-10-18: "I can't see any of the agent output without scrolling") - the answer, not the turn's steps.
export const endTop = (v, said) => {
  const bottom = Math.max(0, v.scrollHeight - v.clientHeight);
  if (!said) return bottom;
  const at = said.getBoundingClientRect().top - v.getBoundingClientRect().top + v.scrollTop - 8;
  return Math.max(0, Math.min(bottom, Math.round(at)));
};

// the owner's own moves in the chat let go of it - a press on a fold to read it too, which grows the chat under them
export const OWN = ["wheel", "touchstart", "keydown", "pointerdown"];

// `target(v)` says where its end is now; returns the cleanup. Never fights the owner: the first move of theirs ends it for good.
export function stickToEnd(v, target, { settle = 1500, most = 10000 } = {}) {
  if (!v) return () => {};
  let quiet = null, done = false;
  const place = () => { if (done) return; const t = target(v); if (Math.abs(v.scrollTop - t) > 1) v.scrollTop = t; clearTimeout(quiet); quiet = setTimeout(stop, settle); };
  const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(place);
  const watch = () => { if (!ro) return; ro.disconnect(); ro.observe(v); [...v.children].forEach((c) => ro.observe(c)); };
  const mo = typeof MutationObserver === "undefined" ? null : new MutationObserver(() => { watch(); place(); });
  const cap = setTimeout(() => stop(), most);
  function stop() {
    if (done) return; done = true;
    clearTimeout(quiet); clearTimeout(cap); ro?.disconnect(); mo?.disconnect(); OWN.forEach((e) => v.removeEventListener(e, stop));
  }
  OWN.forEach((e) => v.addEventListener(e, stop, { passive: true }));
  watch(); mo?.observe(v, { childList: true, subtree: true }); place();
  return stop;
}
