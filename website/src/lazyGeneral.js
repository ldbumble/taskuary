// One guarded loader for the GeneralWorkspace chunk, wherever it is mounted.
//
// A lazy chunk carries the build's hash in its name, so a page left open across a deploy asks for a
// file that no longer exists and the whole view dies with "Failed to fetch dynamically imported
// module" (the owner, 2026-09-03, on the Board). TasksView already reloaded once and carried on;
// every other mount point did not, so the same stale build looked like three different bugs.
//
// One reload, once per session: a second failure is a real error and must reach the boundary rather
// than loop the page.
const ONCE = "tq-general-chunk-reload";
const STALE = /dynamically imported module|importing a module script failed|failed to fetch/i;

export const loadGeneral = () => import("./GeneralWorkspace.jsx").then((m) => {
  try { sessionStorage.removeItem(ONCE); } catch { /* storage disabled */ }
  return m;
}).catch((error) => {
  let retried = false;
  try { retried = sessionStorage.getItem(ONCE) === "1"; } catch { /* storage disabled */ }
  if (STALE.test(String(error?.message || error)) && !retried) {
    try { sessionStorage.setItem(ONCE, "1"); } catch { /* storage disabled */ }
    window.location.reload();
    return new Promise(() => {});                 // the reload is the outcome; never resolve into a render
  }
  throw error;
});

export const lazyGeneral = (name = "GeneralWorkspace") => () => loadGeneral().then((m) => ({ default: m[name] }));
