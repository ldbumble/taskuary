import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { foldedSummaries, nextSteps } from "../src/agentSummary.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

// EACH TURN ENDS IN THREE PARTS (general.SUMMARY_TYPE, Task 3.5): the newest stays open, every earlier one folds
test("every summary but the newest folds", () => {
  const f = foldedSummaries([{ id: "a", summary: {} }, { id: "b" }, { id: "c", summary: {} }]);
  assert.ok(f.has("a"));
  assert.ok(!f.has("c"));
  assert.ok(!f.has("b"));
  assert.equal(foldedSummaries([]).size, 0);
  assert.equal(foldedSummaries(undefined).size, 0);
});

test("Next steps: nothing left only when no draft waits and no On you step is unticked", () => {
  assert.equal(nextSteps({ summary: { nothing_left: true } }).nothing, true);
  assert.equal(nextSteps({ summary: { nothing_left: false } }).nothing, false);
  assert.equal(nextSteps({ summary: null }).nothing, false);
  const steps = [{ id: "1", text: "Send Ray Colton the signed form", done: false, on_you: true },
                 { id: "2", text: "Already sent", done: true, on_you: true }, { id: "3", text: "Triage's box", done: false }];
  const s = nextSteps({ summary: { nothing_left: true }, checklist: steps });
  assert.equal(s.onYou.length, 1);
  assert.equal(s.onYou[0].text, "Send Ray Colton the signed form");
  assert.equal(s.nothing, false, "an unticked On you step is something left");
  // a pending reply waits: drafts count it, and it is something left; an action or a sent one is not a draft
  const reviews = [{ ReviewId: 1, Kind: "reply", Status: "pending" }, { ReviewId: 2, Kind: "action", Status: "pending" },
                   { ReviewId: 3, Kind: "reply", Status: "sent" }];
  const d = nextSteps({ summary: { nothing_left: true }, reviews });
  assert.deepEqual(d.drafts.map((r) => r.ReviewId), [1]);
  assert.equal(d.nothing, false);
  assert.deepEqual(nextSteps({ summary: { nothing_left: true }, reviews, cards: false }).drafts, []);
});

// ...and a held browser act or a playbook waiting on Approve is something left too (review, Task 3.6)
test("Next steps: an Approve still pending is never Nothing left to do here", () => {
  const held = [{ ReviewId: 7, Kind: "action", Status: "pending" }];
  const a = nextSteps({ summary: { nothing_left: true }, reviews: held });
  assert.deepEqual(a.held.map((r) => r.ReviewId), [7]);
  assert.equal(a.nothing, false);
  const b = nextSteps({ summary: { nothing_left: true }, acts: [{ ReviewId: 8, Kind: "action", Status: "pending" }], reviews: held });
  assert.deepEqual(b.held.map((r) => r.ReviewId), [7, 8], "the chat's own acts and the task's reviews, each once");
  assert.equal(b.nothing, false);
  assert.deepEqual(nextSteps({ summary: { nothing_left: true }, reviews: [{ ReviewId: 9, Kind: "action", Status: "approved" }] }).held, []);
  assert.equal(nextSteps({ summary: { nothing_left: true }, reviews: [{ ReviewId: 9, Kind: "action", Status: "approved" }] }).nothing, true);
});

test("the chat draws the summary, and the turn's working is one line with its steps folded under it", () => {
  const view = read("GeneralWorkspace.jsx");
  assert.match(view, /import AgentSummary from "\.\/AgentSummary\.jsx";/);
  assert.match(view, /foldedSummaries\(/);
  assert.match(view, /data-tq-working=""/);
  assert.match(view, /Working on this…/);
  const card = read("AgentSummary.jsx");
  for (const h of ["What this is about", "What I did", "Next steps", "Nothing left to do here", "data-tq-summary", "data-tq-on-you"])
    assert.ok(card.includes(h), h);
  assert.doesNotMatch(card, /<Button|onClick/, "the summary draws no press of its own yet (Task 4.2 brings the cards)");
  assert.doesNotMatch(card + view.slice(view.indexOf("<AgentSummary")), /onChanged=\{work/, "no prop nothing reads yet (Task 4.2 adds it with the cards)");
});

// Review Focus 4 (Task 4.1): until the cards live in the summary (4.2), a pending draft is not counted where no cards are drawn - Close out still draws it
test("a pending draft is no Next step where the summary draws no cards", () => {
  const reviews = [{ ReviewId: 1, Kind: "reply", Status: "pending", DraftText: "Thanks, Erin" }];
  assert.equal(nextSteps({ summary: { nothing_left: false }, reviews, cards: false }).drafts.length, 0);
  assert.equal(nextSteps({ summary: { nothing_left: false }, reviews }).drafts.length, 1);
});
