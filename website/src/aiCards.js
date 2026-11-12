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
// choosing the AI a card already shows IS a choice while nobody made one (a Select fires no change for the value it holds)
export const repick = (slot, value) => !slot.chosen && value === slot.value;
