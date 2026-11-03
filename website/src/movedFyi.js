// SHOULD BE A TASK KEEPS THE FYI WHERE IT WAS (the owner, 2026-11-03: "i think we should keep it there but say was moved to task"). The
// press makes the line a task, and the rail draws that task under Tasks as it always did - but the FYI it came from stays in its place, in
// the FYI band and in the batch card it was pressed in, wearing where it went ("Moved to Tasks · TQ-1290"). It leaves the way a read FYI
// row does: when the walk moves past the table it was pressed on - the batch read, Next, Back, another row opened - and never on a clock.
// The server never reads it with the batch (railwalk._effect, _settle_unmoved): it is the task now, unread under Tasks.
// `moved` is {key: {key, tid, ref, row, on}} - `row` the FYI row as it stood, `on` the table's key at the press.
import { levelOf } from "./funnelPile.js";

export const refOf = (tid, ref) => ref || (tid ? `TQ-${String(tid).padStart(4, "0")}` : "");
// the row the press was made on, if it was an FYI one: the rail's, or the batch's own line on the table
export function movedEntry(key, tid, ref, rail, cur) {
  if (!key || !tid) return null;
  const row = (rail || []).find((i) => i.key === key) || (cur?.items || []).find((i) => i.key === key) || (cur?.key === key ? cur : null);
  return row && levelOf(row) === "fyi" && !row.tid ? { key, tid: Number(tid), ref: refOf(tid, ref), row, on: cur?.key || key } : null;
}
// does the table still hold it: the batch it was pressed in, or the task it became, put up at its place (W49)
export const holds = (cur, m) => !!cur && ([cur.key, ...(cur.aliases || []), ...(cur.members || [])].some((k) => k === m.on || k === m.key || k === `task:${m.tid}`)
  || (!cur.members && Number(cur.tid) === m.tid));
const only = (moved, keep) => { const out = Object.fromEntries(Object.entries(moved || {}).filter(([, m]) => keep(m)));
  return Object.keys(out).length === Object.keys(moved || {}).length ? moved : out; };
// ...kept while the table holds it; with nothing on the table (a move in flight) it waits
export const keepHeld = (moved, cur) => (cur ? only(moved, (m) => holds(cur, m)) : moved);
// ...and let go with the table a press puts down
export const dropHeld = (moved, cur) => (cur ? only(moved, (m) => !holds(cur, m)) : moved);
// its FYI row as it stood, wearing where it went - drawn in its band at its arrival, beside the task's own row under Tasks
export const ghostsOf = (moved) => Object.values(moved || {}).map((m) => ({ ...m.row, key: m.key, moved: { tid: m.tid, ref: m.ref } }));
