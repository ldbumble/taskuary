import test from "node:test";
import assert from "node:assert/strict";


import { storyPlace, storyShown } from "../src/agentStory.js";

const held = { kind: "held", line: "Waiting for you. pat@vendor.example is not on your domain and you have never written to them, so no agent starts on their words by itself. Start the coding agent, or do it yourself." };

test("the story shows only when nothing is live and the task is open", () => {
  assert.equal(storyShown(held), true);
  assert.equal(storyShown(held, { alive: true }), false);
  assert.equal(storyShown(held, { liveRun: { Status: "running" } }), false);
  assert.equal(storyShown(held, { closed: true }), false);
  assert.equal(storyShown(null), false);
});

test("a queued start is left to its own card, which has Start now and Cancel", () => {
  assert.equal(storyShown({ kind: "queued", line: "next in line" }, { queued: true }), false);
});

// One telling of the run (the owner, 2026-10-12): with a record the sentence heads it - folded over its summary, open over it all
// with the timeline behind More; with none the story is the whole account.
test("the story is the record's first line when there is a record, and the whole account only when there is none", () => {
  const left = { kind: "left", line: "You ended the session.", steps: [{ at: "2026-10-12 08:00:00", text: "Started" }], said: "Merged." };
  assert.equal(storyPlace(left, { open: false, hasRecord: true }), "summary");
  assert.equal(storyPlace(left, { open: false, hasRecord: false }), "line");
  assert.equal(storyPlace(left, { open: true, hasRecord: true }), "record");
  assert.equal(storyPlace(left, { open: true, hasRecord: false }), "story");
  assert.equal(storyPlace(null, { open: true }), null);
});

