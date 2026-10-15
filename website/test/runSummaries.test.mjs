// "you don't see the last message from the agent from prior runs ... it should summary from run 1|2|3 ... the step by step thing
// should be hidden behind clear door of full script.. main thing is the last summary message from each model run" (the owner,
// 2026-10-15). Every run, newest first, by its last words; everything else behind one Full transcript.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { lastWords, runsOf } from "../src/agentRecord.js";

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
