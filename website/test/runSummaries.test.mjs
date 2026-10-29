// "you don't see the last message from the agent from prior runs ... it should summary from run 1|2|3 ... the step by step thing
// should be hidden behind clear door of full script.. main thing is the last summary message from each model run" (the owner,
// 2026-10-15). Every run, newest first, by its last words; everything else behind one Full transcript.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { lastWords, runHeads, runsOf } from "../src/agentRecord.js";

test("a run's last words are its last message, without the prompt box the screen read along with it", () => {
  assert.equal(lastWords({ result: "▌▌ Work in a new folder ~/taskuary-post, not the repo\n\nAnimated round done: combined.mp4 and post.md." }),
    "Animated round done: combined.mp4 and post.md.");
  assert.equal(lastWords({ result: "", report: { summary: "Fixed the export." } }), "Fixed the export.");
  assert.equal(lastWords({}), "");
  // `result` is the whole run's messages strung together: the last one SAID is the run's last words
  assert.equal(lastWords({ result: "Checking.\n\nDone: the video is ready.",
    steps: [{ k: "said", text: "Checking." }, { k: "tool", text: "ls" }, { k: "said", text: "Done: the video is ready." }, { k: "tool", text: "x" }] }),
    "Done: the video is ready.");
});

test("a line said and then worked past is not the last words: the written result the agent filed after it is", () => {
  // the agent said what it would check next, checked, and filed its answer through a tool - the run led with the progress line
  const steps = [{ k: "tool", text: "grep", at: "2026-10-18T13:25:14Z" }, { k: "said", text: "Next I'm checking the run log.", at: "2026-10-18T13:25:16Z" },
    { k: "tool", text: "taskuary --reply", at: "2026-10-18T13:25:38Z" }];
  const s = { sid: "a", at: "2026-10-18T13:26:00Z", steps, result: "Looked into the run. Nothing for you to do." };
  assert.equal(lastWords(s), "Looked into the run. Nothing for you to do.");
  assert.equal(runsOf([s])[0].said, "Looked into the run. Nothing for you to do.");
  // a said line that IS the result's end stays the last words, and so does one nothing came after
  assert.equal(lastWords({ ...s, steps: steps.slice(0, 2) }), "Next I'm checking the run log.");
});

test("runs are numbered oldest-first and shown newest-first", () => {
  const runs = runsOf([{ sid: "c", result: "third" }, { sid: "b", result: "second" }, { sid: "a", result: "first" }]);
  assert.deepEqual(runs.map((r) => [r.n, r.said]), [[3, "third"], [2, "second"], [1, "first"]]);
});

test("runs that resumed one conversation share its log: each is cut at the run before it ended, so each says its OWN last words", () => {
  // a resumed CLI keeps one log, so every run's record carried all of it and Run 2 repeated Run 3's last message (2026-10-15)
  const steps = [{ k: "said", text: "round one done", at: "2026-10-15T16:50:00Z" }, { k: "said", text: "round two done", at: "2026-10-15T17:20:00Z" },
    { k: "said", text: "round three done", at: "2026-10-15T19:00:00Z" }];
  const at = (h, m) => new Date(Date.UTC(2026, 9, 15, h, m)).toISOString();
  const runs = runsOf([{ sid: "c", at: at(19, 8), steps }, { sid: "b", at: at(17, 25), steps }, { sid: "a", at: at(16, 52), steps }]);
  assert.deepEqual(runs.map((r) => r.said), ["round three done", "round two done", "round one done"]);
});

test("the record leads with the runs and keeps the rest behind Full transcript", () => {
  const src = readFileSync(new URL("../src/AgentRecord.jsx", import.meta.url), "utf8");
  assert.match(src, /<RunSummaries /);
  assert.match(src, /Full transcript/);
});

// THE LATEST RUN FIRST, EVERY EARLIER ONE UNDER IT (the owner, 2026-10-29): Continue, Run another agent or a second Send to agent - the newest
// report leads, the ones before it follow newest first, each one line (when, which agent, what came of it), and none is dropped
test("runs read latest first, the earlier ones below it newest first, none dropped, each a line of when, who and what came of it", () => {
  const sessions = [  // the record's own order (sessionrecord.record): newest first
    { sid: "c", cli: "claude", at: "2026-10-29 15:10:00", result: "Third pass.", report: { summary: "Fixed the export\n\nand **tested** it." } },
    { sid: "b", by: "coding", at: "2026-10-29 12:40:00", result: "Found the cause.\n\nNo fix yet." },
    { sid: "a", cli: "codex", at: "2026-10-29 09:05:00", result: "" }];
  const runs = runHeads(sessions);
  assert.deepEqual(runs.map((r) => [r.n, r.s.sid, r.at, r.who, r.line]), [
    [3, "c", "2026-10-29 15:10", "claude", "Fixed the export"],
    [2, "b", "2026-10-29 12:40", "coding", "Found the cause."],
    [1, "a", "2026-10-29 09:05", "codex", ""]]);
  assert.equal(runs.length, sessions.length, "no run is dropped");
  // ...and a live session is the terminal above, never a report under it: the rest keep their order
  assert.deepEqual(runHeads(sessions, "c").map((r) => r.s.sid), ["b", "a"]);
  assert.deepEqual(runHeads([]), []);
});

test("the record draws the latest run, then every earlier one under it, at rest, opened, live and once the sender wrote again", () => {
  const src = readFileSync(new URL("../src/AgentRecord.jsx", import.meta.url), "utf8"), page = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(src, /<EarlierRuns runs=\{runHeads\(rec\.sessions\)\.slice\(1\)\} \/>/, "under the Result at rest");
  assert.match(src, /earlier = <EarlierRuns runs=\{runs\.slice\(1\)\} \/>/, "under the open record");
  assert.match(page, /<AgentRecord \{\.\.\.recordProps\} history live=\{term\.sid\} \/>/, "under a live terminal");
  assert.match(page, /<AgentRecord \{\.\.\.recordProps\} history title="Before they wrote again" \/>/, "every run folded once the sender wrote again");
});
