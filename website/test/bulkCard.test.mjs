import test from "node:test";
import assert from "node:assert/strict";
import { pressOf, progress, rowOf, rowState, running } from "../src/bulkCard.js";

// ONE CARD FOR A BULK JOB (taskuary/bulkcard.py; the owner, 2026-11-16). Invented people and a stand-in repository.
const mail = (id, to, extra = {}) => ({ ReviewId: id, Kind: "slot", Status: "pending", Batch: "b1", DraftText: "Hello - about Market St.",
  Deliver: JSON.stringify({ to: [to], subject: `Interest in ${id} Market St`, ...extra }) });
const close = (id) => ({ ReviewId: id, Kind: "action", Status: "pending", Batch: "b2", Reason: "the agent proposes to close it",
  DraftText: JSON.stringify({ action: "run_tool", type: "github_close", repo: "northwind/ledger", number: id, comment: "Stale - closing." }) });

test("a row says whom or what it goes to, its one line, and what to check", () => {
  assert.deepEqual(rowOf(mail(1, "owner1@cedar.example")), { id: 1, target: "owner1@cedar.example", line: "Interest in 1 Market St", flags: [] });
  assert.deepEqual(rowOf(mail(2, "owner2@cedar.example", { guessed: ["owner2@cedar.example"] })).flags, ["address guessed"]);
  assert.deepEqual(rowOf(close(7)), { id: 7, target: "northwind/ledger#7", line: "Stale - closing.", flags: [] });
});

test("the press says what it does, by the act's own words", () => {
  assert.equal(pressOf([mail(1, "a@cedar.example")], 24), "Send 24 emails");
  assert.equal(pressOf([close(1)], 37), "Close 37 issues");
});

test("each row stands where its run left it, and the bar counts what is over", () => {
  const run = { state: "running", total: 4, done: 1, failed: 1, left: 0, rows: { 1: "ok", 2: "issue was deleted" } };
  assert.deepEqual([1, 2, 3].map((id) => rowState(close(id), run)), [{ done: true }, { failed: "issue was deleted" }, { waiting: true }]);
  assert.equal(progress(run), 50); assert.ok(running(run)); assert.ok(!running({ state: "finished" }));
  assert.deepEqual(rowState({ ...close(4), Status: "superseded", DecideNote: "set aside when you moved on" }, null), { aside: true });
});
