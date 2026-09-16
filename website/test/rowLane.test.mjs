// The work rail says what is waiting, not what kind of job it is.
//
// TQ-0526 sat on the rail wearing "coding" while a reply was drafted and waiting for a yes - the
// chip drew triage's ROAD because the branch meant to draw the state tests a `Lane` the feed has
// never sent (the owner, 2026-09-14: "that should only be if in coding, if waiting should be agent
// waving emoji, and if reply pending should say that").
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { rowLane } from "../src/rowLane.js";
import { laneMeta } from "../src/funnelPile.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

// TQ-0526's row, exactly as /api/feed sent it the moment the screenshot was taken
const PTO_ROW = { MessageId: 6955, TaskId: 526, FromName: "Gitty Weichbrod", MsgStatus: "routed",
  TaskStatus: "in_progress", TaskKind: "coding", Category: "coding", FunnelKey: "msg:6955",
  ReviewId: 128, ReviewStatus: "pending", ReviewKind: "draft_reply", HasDraft: 1, NeedsYou: 0, CanSend: true };

test("a drafted reply waiting for a yes says so, and never says coding", () => {
  assert.equal(rowLane(PTO_ROW), "approve");
  assert.equal(laneMeta(rowLane(PTO_ROW)).word, "reply ready");
  assert.equal(laneMeta(rowLane(PTO_ROW)).mark, "✉️");
});

test("an agent that stopped is waving, and one still going says it is working", () => {
  assert.equal(rowLane({ TaskKind: "coding", Working: "coder", AgentWaiting: true }), "blocked");
  assert.equal(laneMeta("blocked").word, "agent waving");
  assert.equal(laneMeta("blocked").mark, "👋");
  assert.equal(rowLane({ TaskKind: "coding", Working: "coder", AgentWaiting: false }), "working");
  assert.equal(laneMeta("working").word, "working");
  // a parked agent reaches the row as NeedsYou when its session is not live in this window
  assert.equal(rowLane({ TaskKind: "coding", NeedsYou: 1 }), "blocked");
});

test("a yes outranks the agent: sending the draft is what closes the task", () => {
  assert.equal(rowLane({ ...PTO_ROW, Working: "coder", AgentWaiting: true }), "approve");
});

test("with nothing waiting the row keeps triage's road word", () => {
  assert.equal(rowLane({ TaskId: 1, TaskKind: "coding", Category: "coding", ReviewStatus: "no_reply" }), null);
  assert.equal(rowLane({ TaskId: 2, TaskKind: "chat" }), null);
  assert.equal(rowLane({}), null);
  assert.equal(rowLane(null), null);
  // a decided review is not a waiting one
  assert.equal(rowLane({ ReviewStatus: "approved", HasDraft: 1 }), null);
});

test("the rail asks for it, and the server's word for that lane matches the page's", () => {
  const feed = read("FeedView.jsx");
  assert.match(feed, /import \{ rowLane \} from "\.\/rowLane\.js"/);
  // computed ONCE into rowWord, because the state mark now asks the same question - "did anything
  // already say a word for this row?" - and a second copy of the expression could disagree with it
  assert.match(feed, /const rowWord = view === "unread" \? \(r\.Lane \|\| rowLane\(r\)\) : null;/);
  assert.match(feed, /\{rowWord \? <LaneTag lane=\{rowWord\} \/>/);
});
