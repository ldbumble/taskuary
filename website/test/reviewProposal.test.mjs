import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { heldActsLine, proposalPresentation, reviewStatusLabel, resultOf, reviewText } from "../src/reviewProposal.js";

const playbook = {
  Kind: "action",
  Title: "Pto",
  DraftText: JSON.stringify({
    action: "write_playbook",
    slug: "run-manual-pto-import",
    text: "# Run manual PTO import\nwhen: files are waiting\n",
  }),
};

test("a playbook review is a save process, not a reply", () => {
  const shown = proposalPresentation(playbook);
  assert.equal(shown.kind, "playbook");
  assert.equal(shown.title, "Playbook · Run manual PTO import");
  assert.equal(shown.destination, "Reports → Playbooks → run-manual-pto-import.md");
  assert.equal(shown.approveLabel, "Approve");          // one word for every proposal (buttons.json approve.states.action)
  assert.match(shown.context, /nothing will be sent/);
});

test("a playbook proposed as new names the file its title files it under", () => {
  // playbooks.write files slug "new" under slugify(title): the card said new.md over a playbook saved as send-our-w-9-....md
  const review = { Kind: "action", DraftText: JSON.stringify({ action: "write_playbook", slug: "new",
    text: "# Send our W-9 to a customer who asks\nwhen: a customer asks for our W-9\n" }) };
  assert.equal(proposalPresentation(review).destination, "Reports → Playbooks → send-our-w-9-to-a-customer-who-asks.md");
});

test("a workflow's write waiting for the yes reads as what it writes and where, never its JSON", () => {
  const review = { Kind: "action", Reason: "the workflow asks to write Onboarding/new-starter-checklist.txt on Network file share",
    DraftText: JSON.stringify({ action: "run_tool", type: "smb_write", connector_id: 44, path: "Onboarding/new-starter-checklist.txt",
      text: "Start-day checklist\nJordan Pike - Finance", why: "workflow Monday onboarding run step Checklist", flow_run: { run_id: 4 } }) };
  const p = proposalPresentation(review);
  assert.equal(p.title, "A routine step waits for your yes");
  assert.equal(p.destination, "Onboarding/new-starter-checklist.txt · smb write");
  assert.equal(p.readOnly, true);
  assert.equal(reviewText(review), "Start-day checklist\nJordan Pike - Finance");
  const other = { Kind: "action", DraftText: JSON.stringify({ action: "run_tool", type: "treg_call", endpoint: "e1", args: { q: "x" } }) };
  assert.equal(reviewText(other), 'endpoint: e1\nargs: {"q":"x"}');
  assert.doesNotMatch(reviewText(other), /"action"/);
});

test("the editable review body is the playbook markdown, not its action envelope", () => {
  assert.equal(reviewText(playbook), "# Run manual PTO import\nwhen: files are waiting\n");
  assert.equal(reviewText({ Kind: "draft", DraftText: "Thanks." }), "Thanks.");
});

test("even an unreadable action is never presented as a reply", () => {
  const shown = proposalPresentation({ Kind: "action", DraftText: "not json" });
  assert.equal(shown.kind, "action");
  assert.equal(shown.approveLabel, "Approve");
  assert.match(shown.context, /nothing will be sent/);
});

// The queue's chip printed the DB's own word for a verdict - "closed_unsent", "no_reply" - at the
// owner, who never chose either of those words (2026-09-10 audit).
test("a verdict is shown in the words the owner used, never the column value", () => {
  assert.equal(reviewStatusLabel("closed_unsent"), "closed without sending");
  assert.equal(reviewStatusLabel("no_reply"), "no reply needed");
  assert.equal(reviewStatusLabel("superseded"), "overtaken");
  assert.equal(reviewStatusLabel("pending"), "waiting on you");
  assert.equal(reviewStatusLabel("some_new_state"), "some new state");   // never blank, never a column name
  assert.equal(reviewStatusLabel(null), "");
});

// the ledger's facts about a kind of work reach its playbook as a proposal: the card shows the page, and says where it goes (build step 5)
test("an amend_playbook proposal shows the page and saves to its playbook", () => {
  const review = { Kind: "action", DraftText: JSON.stringify({ action: "amend_playbook", slug: "vendor-onboarding", text: "# Vendor onboarding\nwhen: x\n\n- ask first" }) };
  assert.equal(reviewText(review), "# Vendor onboarding\nwhen: x\n\n- ask first");
  const p = proposalPresentation(review);
  assert.equal(p.kind, "playbook");
  assert.equal(p.title, "Playbook · Vendor onboarding");
  assert.match(p.destination, /vendor-onboarding\.md/);
  assert.match(p.context, /ledger/);
});

