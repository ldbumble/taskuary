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
  assert.deepEqual(Object.keys(HOW), ["rebase", "merge", "pr", "discard", "push", "deploy"]);
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
  assert.match(body, /<Dialog open=\{open\}.*fullWidth maxWidth=\{false\}/, "the whole diff opens the window wide");
});

// the owner, 2026-11-09: See the diff waited for the read before anything opened - it felt dead for a second
test("See the diff opens its window at the press, reading the changes in it, and says so if they cannot be read", () => {
  const body = fs.readFileSync(path.join(process.cwd(), "src", "LandingCard.jsx"), "utf8");
  assert.match(body, /const seeDiff = \(\) => \{ if \(open\) return setOpen\(false\); setOpen\(true\); setDiff\(null\); readDiff\(\); \};/);
  assert.match(body, /<CircularProgress size=\{14\} color="inherit" \/>Loading the changes…<\/Typography>/);
  assert.match(body, /\{diffErr && <Typography variant="body2" data-tq-diff-error=""/);
});

// the owner, 2026-11-09 (~20th time): "i thought actions should be cards/buttons??? why is this text??" - an agent's commits straight on
// master, unpushed, under a card with no button; the owner typed "yes"
test("unpushed commits on the shared base are Push and Push & deploy buttons, and a press posts its how to the landing road", () => {
  const s = { own: false, shared: true, base: "master", commits: 1, changed: 5, plus: 116, minus: 9, ask: true,
    push: { tip: "3a1b9a81c0ffee", ahead: 1, to: "master", deploy: "deploy" },
    answers: [{ how: "push", label: "Push" }, { how: "deploy", label: "Push & deploy" }] };
  const w = landingWords(s);
  assert.equal(w.question, "Push 1 commit to origin/master, up to 3a1b9a8, and deploy it to deploy?");
  assert.equal(w.primary, "deploy", "the furthest the work can go, when the agent picked nothing");
  assert.equal(landingWords({ ...s, proposal: { how: "push" } }).primary, "push");
  assert.equal(landingWords({ ...s, push: { ...s.push, deploy: "" }, answers: s.answers.slice(0, 1) }).question, "Push 1 commit to origin/master, up to 3a1b9a8?");
  assert.equal(landingWords({ own: true, ask: true, answers: [] }).question, "How should it land?");
  const body = fs.readFileSync(path.join(process.cwd(), "src", "LandingCard.jsx"), "utf8");
  assert.match(body, /\{s\.ask && <>[\s\S]*\{w\.question\}[\s\S]*s\.answers\.map\(\(a\) => \([\s\S]*data-tq-land=\{a\.how\}[\s\S]*onClick=\{\(\) => answer\(a\.how\)\}/);
  assert.match(body, /api\.post\(`\/api\/tasks\/\$\{taskId\}\/landing`, \{ how \}\)/, "Push and Push & deploy go down the landing road");
});
