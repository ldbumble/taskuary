import test from "node:test";
import assert from "node:assert/strict";
import { actions, progress, railShort, stateWord } from "../src/batchItems.js";

// A batch (batch.py): one repository's ranked arrivals as one task, worked top-down by a read-only agent.
const PR = "https://github.com/northwind/portal/pull/";
const items = [
  { Place: 1, State: "ended", EndedWhy: "You merged it on GitHub.", Link: PR + "1" },
  { Place: 2, State: "done", Link: PR + "2" },
  { Place: 3, State: "needs_you", Result: "Duplicate of 1.", Link: PR + "3", reviewed: true },
  { Place: 4, State: "waiting", Link: PR + "4" },
];

test("the progress line counts settled lines and names the ones waiting on you", () => {
  assert.equal(progress(items), "2 of 4 done · ③ needs you");
  assert.equal(progress([]), "");
});

test("the filled button is what the agent proposed; a duplicate it says to close never wears a filled Merge", () => {
  const filled = (i) => actions(i).filter((a) => a.primary).map((a) => a.action);
  assert.deepEqual(filled({ ...items[2], Propose: "close" }), ["close"]);
  assert.deepEqual(actions({ ...items[2], Propose: "close" }).map((a) => a.action), ["close", "merge", "settle"]);
  assert.deepEqual(filled({ ...items[2], Propose: "merge" }), ["merge"]);
  assert.deepEqual(filled({ ...items[2], Propose: "changes" }), ["open"]);
  assert.deepEqual(filled(items[2]), [], "no proposal, nothing filled");
});

test("merge is offered only on a reviewed pull request; a settled line can only be opened again", () => {
  assert.deepEqual(actions(items[2]).map((a) => a.action), ["merge", "close", "settle"]);
  assert.deepEqual(actions({ ...items[2], reviewed: false }).map((a) => a.action), ["close", "settle"]);
  assert.deepEqual(actions({ ...items[2], Link: "https://jira.example/browse/X-1" }).map((a) => a.action), ["settle"]);
  assert.deepEqual(actions(items[0]).map((a) => a.action), ["reopen"]);
  assert.deepEqual(actions(items[3]).map((a) => a.action), ["settle"]);
});

test("an ended item says how it ended", () => {
  assert.equal(stateWord(items[0]), "merged");
  assert.equal(stateWord({ State: "ended", EndedWhy: "You closed it on GitHub without merging." }), "closed");
  assert.equal(stateWord(items[2]), "needs you");
});

test("the rail row counts settled items of all", () => {
  assert.equal(railShort(["done", "waiting", "needs_you", "ended"]), "2/4");
});
