// A ROW'S STATUS, SAID ONCE (the task page redesign, owner-approved 2026-10-21): the rail row's icon and the task page's header pill
// draw the SAME mark and word for one task, from taskuary/lanes.json through the rail's own reading (funnelPile.rowMeta) - so the two
// cannot disagree. On the rail the ring round the source's logo wears the state (RING); the header pill keeps the lane's mark and word.
// Pure, so node --test reads it.
import { KIND_META, rowMeta, taskStateMeta } from "./funnelPile.js";

// THE RING ROUND THE LOGO SAYS THE STATE (the owner, 2026-10-22: "The spinning thing around is good. Don't spin the whole thing, just
// the circle around it"): the logo never moves, fades or changes colour; each state is a ring of its own SHAPE, so the shapes alone
// tell the states apart - with motion off, and without colour. Its thin colour is the task page pill's for that state.
//   spin     - an agent at work: the spinning arc, as it always was
//   breathe  - somebody (or an agent) waits on you: a full ring, gently breathing
//   full     - ready to send: a full solid ring, still
//   half     - stopped and saved, or an agent stopped: half a ring, still
//   broken   - a check failed, couldn't sort, didn't send: a ring broken in four, still
//   dots     - waiting to start: a ring of eight dots, its lead dot ticking round once a second
//   faint    - waiting on them, or held: a thin faint ring, still
//   progress - a goal: the ring fills as its steps are done (StatusMark.jsx's `progress`)
//   none     - done, and everything else: no ring
export const RING = { blocked: "breathe", asked: "breathe", approve: "full", saved: "half", stopped: "half", broken: "broken",
  unjudged: "broken", not_sent: "broken", queued: "dots", theirs: "faint", held: "faint" };
export const RINGS = ["spin", "breathe", "full", "half", "broken", "dots", "faint", "progress", "none"];
// the rings that move; under reduced motion none does, and the shapes still tell the states apart
export const MOVES = ["spin", "breathe", "dots"];

const said = (key, m, spins) => ({ key, mark: m.mark, word: m.word, role: m.role ?? null, hint: m.hint || "", spins,
  ring: spins ? "spin" : RING[key] || "none" });

// a RAIL ROW (a funnel item: lane, kind, not_sent, settling) as the rail draws it - a kind's word over its lane's, a refused send over both
export const railStatus = (item) => {
  if (!item?.lane) return null;
  const key = item.not_sent ? "not_sent" : KIND_META[item.kind] ? item.kind : item.lane;
  const spins = item.lane === "working" && !item.settling;
  return said(key, rowMeta(item), spins);
};
// a TASK'S STATE (taskstate.py: a lane, or `theirs`, `agentdone`, `closed`, `dropped`) - the Tasks list's row, and a task with no rail row
export const stateStatus = (key) => {
  const m = key && taskStateMeta(key);
  return m ? said(key, m, key === "working") : null;
};

// THE TASK PAGE'S STATUS: the live session's own word first - the rail's working and waiting lanes read that very session (taskstate:
// a live session is `blocked` when it waits, else `working`) - then the rail's row for the task (on the canvas), then the server's state
// (the Tasks list's row, or the detail's own for a task with no row - a closed one).
// A CLOSED task has no rail row of its own - one pulled onto the table by a link or a search wears whatever lane it was read in - so
// its state is the server's: done, the agent finished, or dropped.
export const taskStatus = ({ live = null, rail = null, state = null, closed = false } = {}) => {
  if (live?.alive) return railStatus({ lane: live.waiting ? "blocked" : "working" });
  if (closed && stateStatus(state)) return stateStatus(state);
  return railStatus(rail) || stateStatus(state);
};

// what a row's icon says to a reader that cannot see it: the state's words (a screen reader, a hover, a reader without colour)
export const statusLabel = (st, agent = "") => (!st ? "" : st.spins ? `${agent || "an agent"} is working on this` : st.word);
