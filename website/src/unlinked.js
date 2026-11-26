// The server seeds the owner token only into a page opened with a one-time launch key (launchkey.py, R29); an unkeyed
// page says so with <meta name="taskuary-unlinked">. A tab that already holds the token works as before; one that has
// none would only meet 401s, so it says how to get in instead of failing silently. ...WITH NO COMMAND IN IT (walk 19): an agent that opened
// the page read "run `taskuary --link`", ran it, and asked HIM to sign Taskuary in for it - his own terminal tells him at start (cli.HEADLESS)
export const UNLINKED_LINE = "Open Taskuary from its app.";

export function needsLink(doc, storage) {
  if (!doc?.querySelector?.('meta[name="taskuary-unlinked"]')) return false;
  try { return !storage?.getItem("taskuary_token"); } catch { return true; }
}

// A stored token the server no longer takes (a token change, a reinstall) used to meet "reload it" - and a reload no
// longer re-seeds one (R29), so that was a dead end. The stale token is dropped instead, and the page shows the line
// above. Only the token gate's own refusal (code "unauthorized") counts: a 403 is a refusal of one act, not of the page.
export const UNLINKED_EVENT = "taskuary-unlinked";
// ...BUT ONLY THE TOKEN THAT WAS REFUSED (the owner, 2026-11-26: "never had this issue before"): the token lives in the server's memory, so
// every restart mints a new one. The tab left open from before the restart was refused with the old token, dropped what was stored - by
// then the NEW token the restart's own keyed tab had just seeded - and both tabs said "Open Taskuary from its app". A tab whose refused
// token is not the stored one only reloads ("renewed"): the stored one is the restart's, and is kept.
export function staleToken(err, storage) {
  if (err?.response?.status !== 401 || err?.response?.data?.code !== "unauthorized") return false;
  let now = null;
  try { now = storage?.getItem?.("taskuary_token") ?? null; } catch { /* unreadable: nothing newer to keep */ }
  const sent = err?.config?.headers?.["X-Taskuary-Token"];
  if (now && sent && now !== sent) return "renewed";
  try { storage?.removeItem("taskuary_token"); } catch { /* storage that cannot be written holds nothing to clear */ }
  return true;
}
