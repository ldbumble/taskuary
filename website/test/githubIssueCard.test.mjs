// A GITHUB "CREATE ISSUE" CARD (the owner, 2026-11-06), the same way LinkedIn's post is drawn: the agent sets up the repository, title,
// body and labels; the card in that turn shows them with Create issue, and nothing is filed until the owner presses it.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { actionFor, cardOf, fieldsOf, isCardReview, stateOf, textKey, wordsOf } from "../src/actionCard.js";

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
  assert.deepEqual(f.filter((x) => x.editable).map((x) => x.key), ["body"], "the owner edits the words; the agent named the rest");
  assert.ok(f.find((x) => x.key === "title").heading);
});

test("it waits for the press, then says Created with the issue's link", () => {
  assert.deepEqual(stateOf({ Status: "pending", post: ISSUE }, true), { live: true });
  const done = stateOf({ Status: "approved", post: { ...ISSUE, result: { url: "https://github.example/northwind/portal/issues/14" } } });
  assert.deepEqual(done, { done: true, said: "Created", url: "https://github.example/northwind/portal/issues/14" });
  assert.equal(stateOf({ Status: "pending", post: ISSUE }, false).said, "Not created");
});

test("the title is drawn bold over the words, never as a header label", () => {
  const s = readFileSync(new URL("../src/ActionCard.jsx", import.meta.url), "utf8");
  assert.match(s, /const lines = fields\.filter\(\(f\) => f\.type === "line" && f\.value && !f\.heading\), heads = fields\.filter\(\(f\) => f\.heading && f\.value\);/);
  assert.match(s, /data-tq-act-heading=\{f\.key\}/);
});
