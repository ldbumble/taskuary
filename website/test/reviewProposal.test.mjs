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
  assert.equal(shown.destination, "Docs → Playbooks → run-manual-pto-import.md");
  assert.equal(shown.approveLabel, "Approve");          // one word for every proposal (buttons.json approve.states.action)
  assert.match(shown.context, /nothing will be sent/);
});

test("a playbook proposed as new names the file its title files it under", () => {
  // playbooks.write files slug "new" under slugify(title): the card said new.md over a playbook saved as send-our-w-9-....md
  const review = { Kind: "action", DraftText: JSON.stringify({ action: "write_playbook", slug: "new",
    text: "# Send our W-9 to a customer who asks\nwhen: a customer asks for our W-9\n" }) };
  assert.equal(proposalPresentation(review).destination, "Docs → Playbooks → send-our-w-9-to-a-customer-who-asks.md");
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
