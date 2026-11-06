import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { HOW, landingWords } from "../src/landing.js";

test("the landing card says the branch's stat and the agent's pick", () => {
  const w = landingWords({ own: true, ahead: 2, changed: 3, plus: 40, minus: 12, proposal: { how: "merge", why: "the base moved" } });
  assert.equal(w.stat, "3 files changed, +40 −12 · 2 commits ahead");
  assert.equal(w.proposal, "The agent proposes Merge commit — the base moved.");
  assert.equal(landingWords({ own: false, changed: 1, plus: 1, minus: 0 }).stat, "1 file changed, +1 −0 since the task started");
});

test("the four answers are the server's and discard asks once more before it goes", () => {
  assert.deepEqual(Object.keys(HOW), ["rebase", "merge", "pr", "discard"]);
  const body = fs.readFileSync(path.join(process.cwd(), "src", "LandingCard.jsx"), "utf8");
  assert.match(body, /how === "discard" && !sure/);
  assert.match(body, /\/api\/tasks\/\$\{taskId\}\/landing/);
});

test("the coding chat draws it only for a coding task where coding exists", () => {
  const page = fs.readFileSync(path.join(process.cwd(), "src", "TaskPage.jsx"), "utf8");
  assert.match(page, /landing=\{canCode && t\.Kind === "coding" && <LandingCard /);
  assert.equal((page.match(/<LandingCard /g) || []).length, 1, "once, in the chat");
});
