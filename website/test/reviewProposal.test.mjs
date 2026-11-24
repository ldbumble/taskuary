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

test("a step's card shows every field its press runs - a script beside harmless words is drawn, never hidden behind them", () => {
  const review = { Kind: "action", DraftText: JSON.stringify({ action: "run_tool", type: "winrm", connector_id: 3, text: "Check the disk space",
    script: "Remove-Item C:\\ -Recurse", url: "https://box.example", path: "C:\\logs" }) };
  const shown = proposalPresentation(review), rows = Object.fromEntries(shown.rows.map((r) => [r.label, r.now]));
  assert.equal(reviewText(review), "Check the disk space");     // ...the box holds the words alone: an edit sends them, never a field's line
  assert.equal(rows.Script, "Remove-Item C:\\ -Recurse");       // ...the script it runs stands beside them, read off
  assert.equal(rows.Url, "https://box.example");                 // ...a second place too: the Where line names only the first
  assert.equal(shown.destination, "C:\\logs · winrm");
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
  // ...on the SITE, never its raw address (the owner's live app, 2026-11-19)
  assert.equal(shown.destination, "toll.example");
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
  assert.match(card, /\$\{cmdOpen \? "Hide" : "Show"\} the \$\{proposal\.foldWord \|\| "command"\}/);
  assert.match(card, /hidden: \(proposal\?\.folded && !cmdOpen\) \|\| proposal\?\.bare/, "the command's box stays folded until asked for");
});

// WALK 15 (S12): a held Submit on a post's form was "Publish your Ask HN post ..." over `agent-browser click @e12` - the agent said "check it on
// the card before you press" and the card had no words of the post. It carries what the press sends: the boxes the agent filled (`fields`)
test("a held press that sends a form shows the post it sends - title, words, picture - and keeps the command folded", () => {
  const p = { action: "browser_act", sid: "s1", args: ["click", "@e12"], command: "agent-browser click @e12", what: "publish your Ask HN post",
    fields: [{ k: "title", t: "text", v: "Ask HN: How do small finance teams track seat usage?" }, { k: "url", t: "text", v: "" },
      { k: "text", t: "textarea", v: "Invoices bill for a number of seats.\n\nHow do you count the ones in use?" },
      { k: "pic", t: "file", v: "C:\\fakepath\\seats.png" }, { k: "agree", t: "checkbox", v: "on" }] };
  const b = proposalPresentation({ Kind: "action", DraftText: JSON.stringify(p) });
  assert.deepEqual(b.post, { title: "Ask HN: How do small finance teams track seat usage?", lines: [],
    body: "Invoices bill for a number of seats.\n\nHow do you count the ones in use?", picture: "seats.png" });
  assert.equal(b.folded, true, "the command stays in its fold");
  assert.equal(proposalPresentation({ Kind: "action", DraftText: JSON.stringify({ ...p, fields: [] }) }).post, null, "a press with no form: no post");
});

// THE CARD ROUND, 2026-11-12 (every card kind drawn in the chat and read): the chat draws no reason line, so a held press in the agent's
// browser stood as "On the agent's browser" over `Approve runs: agent-browser click @e12`; a setting's change and any proposal with no look
// of its own stood as "Action settings" over its own JSON, in a box he could type into
test("every card says what it does in words: a held browser or desktop act leads as a shell step does, and no card shows its JSON", () => {
  const act = (p, Reason = "") => ({ Kind: "action", Reason, DraftText: JSON.stringify(p) });
  const b = proposalPresentation(act({ action: "browser_act", sid: "s1", args: ["click", "@e12"], command: "agent-browser click @e12", what: 'press "Submit order" on portal.vendor.example' }));
  assert.equal(b.lead, 'Press "Submit order" on portal.vendor.example'); assert.equal(b.leadWhy, "Held before it ran - it can't be undone."); assert.equal(b.folded, true);
  assert.equal(proposalPresentation(act({ action: "browser_act", sid: "s1", args: ["click"] })).lead, "Do a step in the agent's browser");
  assert.equal(proposalPresentation(act({ action: "desktop_act", sid: "s1", args: ["click"] })).lead, "Do a step in an app on your desktop");
  assert.equal(proposalPresentation(act({ action: "shell_act", sid: "s1", command: "x" })).lead, "Run a command in the agent's shell");
  // a setting: which one and to what, why under it, and no box at all
  const set = act({ action: "settings", changes: [{ name: "poll_minutes", value: "15" }, { connector: "github", name: "use_as_tracker", value: true }], why: "you asked for the mail to be read less often" });
  const s = proposalPresentation(set);
  assert.equal(s.lead, "Change poll minutes to 15; github: use as tracker to on"); assert.equal(s.leadWhy, "You asked for the mail to be read less often");
  assert.equal(s.bare, true); assert.equal(s.readOnly, true); assert.doesNotMatch(reviewText(set), /[{}]/);
  // any other proposal: the gate's own words for it lead, its box holds what it carries or is not drawn
  const land = act({ action: "land" }, "the agent proposes to publish this work (a draft pull request, or straight to the default branch - your setting)");
  assert.equal(proposalPresentation(land).lead, "Publish this work (a draft pull request, or straight to the default branch - your setting)");
  assert.equal(proposalPresentation(land).bare, true); assert.equal(reviewText(land), "");
  const note = act({ action: "comment_issue", body: "Fixed in the totals branch." }, "the agent proposes to post a PUBLIC comment on the linked issue/PR");
  assert.equal(reviewText(note), "Fixed in the totals branch."); assert.equal(proposalPresentation(note).bare, false);
  // ...its words are his to change while it waits, and what he left is what is posted (proposals.execute); its press says what it does
  assert.ok(!proposalPresentation(note).readOnly); assert.equal(proposalPresentation(note).approveLabel, "Comment");
});

