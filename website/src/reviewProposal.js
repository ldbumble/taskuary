export const proposalFrom = (review) => {
  if (review?.Kind !== "action") return null;
  try {
    const proposal = JSON.parse(review.DraftText || "");
    return proposal?.action ? proposal : null;
  } catch {
    return null;
  }
};

// THE CLOSE-OUT (the owner, 2026-09-27): what finishes a task where it lives - merge the PR the agent opened, close
// the issue it came from. Its text is the summary a merge is squashed with, or the comment the issue closes with.
export const CLOSEOUT = {
  merge_pr: { label: "Merge", busy: "merging…", then: "merges the pull request and closes the task", reject: "Not yet",
    // the other answer: the work is not wanted - the PR closes unmerged and the task ends with it
    alt: { verb: "close_pr", label: "Close PR", busy: "closing…", then: "closes the pull request without merging, and the task" } },
  close_issue: { label: "Close issue", busy: "closing…", then: "closes the issue on GitHub and the task", reject: "Not yet" },
};
export const closeoutOf = (review) => CLOSEOUT[proposalFrom(review)?.action] || null;

export const reviewText = (review) => {
  const proposal = proposalFrom(review);
  if (CLOSEOUT[proposal?.action]) return proposal.text || "";      // never the JSON envelope: an empty box sends nothing extra
  return proposal?.action === "write_playbook" && proposal.text ? proposal.text : review?.DraftText || "";
};

export const proposalPresentation = (review) => {
  if (review?.Kind !== "action") return null;
  const proposal = proposalFrom(review);
  const co = CLOSEOUT[proposal?.action];
  if (co) {
    const pr = proposal.action === "merge_pr";
    return {
      kind: "closeout",
      title: review.Title || review.Subject || (pr ? "Merge the pull request" : "Close the issue"),
      context: pr ? `The agent finished · the task closes when pull request #${proposal.number || ""} merges, or you close it`
        : "The agent finished · the task closes with the issue",
      destinationLabel: pr ? "MERGE" : "CLOSE",
      destination: pr ? `${proposal.repo || ""}#${proposal.number || ""}` : "the GitHub issue this task came from",
      approveLabel: co.label,
      busyLabel: co.busy,
      rejectLabel: co.reject,
      alt: co.alt || null,
      placeholder: pr ? "No summary - GitHub writes the merge message" : "No comment - the reply carries it",
    };
  }
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
