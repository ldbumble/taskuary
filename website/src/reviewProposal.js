import { label } from "./buttons.js";

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
// ONE SET OF WORDS FOR EVERY SYSTEM (the owner, 2026-09-27: "if we have button to close out per system it will be
// endless"): Approve / Decline / Remind me (the task's own - 2026-10-02: "not yet is really remind me later"). Only `then` - what it does THERE - differs; a new connector adds a line.
// ...and Approve is the one word for every proposal (buttons.json: approve's `action` state) - "Merge & close", "Run action" and
// "Save playbook" were three more names for the same press
const APPROVE = label("approve", "action");
export const CLOSEOUT = {
  merge_pr: { label: APPROVE, busy: "merging…", then: "merges the pull request on GitHub", reject: null,
    // the other answer, where the system has one: the work is not wanted - the PR closes unmerged
    alt: { verb: "close_pr", label: "Decline", busy: "declining…", then: "closes the pull request without merging it" } },
  close_issue: { label: APPROVE, busy: "closing…", then: "closes the issue on GitHub", reject: null },
};
export const closeoutOf = (review) => CLOSEOUT[proposalFrom(review)?.action] || null;

// a playbook's file name from its title - playbooks.slugify's rule: lower case, every other run of characters one "-", cut, trimmed
const slugify = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 60).replace(/^-+|-+$/g, "");

// a proposal whose words ARE a playbook page: a new one (the agent's on-close draft) or the ledger's block on one (build step 5)
export const PAGES = new Set(["write_playbook", "amend_playbook"]);

// a tool run's place (proposals.WHERE_KEYS, the same order) and what it carries: the text it writes, the query or script it runs,
// else its other settings one per line - the plumbing (the action, the run it belongs to, the connection id) left out
const WHERE_KEYS = ["path", "to", "folder", "table", "url", "bucket", "key", "container", "blob", "channel", "list", "database"];
const PLUMBING = new Set(["action", "type", "flow_run", "connector_id", "why", ...WHERE_KEYS]);
export const toolWhere = (p) => {
  const k = WHERE_KEYS.find((x) => p?.[x]);
  const sys = String(p?.type || "").replace(/_/g, " ");
  return k ? `${String(p[k])} · ${sys}` : sys || "a connected system";
};
export const toolBody = (p) => {
  const body = p?.text ?? p?.body ?? p?.message ?? p?.query ?? p?.script;
  if (body != null && body !== "") return String(body);
  return Object.entries(p || {}).filter(([k, v]) => !PLUMBING.has(k) && v !== "" && v != null)
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${typeof v === "string" ? v : JSON.stringify(v)}`).join("\n");
};

export const reviewText = (review) => {
  const proposal = proposalFrom(review);
  if (CLOSEOUT[proposal?.action]) return proposal.text || "";      // never the JSON envelope: an empty box sends nothing extra
  // a workflow repair reads as what was wrong and what changes, never the step list's JSON (flow.repair)
  if (proposal?.action === "repair_workflow") return [proposal.why, proposal.changes].filter(Boolean).join("\n\n");
  if (proposal?.action === "run_tool") return toolBody(proposal);
  if (proposal?.action === "browser_act") return [proposal.what, proposal.command].filter(Boolean).join("\n\n");
  return PAGES.has(proposal?.action) && proposal.text ? proposal.text : review?.DraftText || "";
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
      destinationLabel: pr ? "Merge" : "Close",
      destination: pr ? `${proposal.repo || ""}#${proposal.number || ""}` : "the GitHub issue this task came from",
      approveLabel: co.label,
      then: co.then,
      busyLabel: co.busy,
      rejectLabel: co.reject,
      alt: co.alt || null,
      placeholder: pr ? "No summary - GitHub writes the merge message" : "No comment - the reply carries it",
    };
  }
  if (PAGES.has(proposal?.action)) {
    const title = String(proposal.text || "").match(/^#\s+(.+)$/m)?.[1]?.trim();
    // "new" (or none) is filed under its TITLE (playbooks.write -> slugify), so that is the file it names: the card said new.md
    // over a W-9 playbook the approve then saved as send-our-w-9-to-a-customer-who-asks.md (walk 2026-10-21)
    const given = String(proposal.slug || "").trim();
    const slug = (given && given !== "new" ? given : slugify(title)) || "playbook";
    const amend = proposal.action === "amend_playbook";
    return {
      kind: "playbook",
      title: title ? `Playbook · ${title}` : "New playbook",
      context: amend ? "What the outcome ledger counted about this kind of work, added to its playbook · nothing is sent"
        : "Playbook proposal · nothing will be sent to the conversation",
      destinationLabel: "Save to",
      destination: `Reports → Playbooks → ${slug}.md`,         // where playbooks live (PlaybookShelf.jsx)
      approveLabel: APPROVE,
      busyLabel: "saving…",
      rejectLabel: "Discard proposal",
    };
  }
  // A TOOL RUN IN WORDS (the owner, 2026-10-21): what it will write, send or run, and where - never the proposal's JSON. The
  // sentence with the connection's own name is the server's (proposals.tool_words, the review's Reason); this is the place and the
  // content, read-only - an edit to them was never what ran (proposals.execute runs the proposal as queued)
  if (proposal?.action === "run_tool") return {
    kind: "action",
    title: proposal.flow_run ? "A workflow step waits for your yes" : "Run a step in a connected system",
    context: review.Reason || "Proposed action · nothing will be sent to the conversation",
    destinationLabel: "Where",
    destination: toolWhere(proposal),
    approveLabel: APPROVE,
    busyLabel: "running…",
    rejectLabel: "Dismiss",
    readOnly: true,
  };
  // A HELD BROWSER ACT (browsergate.py, 2026-10-25): what the agent's browser would do and on which page, in words - Approve runs that
  // exact command there, so the words are read-only like a tool run's
  if (proposal?.action === "browser_act") return {
    kind: "action",
    title: "The agent's browser waits for your yes",
    context: review.Reason || "Held before it ran · it can't be undone",
    destinationLabel: "On",
    destination: proposal.url || proposal.site || "the agent's browser",
    approveLabel: APPROVE,
    busyLabel: "running…",
    rejectLabel: "Dismiss",
    readOnly: true,
  };
  if (proposal?.action === "repair_workflow") return {
    kind: "action",
    title: "Repair this workflow's steps",
    context: "A step failed · the AI wrote a fix · the steps change only if you approve",
    destinationLabel: "Changes",
    destination: "the workflow's saved steps",
    approveLabel: APPROVE,
    busyLabel: "saving…",
    rejectLabel: "Dismiss",
  };
  return {
    kind: "action",
    title: review.Subject || review.Title || "Proposed action",
    context: "Proposed action · nothing will be sent to the conversation",
    destinationLabel: "Action",
    destination: String(proposal?.action || "proposed action").replaceAll("_", " "),
    approveLabel: APPROVE,
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
