import vocab from "../../taskuary/lanes.json" with { type: "json" };
// ONE SENTENCE PER SUB-STATE of a blocked agent - the same entry workerstate.says reads on the
// server. Seven surfaces each spelled "parked at its prompt" their own way (the 2026-09-18 audit's
// top open item), and none could say "stuck on a rate limit", because each composed its sentence
// from two booleans. The request's KIND picks the sentence; the booleans are the fallback for a
// run whose word is silent. Dependency-free so it runs under bare node (test/laneSays.test.mjs).
const SAYS = vocab.lanes.find((l) => l.key === "blocked").says;
const SUB = { approval_needed: "approval", stalled: "stalled", input_needed: "asking" };

// x is anything that carries the state: a session row ({state, request, asking}), a pile item
// ({request_kind, asking}) or a hand-raise ({state, asking}).
export const subState = (x) => x?.state || SUB[x?.request?.kind || x?.request_kind] || (x?.asking ? "asking" : "parked");

export const says = (sub, agent, text = "") => {
  const s = SAYS[sub] || SAYS.parked, t = String(text || "").replace(/\s+/g, " ").trim().slice(0, 300);
  return (t && s.line ? s.line : s.bare).replace("{agent}", agent || "the agent").replace("{text}", t);
};
