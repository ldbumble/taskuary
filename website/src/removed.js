// A REMOVE ACTS AT ONCE, AND IS TAKEN BACK IN PLACE (the owner, 2026-10-21: no "are you sure"). Every Remove - a report, a workflow,
// a routing rule, a profile, a mailbox address, a connection, a sign-in - runs on the press; the server keeps what it took
// (recentlydeleted.py) and answers with its id. The page then says "Removed <it> - Undo" where the thing was. The press and the
// line are often on two screens (an editor removes, its list shows the line), so the line is announced here and drawn by whichever
// list is showing that kind.
const subs = new Set();
let last = null, timer = null;

// `kind`: which lists draw it ("report", "workflow", "rule", "profile", "source", "connection", "signout"); `did`: the server's id
export const removedLine = (title, verb = "Removed") => `${verb} ${title || "it"}`;
export function announceRemoved({ did, title, kind, verb = "Removed" }) {
  last = did ? { did, title, kind, verb, at: Date.now() } : null;
  clearTimeout(timer); timer = last ? setTimeout(() => clearRemoved(last?.did), UNDO_MS) : null;
  subs.forEach((f) => f(last));
  return last;
}
export function clearRemoved(did) { if (!did || last?.did === did) { last = null; clearTimeout(timer); subs.forEach((f) => f(null)); } }
// ...and the next thing the owner does ends it: a press anywhere but the line itself (its Undo, its ×). The press that removed has
// already landed by the time the server answers, so it never ends its own line.
export function endRemovedOnPress(e) { if (last && !e?.target?.closest?.("[data-tq-undo]")) clearRemoved(); }
if (typeof document !== "undefined") document.addEventListener("pointerdown", endRemovedOnPress, true);
// ...read through its age as well as the timer: a laptop asleep past the window holds the timer back, never the line
export const lastRemoved = () => (last && Date.now() - last.at < UNDO_MS ? last : null);
export function onRemoved(f) { subs.add(f); return () => subs.delete(f); }
// ...shown only by a list that holds its kind, and only for a few seconds, as SaveNote's Undo is: when they pass the slot empties, so
// a list that mounts later (Walk me through, a reload of the view) has nothing to draw. Before 2026-11-09 it was ten minutes with no
// clock: "an old undo came back". What a Remove took stays restorable under Recently deleted (and the server's own window).
export const UNDO_MS = 10000;
export const showsRemoved = (r, kinds, now = Date.now()) => !!r && kinds.includes(r.kind) && now - r.at < UNDO_MS;
// the server's answer to a Remove is the line's: its id and title, and the kind the list knows it by
export const fromAnswer = (data, kind, fallback = "") => ({ did: data?.deleted, title: data?.title || fallback, kind: data?.kind || kind });
