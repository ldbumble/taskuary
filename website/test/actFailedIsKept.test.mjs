// THE SPINE AUDIT, 2026-11-09: an act whose press failed said so only from that press's own answer. After a reload its card stood as if never
// pressed - the review now keeps what it failed on (store.review_act_failed, ActError) and every card that draws an act reads it from there.
// And a yes the page refused read "ran on the page". Invented people.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { heldCard, resultOf } from "../src/reviewProposal.js";
import { failureHead, failureWhy, savedSendFailure } from "../src/sendState.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const WHY = "GitHub refused it: the token may not comment on northwind/ledger";
const step = (id, command, about, status = "pending", extra = {}) => ({ ReviewId: id, TaskId: 7, Kind: "action", Status: status,
  DraftText: JSON.stringify({ action: "shell_act", sid: "run1", turn: 4, command, about, why: "it leaves this computer", cwd: "C:\\work\\ledger" }), ...extra });

test("an act that failed is said on its card after a reload, as its own sentence", () => {
  const r = { Kind: "action", Status: "pending", ActError: WHY, DraftText: JSON.stringify({ action: "comment_issue", body: "Fixed." }) };
  const f = savedSendFailure(r);
  assert.deepEqual(f, { message: WHY, unknown: false, saved: true });
  assert.equal(`${failureHead(f, true)} ${failureWhy(f)}`.trim(), WHY, "no reply was drafted, so nothing says one was not sent");
  // answered since, or an attempt open right now: the line is that press's, never the old one's
  for (const x of [{ ...r, Status: "approved" }, { ...r, Status: "rejected" }, { ...r, DeliveryClaim: "p1" }, { ...r, ActError: null }]) assert.equal(savedSendFailure(x), null);
  // ...and a send that failed still reads as a send
  assert.equal(savedSendFailure({ Status: "pending", DeliveryState: "failed", Reason: "Not sent: refused.", ActError: WHY }).message, "refused.");
  assert.match(read("ActionCard.jsx"), /row\?\.Status === "pending" && row\?\.ActError/, "a connector's act card reads it off its row");
});

test("a held step that failed says which, and the card still waits with Approve", () => {
  const ran = step(1, "git push origin fix-export", "Push the fix", "approved", { FinalText: JSON.stringify({ action: "shell_act", result: { said: "pushed" } }) });
  const bad = step(2, "gh pr create --fill", "Open the pull request", "pending", { ActError: "The held step failed: remote: Permission to northwind/ledger denied" });
  const c = heldCard([ran, bad, step(3, "gh pr comment 12 --body done", "Say it is up")]);
  assert.equal(c.pressed, null); assert.deepEqual(c.waiting, [2, 3]);
  assert.equal(c.error, "Step 2 failed: The held step failed: remote: Permission to northwind/ledger denied");
  assert.equal(heldCard([bad]).error, "The held step failed: remote: Permission to northwind/ledger denied", "one step needs no number");
  assert.equal(heldCard([ran, step(3, "x", "X")]).error, "");
  // a step that failed and then ran keeps the word on its row; the card no longer says it
  assert.equal(heldCard([{ ...ran, ActError: "The held step failed: exit 1" }]).error, "");
  assert.match(read("HeldSteps.jsx"), /live && c\.error/);
});

test("a yes the page refused reads as not done, with the one plain line", () => {
  const said = "vendor.example did not take it - something on the page covers that control. The agent was told and goes on another way.";
  const p = { action: "browser_act", command: "click @e4", what: "Press Submit on the order", result: { performed: null, refused: said } };
  assert.deepEqual(resultOf({ Kind: "action", Status: "approved", FinalText: JSON.stringify(p) }), { said: "Approved · not done", what: said, url: "", command: "click @e4" });
});
