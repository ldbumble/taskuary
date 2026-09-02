// Taskuary updates underneath an open tab - a git pull and a rebuild, `pip install -U`, the
// coding agent shipping its own fix - and the tab goes on running the JavaScript it loaded at
// breakfast. Every symptom of that looks exactly like a bug that was already fixed, and from
// inside the page there is no way to tell the difference. (It cost this project an afternoon:
// three rounds of "still broken" against a build that was not being loaded.)
//
// So: what bundle did THIS page load, and what is on disk now. Nothing reloads itself - the
// owner may be mid-sentence in a terminal - it just says so.
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
  return isStale(loaded, build.asset) ? "update ready — reload" : "";
};
