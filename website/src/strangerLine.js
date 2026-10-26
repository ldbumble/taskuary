// The card's one line for a stranger's task (origin.py): null for the owner's and trusted work, so nothing renders for them.
// ...and what triage or ranking read the words as trying to make an agent do (message.Danger): a warning, never a gate.
// Said in plain words (the audit, 2026-10-17): "Stranger's words · runs in auto mode" meant nothing to someone who never ran a coding
// tool. Words Taskuary itself wrote from what it read (a report, the assistant) are not "someone" - they say so instead.
// The presses are the server's words for this sender (senders.trust_offer) - the same ones the held box carries (the owner,
// 2026-10-26): "Trust Erin", "Trust everyone at vendor.example", a Slack workspace's name - and no organisation where there is none.
export const strangerLine = (d) => {
  if (d?.origin?.origin !== "stranger") return null;
  const ours = /^written by Taskuary/i.test(d.origin.why || "");
  return { text: `${ours ? "Written by Taskuary from what it read" : "From someone you haven't worked with here yet"} - anything risky waits for your OK`,
    trust: ours ? "Trust it" : d.origin.trust?.person || "Trust them", trustOrg: ours ? null : d.origin.trust?.org || null,
    why: d.origin.why || "", danger: d.origin.danger || null };
};

// THE HOLD CARRIES ITS OWN WAY OUT (the owner, 2026-10-26: "we should have button on untrusted user to either trust user or trust domain
// and then we won't have issue again"): a step held for a new sender shows the presses in its box, and Came from then shows none -
// one place, one wording
export const trustInBox = (story) => story?.kind === "held" && !!story.trust?.person;
