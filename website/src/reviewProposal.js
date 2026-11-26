import { label } from "./buttons.js";
import { whyFailed } from "./stepWhy.js";

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
// "Save skill" were three more names for the same press
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

// a skill's file name from its title - skills.slugify's rule: lower case, every other run of characters one "-", cut, trimmed
const slugify = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 60).replace(/^-+|-+$/g, "");

// a proposal whose words ARE a skill's SKILL.md: a new one its agent drafted, or a change to one he has (the ledger's block, its lessons)
export const PAGES = new Set(["save_skill"]);

// a tool run's place (proposals.WHERE_KEYS, the same order) and what it carries: the text it writes, the query or script it runs,
// else its other settings one per line - the plumbing (the action, the run it belongs to, the connection id) left out
const WHERE_KEYS = ["path", "to", "folder", "table", "url", "bucket", "key", "container", "blob", "channel", "list", "database", "item"];
const PLUMBING = new Set(["action", "type", "flow_run", "connector_id", "why", "network"]);
const whereKey = (p) => (p?.network ? "" : WHERE_KEYS.find((x) => p?.[x]) || "");
export const toolWhere = (p) => {
  if (p?.network) return String(p.network);            // ...a post says its network as he knows it (proposals.queue), never "x post"
  const k = whereKey(p);
  const sys = String(p?.type || "").replace(/_/g, " ");
  return k ? `${String(p[k])} · ${sys}` : sys || "a connected system";
};
// ...EVERY FIELD THE PRESS RUNS IS ON THE CARD (red team F1): a `script` beside harmless `text` was never drawn and ran at the press. The box
// holds the words alone - the words are what an edit sends - and every other field it runs stands beside them as a read-only row (toolFacts).
// Only the plumbing, and the place the "Where" line already names, are left out
const BODY_KEYS = ["text", "body", "message", "query", "script"];
const bodyKey = (p) => BODY_KEYS.find((x) => p?.[x] != null && p[x] !== "");
// ...AND A THING NAMED WITH ITS ID IS ONE ROW, BY NAME (reports.CHECKS; walk 22, 2026-11-25: "vendor id: 58 / account id: 7" was all a bill's card
// said): "Vendor: Payworth (id 58)" - the id still on the card, beside what it is the id of
const facts = (p) => { const k = bodyKey(p), w = whereKey(p), said = (v) => (typeof v === "string" ? v : JSON.stringify(v));
  const named = (x) => x.endsWith("_id") && p[x.slice(0, -3)] != null && p[x.slice(0, -3)] !== "";
  return Object.entries(p || {}).filter(([x, v]) => x !== k && x !== w && !PLUMBING.has(x) && v !== "" && v != null && !named(x))
    .map(([x, v]) => ({ label: upFirst(x.replace(/_/g, " ")), now: said(v) + (p[`${x}_id`] != null && p[`${x}_id`] !== "" ? ` (id ${said(p[`${x}_id`])})` : "") })); };
export const toolFacts = (p) => (bodyKey(p) ? facts(p) : []);
export const toolBody = (p) => { const k = bodyKey(p); return k ? String(p[k]) : facts(p).map((f) => `${f.label.toLowerCase()}: ${f.now}`).join("\n"); };

// A CHANGE'S CARD (workflows.change_card): its new words to edit ({key, label, was, now}) and the facts it changes besides ({label, was, now}),
// led by the title and why it changes in one line
const changeOf = (title, p) => ({ title, lead: title, leadWhy: p?.why ? upFirst(String(p.why).replace(/[.\s]*$/, ".")) : "", destination: "",
  texts: Array.isArray(p?.texts) ? p.texts : [], rows: Array.isArray(p?.rows) ? p.rows : [], bare: Array.isArray(p?.texts) });
const onOff = (v) => (v === true || v === "1" ? "on" : v === false || v === "0" ? "off" : String(v ?? ""));
// ...each switch a settings card changes, as it was and as it will be: its rows while it waits, and what it says it changed once pressed
const settingRows = (p) => (Array.isArray(p?.changes) ? p.changes : []).filter((c) => c && c.name)
  .map((c) => ({ label: `${c.connector ? `${c.connector}: ` : ""}${upFirst(String(c.name).replaceAll("_", " "))}`, was: c.was == null ? "" : onOff(c.was), now: onOff(c.value) }));
