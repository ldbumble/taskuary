// THE AGENT'S TURN IS ON SCREEN THE MOMENT IT IS ASKED FOR (the owner, 2026-11-09: "it should show the 'AGENT 2:05 PM' right away and spin while
// spinning up"). A line sent on a road this pane does not stream - an answer to the agent's question goes through the server - drew the owner's
// line and nothing under it until the request came back, then a "Working on this…" with no head, which went when the server's turn landed
// and came back as the turn. The pane draws the agent's turn itself - its head and its clock - from the press, until a turn the thread on
// screen draws takes its place at the same spot.

// a turn the thread on screen draws as live: this pane's own stream (running), or the server's turn read from its trace (`live-` rows)
export const live = (m) => m?.status?.type === "running" || String(m?.id || "").startsWith("live-");
const answers = (ms) => (ms || []).filter((m) => m?.role === "assistant").length;

// what the press keeps, before any request goes: when, and how many answers the thread had then
export const sentNow = (thread, at = Date.now()) => ({ at, answers: answers(thread) });

// ...let go once the thread has a turn after it: the reply (or the live turn) is the thread's own from there
export const settled = (thread, sent) => !!sent && answers(thread) > sent.answers;

// whether the pane draws the agent's turn: a line was just sent, or the agent is at work, and the thread draws no live turn at its end
export function pendingTurn(thread, { busy = false, sent = null } = {}) {
  const last = (thread || []).at(-1);
  if (last?.role === "assistant" && live(last)) return false;
  if (settled(thread, sent)) return false;
  return !!sent || !!busy;
}
