// Polls that exist to keep a visible screen honest should not run while the window is
// in the background. The Timeline's 30s refresh, the Board's 4s live tails, the Studio
// animation clock - they all hit one sqlite lock, and they have nothing to show if
// nobody is looking. Hand-raise notifications are the exception: they fire BECAUSE
// you are on another tab, so they keep their own timer.
//
// No document (node:test, SSR) behaves as visible - the interval just runs.

export function pollWhileVisible(fn, ms) {
  let id = 0;
  const visible = () => typeof document === "undefined" || document.visibilityState !== "hidden";
  const arm = () => {
    clearInterval(id);
    id = 0;
    if (visible()) id = setInterval(fn, ms);
  };
  arm();
  if (typeof document !== "undefined") document.addEventListener("visibilitychange", arm);
  return () => {
    clearInterval(id);
    if (typeof document !== "undefined") document.removeEventListener("visibilitychange", arm);
  };
}
