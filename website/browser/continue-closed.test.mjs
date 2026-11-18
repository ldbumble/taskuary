import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { startHarness } from "./harness.mjs";
import { headUnderLine, turnWatched, watchTurn } from "./turnWatch.mjs";

const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
/* CONTINUE ON A FINISHED OR FAILED CHAT (the Continue round, 2026-11-18): a chat task marked done, or one whose turn failed, and a line typed
   into its box - the Continue of a chat. From the press: his line once, one running head under it, and what stands above his line never changes
   after his line is drawn - recorded, "You reopened it" entered above the line a frame later, and a failed turn went from above it. Invented
   people only. */
const SCRIPT = [{ when: "now the south office", anywhere: true, first: "Starting with the south office: two sites, both on Payworth." },
  { when: "fail now", exit: 3, anywhere: true },
  { when: ".", first: "Compared three vendors: Payworth is cheapest at 4 a head." }];

async function agentWorld(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const py = execFileSync("python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  await writeFile(path.join(bin, "claude"), `#!/bin/sh\nexec "${py}" "${path.join(repo, "tests", "fake_claude.py")}" "$@"\n`);
  await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify(SCRIPT));
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "2.0" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api, bin };
}
const pageText = (page) => page.evaluate(() => document.querySelector("[data-tq-task-page]")?.innerText || "");
const inTask = (page, re, timeout = 30000) => page.waitForFunction((src) => new RegExp(src).test(document.querySelector("[data-tq-task-page]")?.innerText || ""),
  { timeout, polling: 50 }, re.source).catch(async () => { throw new Error(`no ${re} on the task:\n${(await pageText(page)).slice(0, 2000)}`); });
const above = (page, line) => page.evaluate((line) => {
  const vp = document.querySelector("[data-tq-task-page] .tq-aui-viewport"); const t = vp?.innerText || ""; const i = t.indexOf(line);
  return i < 0 ? t : t.slice(0, i); }, line);

for (const shape of ["done", "failed"]) test(`a ${shape} chat task, then a line typed: one head under it, nothing above it moves`, { timeout: 300000 }, async (t) => {
  const w = await agentWorld(t);
  const page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  const made = await w.api("/api/tasks", { Title: "Compare payroll vendors", Summary: "Compare three payroll vendors on price for Northwind", Kind: "general" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const box = () => page.waitForSelector("[data-tq-task-page] [data-tq-agent-room] .tq-aui-input", { visible: true, timeout: 30000 });
  await (await box()).type(shape === "failed" ? "compare them, fail now" : "compare them on price."); await page.keyboard.press("Enter");
  if (shape === "failed") await inTask(page, /Failed|failed|exit|stopped/i, 40000);
  else {
    await inTask(page, /Payworth is cheapest/);
    const op = await w.api("/api/operations", { kind: "task.complete", target: made.taskId, params: {} });
    await w.api(`/api/operations/${op.id}/execute`, { version: op.version });
    await inTask(page, /marked it done/i);
  }
  await new Promise((r) => setTimeout(r, 1500));
  await page.waitForFunction(() => !document.querySelector("[data-tq-task-page] .tq-aui-input")?.disabled, { timeout: 30000 });
  const note = "now the south office";
  const before = await above(page, "@@nothing@@");
  await (await box()).type(note);
  await watchTurn(page, note, /Starting with the south office/, headUnderLine);
  // what was above, sampled each frame from the press
  await page.evaluate((before) => { window.__tqAbove = []; const f = () => { const vp = document.querySelector("[data-tq-task-page] .tq-aui-viewport")?.innerText || "";
    const i = vp.indexOf("now the south office"); if (i >= 0) window.__tqAbove.push(vp.slice(0, i)); if (!/Starting with the south/.test(vp)) requestAnimationFrame(f); }; requestAnimationFrame(f); }, before);
  await page.keyboard.press("Enter");
  const wt = await turnWatched(page, 40000);
  await new Promise((r) => setTimeout(r, 1500));
  const aboves = [...new Set(await page.evaluate(() => window.__tqAbove))];
  assert.deepEqual(aboves.map((x) => x.trim()), [aboves[0].trim()], `what stands above his line changed after it was drawn:\n${aboves.join("\n=====\n")}`);
  assert.ok(aboves[0].startsWith(before.trim()), `the chat above his line is the chat he typed under:\n${before}\n---\n${aboves[0]}`);
  assert.ok(wt.first != null && wt.first <= 1500, `the turn's head under his line at ${wt.first} ms`);
  assert.deepEqual(wt.bad.filter(([at, why]) => !(at < wt.first && /drawn 0 times/.test(why))), [], "every state after the press: one head, under his line");
  if (shape === "failed") assert.match(aboves[0], /stopped in the middle of its turn/, "the failure stays where it happened");
  else assert.doesNotMatch(aboves[0], /You reopened it/, "his line is the reopen");
  assert.deepEqual(errors, []);
});
