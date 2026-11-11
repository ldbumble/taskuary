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
  // a Jira, Monday or Linear item (trackers.py, 2026-10-25): the comment, then the move to the tracker's own done state
  close_item: { label: APPROVE, busy: "closing…", then: "posts the comment and moves the item to done", reject: null },
};
const TRACKER = { jira: "Jira", monday: "Monday", linear: "Linear" };
export const closeoutOf = (review) => CLOSEOUT[proposalFrom(review)?.action] || null;

// a playbook's file name from its title - playbooks.slugify's rule: lower case, every other run of characters one "-", cut, trimmed
const slugify = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 60).replace(/^-+|-+$/g, "");

// a proposal whose words ARE a playbook page: a new one (the agent's on-close draft) or the ledger's block on one (build step 5)
export const PAGES = new Set(["write_playbook", "amend_playbook"]);

// a tool run's place (proposals.WHERE_KEYS, the same order) and what it carries: the text it writes, the query or script it runs,
// else its other settings one per line - the plumbing (the action, the run it belongs to, the connection id) left out
const WHERE_KEYS = ["path", "to", "folder", "table", "url", "bucket", "key", "container", "blob", "channel", "list", "database", "item"];
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
  // a part of the task going to a task of its own (proposals.break_out): the new task's title, what it is, and each thing that moves
  if (proposal?.action === "break_out") return [proposal.summary, proposal.moves].filter(Boolean).join("\n\n");
  // a script to keep as a routine (proposals 'save_routine'): what feeds it, the script whole, and what the AI step is asked about its output
  if (proposal?.action === "save_routine") return [
    proposal.reads ? `It reads: ${toolWhere(proposal.reads)}` : "", String(proposal.script || ""),
    proposal.prompt ? `Then an AI step reads what it printed: ${proposal.prompt}` : ""].filter(Boolean).join("\n\n");
  // the WHAT is the context line already (proposals.queue's Reason); the box is the exact command Approve runs, once - with no AI the card
  // said "agent-browser click @e12" three times over (2026-10-25)
  if (["browser_act", "shell_act", "desktop_act"].includes(proposal?.action)) return proposal.command ? `Approve runs: ${proposal.command}` : proposal.what || "";
  return PAGES.has(proposal?.action) && proposal.text ? proposal.text : review?.DraftText || "";
};

// WHAT A WAITING CARD SAYS OVER ITSELF IN THE CHAT - what its Approve does, in one line: a drafted playbook's, a held act's. Said with the one
// card, wherever that card stands (a turn of the task's chat, the foot of a walk's)
const PAGE_NOTE = "Approve saves this playbook to Reports → Playbooks, and triage starts matching new mail against its when line. Nothing is sent to anyone.";
export const askNote = (r) => { const a = proposalFrom(r)?.action; return PAGES.has(a) ? PAGE_NOTE : ["browser_act", "desktop_act"].includes(a) ? heldActsLine([r]) : ""; };
// THE LINE OVER A HELD STEP'S CARD IN THE CHAT, said for what was held: a held delete read "The agent's browser waits for your yes" (2026-11-03)
export const heldActsLine = (reviews = []) => {
  const kinds = new Set(reviews.map((r) => proposalFrom(r)?.action));
  const only = (k) => kinds.size === 1 && kinds.has(k);
  if (only("browser_act")) return "The agent's browser waits for your yes. Approve runs exactly this in its browser; Dismiss tells the agent it was not done.";
  if (only("desktop_act")) return "An app on your desktop waits for your yes. Approve runs exactly this; Dismiss tells the agent it was not done.";
  return `${reviews.length > 1 ? "These steps wait" : "This step waits"} for your yes. Approve runs exactly what is shown; Dismiss tells the agent it was not done.`;
};

// what a held step does, in words, and why it waits: the lead over its card, the command itself folded (`folded`)
const upFirst = (x) => (x ? x[0].toUpperCase() + x.slice(1) : x);
export const heldLead = (p) => {
  const about = String(p?.about || "").trim(), what = String(p?.what || "").trim();
  return { lead: upFirst(about || what) || "Run a command in the agent's shell",
    leadWhy: `Held before it ran - ${p?.why || "it leaves this computer"}${about && what ? `: it would ${what}` : ""}.`, folded: !!p?.command };
};

