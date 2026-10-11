import test from "node:test";
import assert from "node:assert/strict";
import { STORY_CHIP, startLabel, storyAlarm, storyShown } from "../src/agentStory.js";

const held = { kind: "held", line: "first message from pat@vendor.example - not one of your domains" };

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

test("only the two that wait on the owner wear the alarm colour", () => {
  assert.deepEqual(Object.keys(STORY_CHIP).filter(storyAlarm), ["held", "interrupted"]);
});

test("a step that never ran names who Start starts", () => {
  assert.equal(startLabel(held, "coder", false), "Start coder");
  assert.equal(startLabel(held, "coder", true), null);
  assert.equal(startLabel({ kind: "interrupted", line: "x" }, "coder", false), null);
  assert.equal(startLabel(held, "", false), null);
});
