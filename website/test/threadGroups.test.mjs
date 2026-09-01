import test from "node:test";
import assert from "node:assert/strict";
import { FOLD_MIN, groupThreads, loudest, spanText } from "../src/threadGroups.js";

const row = (id, tid, at) => ({ MessageId: id, TaskId: tid, SentAt: at });
const keys = (out) => out.map((e) => (e.kind === "fold" ? `fold:${e.rows.length}` : `row:${e.row.MessageId}`));

test("several rows on ONE TASK fold into one entry", () => {
  const out = groupThreads([row(3, "c1", "12:47"), row(2, "c1", "12:44"), row(1, "c1", "12:41")]);
  assert.deepEqual(keys(out), ["fold:3"]);
});

test("the fold takes the place of its NEWEST member", () => {
  const out = groupThreads([row(9, "x", "13:00"), row(3, "c1", "12:47"), row(1, "c1", "12:41"), row(8, "y", "12:00")]);
  assert.deepEqual(keys(out), ["row:9", "fold:2", "row:8"]);
  assert.equal(out[1].row.MessageId, 3);          // the fold reports the newest as its own row
});

test("members read newest first inside, like the rail around them", () => {
  const out = groupThreads([row(1, "c1", "12:41"), row(3, "c1", "12:47"), row(2, "c1", "12:44")]);
  assert.deepEqual(out[0].rows.map((r) => r.MessageId), [3, 2, 1]);
});

test("a task with a single message is never folded", () => {
  assert.deepEqual(keys(groupThreads([row(1, "c1", "12:41"), row(2, "c2", "12:40")])), ["row:1", "row:2"]);
});

test("rows with NO TASK are left exactly alone - nothing judged them to be one thing", () => {
  const out = groupThreads([row(1, "", "12:41"), row(2, null, "12:40"), row(3, undefined, "12:39")]);
  assert.deepEqual(keys(out), ["row:1", "row:2", "row:3"]);
});

test("two different tasks fold separately", () => {
  const out = groupThreads([row(4, "b", "13:00"), row(3, "a", "12:50"), row(2, "b", "12:40"), row(1, "a", "12:30")]);
  assert.deepEqual(keys(out), ["fold:2", "fold:2"]);
  assert.equal(out[0].tid, "b");                  // b is newest, so b's fold comes first
});

test("nothing is dropped and nothing is duplicated", () => {
  const rows = [row(1, "a", "1"), row(2, "a", "2"), row(3, "", "3"), row(4, "b", "4"), row(5, "b", "5"), row(6, "c", "6")];
  const out = groupThreads(rows);
  const seen = out.flatMap((e) => (e.kind === "fold" ? e.rows : [e.row])).map((r) => r.MessageId).sort();
  assert.deepEqual(seen, [1, 2, 3, 4, 5, 6]);
});

test("an empty or missing day is not an error", () => {
  assert.deepEqual(groupThreads([]), []);
  assert.deepEqual(groupThreads(null), []);
});

test("the fold threshold is two, and it is adjustable", () => {
  assert.equal(FOLD_MIN, 2);
  assert.deepEqual(keys(groupThreads([row(1, "a", "1"), row(2, "a", "2")], { min: 3 })), ["row:1", "row:2"]);
});

// ── what the fold WEARS ───────────────────────────────────────────────────────────────────
const RANK = ["reply", "waving", "working", "todo", "done", "fyi"];
const st = (r) => r.state;

test("the fold wears the loudest state inside it, not the newest", () => {
  // the newest line is fyi and a reply is waiting two down: folding must not hide that
  assert.equal(loudest([{ state: "fyi" }, { state: "reply" }, { state: "fyi" }], st, RANK), "reply");
});

test("an all-quiet thread stays quiet", () => {
  assert.equal(loudest([{ state: "fyi" }, { state: "fyi" }], st, RANK), "fyi");
});

test("a state nobody ranks does not win by accident", () => {
  assert.equal(loudest([{ state: "mystery" }, { state: "done" }], st, RANK), "done");
});

test("no members at all is fyi, never a crash", () => {
  assert.equal(loudest([], st, RANK), "fyi");
});

// ── the span ──────────────────────────────────────────────────────────────────────────────
const fmt = (s) => s;

test("the span reads oldest to newest", () => {
  assert.equal(spanText([{ SentAt: "1:47 PM" }, { SentAt: "1:00 PM" }], fmt), "1:00 PM – 1:47 PM");
});

test("a thread inside one minute shows one time, not a range of nothing", () => {
  assert.equal(spanText([{ SentAt: "1:47 PM" }, { SentAt: "1:47 PM" }], fmt), "1:47 PM");
});