export const proposalPresentation = (review) => {
  if (review?.Kind !== "action") return null;
  const proposal = proposalFrom(review);
  const co = CLOSEOUT[proposal?.action];
  // A TRACKER ITEM'S CLOSE-OUT (2026-10-25): where it goes, and the done state the tracker itself names - or, where it names none or its
  // workflow has no move there, that it is the comment alone, said before the press
  if (co && proposal.action === "close_item") {
    const sys = TRACKER[proposal.tracker] || "the tracker", at = `${proposal.item || ""} in ${sys}`;
    return {
      kind: "closeout",
      title: review.Title || review.Subject || `Close ${proposal.item || "the item"} in ${sys}`,
      context: proposal.no_done ? `The agent finished · ${proposal.no_done}, so ${APPROVE} posts the comment alone`
        : `The agent finished · ${APPROVE} comments on ${proposal.item || "the item"} and moves it to ${proposal.status || "done"}`,
      destinationLabel: "Close",
      destination: proposal.no_done ? `${at} · comment only` : `${at} → ${proposal.status || "its done state"}`,
      approveLabel: co.label,
      then: proposal.no_done ? `posts the comment on ${at}` : `posts the comment on ${at} and moves it to ${proposal.status || "done"}`,
      busyLabel: co.busy,
      rejectLabel: co.reject,
      alt: null,
      placeholder: proposal.no_done ? "Write the comment to post" : "No comment - only the move to done",
    };
  }
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
    title: proposal.flow_run ? "A routine step waits for your yes" : "Run a step in a connected system",
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
  // ...AND A HELD SHELL STEP (shellgate.py, the owner 2026-10-28): a push, a merge, a public post, a publish or a mail the agent tried to
  // run - Approve runs that exact command in the folder it was held in
  // ...LEADING WITH WHAT IT DOES AND WHY, in words (the owner, 2026-11-09: a card that was only "Approve runs: <a long PowerShell line>"): the
  // agent's own words for the call where it gave any, else what the gate read it as; the raw line folded under "Show the command"
  if (proposal?.action === "shell_act") return {
    kind: "action",
    title: "The agent's step waits for your yes",
    context: review.Reason || `Held before it ran · ${proposal.why || "it leaves this computer"}`,
    ...heldLead(proposal),
    destinationLabel: "In",
    // a delete names the folder it aims at (shellgate.deletes): a general agent's own scratch folder told the owner nothing (2026-11-03)
    destination: proposal.where || proposal.cwd || "the agent's folder",
    approveLabel: APPROVE,
    busyLabel: "running…",
    rejectLabel: "Dismiss",
    readOnly: true,
  };
  // ...AND A HELD DESKTOP ACT (agentdesktop.py, 2026-10-31): what an app on the owner's desktop would do - Approve runs that exact command
  if (proposal?.action === "desktop_act") return {
    kind: "action",
    title: "The agent's desktop step waits for your yes",
    context: review.Reason || "Held before it ran · it can't be undone",
    destinationLabel: "On",
    destination: "an app on your desktop",
    approveLabel: APPROVE,
    busyLabel: "running…",
    rejectLabel: "Dismiss",
    readOnly: true,
  };
  // A PART OF THE TASK THAT IS ANOTHER MATTER (proposals.break_out, the owner 2026-11-10): the new task's title leads, what moves is read-only -
  // Approve runs the task page's own split with exactly those messages and to-dos
  if (proposal?.action === "break_out") return {
    kind: "action",
    title: "Move this part to a task of its own",
    context: review.Reason || "Proposed · nothing moves until you approve",
    destinationLabel: "Its own task",
    destination: proposal.title || "",
    approveLabel: APPROVE,
    busyLabel: "moving…",
    rejectLabel: "Dismiss",
    readOnly: true,
  };
  // A SCRIPT THE AGENT WROTE ON THE JOB, KEPT AS A ROUTINE (proposals 'save_routine', the owner 2026-11-10): the script stands whole and
  // read-only in the box - Approve saves exactly that as a routine (workflows.save_script_routine) and runs nothing
  if (proposal?.action === "save_routine") return {
    kind: "action",
    title: "Save this as a routine",
    context: review.Reason || "Proposed · nothing is saved or run until you approve",
    destinationLabel: "It runs",
    destination: `${proposal.runs || "when you run it"} · ${proposal.title || ""}`,
    approveLabel: APPROVE,
    busyLabel: "saving…",
    rejectLabel: "Dismiss",
    readOnly: true,
  };
  if (proposal?.action === "repair_workflow") return {
    kind: "action",
    title: "Repair this routine's steps",
    context: "A step failed · the AI wrote a fix · the steps change only if you approve",
    destinationLabel: "Changes",
    destination: "the routine's saved steps",
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

// AN APPROVED ACT'S CARD IS ITS RESULT (the owner, 2026-11-09: "once i approve it should say sent and what to do next, not a new prompt"): what
// it did in words, its link, and the command it ran folded - read off the receipt the server keeps (proposals.receipt). Null while it waits
const VERB = { shell_act: "ran", browser_act: "ran on the page", desktop_act: "ran", comment_issue: "commented", close_issue: "closed",
  merge_pr: "merged", land: "landed", open_pr: "opened the pull request", push_direct: "pushed", close_item: "closed", run_tool: "done",
  break_out: "moved to its own task", save_routine: "saved the routine" };
export const resultOf = (review) => {
  if (review?.Kind !== "action" || !["approved", "edited"].includes(review?.Status)) return null;
  let p = {};
  try { p = JSON.parse(review.FinalText || review.DraftText || "{}") || {}; } catch { p = {}; }
  const r = p.result || {}, url = r.url || (/https?:\/\/\S+/.exec(String(r.said || "")) || [""])[0].replace(/[.,)]+$/, "");
  // ...a yes the page refused (browsergate._perform's `refused`) is over, and did nothing: it never reads "ran on the page"
  if (r.refused) return { said: "Approved · not done", what: String(r.refused), url: "", command: String(p.command || "") };
  const what = String(p.about || p.what || r.performed || r.commented || r.closed || r.merged || (r.task || r.source ? r.said : "") || "").trim();
  return { said: `Approved · ${VERB[p.action] || "done"}`, what, url, command: String(p.command || "") };
};

// ONE CARD FOR A TURN'S HELD STEPS (the owner, 2026-11-09: "this should be one action button and one card. make it smaller and more
// combined"): the shell steps one agent turn had held (shellgate.turn_of - the owner's last line when it held them) are one action. One title,
// why it waits said once, the folder once, the steps numbered, every command under one "Show the commands", one Approve that runs them in order
// (/api/reviews/steps) and one Dismiss. A step held after the owner wrote again is another turn's card. Each item: { key, reviews }
const isHeldStep = (r) => proposalFrom(r)?.action === "shell_act";
// ...a proposal the owner pressed, kept as its pressed card (PassedCard) - a close-out's press is its own card's (closeoutState)
export const decidedAsk = (r) => r?.Kind === "action" && ["approved", "edited", "rejected"].includes(r.Status) && !isHeldStep(r) && !closeoutOf(r);
const turnKey = (r) => { const p = proposalFrom(r); return p?.turn == null ? `rv${r.ReviewId}` : `${r.TaskId}|${p.sid || ""}|${p.turn}|${p.where || p.cwd || ""}`; };
export const heldGroups = (rows) => {
  const out = [], at = new Map();
  for (const r of rows || []) {
    if (!isHeldStep(r)) { out.push({ key: `rv${r.ReviewId}`, reviews: [r] }); continue; }
    const k = turnKey(r);
    if (at.has(k)) at.get(k).reviews.push(r); else { const g = { key: `held:${r.ReviewId}`, held: true, reviews: [r] }; at.set(k, g); out.push(g); }
  }
  return out;
};
// ...what the card says: its title, the one why, the folder, each step's words and state, and how its press ended
export const heldCard = (reviews) => {
  const rs = [...(reviews || [])].sort((a, b) => a.ReviewId - b.ReviewId), ps = rs.map((r) => proposalFrom(r) || {});
  const n = rs.length, lead = (p) => heldLead(p).lead;
  const whys = [...new Set(ps.map((p) => p.why || "it leaves this computer"))];
  // ...a step whose press FAILED is over and its agent's (shellgate.approve_steps, the owner 2026-11-10: "no idea what this is. it's broken"):
  // settled with its error kept, never waiting under a lit Approve
  const steps = rs.map((r, i) => ({ id: r.ReviewId, text: lead(ps[i]), command: String(ps[i].command || ""),
    state: r.Status === "pending" ? "waiting" : ["approved", "edited"].includes(r.Status) ? "ran" : r.ActError ? "failed" : "dismissed", result: resultOf(r),
    error: String(r.ActError || "") }));
  const waiting = steps.filter((s) => s.state === "waiting"), ran = steps.filter((s) => s.state === "ran");
  // ...the step a press failed on, in one sentence: the card's own "Step 2 failed:" leads it, never a second "The held step failed:" after it
  const bad = steps.find((s) => s.state === "failed") || waiting.find((s) => s.error), k = steps.indexOf(bad) + 1;
  const why = bad ? bad.error.replace(/^The held step failed:\s*/, "") : "";
  const pressed = waiting.length ? null : steps.some((s) => s.state === "failed") ? "failed" : ran.length ? "approved" : "dismissed";
  return { title: n > 1 ? `${lead(ps[0])} - ${n} steps` : lead(ps[0]), why: `Held before it ran - ${whys.join("; ")}.`,
    folder: ps[0].where || ps[0].cwd || "the agent's folder", steps, waiting: waiting.map((s) => s.id), pressed,
    said: pressed === "approved" ? (n > 1 ? `${ran.length} of ${n} ran` : "it ran")
      : pressed === "failed" ? `${n > 1 ? `${ran.length} of ${n} ran, step ${k} failed` : "it failed"} - the agent was told and goes on from there`
      : pressed === "dismissed" ? "nothing was run" : ran.length ? `${ran.length} of ${n} ran` : "",
    url: ran.map((s) => s.result?.url).filter(Boolean).at(-1) || "",
    error: !bad ? "" : n > 1 ? `Step ${k} failed: ${why}` : `It failed: ${why}` };
};
// ...and once pressed it stays in the turn, pressed, until the owner writes again (general.press_lines draws it as a line from then on)
export const keptHeld = (reviews, comments) => {
  const last = (comments || []).filter((c) => c.ActorType === "assistant_user").map((c) => String(c.CreatedAt || "")).sort().at(-1) || "";
  return (reviews || []).filter((r) => isHeldStep(r) && r.Status !== "pending" && String(r.DecidedAt || "") > last);
};
// ...AND ONCE PRESSED IT IS THE CARD IN THE TURN THAT HELD IT, for good (the owner, 2026-11-09: "compact the land" - after the owner wrote again
// it gave way to a one-line summary, and the task's comments carry no owner line to tell "since" by): `asks` the cards still waiting - every
// other ask, and a turn's held steps while any of them waits (the ones that ran ticked in it) - and `past` each turn's pressed card, with when
// its turn held it (GeneralWorkspace's turn cards)
// ...AND SO DOES EVERY OTHER PROPOSAL ONCE DECIDED (decidedAsk; the owner, 2026-11-10: "it should stay where it is with buttons grayed out"): an
// approved playbook left its turn at the press, and Taskuary's note to its agent stood where it had been
export const splitHeld = (reviews, asks) => {
  const gs = heldGroups([...(reviews || []).filter(isHeldStep), ...(asks || []).filter((r) => !isHeldStep(r))].sort((a, b) => a.ReviewId - b.ReviewId));
  const waits = (g) => g.reviews.some((r) => r.Status === "pending");
  return { asks: gs.filter(waits), past: gs.filter((g) => !waits(g)).map((g) => ({ ...g, at: g.reviews[0].CreatedAt || "" })) };
};