const rowSaid = (x) => (x.was ? `${x.was} → ${x.now}` : x.now);
export const reviewText = (review) => {
  const proposal = proposalFrom(review);
  if (CLOSEOUT[proposal?.action]) return proposal.text || "";      // never the JSON envelope: an empty box sends nothing extra
  // a workflow repair reads as what was wrong and what changes, never the step list's JSON (flow.repair)
  // ...a change's new words - its boxes are its own fields (texts); the box itself is drawn only for a card filed before them
  if (["repair_workflow", "change_setup"].includes(proposal?.action)) return Array.isArray(proposal.texts) ? proposal.texts.map((t) => t.now).join("\n\n")
    : [proposal.why, proposal.changes].filter(Boolean).join("\n\n");
  if (proposal?.action === "run_tool") return toolBody(proposal);
  // a part of the task going to a task of its own (proposals.break_out): the new task's title, what it is, and each thing that moves
  if (proposal?.action === "break_out") return [proposal.summary, proposal.moves].filter(Boolean).join("\n\n");
  // a script to keep as a routine (proposals 'save_routine'): what feeds it, the script whole, and what the AI step is asked about its output
  if (proposal?.action === "save_routine" && !proposal.script) return [String(proposal.prompt || ""), proposal.based_on ? `Built from: ${proposal.based_on}` : ""].filter(Boolean).join("\n\n");
  if (proposal?.action === "save_routine") return [
    proposal.reads ? `It reads: ${toolWhere(proposal.reads)}` : "", String(proposal.script || ""),
    proposal.prompt ? `Then an AI step reads what it printed: ${proposal.prompt}` : ""].filter(Boolean).join("\n\n");
  // the WHAT is the context line already (proposals.queue's Reason); the box is the exact command Approve runs, once - with no AI the card
  // said "agent-browser click @e12" three times over (2026-10-25)
  if (["browser_act", "shell_act", "desktop_act"].includes(proposal?.action)) return proposal.command ? `Approve runs: ${proposal.command}` : proposal.what || "";
  if (proposal?.action === "page_step") return "";             // ...his step is the card's own line: no box of words under it
  if (PAGES.has(proposal?.action) && proposal.text) return proposal.text;
  // ...AND NO CARD SHOWS ITS OWN JSON (the card round, 2026-11-12: a setting's change stood as `{"action": "settings", "changes": [...]}` in a
  // box he could type into): any other proposal's box holds what it carries, in words - or nothing, and the card draws no box (`bare`)
  return proposal ? toolBody(Object.fromEntries(Object.entries(proposal).filter(([k]) => k !== "changes"))) : review?.DraftText || "";
};
// a setting's change in words: "poll minutes to 15" (proposals.setting_changes: {name, value} or {connector, name, value})
export const changeWords = (p) => (Array.isArray(p?.changes) ? p.changes : []).filter((c) => c && c.name)
  .map((c) => `${c.connector ? `${c.connector}: ` : ""}${String(c.name).replaceAll("_", " ")} to ${c.value === true ? "on" : c.value === false ? "off" : String(c.value)}`).join("; ");
// ...and what any proposal does, as the server worded it for its card (proposals.queue's Reason: "the agent proposes to <what> - <why>"),
// without the lead that names who asked
const saysOf = (review) => String(review?.Reason || "").replace(/^the (agent proposes|workflow asks) to /, "").trim();
// ...AS EVERY CARD'S LEAD, one road (design round 5, 2026-11-19; round 4 did routines): what Approve does in words, bold over the card, and that
// nothing happens before it - a step in a connected system, a part moved out, a routine's change and any other proposal alike
// ...said once (the owner, 2026-11-24: "it says on top it changes 3 times ... we don't need it a bunch of times"): no "nothing happens until you
// approve" under it - nothing on any card acts before its press, and the press says what it does
const leadOf = (review) => { const says = saysOf(review); return says ? { lead: upFirst(says), leadWhy: "" } : {}; };

