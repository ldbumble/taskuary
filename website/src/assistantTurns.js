// Reconcile optimistic chat bubbles with the durable turns returned by the server.
// Local bubbles use a/u/r/context ids; persisted comments use their database id. Comparing only
// ids drew both copies after every freshness read even though the server had recorded one turn.
const optimistic = (m) => typeof m?.id === "string" && /^(?:a|u|r|context)\d+$/.test(m.id);
const words = (v) => String(v || "").replace(/\s+/g, " ").trim();
const sameTurn = (a, b) => a?.role === b?.role && words(a?.text) === words(b?.text);

export function mergeDurableTurns(local = [], durable = []) {
  const messages = [...local];
  // A reconciled bubble answers to BOTH names: the optimistic id it is keyed by on screen, and the
  // comment id the server gave it. Tracking only the visible one made every freshness read re-match
  // a turn that had already been reconciled.
  const ids = new Set(messages.flatMap((m) => [m.id, m.commentId]).filter((v) => v != null));
  const claimed = new Set();
  const added = [];
  for (const turn of durable || []) {
    if (ids.has(turn.id)) continue;
    const at = messages.findIndex((candidate, i) => !claimed.has(i) && optimistic(candidate) && sameTurn(candidate, turn));
    if (at >= 0) {
      // KEEP THE BUBBLE'S OWN ID. AssistantView keys the chat by it, so swapping it for the comment
      // id unmounted the line and mounted a fresh one in its place - destroying and rebuilding the
      // card inside it. That is the blink every message did a moment after it was sent (the owner,
      // 2026-09-04: "appears, flickers and reapears"). The durable id rides along instead, so the
      // next read still recognises the turn and skips it.
      const bubble = messages[at];
      messages[at] = { ...turn, id: bubble.id, commentId: turn.id };
      claimed.add(at);
    } else {
      messages.push(turn);
      added.push(turn);
    }
    ids.add(turn.id);
  }
  return { messages, added };
}
