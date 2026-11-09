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

// A POLL THAT CALMS WHILE NOTHING MOVES (2026-11-09). A running agent's page read its task every 3 s and its chat every 2.5 s, at
// 0.4-4 s a read on a busy home, the same answer nearly every time - and each read waited behind the rail's build for the next
// press. `fn` resolves false when its read changed nothing: the gap doubles, up to `most`; any other answer (a change, an error)
// snaps it back to `ms`. Writes still arrive at once over the live socket (task-changed) - this is only the safety net. `first`:
// read at once, as pollWhileActive does. Hidden, it waits; shown again, it reads at once and starts from `ms`.
export function pollCalming(active, fn, ms, most = ms * 4, first = true) {
  if (!active) return undefined;
  let gap = ms, id = 0, dead = false;
  const hidden = () => typeof document !== "undefined" && document.visibilityState === "hidden";
  const arm = () => { clearTimeout(id); id = 0; if (!dead && !hidden()) id = setTimeout(beat, gap); };
  async function beat() {
    let moved = true;
    try { moved = (await fn()) !== false; } catch { moved = true; }
    gap = moved ? ms : Math.min(most, gap * 2);
    arm();
  }
  const onChange = () => { if (hidden()) { clearTimeout(id); id = 0; } else { gap = ms; clearTimeout(id); beat(); } };
  if (first && !hidden()) beat(); else arm();
  if (typeof document !== "undefined") document.addEventListener("visibilitychange", onChange);
  return () => {
    dead = true; clearTimeout(id);
    if (typeof document !== "undefined") document.removeEventListener("visibilitychange", onChange);
  };
}
