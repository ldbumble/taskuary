import test from "node:test";
import assert from "node:assert/strict";
import { proposalPresentation, reviewStatusLabel, reviewText } from "../src/reviewProposal.js";

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
