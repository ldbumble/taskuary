// The server seeds the owner token only into a page opened with a one-time launch key (launchkey.py, R29); an unkeyed
// page says so with <meta name="taskuary-unlinked">. A tab that already holds the token works as before; one that has
// none would only meet 401s, so it says how to get in instead of failing silently.
export const UNLINKED_LINE = "Open Taskuary from its app, or run `taskuary --link`";

export function needsLink(doc, storage) {
  if (!doc?.querySelector?.('meta[name="taskuary-unlinked"]')) return false;
  try { return !storage?.getItem("taskuary_token"); } catch { return true; }
}
