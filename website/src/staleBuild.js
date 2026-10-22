// Taskuary updates underneath an open tab - a git pull and a rebuild, `pip install -U`, the
// coding agent shipping its own fix - and the tab goes on running the JavaScript it loaded at
// breakfast. Every symptom of that looks exactly like a bug that was already fixed, and from
// inside the page there is no way to tell the difference. (It cost this project an afternoon:
// three rounds of "still broken" against a build that was not being loaded.)
//
// So: what bundle did THIS page load, and what is on disk now. A page at rest reloads itself
// (buildMove, below); one the owner is mid-sentence in only says so.
export const loadedAsset = (doc = document) => {
  const src = [...doc.querySelectorAll("script[src]")].map((s) => s.getAttribute("src") || "")
    .find((s) => /assets\/index-[^/]+\.js$/.test(s)) || "";
  return src.split("/").pop() || "";
};

/** Is the served bundle a DIFFERENT one from the one running? Unknown answers are never stale. */
export const isStale = (loaded, served) => !!loaded && !!served && loaded !== served;

/** What the banner should say, if anything. A version bump on disk needs a RESTART (the server
 *  process still reports the number it started with); a rebuilt bundle only needs a reload.
 *  The restart case wins: after a pull both are usually true, and reloading alone fixes neither
 *  the header's version nor the server's code. */
export const staleWhat = (loaded, build) => {
  if (!build) return "";
  if (build.disk_version && build.version && build.disk_version !== build.version) return `v${build.disk_version} on disk — restart Taskuary`;
  return isStale(loaded, build.asset) ? "A new version is running – Reload" : "";
};

/* A restart onto a newer version left an open window drawing the OLD page - the rail's old sections - until a manual
   reload (0.3.9.15 -> 0.3.9.20, 2026-10-21): the line above only SAID so, and nobody reads a pill they did not expect.
   So a page at rest reloads itself; a page someone is typing in keeps the line. `own` is the bundle this page loaded,
   `reloaded` the server build this tab already reloaded for (sessionStorage), so a server that keeps answering
   differently - a cached index.html, a proxy - costs one reload, never a loop. A restart still pending (disk newer than
   the process) is not reloaded for: a reload fixes nothing until the server itself is the new one. */
export const buildMove = (own, build, { busy = false, reloaded = "" } = {}) => {
  if (!own || !build?.asset || own === build.asset) return "";
  if (build.disk_version && build.version && build.disk_version !== build.version) return "";
  if (reloaded === build.asset) return "";
  return busy ? "line" : "reload";
};

/** Is someone mid-input? Any field - a composer, a draft, a sheet's form - still holding text a reload would throw away.
 *  Focus alone is not it: the composer takes focus on load, and an empty one loses nothing. */
const EDITABLE = 'textarea, input:not([type]), input[type=text], input[type=search], input[type=email], input[type=url], input[type=tel], '
  + 'input[type=password], input[type=number], [contenteditable=""], [contenteditable=true]';
export const isBusy = (doc = document) => [...doc.querySelectorAll(EDITABLE)].some((el) => !el.readOnly && !el.disabled
  && ((el.isContentEditable ? el.textContent : el.value) || "").trim() !== "");

const RELOADED = "tq-build-reloaded";
export const reloadedFor = () => { try { return sessionStorage.getItem(RELOADED) || ""; } catch { return ""; } };
/** Remember the build before reloading for it. Storage that cannot be written means no reload: a loop is worse than a line. */
export const markReloaded = (asset) => {
  try { sessionStorage.setItem(RELOADED, asset); return sessionStorage.getItem(RELOADED) === asset; } catch { return false; }
};
