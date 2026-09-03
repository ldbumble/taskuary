// Polls that exist to keep a visible screen honest should not run while the window is
// in the background. The Studio animation clock still ticks this way; Timeline / Board /
// Studio *data* now rides the live socket (live.js) instead. Hand-raise notifications
// are the remaining exception: they fire BECAUSE you are on another tab, so they keep
// their own timer.
//
// No document (node:test, SSR) behaves as visible - the interval just runs.

export function pollWhileVisible(fn, ms) {
  let id = 0;
  const visible = () => typeof document === "undefined" || document.visibilityState !== "hidden";
  const arm = (fromVisibility) => {
    clearInterval(id);
    id = 0;
    if (visible()) {
      // Re-arming on hidden->visible used to only start the interval, so the
      // Timeline could sit on a 30s-stale list until the first tick.
      if (fromVisibility) fn();
      id = setInterval(fn, ms);
    }
  };
  arm(false);
  const onChange = () => arm(true);
  if (typeof document !== "undefined") document.addEventListener("visibilitychange", onChange);
  return () => {
    clearInterval(id);
    if (typeof document !== "undefined") document.removeEventListener("visibilitychange", onChange);
  };
}

// Views kept mounted behind another tab need a fresh read at the moment they become
// active, not only when their next interval happens to fire.
export function pollWhileActive(active, fn, ms) {
  if (!active) return undefined;
  if (typeof document === "undefined" || document.visibilityState !== "hidden") fn();
  return pollWhileVisible(fn, ms);
}