// the owner, 2026-10-25: "browser acts that can't be undone (submit, pay, delete, send) wait as a proposal the owner presses" - the card
// says what the browser would do and on which page, in words, with the command under it; Approve runs it there (browsergate.perform)
test("a held browser act reads as what it does and where, never its JSON", () => {
  const review = { Kind: "action", Reason: "held before it ran, in the agent's browser: pays the $412.50 order on toll.example - it can't be undone",
    DraftText: JSON.stringify({ action: "browser_act", sid: "run1", args: ["click", "@e12"], command: "agent-browser click @e12",
      url: "https://pay.toll.example/checkout/review", site: "toll.example", what: "pays the $412.50 order on toll.example" }) };
  const shown = proposalPresentation(review);
  assert.equal(shown.title, "The agent's browser waits for your yes");
  assert.equal(shown.destination, "https://pay.toll.example/checkout/review");
  assert.equal(shown.approveLabel, "Approve");
  assert.equal(shown.readOnly, true);
  // the what is the context line (Reason) already; the box is the exact command, once (2026-10-25)
  assert.equal(reviewText(review), "Approve runs: agent-browser click @e12");
  assert.equal((shown.context.match(/pays the \$412\.50/g) || []).length, 1);
});

// ...and the same for an app on the owner's desktop (agentdesktop.py, 2026-10-31): Approve runs that exact agent-desktop command
test("a held desktop act reads as what it does, with the exact command under it", () => {
  const review = { Kind: "action", Reason: 'held before it ran, on your desktop: sends the reply to Erin Blake in the mail app - it can\'t be undone',
    DraftText: JSON.stringify({ action: "desktop_act", sid: "run1", args: ["click", "@s8f3k2p9:e8"], command: "agent-desktop click @s8f3k2p9:e8",
      what: "sends the reply to Erin Blake in the mail app" }) };
  const shown = proposalPresentation(review);
  assert.equal(shown.title, "The agent's desktop step waits for your yes");
  assert.equal(shown.destination, "an app on your desktop");
  assert.equal(shown.approveLabel, "Approve");
  assert.equal(shown.readOnly, true);
  assert.equal(reviewText(review), "Approve runs: agent-desktop click @s8f3k2p9:e8");
});

// A TRACKER ITEM'S CLOSE-OUT (trackers.py, 2026-10-25): the card says where it goes and the done state the tracker names - or that it
// is the comment alone, before the press
test("a Jira close-out reads as the comment and the move to the tracker's own done state", () => {
  const review = { Kind: "action", DraftText: JSON.stringify({ action: "close_item", tracker: "jira", item: "NW-12", status: "Done",
    text: "Fixed - tonight's export will be full.", closeout: true }) };
  const p = proposalPresentation(review);
  assert.equal(p.kind, "closeout");
  assert.equal(p.destination, "NW-12 in Jira → Done");
  assert.equal(p.approveLabel, "Approve");
  assert.match(p.then, /posts the comment on NW-12 in Jira and moves it to Done/);
  assert.equal(reviewText(review), "Fixed - tonight's export will be full.");
});

test("a tracker with no done state to move to says so, and the press is the comment alone", () => {
  const review = { Kind: "action", DraftText: JSON.stringify({ action: "close_item", tracker: "monday", item: "4410", status: null,
    no_done: "its status column \"Stage\" marks no label as done", text: "Shipped.", closeout: true }) };
  const p = proposalPresentation(review);
  assert.equal(p.destination, "4410 in Monday · comment only");
  assert.match(p.context, /marks no label as done, so Approve posts the comment alone/);
  assert.doesNotMatch(p.then, /moves/);
});

test("an agent's tracker act names the item it lands on", () => {
  const review = { Kind: "action", Reason: "the agent proposes to move NW-12 in Linear to In Review",
    DraftText: JSON.stringify({ action: "run_tool", type: "linear_move", connector_id: 56, item: "NW-12", status: "In Review" }) };
  const p = proposalPresentation(review);
  assert.equal(p.destination, "NW-12 · linear move");
  assert.equal(reviewText(review), "status: In Review");
});

