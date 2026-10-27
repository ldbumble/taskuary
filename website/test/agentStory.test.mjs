import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { STORY_CHIP, startLabel, storyAlarm, storyPlace, storyShown } from "../src/agentStory.js";

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

test("only the two that wait on the owner, and a run that failed, wear the alarm colour", () => {
  assert.deepEqual(Object.keys(STORY_CHIP).filter(storyAlarm), ["held", "interrupted", "failed"]);
});

// a failed run is said as a failure (owner-approved, 2026-10-21): it read "not started" or "stopped" over its own reason
test("a failed run's chip says failed", () => {
  assert.equal(STORY_CHIP.failed, "failed");
});

// ...and its step offers Try again at the press, with the fix (Connect an AI) filled when it has one - never the Continue card
test("the agent step tries a failed run again and lights its fix", () => {
  const page = readFileSync(fileURLToPath(new URL("../src/TaskPage.jsx", import.meta.url)), "utf8");
  assert.match(page, /failedRun \? btn\("try_again"\)/);
  assert.match(page, /continue-work`, \{ note: null \}/);
  // ...but no Connect an AI on the canvas's row (the owner, 2026-10-26: "why would we need connect an ai?") - the Result's line says why
  assert.match(page, /\.\.\.\(runFix && !\(inRow && runFix\.href === place\("ai"\)\.href\) \? \[\{ id: "fix", group: "decide", tone: "p"/);
});

// by what the agent IS, from the task's kind - "Start coder" named a profile as if it were a worker (the owner, 2026-10-16)
test("a step that never ran names what Start starts, by the task's kind", () => {
  assert.equal(startLabel(held, "coding", false), "Start the coding agent");
  assert.equal(startLabel(held, "general", false), "Start the assistant");
  assert.equal(startLabel(held, "coding", true), null);
  assert.equal(startLabel({ kind: "interrupted", line: "x" }, "coding", false), null);
});

// the server's sentence is whole and leads with its state; "<profile> did not start: " glued before a fragment is gone
test("the story line adds no lead of its own", () => {
  const story = readFileSync(fileURLToPath(new URL("../src/AgentStory.jsx", import.meta.url)), "utf8");
  assert.doesNotMatch(story, /did not start|LEAD\[/);
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
  assert.match(page, /storyAt === "summary" && <AgentRecord \{\.\.\.recordProps\} story=\{story\} folded \/>/);
  assert.match(page, /<AgentRecord \{\.\.\.recordProps\} story=\{storyAt === "record" \? story : null\}/);
  assert.doesNotMatch(story.slice(story.indexOf("export default")), /PANEL2|bgcolor/, "no tinted bubble");
  assert.equal(story.match(/setMore\(/g).length, 1, "the timeline is behind one More");
});

test("a run that finished wears the list's word for it, never 'not started' (G7)", () => {
  assert.equal(STORY_CHIP.finished, "agent finished");
  assert.equal(startLabel({ kind: "finished", line: "The coding agent finished its work" }, "coding", true), null);
});
