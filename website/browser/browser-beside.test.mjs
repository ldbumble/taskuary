import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* THE LIVE BROWSER SITS BESIDE THE CHAT, NEVER OVER THE TASK LIST (design round 6, D8: a LinkedIn sign-in opened the page and his task list went
   with it - twice; "Back to task" did nothing; the card above the turn moved under it). A laptop's 1280 px window: the stand-in opens a sign-in
   page and hands it over; the rail, the chat's rows and their places are read every 100 ms from his Enter to after the pane is up, then the
   X ("Back to task") is pressed. Recorded and read frame by frame. Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "r6", "video", process.env.R6_NAME || "browser-beside");

test("the browser opens beside the chat with the task list still there, and nothing in the chat moves", { timeout: 600000 }, async (t) => {
  await mkdir(out, { recursive: true });
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${path.join(repo, "tests", "fake_claude.py")} %*\r\n` : `#!/bin/sh\nexec "${py}" "${path.join(repo, "tests", "fake_claude.py")}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify([
    { when: "open the vendor portal", anywhere: true, first: "The portal wants a sign-in. [[TASKUARY-YOURTURN: sign in to the vendor portal]]" }]));
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "1" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  const task = await api("/api/fixture/mail-task", { title: "Price list from the portal" });
  assert.ok((await api("/api/fixture/browser-page", { taskId: task.taskId })).ok);
  const page = await h.newPage(), errors = [], samples = [];
  await page.setViewport({ width: 1280, height: 900 });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, task.taskId);
  await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 });
  const rec = await record(page, out);
  // ...each sample: is the task list on screen, is the page's view up, and each chat row's words with its top - so a row that moves is seen
  const sample = (label) => page.evaluate((label) => {
    const vis = (e) => !!e && e.getBoundingClientRect().width > 40 && e.getBoundingClientRect().height > 40;
    const tp = document.querySelector("[data-tq-task-page]"), vp = tp?.querySelector(".tq-aui-viewport");
    const rows = vp ? [...vp.querySelectorAll(".tq-aui-message")].filter((e) => e.getBoundingClientRect().height > 0)
      .map((e) => ({ w: (e.innerText || "").replace(/\s+/g, " ").slice(0, 60), top: Math.round(e.getBoundingClientRect().top - vp.getBoundingClientRect().top + vp.scrollTop) })) : [];
    const view = [...document.querySelectorAll("canvas, [data-tq-browser-view], [data-tq-browser]")].some(vis);
    return { label, rail: vis(document.querySelector("[data-tq-rail]")), view, task: vis(tp), chatW: Math.round(vp?.getBoundingClientRect().width || 0), rows };
  }, label);
  try {
    await page.evaluate(() => document.querySelector("[data-tq-task-page] .tq-aui-input")?.focus());
    await page.keyboard.type("open the vendor portal and get the price list"); await page.keyboard.press("Enter");
    const t0 = Date.now();
    while (Date.now() - t0 < 15000) { samples.push({ ms: Date.now() - t0, ...(await sample("open")) }); await new Promise((r) => setTimeout(r, 100)); }
    await page.screenshot({ path: path.join(out, "1-pane-up.png") });
    // ...and the X at the task's head: "Back to task"
    const x = await page.evaluate(() => { const b = document.querySelector('[data-tq-task-page] [aria-label="Back to task"], [data-tq-task-page] [aria-label="Close task"]'); b?.click(); return b?.getAttribute("aria-label") || ""; });
    const t1 = Date.now();
    while (Date.now() - t1 < 3000) { samples.push({ ms: 15000 + Date.now() - t1, ...(await sample("after-x")) }); await new Promise((r) => setTimeout(r, 100)); }
    await page.screenshot({ path: path.join(out, "2-after-back-to-task.png") });
    samples.push({ label: "x pressed", x });
  } finally {
    await rec.stop();
    await writeFile(path.join(out, "samples.json"), JSON.stringify(samples, null, 1));
    await note(out, { done: "At 1280 px he asks for the portal; the stand-in hands its sign-in over on an open page; then the X at the task's head.",
      expect: "The task list stays on screen throughout; the page beside the chat; no chat row moves once drawn; the X does something he can see.",
      saw: "see samples.json", verdict: "RECORDED" });
  }
  const up = samples.filter((s) => s.view);
  assert.ok(up.length, "the page was shown beside the chat");
  assert.ok(up.every((s) => s.rail), "the task list stays on screen while the page is up");
  assert.ok(samples.filter((s) => s.label === "after-x").some((s) => !s.task || !s.view), "the X does something he can see");
  assert.deepEqual(errors, []);
});
