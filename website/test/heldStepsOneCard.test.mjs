import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { heldCard, heldGroups, keptHeld, splitHeld } from "../src/reviewProposal.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const step = (id, turn, command, about, status = "pending", extra = {}) => ({ ReviewId: id, TaskId: 7, Kind: "action", Status: status,
  DraftText: JSON.stringify({ action: "shell_act", sid: "run1", turn, command, about, why: "it leaves this computer", cwd: "C:\work\portal" }), ...extra });

// THE OWNER, 2026-11-09: "this should be one action button and one card"
test("two held steps of one turn are one card with one Approve; another turn's step is its own", () => {
  const a = step(1, 4, "git merge master && git push origin deploy", "Merge master into deploy and push"),
    b = step(2, 4, "git push origin master", "Push master"), c = step(3, 9, "git push origin v2", "Push the tag");
  const other = { ReviewId: 5, TaskId: 7, Kind: "action", Status: "pending", DraftText: JSON.stringify({ action: "write_playbook", slug: "x" }) };
  const gs = heldGroups([a, b, c, other]);
  assert.deepEqual(gs.map((g) => g.reviews.map((r) => r.ReviewId)), [[1, 2], [3], [5]]);
  assert.deepEqual(gs.map((g) => !!g.held), [true, true, false]);
  const card = heldCard(gs[0].reviews);
  assert.equal(card.title, "Merge master into deploy and push - 2 steps");
  assert.equal(card.why, "Held before it ran - it leaves this computer.", "why it waits, once");
  assert.equal(card.folder, "C:\work\portal");
  assert.deepEqual(card.steps.map((s) => s.text), ["Merge master into deploy and push", "Push master"]);
  assert.deepEqual(card.waiting, [1, 2], "the one Approve sends every waiting step, in order");
  assert.equal(card.pressed, null);
});

test("a row filed before turns were stamped stays its own card", () => {
  const old = (id) => ({ ...step(id, null, "git push", "Push"), DraftText: JSON.stringify({ action: "shell_act", sid: "run1", command: "git push" }) });
  assert.equal(heldGroups([old(1), old(2)]).length, 2);
});

test("pressed, the card stays in the turn with the press it took and what came of it", () => {
  const done = (id) => step(id, 4, "git push", "Push", "approved", { DecidedAt: "2026-11-09 10:05:00",
    FinalText: JSON.stringify({ action: "shell_act", command: "git push", result: { said: "https://github.com/northwind/portal/actions/runs/1" } }) });
  const c = heldCard([done(1), done(2)]);
  assert.equal(c.pressed, "approved"); assert.equal(c.said, "2 of 2 ran"); assert.match(c.url, /actions\/runs\/1/);
  assert.deepEqual(c.steps.map((s) => s.state), ["ran", "ran"]);
  const half = heldCard([done(1), step(2, 4, "git push origin master", "Push master")]);
  assert.equal(half.pressed, null); assert.deepEqual(half.waiting, [2], "after a failure Approve runs only what is left");
  assert.equal(heldCard([step(1, 4, "x", "X", "rejected"), step(2, 4, "y", "Y", "rejected")]).pressed, "dismissed");
  // ...kept until the owner writes again
  const said = (at) => [{ ActorType: "assistant_user", CreatedAt: at }];
  assert.deepEqual(keptHeld([done(1)], said("2026-11-09 10:00:00")).map((r) => r.ReviewId), [1]);
  assert.deepEqual(keptHeld([done(1)], said("2026-11-09 10:10:00")), []);
  // ...and after that it is still the card, in its own turn (the owner, 2026-11-09: "compact the land") - never a line in its place
  const ask = { ReviewId: 9, TaskId: 7, Kind: "action", Status: "pending", DraftText: JSON.stringify({ action: "write_playbook", slug: "x" }) };
  const { asks, past } = splitHeld([{ ...done(1), CreatedAt: "2026-11-09 09:58:00" }, { ...done(2), CreatedAt: "2026-11-09 09:58:01" }, ask], [ask]);
  assert.deepEqual(asks.map((g) => g.key), ["rv9"]);
  assert.deepEqual(past.map((g) => [g.held, g.at, g.reviews.map((r) => r.ReviewId)]), [[true, "2026-11-09 09:58:00", [1, 2]]], "one card, in its turn");
  // ...while one of its steps still waits the card waits whole, the ones that ran ticked in it
  const halfway = splitHeld([done(1), step(2, 4, "git push origin master", "Push master")], []);
  assert.deepEqual([halfway.asks.map((g) => g.reviews.length), halfway.past], [[2], []]);
});

test("a pressed card - held steps approved, a reply sent - is drawn in the turn that set it up, whatever came after", () => {
  const page = read("TaskPage.jsx"), chat = read("GeneralWorkspace.jsx");
  assert.match(page, /const turnCards = \[\.\.\.passedCards, \.\.\.replacedCards, \.\.\.pressedHeld\.map\(\(g\) =>/);
  assert.match(page, /node: <SentCard id=\{r\.ReviewId\}/);
  assert.match(page, /turnCards=\{turnCards\}/);
  assert.match(chat, /const placed = React\.useMemo\(\(\) => placeCards\(turnCards, messages, turns\), \[turnCards, messages, turns\]\);/, "placed in the turn that raised it (agentSummary.placeCards)");
  assert.match(chat, /\{pressed\.map\(\(c\) => <React\.Fragment key=\{c\.key\}>\{c\.node\}<\/React\.Fragment>\)\}/);
});

test("the task page draws a turn's held steps as one HeldSteps card, one Approve through the batch door", () => {
  const page = read("TaskPage.jsx"), card = read("HeldSteps.jsx");
  assert.match(page, /const \{ asks: askCards, past: pressedHeld \} = splitHeld\(allReviews\.filter\(\(r\) => !isPassed\(r\)\), asks\)/);
  assert.match(page, /g\.held\s*\n?\s*\? <HeldSteps/);
  assert.match(card, /pressSteps\(api, c\.waiting, verb\)/);          // the batch door, through the one press (press.js)
  assert.equal((card.match(/data-tq-held-approve/g) || []).length, 1, "one Approve on the card");
});
