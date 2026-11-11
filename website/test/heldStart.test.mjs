// The owner, 2026-11-09: a coding task held because its sender was new opened on "waiting to start" over an empty chat, with nothing to press.
// The chat says why nothing started by itself, and Run anyway starts it through the hold's own release - for a coding and a general task alike.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { heldStartOf } from "../src/agentStory.js";

const story = { kind: "held", line: "Waiting for you. Gail Moreno (gail@vendor.example) is not on your domain and you have never written to them, so no agent starts on their words by itself." };

test("the held line is said only for a new sender's hold, and only while no agent ever ran", () => {
  assert.equal(heldStartOf({ story, tags: "repo:x,hold:new-sender" }), story.line);
  assert.equal(heldStartOf({ story, tags: "hold:new-sender", ran: true }), "", "once an agent ran, the chat tells its own story");
  assert.equal(heldStartOf({ story, tags: "held:repo" }), "", "a hold on where the code is has its own way on");
  assert.equal(heldStartOf({ story: { ...story, kind: "idle" }, tags: "hold:new-sender" }), "");
});

test("the chat draws Run anyway (this once) and Trust sender (vouches too), both through the hold's release", () => {
  const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
  assert.match(src("HeldStart.jsx"), /api\.post\(`\/api\/tasks\/\$\{taskId\}\/release`, \{ trust \}\)/);
  assert.match(src("HeldStart.jsx"), /btn\(false, "Run anyway"/);
  assert.match(src("HeldStart.jsx"), /btn\(true, "Trust sender"/);
  assert.match(src("GeneralWorkspace.jsx"), /\{!dock && heldStart\}/);
  assert.match(src("TaskPage.jsx"), /heldStart=\{chatPane && heldStart \? <HeldStart taskId=\{t\.TaskId\} line=\{heldStart\}/);
});

// ...AND A LINE OF HIS IS NO RUN (the recorded walk, 2026-11-10): he typed on a stranger's task whose AI could not start, the start was held -
// and the hold was hidden because the chat now had history, his own line. Only the agent's words, a session or a queued start are a run
test("the owner's own line does not hide the hold: only an agent that spoke, a session or a queued start does", () => {
  const page = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /const agentSpoke = \(detail\?\.comments \|\| \[\]\)\.some\(\(c\) => c\.ActorType === "assistant_agent"\);/);
  assert.match(page, /heldStartOf\(\{ story: detail\?\.agentStory, tags: t\?\.Tags, ran: ranBefore \|\| agentSpoke \|\| !!term \|\| liveSession \|\| !!queuedRow \}\)/);
});
