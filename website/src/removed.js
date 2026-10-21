// A REMOVE ACTS AT ONCE, AND IS TAKEN BACK IN PLACE (the owner, 2026-10-21: no "are you sure"). Every Remove - a report, a workflow,
// a routing rule, a profile, a mailbox address, a connection, a sign-in - runs on the press; the server keeps what it took
// (recentlydeleted.py) and answers with its id. The page then says "Removed <it> - Undo" where the thing was. The press and the
// line are often on two screens (an editor removes, its list shows the line), so the line is announced here and drawn by whichever
// list is showing that kind.
const subs = new Set();
let last = null;

// `kind`: which lists draw it ("report", "workflow", "rule", "profile", "source", "connection", "signout"); `did`: the server's id
export const removedLine = (title, verb = "Removed") => `${verb} ${title || "it"}`;
export function announceRemoved({ did, title, kind, verb = "Removed" }) {
  last = did ? { did, title, kind, verb, at: Date.now() } : null;
  subs.forEach((f) => f(last));
  return last;
}
export function clearRemoved(did) { if (!did || last?.did === did) { last = null; subs.forEach((f) => f(null)); } }
export const lastRemoved = () => last;
export function onRemoved(f) { subs.add(f); return () => subs.delete(f); }
// ...shown only by a list that holds its kind, and only fresh: a line from ten minutes ago is not "just now" any more (the server
// keeps a connection's sign-in only that long - recentlydeleted.UNDO_SECONDS)
export const UNDO_MS = 600000;
export const showsRemoved = (r, kinds, now = Date.now()) => !!r && kinds.includes(r.kind) && now - r.at < UNDO_MS;
// the server's answer to a Remove is the line's: its id and title, and the kind the list knows it by
export const fromAnswer = (data, kind, fallback = "") => ({ did: data?.deleted, title: data?.title || fallback, kind: data?.kind || kind });
