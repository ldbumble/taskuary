export const proposalFrom = (review) => {
  if (review?.Kind !== "action") return null;
  try {
    const proposal = JSON.parse(review.DraftText || "");
    return proposal?.action ? proposal : null;
  } catch {
    return null;
  }
};

export const reviewText = (review) => {
  const proposal = proposalFrom(review);
  return proposal?.action === "write_playbook" && proposal.text ? proposal.text : review?.DraftText || "";
};

export const proposalPresentation = (review) => {
  if (review?.Kind !== "action") return null;
  const proposal = proposalFrom(review);
  if (proposal?.action === "write_playbook") {
    const title = String(proposal.text || "").match(/^#\s+(.+)$/m)?.[1]?.trim();
    const slug = String(proposal.slug || "playbook").trim();
    return {
      kind: "playbook",
      title: title ? `Playbook · ${title}` : "New playbook",
      context: "Playbook proposal · nothing will be sent to the conversation",
      destinationLabel: "SAVE TO",
      destination: `Docs → Playbooks → ${slug}.md`,
      approveLabel: "Save playbook",
      busyLabel: "saving…",
      rejectLabel: "Discard proposal",
    };
  }
  return {
    kind: "action",
    title: review.Subject || review.Title || "Proposed action",
    context: "Proposed action · nothing will be sent to the conversation",
    destinationLabel: "ACTION",
    destination: String(proposal?.action || "proposed action").replaceAll("_", " "),
    approveLabel: "Run action",
    busyLabel: "running…",
    rejectLabel: "Dismiss",
  };
};

// The DB's own word for a verdict is not a sentence in English: the queue's chip printed
// "closed_unsent" and "no_reply" straight out of the row (2026-09-10 audit). An unknown status still
// shows rather than disappearing - a blank chip would hide a state nobody has named yet.
export const REVIEW_STATUS = {
  pending: "waiting on you", held: "on hold", approved: "sent", edited: "edited & sent",
  rejected: "rejected", no_reply: "no reply needed", closed_unsent: "closed without sending",
  superseded: "overtaken",
};
export const reviewStatusLabel = (status) => REVIEW_STATUS[status] || String(status || "").replace(/_/g, " ");
