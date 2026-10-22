// The card's one line for a stranger's task (origin.py): null for the owner's and trusted work, so nothing renders for them.
// ...and what triage or ranking read the words as trying to make an agent do (message.Danger): a warning, never a gate.
// Said in plain words (the audit, 2026-10-17): "Stranger's words · runs in auto mode" meant nothing to someone who never ran a coding
// tool. Words Taskuary itself wrote from what it read (a report, the assistant) are not "someone" - they say so instead.
export const strangerLine = (d) => {
  if (d?.origin?.origin !== "stranger") return null;
  const ours = /^written by Taskuary/i.test(d.origin.why || "");
  return { text: `${ours ? "Written by Taskuary from what it read" : "From someone you haven't worked with here yet"} - anything risky waits for your OK`,
    trust: ours ? "Trust it" : "Trust them", trustOrg: ours ? null : "Trust their organisation", why: d.origin.why || "", danger: d.origin.danger || null };
};
