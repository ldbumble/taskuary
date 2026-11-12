// WHAT THE "WHICH AI DOES WHAT" PAGE SAYS, in one place (the owner, 2026-11-11: "what is the cards ai on top? settings are not clear").
// Every line names the AI and the model that run, from the server's own answer (brainroute.runs / default_level) - never "the card's
// AI" or "its own model" with nothing to say which.

// a level left on Default: the General agent card's AI by name, and the Coding agent's where that is another
export const levelDefault = (d) => {
  const g = d?.general, c = d?.coding;
  if (!g?.pick) return "Default - the General agent card below";
  return `Default - ${g.brain}${c?.pick && c.pick !== g.pick ? ` (coding: ${c.brain})` : ""}, set on its card below`;
};
// the model a level runs while its model box is blank: the AI picked for it, else the General agent card's
export const levelModel = (d, brain, lvl) => (brain ? brain.runs?.[lvl] : d?.general?.[lvl]) || "its default model";
// a card's RUNS line: the router's answer for the card's job this minute
export const runsLine = (slot) => (slot.runs?.brain ? [slot.runs.brain, slot.runs.model].filter(Boolean).join(" · ") : "nothing yet");
// THE "RIGHT NOW" ROWS, SAID ONCE: three levels on one AI and model for one reason are one line; and a reason all three share - the AI
// they run on is resting until 14:05 - stands once under them, never under each
export const sharedWhy = (now) => { const w = now?.[0]?.why || ""; return now?.length > 1 && w && now.every((n) => n.why === w) && !oneRow(now) ? w : ""; };
const oneRow = (now) => now.every((n) => n.pick === now[0].pick && n.model === now[0].model && n.why === now[0].why);
export const nowRows = (now) => (!now?.length ? [] : oneRow(now) ? [{ ...now[0], level: "every level" }] : sharedWhy(now) ? now.map((n) => ({ ...n, why: "" })) : now);
// ...and an AI's own line of levels ("Claude Code · quick: haiku · normal: ...") is drawn only where it says more than those rows do:
// with every level of agent work on that AI at that very model, it was the same three facts twice, one over the other
// ...nor where a level runs elsewhere (decided 2026-11-12): the card AI's own line then read "Claude Code · quick: OpenAI Codex CLI, ..." - the
// rows under it already say which AI and model each level is on
const elsewhere = (now, l) => now.some((n) => n.pick === l.pick) && now.some((n) => n.pick && n.pick !== l.pick);
export const levelLines = (p) => (p?.levels || []).filter((l) => { const now = p.now || [];
  return !(now.length && (now.every((n) => n.pick === l.pick && n.model === l[n.level]) || elsewhere(now, l))); });
// choosing the AI a card already shows IS a choice while nobody made one (a Select fires no change for the value it holds)
export const repick = (slot, value) => !slot.chosen && value === slot.value;
