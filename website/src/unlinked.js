// The server seeds the owner token only into a page opened with a one-time launch key (launchkey.py, R29); an unkeyed
// page says so with <meta name="taskuary-unlinked">. A tab that already holds the token works as before; one that has
// none would only meet 401s, so it says how to get in instead of failing silently.
export const UNLINKED_LINE = "Open Taskuary from its app, or run `taskuary --link`";

export function needsLink(doc, storage) {
  if (!doc?.querySelector?.('meta[name="taskuary-unlinked"]')) return false;
  try { return !storage?.getItem("taskuary_token"); } catch { return true; }
}

// A stored token the server no longer takes (a token change, a reinstall) used to meet "reload it" - and a reload no
// longer re-seeds one (R29), so that was a dead end. The stale token is dropped instead, and the page shows the line
// above. Only the token gate's own refusal (code "unauthorized") counts: a 403 is a refusal of one act, not of the page.
export const UNLINKED_EVENT = "taskuary-unlinked";
export function staleToken(err, storage) {
  if (err?.response?.status !== 401 || err?.response?.data?.code !== "unauthorized") return false;
  try { storage?.removeItem("taskuary_token"); } catch { /* storage that cannot be written holds nothing to clear */ }
  return true;
}
