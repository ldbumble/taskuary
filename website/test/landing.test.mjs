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
  assert.match(body, /data-tq-land=\{h\}[\s\S]*onClick=\{\(\) => answer\(h\)\}/);
  assert.match(body, /\{s\.ask \? <Box[\s\S]*\{w\.first && press\(w\.first, "p"\)\}\{w\.second && press\(w\.second, "s"\)\}/);
  assert.match(body, /api\.post\(`\/api\/tasks\/\$\{taskId\}\/landing`, \{ how \}\)/, "Push and Push & deploy go down the landing road");
});

// the owner, 2026-11-09: "compact the land" - 26 files listed over Push and Push & deploy; then the card went once pressed
test("the landing card is one title, the files folded, one filled button and the other beside it - and stays pressed once it landed", () => {
  const s = { own: false, shared: true, base: "master", commits: 1, changed: 26, plus: 38, minus: 38, ask: true,
    push: { tip: "3a1b9a81c0ffee", ahead: 1, to: "master", deploy: "deploy" },
    answers: [{ how: "push", label: "Push" }, { how: "deploy", label: "Push & deploy" }] };
  const w = landingWords(s);
  assert.equal(w.title, "Push 1 commit to master and deploy - 26 files");
  assert.deepEqual([w.first, w.second], ["deploy", "push"]);
  const solo = { ...s, push: { ...s.push, deploy: "" }, answers: s.answers.slice(0, 1) };
  assert.equal(landingWords(solo).title, "Push 1 commit to master - 26 files");
  assert.deepEqual([landingWords(solo).first, landingWords(solo).second], ["push", ""]);
  const own = { own: true, branch: "fix-export", base: "master", ahead: 2, commits: 2, changed: 4, ask: true,
    answers: ["rebase", "merge", "pr", "discard"].map((how) => ({ how, label: HOW[how] })) };
  assert.equal(landingWords(own).title, "Land fix-export into master - 2 commits, 4 files");
  assert.deepEqual([landingWords(own).first, landingWords(own).second], ["rebase", "merge"]);
  assert.equal(landingWords({ ...own, proposal: { how: "merge" } }).second, "rebase", "never Discard as the second");
  const done = landingWords({ ...s, ask: false, push: null, answers: [], landed: { how: "deploy", sha: "3a1b9a81c0ffee", deploy: "deploy" } });
  assert.equal(done.done, "✓ Pushed and deployed");
  assert.equal(done.doneLine, "3a1b9a8 · to master and deploy");
  const body = fs.readFileSync(path.join(process.cwd(), "src", "LandingCard.jsx"), "utf8");
  assert.match(body, /\{filesOpen && <Box data-tq-landing-list=""/, "the file list waits behind Show the files");
  assert.match(body, /data-tq-pressed=\{s\.landed\.how\}/, "the press it took stays drawn");
  assert.doesNotMatch(body, /LAND THE BRANCH/);
});

// NO NOT NOW (the owner, 2026-11-10: "why ddo we need not now card? just hit next and you go to the next task and it stays on the rail"): the
// push card the agent raised is passed like every card once the conversation moves on (proposals.move_on) - greyed, nothing to press
test("the push card has no Not now; a passed one is greyed with no button, the way back said under its title", () => {
  const s = { own: false, shared: true, base: "master", commits: 1, changed: 5, plus: 116, minus: 9, ask: false, passed: true,
    push: { tip: "3a1b9a81c0ffee", ahead: 1, to: "master", deploy: "" }, answers: [] };
  assert.equal(landingWords(s).passed, "Set aside when you moved on - ask the agent to bring it back.");
  assert.equal(landingWords({ ...s, passed: false }).passed, "");
  const body = fs.readFileSync(path.join(process.cwd(), "src", "LandingCard.jsx"), "utf8");
  assert.doesNotMatch(body, /landing\/hold|data-tq-land-hold|Not now|s\.held/);
  assert.match(body, /data-tq-act-state=\{s\.passed \? "passed" : s\.ask \? "waiting"/);
  assert.match(body, /const sub = s\.passed \? w\.passed :/);
});

// REVIEW CHANGES STAYS AFTER THE SESSION IS GONE (the owner, 2026-11-10: "yes, keep it"): lit on work left to review, the row's button opens
// the landing card's own diff - one road to the diff, never a second viewer; the checkout's drawer only where no card stands to take it
test("the row's Review changes with no session open opens the landing card's diff", async () => {
  const { readFileSync } = await import("node:fs");
  const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
  const card = read("LandingCard.jsx"), page = read("TaskPage.jsx");
  assert.match(card, /export const LANDING_DIFF = "tq-landing-diff";/);
  assert.match(card, /window\.addEventListener\(LANDING_DIFF, on\)/);
  assert.match(card, /e\.detail\.handled = true; seeRef\.current\(\);/);
  // ...the listener stands before the card's early return: hooks in one order on every render
  assert.ok(card.indexOf("window.addEventListener(LANDING_DIFF") < card.indexOf("if (!s || (!s.ask && !s.landed && !s.changed)) return null;"));
  assert.match(page, /!liveSession && filled\("review_changes"\) \? \[\{ id: "diff"/);
  assert.match(page, /window\.dispatchEvent\(new CustomEvent\(LANDING_DIFF, \{ detail: ask \}\)\); if \(!ask\.handled\) setDiffOpen\(true\);/);
});