// WHAT A WAITING CARD SAYS OVER ITSELF IN THE CHAT - what its Approve does, in one line: a drafted skill's, a held act's. Said with the one
// card, wherever that card stands (a turn of the task's chat, the foot of a walk's)
const PAGE_NOTE = "Approve saves this skill to Reports → Skills, where triage and the next agent find it by its description. Nothing is sent to anyone.";
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
// ...ONE LOOK FOR EVERY HELD STEP (the card round, 2026-11-12: a held press in the agent's browser stood in the chat as "On the agent's browser"
// over `Approve runs: agent-browser click @e12` - what it would press was the reason line the chat does not draw): a shell step, a browser
// act and a desktop act each lead with what they do
const HELD = { shell_act: ["Run a command in the agent's shell", "it leaves this computer"], browser_act: ["Do a step in the agent's browser", "it can't be undone"],
  desktop_act: ["Do a step in an app on your desktop", "it can't be undone"] };
export const heldLead = (p) => {
  const about = String(p?.about || "").trim(), what = String(p?.what || "").trim(), [lead, why] = HELD[p?.action] || HELD.shell_act;
  return { lead: upFirst(about || what) || lead,
    leadWhy: `Held before it ran - ${p?.why || why}${about && what ? `: it would ${what}` : ""}.`, folded: !!p?.command };
};

