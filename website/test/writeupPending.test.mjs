// Stop and save opens Close out at once with the write-up's pending block - the server job's own stage - and the draft replaces it in
// place (the owner, 2026-10-21: "open the Close out right away and show the reply is being created, pending").
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { writeupHead, writeupSteps, writeupView } from "../src/writeupState.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");
const job = (stage, more = {}) => ({ job: "j1", stage, running: !["done", "failed"].includes(stage), error: "", close: false, ...more });
const draft = { ReviewId: 4, Status: "pending", DraftText: "Hi Gail, the bill is posted.", DraftBy: null };

test("the press shows the pending block before the server has answered", () => {
  assert.deepEqual(writeupView({ pressed: { n: 3 } }), { state: "pending", stage: "reading" });
  // ...and an older job's `done` does not end it: this press has not been answered yet
  assert.deepEqual(writeupView({ pressed: { n: 3 }, server: job("done", { job: "old" }) }), { state: "pending", stage: "reading" });
});

test("the block follows the job's own stage, and the draft replaces it once the reply is filed", () => {
  const pressed = { n: 3, job: "j1" };
  for (const s of ["reading", "report", "reply"]) assert.deepEqual(writeupView({ pressed, server: job(s) }), { state: "pending", stage: s });
  // the reply is filed: the job asks its last two questions, Close out draws the draft meanwhile
  assert.equal(writeupView({ pressed, server: job("learning"), review: draft }), null);
  assert.equal(writeupView({ pressed, server: job("done"), review: draft }), null);
  // ...a review raised but still being written stays behind the block while the job drafts it
  assert.deepEqual(writeupView({ pressed, server: job("reply"), review: draft }), { state: "pending", stage: "reply" });
});

test("the agent's own saved reply (--reply) is shown at once", () => {
  const own = { ...draft, DraftBy: "agent:coding" };
  assert.equal(writeupView({ pressed: { n: 3 }, review: own }), null);
  assert.equal(writeupView({ pressed: { n: 3, job: "j1" }, server: job("report"), review: own }), null);
});

test("a write-up that fails says so with why, never an empty Close out", () => {
  const v = writeupView({ pressed: { n: 3, job: "j1" }, server: job("failed", { error: "the AI did not answer" }) });
  assert.deepEqual(v, { state: "failed", error: "the AI did not answer" });
  assert.equal(writeupHead(v, true), "The write-up of this session did not finish");
  // ...a reply drafted by hand afterwards is the Close out again
  assert.equal(writeupView({ pressed: { n: 3, job: "j1" }, server: job("failed"), review: draft }), null);
  // ...and with no word from the job (a restart), the task's own note says it
  const comments = [{ Body: "a" }, { Body: "b" }, { Body: "c" }, { Body: "The write-up of this session did not finish: Taskuary restarted before the session was read" }];
  assert.deepEqual(writeupView({ pressed: { n: 3, job: "j1" }, comments }), { state: "failed", error: "Taskuary restarted before the session was read" });
  assert.equal(writeupView({ pressed: { n: 3, job: "j1" }, comments: [...comments.slice(0, 3), { Body: "AGENT REPORT\nPosted." }] }), null);
});

test("a job running when the task is opened shows too; a close (Mark done) never holds Close out", () => {
  assert.deepEqual(writeupView({ server: job("report") }), { state: "pending", stage: "report" });
  assert.equal(writeupView({ server: job("report", { close: true }) }), null);
  assert.equal(writeupView({ server: job("failed") }), null);                // a failure is the press's to show; the note stays on the task
});

test("the steps say done, now and to come; the reply step only where somebody is owed one", () => {
  assert.deepEqual(writeupSteps({ stage: "report" }, true).map((s) => [s.k, s.state]), [["reading", "done"], ["report", "now"], ["reply", "next"]]);
  assert.deepEqual(writeupSteps({ stage: "reading" }, false).map((s) => s.k), ["reading", "report"]);
  assert.equal(writeupHead({ state: "pending" }, true), "Writing the reply from the session…");
  assert.equal(writeupHead({ state: "pending" }, false), "Writing up the session…");
});

test("Stop and save puts the agent down and opens Close out at the press; the block stands where the draft will", () => {
  const page = read("TaskPage.jsx");
  assert.match(page, /setErr\(""\); setWritingUpAt\(\{ id, n, sid \}\); setTerm\(null\); setSeekCloseOut\(true\);\n    try \{\n      const \{ data \} = await api\.post\(`\/api\/tasks\/\$\{id\}\/wrap`, \{ close: false, background: true \}\);/);
  assert.match(page, /setWritingUpAt\(null\); findTerm\(id\);/);                                  // a press that fails gives the session back
  assert.match(page, /openStage \|\| \(pressedHere \|\| writeup \? "reply" :/);                    // Close out held open: no jump when it lands
  assert.match(page, /\{pane === "reply" && writeup && <WriteupBlock view=\{writeup\}/);
  assert.match(page, /\{pane === "reply" && !writeup && \(\(pendingReview \|\|/);                 // ...and the draft in its place, same card
  assert.match(page, /if \(pressedHere\?\.sid && live\.sid === pressedHere\.sid\) return;/);       // the closing pty is not adopted back
  assert.match(page, /<Box ref=\{closeOutRef\} data-tq-closeout=""/);
  // Mark done on a live agent stays the background close: the page walks on, no pending Close out
  assert.match(page, /if \(canWrap && await writeUpThenClose\(api, id\)\) \{\n      if \(stale\(id\)\) return;\n      setTerm\(null\);\n      return closedHere\("done"\);/);
  const mod = read("closeAgent.jsx");
  assert.match(mod, /data-tq-writeup=\{view\.state\} data-tq-writeup-stage=\{view\.stage \|\| ""\} role="status"/);
  assert.match(mod, /label\("try_again"\)/);
});
