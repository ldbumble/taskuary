// THE AGENT'S TURN IS ON SCREEN THE MOMENT IT IS ASKED FOR (the owner, 2026-11-09: "it should show the 'AGENT 2:05 PM' right away and spin while
// spinning up"). A line sent on a road this pane does not stream - an answer to the agent's question goes through the server - drew the owner's
// line and nothing under it until the request came back, then a "Working on this…" with no head, which went when the server's turn landed
// and came back as the turn. The pane draws the agent's turn itself - its head and its clock - from the press, until a turn the thread on
// screen draws takes its place at the same spot.

import { asUtc } from "./dates.js";

// a turn the thread on screen draws as live: this pane's own stream (running), or the server's turn read from its trace (`live-` rows)
export const live = (m) => m?.status?.type === "running" || String(m?.id || "").startsWith("live-");
// ...and one that has drawn NOTHING yet - no word, no step: its head is the pane's own (AtWorkHead), under his newest line, as a coding chat's live
// turn is no row until its first step (the side-by-side walk, 2026-11-11: an empty "AGENT · Along the way" stood over a line typed mid-turn)
export const bare = (m) => m?.role === "assistant" && live(m) && !(m.content || []).some((p) => p.type === "data" || String(p.text || "").trim());
const answers = (ms) => (ms || []).filter((m) => m?.role === "assistant").length;

// what the press keeps, before any request goes: when, and how many answers the thread had then
// `busy`: a turn already at work then - and one the thread does not draw yet (its adapter silent so far, its head the pane's own) will file an
// answer after the press that is its own, not the line's: counted in, so it never lets the press go (the recorded coding walk, 2026-11-10)
export const sentNow = (thread, at = Date.now(), busy = false) => ({ at, answers: answers(thread) + (busy && !live((thread || []).at(-1)) ? 1 : 0), busy });

// ...let go once the thread has a turn after it: the reply (or the live turn) is the thread's own from there
export const settled = (thread, sent) => !!sent && answers(thread) > sent.answers;

// whether the pane draws the agent's turn: a line was just sent, or the agent is at work, and the thread draws no live turn at its end
// ...and a line of his the thread has JUST drawn with nothing after it: the chat's own send draws it a beat before its run begins, with no `sent`
// of the pane's - his line stood alone, no head under it, for a beat (CI and the frame-by-frame watch, 2026-11-10). A minute bounds it: a line
// nothing ever answered is no turn at work
const fresh = (m, now) => m?.role === "user" && !(m.brief || m.metadata?.custom?.brief || m.press || m.metadata?.custom?.press)
  && m.createdAt && now - +new Date(m.createdAt) < 60000;
// ...and ONE FACT ENDS A TURN: its answer filed at or after the turn at work began (`began`, ms). A working flag read a poll late drew a second
// running head under the finished turn for a beat (the recorded rewrite walk, 2026-11-10); a turn begun after the answer is a new one
// ...and with no start said, an answer is the turn over: a working flag alone is no new turn (the poll that said it read the turn just filed)
const over = (m, began) => m?.role === "assistant" && !live(m) && !(began && (!m.createdAt || +(m.createdAt instanceof Date ? m.createdAt : asUtc(String(m.createdAt))) < began));
export const turnOver = (thread, { sent = null, began = null } = {}) => !sent && over((thread || []).at(-1), began);
// ...and `held`: the server held the start his line asked for (a stranger's task its AI cannot be kept to reading - HeldStart says so under it):
// nothing is running, so no head over the hold - the fresh line's bridge stood a minute (the recorded walk, 2026-11-10)
export function pendingTurn(thread, { busy = false, sent = null, now = Date.now(), began = null, held = false } = {}) {
  const last = (thread || []).at(-1);
  if (last?.role === "assistant" && live(last)) return false;
  if (held && !busy) return false;
  if (fresh(last, now)) return true;
  if (turnOver(thread, { sent, began })) return false;
  if (settled(thread, sent)) return false;
  return !!sent || !!busy;
}
