// A ROW'S STATUS, SAID ONCE (the task page redesign, owner-approved 2026-10-21): the rail row's icon and the task page's header pill
// draw the SAME mark and word for one task, from taskuary/lanes.json through the rail's own reading (funnelPile.rowMeta) - so the two
// cannot disagree. The spinning ring is an agent at work; every other state is the lane's mark, worn as a badge on the source's logo.
// Pure, so node --test reads it.
import { KIND_META, rowMeta, taskStateMeta } from "./funnelPile.js";

// WHERE A BADGE MOVES: the hand of somebody - or an agent - waiting on you waves, a start not yet made turns its hourglass. Everything
// else holds still: a still mark is easier to read, and a rail of moving badges is noise. `ring` is the agent at work.
export const ANIM = { blocked: "wave", asked: "wave", queued: "turn" };

const said = (key, m, spins) => ({ key, mark: m.mark, word: m.word, role: m.role ?? null, hint: m.hint || "", spins,
  anim: spins ? "ring" : ANIM[key] || null });

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
export const taskStatus = ({ live = null, rail = null, state = null } = {}) => {
  if (live?.alive) return railStatus({ lane: live.waiting ? "blocked" : "working" });
  return railStatus(rail) || stateStatus(state);
};

// what a row's icon says to a reader that cannot see it: the state's words (a screen reader, a hover, a reader without colour)
export const statusLabel = (st, agent = "") => (!st ? "" : st.spins ? `${agent || "an agent"} is working on this` : st.word);
