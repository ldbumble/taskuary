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
  assert.equal(shown.approveLabel, "Save playbook");
  assert.match(shown.context, /nothing will be sent/);
});

test("the editable review body is the playbook markdown, not its action envelope", () => {
  assert.equal(reviewText(playbook), "# Run manual PTO import\nwhen: files are waiting\n");
  assert.equal(reviewText({ Kind: "draft", DraftText: "Thanks." }), "Thanks.");
});

test("even an unreadable action is never presented as a reply", () => {
  const shown = proposalPresentation({ Kind: "action", DraftText: "not json" });
  assert.equal(shown.kind, "action");
  assert.equal(shown.approveLabel, "Run action");
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