// A HELD DELETE (shellgate.deletes, the desktop stress test 2026-11-03): its card says where it aims, and the line over it is no browser's
test("a held delete names the folder it aims at, and the line over the card says what was held", () => {
  const del = { Kind: "action", Reason: "held before it ran, in the agent's shell: delete notes in Downloads - it can't be undone",
    DraftText: JSON.stringify({ action: "shell_act", sid: "g1", command: 'rm -rf "/home/alex/Downloads/notes"', cwd: "/home/alex/.taskuary/scratch",
      what: "delete notes in Downloads", why: "it can't be undone", where: "/home/alex/Downloads" }) };
  assert.equal(proposalPresentation(del).destination, "/home/alex/Downloads");
  const push = { Kind: "action", DraftText: JSON.stringify({ action: "shell_act", sid: "g1", command: "git push", cwd: "/work/ledger", why: "it leaves this computer" }) };
  assert.equal(proposalPresentation(push).destination, "/work/ledger");
  assert.match(proposalPresentation(push).context, /it leaves this computer/);
  const browse = { Kind: "action", DraftText: JSON.stringify({ action: "browser_act", sid: "g1", command: "agent-browser click @e1" }) };
  assert.doesNotMatch(heldActsLine([del]), /browser/);
  assert.match(heldActsLine([del]), /^This step waits for your yes\./);
  assert.match(heldActsLine([browse]), /^The agent's browser waits/);
  assert.match(heldActsLine([browse, del]), /^These steps wait/);
});

// THE OWNER, 2026-11-09: a held run's card was only "Approve runs: <a long PowerShell line>" with nothing saying why. It leads with the
// agent's own words for the call, else what the gate read it as, and why it waits; the raw line is folded under "Show the command"
test("a held shell step leads with what it does and why, its command folded", () => {
  const p = (x) => proposalPresentation({ Kind: "action", Reason: "held before it ran, in the agent's shell: delete build in ledger - it can't be undone",
    DraftText: JSON.stringify({ action: "shell_act", sid: "s1", command: "Remove-Item -Recurse -Force C:\work\ledger\build", what: "delete build in ledger",
      why: "it can't be undone", ...x }) });
  const own = p({ about: "clean checkout before the release build" });
  assert.equal(own.lead, "Clean checkout before the release build");
  assert.equal(own.leadWhy, "Held before it ran - it can't be undone: it would delete build in ledger.");
  assert.equal(own.folded, true);
  const gate = p({});
  assert.equal(gate.lead, "Delete build in ledger"); assert.equal(gate.leadWhy, "Held before it ran - it can't be undone.");
  const card = readFileSync(new URL("../src/ReviewDecision.jsx", import.meta.url), "utf8");
  assert.match(card, /\{cmdOpen \? "Hide the command" : "Show the command"\}/);
  assert.match(card, /\.\.\.\(proposal\?\.folded && !cmdOpen \? \{ display: "none" \} : \{\}\)/, "the command's box stays folded until asked for");
});

test("a break-out card says the new task and what moves to it, and its result names the task", () => {
  const p = { action: "break_out", title: "Renew the Trainly seats", summary: "Erin's ask about seats, apart from the invoice", messages: [12], items: [],
    moves: "Erin Blake: can we renew the Trainly seats before Friday?" };
  assert.equal(reviewText({ Kind: "action", DraftText: JSON.stringify(p) }),
    "Erin's ask about seats, apart from the invoice\n\nErin Blake: can we renew the Trainly seats before Friday?");
  const card = proposalPresentation({ Kind: "action", DraftText: JSON.stringify(p), Reason: "the agent proposes to move 1 message to a task of its own" });
  assert.deepEqual([card.title, card.destinationLabel, card.destination, card.readOnly], ["Move this part to a task of its own", "Its own task", "Renew the Trainly seats", true]);
  const done = { ...p, result: { task: 9, ref: "TQ-0009", said: "TQ-0009 is the new task: Renew the Trainly seats" } };
  assert.deepEqual(resultOf({ Kind: "action", Status: "approved", FinalText: JSON.stringify(done) }),
    { said: "Approved · moved to its own task", what: "TQ-0009 is the new task: Renew the Trainly seats", url: "", command: "" });
});

test("a save-as-routine card shows the script whole and read-only, with when it runs on its own line", () => {
  const script = "import sys, json\nprint(json.dumps([]))";
  const p = { action: "save_routine", title: "Late fees", script, runs: "daily 07:00", prompt: "Say which invoices carry a fee.",
    reads: { type: "local_file", path: "C:/exports/ar-*.csv" } };
  const rv = { Kind: "action", DraftText: JSON.stringify(p), Reason: 'the agent proposes to save a script as the routine "Late fees", to run daily 07:00' };
  assert.equal(reviewText(rv), `It reads: C:/exports/ar-*.csv · local file\n\n${script}\n\nThen an AI step reads what it printed: Say which invoices carry a fee.`);
  assert.equal(reviewText({ Kind: "action", DraftText: JSON.stringify({ action: "save_routine", title: "Late fees", script }) }), script);
  const card = proposalPresentation(rv);
  assert.deepEqual([card.title, card.destinationLabel, card.destination, card.readOnly], ["Save this as a routine", "It runs", "daily 07:00 · Late fees", true]);
  const done = { ...p, result: { source: 7, link: "#report=7", said: 'Saved the routine "Late fees" - it runs daily 07:00.' } };
  assert.deepEqual(resultOf({ Kind: "action", Status: "approved", FinalText: JSON.stringify(done) }),
    { said: "Approved · saved the routine", what: 'Saved the routine "Late fees" - it runs daily 07:00.', url: "", command: "" });
});

test("a Python script is a source type on this computer, its script in a multi-line box", () => {
  const view = readFileSync(new URL("../src/ReportsView.jsx", import.meta.url), "utf8");
  assert.match(view, /python_script: \[\["the script - Python, run as written[^"]*", "script", "multiline",/);
  assert.match(view, /\["This computer", \["local_file", "python_script", "sqlite", "mcp"\]\]/);
  assert.match(readFileSync(new URL("../src/reportWords.js", import.meta.url), "utf8"), /python_script: "Python script on this computer"/);
});

test("the section says Also waiting on you only under something else that waits", () => {
  const page = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /\$\{asksBelow \? "Also waiting on you" : "Waiting on you"\}\$\{liveAsks > 1 \? ` · \$\{liveAsks\}` : ""\}/);
  assert.match(page, /const asksBelow = !!\(pendingReview \|\| moreDrafts\.length \|\| owesEmails/);
});