// ...AND A HELD PRESS THAT SENDS A FORM SHOWS WHAT IT SENDS (walk 15 S12: "check it on the card before you press" over a card that showed only
// `agent-browser click @e12`): the boxes the agent filled on that page, kept with the card (browsergate `fields`) - its short lines first, the
// first as the title, then its long words, and the picture a file box holds where the task made it. Null when the form holds nothing to read
const FAKE = /^.*[\\/]/;
export const heldPost = (p) => {
  const fs = (Array.isArray(p?.fields) ? p.fields : []).filter((f) => f && !["checkbox", "radio", "hidden", "password"].includes(f.t) && String(f.v ?? "").trim());
  const lines = fs.filter((f) => f.t !== "textarea" && f.t !== "file").map((f) => String(f.v).trim()), body = fs.filter((f) => f.t === "textarea").map((f) => String(f.v)).join("\n\n");
  const picture = String(fs.find((f) => f.t === "file")?.v || "").replace(FAKE, "");
  return lines.length || body || picture ? { title: lines[0] || "", lines: lines.slice(1), body, picture } : null;
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
    const title = (String(proposal.text || "").match(/^#\s+(.+)$/m) || String(proposal.text || "").match(/^name:\s*(.+)$/m))?.[1]?.trim();
    // "new" (or none) is filed under its own name (skills.write -> slugify), so that is the folder it names: the card said new.md
    // over a W-9 skill the approve then saved as send-our-w-9-to-a-customer-who-asks (walk 2026-10-21)
    const given = String(proposal.slug || "").trim();
    const slug = (given && given !== "new" ? given : slugify(title)) || "skill";
    const amend = !!(proposal.block || proposal.lessons || proposal.was_text);          // a change to one he has, not a new one
    return {
      kind: "skill",
      title: title ? `Skill · ${title}` : "New skill",
      context: amend ? "What was learned about this kind of work, added to its skill · nothing is sent"
        : "Skill proposal · nothing will be sent to the conversation",
      destinationLabel: "Save to",
      destination: `Reports → Skills → ${slug}`,         // where skills live (SkillShelf.jsx)
      // ...the page it replaces, where there is one (proposals.change_card): the box marks where this one changes it
      ...(proposal.was_text ? { was: String(proposal.was_text) } : {}),
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
    ...leadOf(review),
    destinationLabel: "Where",
    destination: toolWhere(proposal),
    rows: toolFacts(proposal),
    approveLabel: APPROVE,
    busyLabel: "running…",
    rejectLabel: "Dismiss",
    readOnly: true,
  };
  // A HELD BROWSER ACT (browsergate.py, 2026-10-25): what the agent's browser would do and on which page, in words - Approve runs that
  // exact command there, so the words are read-only like a tool run's
  // A STEP ON THE AGENT'S PAGE ONLY HE CAN DO (pagestep.py, the owner 2026-11-25: "the browser should be treated like a card, so only one at a
  // time"): what he does and on which site, in the words it was handed over with - its press is his I'm done, the step's own hand-back
  if (proposal?.action === "page_step") return {
    kind: "action",
    title: "Your step on the agent's page",
    context: "",
    // ...a sign-in the fill page can type says that way too, on this card alone (`fill`: ReviewDecision's FillLink)
    lead: upFirst(String(proposal.what || "A step on the page only you can do")), fill: !!proposal.fill,
    leadWhy: proposal.fill ? "The page is open beside this card - sign in there" : "The page is open beside this card - do the step there, then press I'm done.",
    destinationLabel: "On",
    destination: proposal.site || "",
    approveLabel: "I'm done",
    busyLabel: "handing back…",
    rejectLabel: "Dismiss",
    readOnly: true, bare: true,
  };
  if (proposal?.action === "browser_act") return {
    kind: "action",
    title: "The agent's browser waits for your yes",
    context: review.Reason || "Held before it ran · it can't be undone",
    ...heldLead(proposal),
    destinationLabel: "On",
    // ...the SITE, never its raw address (the owner's live app, 2026-11-19: "On https://app.box.example/folder/..." under the step)
    // ...by the name the server gives it (its `name`: signin.site_name - a bare address by its page's title), never "127.0.0.4"
    destination: proposal.name || proposal.site || proposal.url || "the agent's browser",
    post: heldPost(proposal),
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
    ...heldLead(proposal),
    destinationLabel: "On",
    destination: "an app on your desktop",
    approveLabel: APPROVE,
    busyLabel: "running…",
    rejectLabel: "Dismiss",
    readOnly: true,
  };
  // A PUBLIC COMMENT ON GITHUB (proposals 'comment_issue'): where it goes, its words his to change while it waits - what he left in the box is
  // what is posted (proposals.execute) - and its press named by what it does
  if (proposal?.action === "comment_issue") return {
    kind: "action",
    title: "Comment on GitHub",
    context: review.Reason || "Nothing is posted until you press Comment",
    destinationLabel: "On",
    destination: proposal.repo ? `${proposal.repo}${proposal.number != null ? `#${proposal.number}` : ""}` : "the issue or pull request this task came from",
    approveLabel: "Comment",
    bare: !reviewText(review).trim(),
    busyLabel: "Commenting…",
    rejectLabel: "Dismiss",
  };
  // A PULL REQUEST SAYS WHAT IT OPENS (the card gallery, 2026-11-25: its body alone, under "On this task"): its title, the repository and the
  // branch into its base, as the server read them for the press (ci.pr_plan) - its body the box, read-only as it goes
  if (proposal?.action === "open_pr" && proposal.pr) return {
    kind: "action",
    title: "Open a draft pull request",
    context: review.Reason || "Proposed · nothing is opened until you approve",
    ...leadOf(review),
    destinationLabel: "In",
    destination: proposal.pr.repo || "",
    rows: [{ label: "Title", now: proposal.pr.title }, ...(proposal.pr.branch ? [{ label: "Branch", now: `${proposal.pr.branch} → ${proposal.pr.base}` }] : [])],
    approveLabel: APPROVE,
    busyLabel: "opening…",
    rejectLabel: "Dismiss",
    readOnly: true,
    bare: !String(proposal.body || "").trim(),
  };
  // A PART OF THE TASK THAT IS ANOTHER MATTER (proposals.break_out, the owner 2026-11-10): the new task's title leads, what moves is read-only -
  // Approve runs the task page's own split with exactly those messages and to-dos
  if (proposal?.action === "break_out") return {
    kind: "action",
    title: "Move this part to a task of its own",
    context: review.Reason || "Proposed · nothing moves until you approve",
    ...leadOf(review),
    destination: "",
    approveLabel: APPROVE,
    busyLabel: "moving…",
    rejectLabel: "Dismiss",
    readOnly: true,
  };
  // A SCRIPT THE AGENT WROTE ON THE JOB, KEPT AS A ROUTINE (proposals 'save_routine', the owner 2026-11-10) - Approve saves exactly that as a
  // routine (workflows.save_script_routine) and runs nothing. SAID IN WORDS (design round 4, 2026-11-19: an ops manager was asked to approve
  // 60 lines of Python): what it does, when and where it runs, its steps - the script folded under "Show the script"
  // ...and a routine or report built from its instructions (no script): what it will do, and the skill or template it was built from, cited
  if (proposal?.action === "save_routine" && !proposal.script) return {
    kind: "action",
    title: `Create the ${proposal.kind || "routine"}${proposal.title ? ` "${proposal.title}"` : ""}`,
    context: review.Reason || "Proposed · nothing is saved until you approve",
    lead: upFirst(String(proposal.why || proposal.title || "A routine")),
    leadWhy: `Runs ${proposal.runs || "when you run it"}${proposal.based_on ? ` · built from ${proposal.based_on}` : ""}.`,
    destinationLabel: "It does",
    destination: String(proposal.prompt || ""),
    approveLabel: APPROVE,
    busyLabel: "saving…",
    rejectLabel: "Dismiss",
    readOnly: true,
  };
  if (proposal?.action === "save_routine") return {
    kind: "action",
    title: "Save this as a routine",
    context: review.Reason || "Proposed · nothing is saved or run until you approve",
    lead: upFirst(String(proposal.why || proposal.title || "A routine")),
    leadWhy: `Runs ${proposal.runs || "when you run it"}, on this computer${Array.isArray(proposal.steps) && proposal.steps.length
      ? `: ${proposal.steps.map((s, i) => (i ? String(s).toLowerCase() : String(s))).join(", then ")}` : ""}.`,
    folded: true, foldWord: "script",
    destinationLabel: "It runs",
    destination: `${proposal.runs || "when you run it"} · ${proposal.title || ""}`,
    approveLabel: APPROVE,
    busyLabel: "saving…",
    rejectLabel: "Dismiss",
    readOnly: true,
  };
  // ...a run's own repair, or its agent's change to the routine it runs (workflows.change_of): one card, the steps change only on Approve
  // ...EACH AS WHAT IT WILL BE (the owner, 2026-11-24: "to edit text it should show the edited text?"): its new words, each set its own box,
  // marked where they change (workflows.change_card: texts), what else changes read off (rows), and why in one line - never "old -> new"
  if (proposal?.action === "repair_workflow") return {
    kind: "action",
    context: proposal.flow_run ? "A step failed · the AI wrote a fix · the steps change only if you approve" : "Proposed · the routine changes only if you approve",
    ...changeOf(proposal.flow_run ? `Repair routine: ${proposal.title || "its steps"}` : `Change routine: ${proposal.title || "this routine"}`, proposal),
    approveLabel: APPROVE,
    busyLabel: "saving…",
    rejectLabel: "Dismiss",
  };
  // ...and a report's or dashboard's own setup changed the same way (workflows.setup_change): its question, schedule or name, old -> new
  if (proposal?.action === "change_setup") return {
    kind: "action",
    context: `Proposed · the ${proposal.kind || "report"} changes only if you approve`,
    ...changeOf(`Change ${proposal.kind || "report"}: ${proposal.title || `this ${proposal.kind || "report"}`}`, proposal),
    approveLabel: APPROVE,
    busyLabel: "saving…",
    rejectLabel: "Dismiss",
  };
  // A SETTING THE AGENT ASKS TO CHANGE (proposals 'settings'): which one and to what, in words, and why - Approve changes exactly that
  if (proposal?.action === "settings") return {
    kind: "action",
    title: "Change a setting",
    context: review.Reason || "Proposed · nothing changes until you approve",
    lead: Array.isArray(proposal.changes) && proposal.changes.some((c) => c && "was" in c) ? `Change ${proposal.changes.length > 1 ? "settings" : "a setting"}`
      : `Change ${changeWords(proposal) || "a setting"}`,
    leadWhy: proposal.why ? upFirst(String(proposal.why)) : "",
    destination: "",
    // ...each switch as it is and as it will be, read off - a fact, never words to type over (proposals.change_card: `was`)
    rows: settingRows(proposal),
    approveLabel: APPROVE,
    busyLabel: "saving…",
    rejectLabel: "Dismiss",
    readOnly: true,
    bare: true,
  };
  // ...AND ANY OTHER PROPOSAL SAYS WHAT IT DOES IN THE SERVER'S OWN WORDS FOR IT (the card round, 2026-11-12: "Action · land" over the proposal's
  // JSON): its lead is what the gate wrote on the review, its box what it carries - none where it carries nothing
  const says = saysOf(review), act = String(proposal?.action || "proposed action").replaceAll("_", " ");
  const said = leadOf(review);
  return {
    kind: "action",
    title: review.Subject || review.Title || upFirst(says) || "Proposed action",
    context: "Proposed action · nothing will be sent to the conversation",
    // ...and where its lead says it, no "Action · open pr" row under that - the proposal's own key is not a place
    ...(says ? { ...said, destinationLabel: "On", destination: "this task" } : { destinationLabel: "Action", destination: act }),
    approveLabel: APPROVE,
    busyLabel: "running…",
    rejectLabel: "Dismiss",
    readOnly: true,
    bare: !reviewText(review).trim(),
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
  break_out: "moved to its own task", save_routine: "saved the routine", repair_workflow: "changed the routine", change_setup: "changed it", settings: "changed",
  save_skill: "saved the skill" };
// ...and what it kept at the press: the proposal as he left it, with what it did (proposals.receipt) - null before
export const receiptOf = (review) => { try { return JSON.parse(review?.FinalText || "") || null; } catch { return null; } };
export const resultOf = (review) => {
  if (review?.Kind !== "action" || !["approved", "edited"].includes(review?.Status)) return null;
  let p = {};
  try { p = JSON.parse(review.FinalText || review.DraftText || "{}") || {}; } catch { p = {}; }
  // ...a link read off what it said keeps none of the quote or bracket around it (the Claude walk, 2026-11-19: "...ledger.git/'")
  const r = p.result || {}, url = r.url || (/https?:\/\/[^\s'"<>()\]]+/.exec(String(r.said || "")) || [""])[0].replace(/[.,)]+$/, "");
  // ...a yes the page refused (browsergate._perform's `refused`) is over, and did nothing: it never reads "ran on the page"
  if (r.refused) return { said: "Approved · not done", what: String(r.refused), url: "", command: String(p.command || "") };
  // ...a settings card by the switches it changed, each to what ("Poll minutes: 15 → 10")
  const set = p.action === "settings" ? settingRows(p).map((x) => `${x.label}: ${rowSaid(x)}`.replace(/\s+/g, " ")).join(" · ") : "";
  const what = String(p.about || p.what || set || r.performed || r.commented || r.closed || r.merged || (r.task || r.source ? r.said : "") || "").trim();
  return { said: `Approved · ${VERB[p.action] || "done"}`, what, url, command: String(p.command || "") };
};
// WHAT A PRESS DID, ON EVERY CARD THAT TOOK ONE, FROM ONE FUNCTION (the card gallery, 2026-11-25: a settings card he approved read "✓ Approved"
// and nothing of what changed; a tracker move "✓ Approved · Where NW-12 · jira move" - while a declared act's card read "✓ Commented"): its mark
// says what it did in the act's own word ("✓ Changed", "✓ Opened the pull request"), its line what and where, its link. A card he dismissed, or
// whose press failed, says that. {mark, label, line, url} - PassedCard and ReviewDecision both draw this
export const outcomeOf = (review) => {
  const done = resultOf(review), p = done && proposalPresentation(review), title = p?.lead || p?.title || "";
  const same = (a, b) => String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();
  // ...what it did where that is more than its title; else where, for a step held on a page or in a folder - a tool run's sentence names its place
  if (done) return { mark: "approved", label: `✓ ${upFirst(done.said.replace(/^Approved · (?!not done)/, ""))}`, url: done.url,
    line: (!same(done.what, title) && done.what) || (p?.destination && proposalFrom(review)?.action !== "run_tool" ? `${p.destinationLabel} ${p.destination}` : "") };
  return failedAsk(review) ? { mark: "failed", label: "✗ Failed", line: String(review.ActError), url: "" } : { mark: "dismissed", label: "✗ Dismissed", line: "Nothing was done.", url: "" };
};

// ONE CARD FOR A TURN'S HELD STEPS (the owner, 2026-11-09: "this should be one action button and one card. make it smaller and more
// combined"): the shell steps one agent turn had held (shellgate.turn_of - the owner's last line when it held them) are one action. One title,
// why it waits said once, the folder once, the steps numbered, every command under one "Show the commands", one Approve that runs them in order
// (the one decide door) and one Dismiss. A step held after the owner wrote again is another turn's card. Each item: { key, reviews }
const isHeldStep = (r) => proposalFrom(r)?.action === "shell_act";
// ...a proposal the owner pressed, kept as its pressed card (PassedCard) - a close-out's press is its own card's (closeoutState)
// ...and one whose press FAILED (verdicts: settled with its error, the owner 2026-11-16 - no Try again): the error is its line, its agent sets up what goes next
export const failedAsk = (r) => r?.Kind === "action" && r.Status === "superseded" && !!r.ActError;
export const decidedAsk = (r) => r?.Kind === "action" && (["approved", "edited", "rejected"].includes(r.Status) || failedAsk(r)) && !isHeldStep(r) && !closeoutOf(r);
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
export const READ_ALLOWED = "Allowed - this task may read that folder";
// ...THE FOLDER BY ITS NAME, where the step really runs (the judge's walk, 2026-11-19: a push card read "In C:\Users\...\scratch" while its
// command went into the ledger checkout): the folder a leading `cd` names, else the one it was held in - its last name only, and Taskuary's own
// work folder said as the agent's
const lastName = (p) => String(p || "").replace(/["']/g, "").replace(/[\\/]+$/, "").split(/[\\/]/).pop();
export const folderSaid = (p) => {
  const into = /^\s*cd\s+(?:\/d\s+)?("[^"]+"|'[^']+'|\S+)\s*(?:&&|;)/i.exec(String(p?.command || ""))?.[1];
  const name = lastName(into || p?.where || p?.cwd || "");
  return !name || name.toLowerCase() === "scratch" ? "the agent's own folder" : name;
};
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
  // ...and a step that RAN after it - the agent's retry, joined to this card - is the outcome (walk 21: a post that went out read "Failed")
  const after = steps.map((s) => s.state).lastIndexOf("ran");
  const bad = steps.find((s, i) => s.state === "failed" && i > after) || waiting.find((s) => s.error), k = steps.indexOf(bad) + 1;
  // ...the one line that says what went wrong (stepWhy.whyFailed), never a program's traceback (the walk, 2026-11-22: "It failed: Read tq3 in Temp
  // failed: Traceback (most recent call last):") - its agent hears the whole of it (general.failed)
  const why = bad ? whyFailed(bad.error.replace(/^The held step failed:\s*/, "")).replace(/^Why: /, "") : "";
  const pressed = waiting.length ? null : bad ? "failed" : ran.length ? "approved" : "dismissed";
  return { title: n > 1 ? `${lead(ps[0])} - ${n} steps` : lead(ps[0]), why: `Held before it ran - ${whys.join("; ")}.`,
    folder: folderSaid(ps[0]), place: ps[0].where || ps[0].cwd || "", steps, waiting: waiting.map((s) => s.id), pressed,
    // ...a read outside the task's folders runs nothing: its yes lets the task read there (readgate.ALLOWED, the owner 2026-11-16)
    said: pressed === "approved" ? (ps.every((p) => !p.command && p.reads?.length) ? READ_ALLOWED : n > 1 ? `${ran.length} of ${n} ran` : "it ran")
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
// approved skill left its turn at the press, and Taskuary's note to its agent stood where it had been
export const splitHeld = (reviews, asks) => {
  const gs = heldGroups([...(reviews || []).filter(isHeldStep), ...(asks || []).filter((r) => !isHeldStep(r))].sort((a, b) => a.ReviewId - b.ReviewId));
  const waits = (g) => g.reviews.some((r) => r.Status === "pending");
  return { asks: gs.filter(waits), past: gs.filter((g) => !waits(g)).map((g) => ({ ...g, at: g.reviews[0].CreatedAt || "" })) };
};
