import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { STORY_CHIP, startLabel, storyAlarm, storyPlace, storyShown } from "../src/agentStory.js";

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

test("the step draws the story once: never beside the record, and its last message in no bubble", () => {
  const read = (n) => readFileSync(fileURLToPath(new URL(`../src/${n}`, import.meta.url)), "utf8");
  const page = read("TaskPage.jsx"), story = read("AgentStory.jsx");
  assert.match(page, /\(storyAt === "line" \|\| storyAt === "story"\) && <AgentStory /);
  assert.match(page, /storyAt === "summary" && <AgentRecord \{\.\.\.recordProps\} story=\{story\} who=\{agentName\(t\)\} folded \/>/);
  assert.match(page, /<AgentRecord \{\.\.\.recordProps\} story=\{storyAt === "record" \? story : null\}/);
  assert.doesNotMatch(story.slice(story.indexOf("export default")), /PANEL2|bgcolor/, "no tinted bubble");
  assert.equal(story.match(/setMore\(/g).length, 1, "the timeline is behind one More");
});
