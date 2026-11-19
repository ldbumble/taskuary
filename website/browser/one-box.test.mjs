import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* ONE ACTION BOX AT A TIME, A HARD RULE (cardqueue.py; the owner's live task, 2026-11-19): a held browser step stood at the front reading
   "1 of 2 · next: the reply to Gail Moreno" - and the reply's own box, with its Send, was drawn under it. What waits behind the front is its
   line and nothing else, on the chat and on the browser's view. Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "one-box");

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

// ...every action box on the task page: an act's card, the reply's box (its Send), a review's card - each by what it can press
const look = (page) => page.evaluate(() => {
  const pane = document.querySelector("[data-tq-task-page]"), vis = (e) => !!e && e.getBoundingClientRect().height > 0;
  const sends = [...(pane?.querySelectorAll("button") || [])].filter((b) => vis(b) && !b.disabled && /^(Send|Approve|Send reply|Draft reply|Reply|Write reply)$/.test(b.innerText.trim()));
  return { queue: [...(pane?.querySelectorAll("[data-tq-card-queue]") || [])].filter(vis).map((e) => e.innerText.trim()),
    presses: sends.map((b) => b.innerText.trim()), next: [...(pane?.querySelectorAll("[data-tq-next-steps]") || [])].filter(vis).length,
    reply: (pane?.innerText || "").includes("you're invited - the email from the portal") };
});

test("a held browser step with a reply behind it draws one box: the step's, with the line naming the reply", { timeout: 180000 }, async (t) => {
  const w = await world(t), page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  const made = await w.api("/api/fixture/held-pair", {});
  assert.ok(made.taskId, JSON.stringify(made));
  const dir = path.join(out, "video", "held-pair"); await mkdir(dir, { recursive: true });
  const rec = await record(page, dir);
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector("[data-tq-task-page] [data-tq-card-queue]", { visible: true, timeout: 60000 });
  await new Promise((r) => setTimeout(r, 4000));
  const seen = await look(page);
  await rec.stop();
  const detail = await w.api(`/api/tasks/${made.taskId}`);
  const ok = seen.queue.length === 1 && /1 of 2 · next: the reply to Gail Moreno/.test(seen.queue[0]) && !seen.reply && seen.presses.length === 1 && !seen.next
    && !(detail.browserActs || []).some((r) => r.ReviewId === made.reviewId);
  await note(dir, { done: "A held browser step on Erin's portal fronts the line; the reply to Gail waits behind it.",
    expect: "One action box (the step's Approve) with the line '1 of 2 · next: the reply to Gail Moreno' over it; no reply box, no second Send.",
    saw: JSON.stringify(seen), verdict: ok ? "PASS" : "FAIL" });
  assert.equal(seen.queue.length, 1, JSON.stringify(seen));
  assert.match(seen.queue[0], /1 of 2 · next: the reply to Gail Moreno/);
  assert.equal(seen.reply, false, `the held reply's box was drawn under the front: ${JSON.stringify(seen)}`);
  assert.equal(seen.presses.length, 1, `more than one action box: ${JSON.stringify(seen)}`);
  assert.equal(seen.next, 0, `the reply's block stood under the front: ${JSON.stringify(seen)}`);
  assert.deepEqual(errors, []);
});
