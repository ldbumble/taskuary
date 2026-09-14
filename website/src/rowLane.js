// WHAT IS WAITING ON THIS ROW, RIGHT NOW.
//
// The work rail meant to say this from the start - "work says what is waiting NOW; the Timeline says
// what TRIAGE said" is written above the chip - and the branch that would have done it tests a
// `Lane` the feed has never sent: lanes are built by the funnel for the PILE, and its items are keyed
// `review:128` where a feed row is keyed `msg:6955`, so there is nothing to join on either. The chip
// therefore always fell through to triage's road word, and a task with a reply drafted and waiting
// wore "coding" (the owner, 2026-09-14: "why does this not say reply pending or agent waving and says
// coding?? that should only be if in coding").
//
// Nothing needs fetching: the row already carries every fact. This names the lane; funnelPile's
// LANE_META owns the words, so there is one vocabulary rather than a second one growing here.
export const ROW_LANES = ["approve", "blocked", "working"];

export function rowLane(row) {
  if (!row) return null;
  // A draft waiting for a yes outranks the rest: sending it is the step that closes the task.
  if (row.ReviewStatus === "pending") return "approve";
  // An agent that stopped and is waiting is the one lane where work has actually HALTED.
  if (row.AgentWaiting || row.NeedsYou) return "blocked";
  // ...and one still going says so rather than wearing the kind of job it happens to be.
  if (row.Working) return "working";
  return null;                       // nothing is waiting: the row keeps triage's road word
}
