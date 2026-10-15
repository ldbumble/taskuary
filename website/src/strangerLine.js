// The card's one line for a stranger's task (origin.py): null for the owner's and trusted work, so nothing renders for them.
// ...and what triage or ranking read the words as trying to make an agent do (message.Danger): a warning, never a gate.
export const strangerLine = (d) => d?.origin?.origin === "stranger"
  ? { text: "Stranger's words · runs in auto mode", why: d.origin.why || "", danger: d.origin.danger || null } : null;
