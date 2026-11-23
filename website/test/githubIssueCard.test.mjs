// A GITHUB "CREATE ISSUE" CARD (the owner, 2026-11-06), the same way LinkedIn's post is drawn: the agent sets up the repository, title,
// body and labels; the card in that turn shows them with Create issue, and nothing is filed until the owner presses it.
import test from "node:test";
import assert from "node:assert/strict";

import { actionFor, cardOf, changed, fieldsOf, isCardReview, pressable, stateOf, textKey, valuesOf, wordsOf } from "../src/actionCard.js";

const ISSUE = { action: "run_tool", type: "github_issue", repo: "northwind/portal", title: "Login page warns about the certificate",
  body: "Users see a certificate warning on login since Monday.", labels: "bug" };
const rv = (p, extra = {}) => ({ ReviewId: 9, Kind: "action", Status: "pending", DraftText: JSON.stringify(p), ...extra });

test("a github_issue run_tool is GitHub's card, its words the issue's body", () => {
  assert.ok(isCardReview(rv(ISSUE)));
  const act = actionFor("github_issue");
  assert.equal(cardOf(rv(ISSUE)).network, "GitHub");
  assert.equal(textKey(act), "body");
  assert.deepEqual(wordsOf(act, {}), { press: "Create issue", busy: "Creating…", done: "Created", undone: "Not created" });
  const f = fieldsOf(act, ISSUE, true);
  assert.deepEqual(f.map((x) => [x.key, x.value]), [["repo", "northwind/portal"], ["title", ISSUE.title], ["labels", "bug"], ["body", ISSUE.body]]);
  assert.deepEqual(f.filter((x) => x.editable).map((x) => x.key), ["title", "labels", "body"], "the owner edits the words; where it goes stays the agent's");
  assert.ok(f.find((x) => x.key === "title").heading);
});

test("it waits for the press, then says Created with the issue's link", () => {
  assert.deepEqual(stateOf({ Status: "pending", post: ISSUE }, true), { live: true });
  const done = stateOf({ Status: "approved", post: { ...ISSUE, result: { url: "https://github.example/northwind/portal/issues/14" } } });
  assert.deepEqual(done, { done: true, said: "Created", url: "https://github.example/northwind/portal/issues/14" });
  assert.equal(stateOf({ Status: "pending", post: ISSUE }, false).said, "Not created");
});

// ...its title and labels are his to change while it waits, as its body is (the owner, 2026-11-23: "all cards should be that way if there is text")
test("an edited title and labels go with the press; an emptied title holds it, emptied labels do not", () => {
  const act = actionFor("github_issue"), v = valuesOf(act, ISSUE);
  assert.deepEqual(changed(act, ISSUE, v), {});
  assert.deepEqual(changed(act, ISSUE, { ...v, title: "Certificate warning on the login page", labels: "" }), { title: "Certificate warning on the login page", labels: "" });
  assert.ok(!pressable(act, ISSUE, ISSUE.body, { ...v, title: "  " }), "an issue with no title is no press");
  assert.ok(pressable(act, ISSUE, ISSUE.body, { ...v, labels: "" }));
  assert.ok(!fieldsOf(actionFor("github_close"), { number: 14 }, true).find((x) => x.key === "number").editable, "which issue is not words");
});
