// A ROW'S STATUS, SAID ONCE (the task page redesign, owner-approved 2026-10-21): the rail row's icon and the task page's header pill
// draw the SAME mark and word for one task, from taskuary/lanes.json through the rail's own reading (funnelPile.rowMeta) - so the two
// cannot disagree. The spinning ring is an agent at work; a hand or a flag on the logo is the owner's move; every other state is the
// plain logo, its words in the icon's label.
// Pure, so node --test reads it.
import { KIND_META, rowMeta, taskStateMeta } from "./funnelPile.js";

// THE ONLY BADGES (the owner, 2026-10-22: too many emojis on the rail): the hand of somebody - or an agent - waiting on you, which
// waves, and the flag of a reply ready to send. Every other state is the plain logo; its words are the icon's label and hover.
export const BADGE = { blocked: "👋", asked: "👋", approve: "🏁" };
// where a badge moves: the hand waves; the flag holds still. `ring` is the agent at work.
export const ANIM = { blocked: "wave", asked: "wave" };

const said = (key, m, spins) => ({ key, mark: m.mark, word: m.word, role: m.role ?? null, hint: m.hint || "", spins,
  badge: spins ? "" : BADGE[key] || "", anim: spins ? "ring" : ANIM[key] || null });

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
