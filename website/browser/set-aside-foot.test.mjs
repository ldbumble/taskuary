import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* A SET-ASIDE DRAFT NEVER STICKS TO THE CHAT'S FOOT (the owner's live app, 2026-11-18: "it never leaves when you put in new prompt. it's
   broken"): on a Teams task a second reply waited its turn behind the first (cardqueue) and was set aside by his line before it ever stood.
   The chat's list places such a card nowhere - it never stood - yet the page drew its greyed Copy card under the newest turn, and again under
   every turn after. Invented people. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "set-aside-foot");
const BEHIND = "Hi Erin, a second note on the tool's pricing tiers.";

async function world(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), "[]");
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "1" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api };
}

// where the held reply's words stand: nowhere, in a turn, or under everything (after the last turn's head)
const where = (page) => page.evaluate((words) => {
  const pane = document.querySelector("[data-tq-task-page]"), turns = [...(pane?.querySelectorAll(".tq-conv [data-tq-ran]") || [])];
  const hits = [...(pane?.querySelectorAll(".tq-conv [data-tq-review], .tq-conv [data-tq-past-card], .tq-conv [data-tq-row-cards]") || [])]
    .filter((e) => (e.innerText + [...e.querySelectorAll("textarea")].map((x) => x.value).join(" ")).includes(words) && e.getBoundingClientRect().height > 0);
  const loose = !!pane?.querySelector('[data-tq-row-cards="loose"]') && [...pane.querySelectorAll('[data-tq-row-cards="loose"]')].some((e) => e.innerText.includes(words));
  return { n: hits.length, loose, turns: turns.length };
}, BEHIND);

test("a reply set aside before it ever stood is drawn nowhere - never greyed at the chat's foot under each new line", { timeout: 300000 }, async (t) => {
  const w = await world(t), page = await w.newPage();
  await page.setViewport({ width: 1400, height: 1000 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  const made = await w.api("/api/fixture/mail-task", { channel: "teams", conversation: "teams-foot" });
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector(`[data-tq-task-page] [data-tq-review="${made.reviewId}"]`, { visible: true, timeout: 60000 });
  const box = async () => page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 });
  const turns = (n) => page.waitForFunction((n) => document.querySelectorAll("[data-tq-task-page] .tq-conv [data-tq-ran]").length >= n, { timeout: 60000 }, n);
  const say = async (words) => { await (await box()).type(words); await page.keyboard.press("Enter"); };
  // ...a first turn, then the agent's two replies: the second waits its turn behind the first, drawn nowhere (cardqueue.mark as the chat is read)
  await say("what do you make of her ask?"); await turns(1);
  const front = await w.api("/api/fixture/draft", { taskId: made.taskId, text: "Hi Erin, the review is on its way this week." });
  const held = await w.api("/api/fixture/draft", { taskId: made.taskId, text: BEHIND });
  await page.reload({ waitUntil: "domcontentloaded" });          // ...the fixture's rows land with no event of their own: read afresh
  await page.waitForSelector(`[data-tq-task-page] [data-tq-review="${front.reviewId}"]`, { visible: true, timeout: 60000 }).catch(async (e) => {
    await page.screenshot({ path: path.join(out, "no-front.png") }); throw e; });
  await new Promise((r) => setTimeout(r, 2500));
  const dir = path.join(out, process.env.FOOT_RUN || "run"); await mkdir(dir, { recursive: true });
  const rec = await record(page, dir), seen = [];
  for (const [i, said] of ["thanks - one more thing on the pricing", "and what did their support say?"].entries()) {
    await say(said); const t0 = Date.now();
    while (Date.now() - t0 < 15000) { seen.push({ said, at: Date.now() - t0, ...(await where(page)) }); await new Promise((r) => setTimeout(r, 400)); }
    await page.screenshot({ path: path.join(dir, `after-line-${i + 1}.png`) });
  }
  await rec.stop();
  const rv = (await w.api(`/api/tasks/${made.taskId}`)).reviews?.find((r) => r.ReviewId === held.reviewId);
  const bad = seen.filter((s) => s.loose || s.n);
  await note(dir, { done: "A Teams task: the agent's reply waits, a second waits behind it; the owner writes twice.",
    expect: "The second reply, set aside before it stood, is drawn nowhere - never greyed under the newest turn.",
    saw: `held reply ${rv?.Status} (${rv?.DecideNote}); drawn in ${bad.length} of ${seen.length} samples: ${JSON.stringify(bad.slice(0, 3))}`, verdict: bad.length ? "FAIL" : "PASS" });
  assert.equal(rv?.Status, "superseded", `the held reply was set aside: ${JSON.stringify(rv)}`);
  assert.deepEqual(bad, [], "the set-aside reply stood at the chat's foot");
  assert.deepEqual(errors, []);
});
