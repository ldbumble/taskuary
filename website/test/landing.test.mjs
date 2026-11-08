import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { HOW, landingFiles, landingTurn, landingWords } from "../src/landing.js";

test("the landing card says the branch's stat and the agent's pick", () => {
  const w = landingWords({ own: true, ahead: 2, changed: 3, plus: 40, minus: 12, proposal: { how: "merge", why: "the base moved" } });
  assert.equal(w.stat, "3 files changed, +40 −12 · 2 commits ahead");
  assert.equal(w.proposal, "The agent proposes Merge commit — the base moved.");
  // ...on the shared base its own commits, never "since the task started" - the branch's whole history (the owner's live coding task, 2026-11-08)
  const shared = landingWords({ own: false, shared: true, base: "master", commits: 2, changed: 1, plus: 1, minus: 0 });
  assert.equal(shared.stat, "1 file changed, +1 −0 · 2 commits of its own");
  assert.match(shared.shared, /^master is shared with other agents and releases - this counts only this task's own commits and edits/);
});

test("the four answers are the server's and discard asks once more before it goes", () => {
  assert.deepEqual(Object.keys(HOW), ["rebase", "merge", "pr", "discard"]);
  const body = fs.readFileSync(path.join(process.cwd(), "src", "LandingCard.jsx"), "utf8");
  assert.match(body, /how === "discard" && !sure/);
  assert.match(body, /\/api\/tasks\/\$\{taskId\}\/landing/);
});

test("the chat draws it only where the task works in a checkout, whatever its kind", () => {
  const page = fs.readFileSync(path.join(process.cwd(), "src", "TaskPage.jsx"), "utf8");
  assert.match(page, /landing=\{canCode && detail\?\.checkout && <LandingCard /);
  assert.equal((page.match(/<LandingCard /g) || []).length, 1, "once, in the chat");
});

test("the card is part of the turn its newest change came in, and moves with the chat", () => {
  const ms = [{ id: "u1", role: "user", createdAt: "2026-11-08 15:55:00" }, { id: "t1", role: "assistant", createdAt: "2026-11-08 15:55:12" },
    { id: "u2", role: "user", createdAt: "2026-11-08 15:56:15" }, { id: "t2", role: "assistant", createdAt: "2026-11-08 15:56:16" },
    { id: "t3", role: "assistant", createdAt: "2026-11-08 16:30:00" }];
  assert.equal(landingTurn(ms, "2026-11-08 16:09:55"), "t2");
  assert.equal(landingTurn(ms, ""), "t3");
  assert.equal(landingTurn(ms.slice(0, 1), "2026-11-08 16:09:55"), null);
  const chat = fs.readFileSync(path.join(process.cwd(), "src", "GeneralWorkspace.jsx"), "utf8");
  assert.match(chat, /\{landing\?\.after === id && landing\.node\}/);
  assert.match(chat, /\{!dock && !landAt && landNode\}/, "at the foot only before any turn");
});

test("the card's list folds the generated files and says how many more, apart from See the diff", () => {
  const { src, gen } = landingFiles([{ path: "taskuary/landing.py" }, { path: "website/package-lock.json" }, { path: "taskuary/static/assets/index-AbCd1234.js" }]);
  assert.deepEqual(src.map((f) => f.path), ["taskuary/landing.py"]);
  assert.equal(gen.length, 2);
  const body = fs.readFileSync(path.join(process.cwd(), "src", "LandingCard.jsx"), "utf8");
  assert.match(body, /sx=\{\{ display: "block", color: FAINT \}\}>and \{src\.length - SHOWN\} more<\/Typography>/, "its own line: never \"510 moreSee the diff\"");
  assert.match(body, /<Dialog open=\{diff !== null\}.*fullWidth maxWidth=\{false\}/, "the whole diff opens the window wide");
});