test("a break-out card says the new task and what moves to it, and its result names the task", () => {
  const p = { action: "break_out", title: "Renew the Trainly seats", summary: "Erin's ask about seats, apart from the invoice", messages: [12], items: [],
    moves: "Erin Blake: can we renew the Trainly seats before Friday?" };
  assert.equal(reviewText({ Kind: "action", DraftText: JSON.stringify(p) }),
    "Erin's ask about seats, apart from the invoice\n\nErin Blake: can we renew the Trainly seats before Friday?");
  // ...the new task named once, in its lead (proposals.break_out_words) - no row under it saying it again (the owner, 2026-11-24)
  const card = proposalPresentation({ Kind: "action", DraftText: JSON.stringify(p), Reason: 'the agent proposes to move 1 message to a task of its own, "Renew the Trainly seats"' });
  assert.deepEqual([card.lead, card.destination, card.readOnly], ['Move 1 message to a task of its own, "Renew the Trainly seats"', "", true]);
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
  // ...SAID IN WORDS, the script folded (design round 4, 2026-11-19: an ops manager was asked to approve 60 lines of Python)
  const said = proposalPresentation({ ...rv, DraftText: JSON.stringify({ ...p, why: "lists the invoices that carry a late fee", steps: ["Read", "Run the script", "Read what it found"] }) });
  assert.deepEqual([said.lead, said.leadWhy, said.folded, said.foldWord], ["Lists the invoices that carry a late fee",
    "Runs daily 07:00, on this computer: Read, then run the script, then read what it found.", true, "script"]);
  const done = { ...p, result: { source: 7, link: "#report=7", said: 'Saved the routine "Late fees" - it runs daily 07:00.' } };
  assert.deepEqual(resultOf({ Kind: "action", Status: "approved", FinalText: JSON.stringify(done) }),
    { said: "Approved · saved the routine", what: 'Saved the routine "Late fees" - it runs daily 07:00.', url: "", command: "" });
});


test("an act whose press failed is a settled card with its error, never a waiting one to press again", async () => {
  // the owner, 2026-11-16: no Try again - the card says what happened, its agent is woken with it (general.failed) and sets up what goes next
  const { decidedAsk, failedAsk } = await import("../src/reviewProposal.js");
  const rv = { Kind: "action", Status: "superseded", ActError: "attempt to write a readonly database. The agent was told and goes on from there.",
    DraftText: JSON.stringify({ action: "run_tool", type: "database", query: "INSERT INTO ledger VALUES (3)" }) };
  assert.equal(failedAsk(rv), true); assert.equal(decidedAsk(rv), true);
  assert.equal(failedAsk({ ...rv, ActError: "" }), false, "a draft set aside is no failure");
  assert.equal(failedAsk({ ...rv, Status: "pending" }), false);
});

// EVERY APPROVAL SAYS IN WORDS WHAT IT WILL DO (design round 5, 2026-11-19; round 4 did routines): a step in a connected system, a part moved to
// a task of its own and a routine's change lead with what Approve does - the server's words for it - as a held step and a routine do; said once,
// never "nothing happens until you approve" under it (the owner, 2026-11-24: "we don't need it a bunch of times")
test("every card leads with what its Approve does, in words", () => {
  const card = (p, Reason) => proposalPresentation({ Kind: "action", DraftText: JSON.stringify(p), Reason });
  const tool = card({ action: "run_tool", type: "sharepoint", path: "/Shared/Q3.xlsx" }, "the agent proposes to write the Q3 totals to Q3.xlsx on SharePoint");
  assert.deepEqual([tool.lead, tool.leadWhy], ["Write the Q3 totals to Q3.xlsx on SharePoint", ""]);
  const out = card({ action: "break_out", title: "Book the caterer" }, 'the agent proposes to move the caterer emails to a task of its own, "Book the caterer"');
  assert.deepEqual([out.lead, out.leadWhy], ['Move the caterer emails to a task of its own, "Book the caterer"', ""]);
  const fix = card({ action: "repair_workflow", title: "Late fees" }, 'the agent proposes to change the routine "Late fees"');
  assert.equal(fix.lead, "Change routine: Late fees");
});

// THE HYDROGEN WALK, 2026-11-19: "Where x" under a post card - a post says its network as he knows it (proposals.queue's `network`)
test("a post card says where it goes by its network's name", async () => {
  const { toolWhere } = await import("../src/reviewProposal.js");
  assert.equal(toolWhere({ action: "run_tool", type: "x_post", network: "X", text: "The portal launches Monday." }), "X");
  assert.equal(toolWhere({ action: "run_tool", type: "linkedin_post", network: "LinkedIn" }), "LinkedIn");
});
