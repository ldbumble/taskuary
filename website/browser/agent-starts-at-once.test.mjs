import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";

/* AN AGENT STARTED ON THE TASK YOU ARE LOOKING AT SAYS SO AT ONCE (the owner, 2026-11-04: "I was looking at a task, then it needed an
   agent, but the agent tab did not say 'agent starting' right away. Until 10 seconds later it just opened"). The task open, nothing live;
   an agent started on it from elsewhere - through the API, as triage, Send to agent, Continue or a new mail does - and the Agent section
   says "Starting…" with its spinner within a poll, then gives way to the conversation. A real start: a stand-in claude on PATH
   (tests/fake_claude.py), slow to come up so the gap the owner saw is there to see. Invented task and people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");

async function agentWorld(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify([{ when: ".", first: "Payworth is cheapest at 4 a head, Trainly 6, Spendly 7." }]));
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "3", FAKE_CLAUDE_THINK: "2" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body, method) => fetch(`${h.fixtureApi}${p}`, { method: method || (body ? "POST" : "GET"),
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api };
}

const pageText = (page) => page.evaluate(() => document.querySelector("[data-tq-task-page]")?.innerText || "");
// the Agent section's starting line and its spinner (the band's pulsing dot), drawn and on screen
const startingShown = (page) => page.evaluate(() => {
  const line = document.querySelector("[data-tq-task-page] [data-tq-starting-line]"), dot = line?.querySelector(".tq-aui-band-dot");
  return !!(line && line.offsetParent && /Starting.*…/.test(line.innerText) && dot && getComputedStyle(dot).animationName !== "none");
});
async function seeStarting(page, from, label) {
  await page.waitForFunction(() => {
    const line = document.querySelector("[data-tq-task-page] [data-tq-starting-line]"), dot = line?.querySelector(".tq-aui-band-dot");
    return !!(line && line.offsetParent && /Starting.*…/.test(line.innerText) && dot && getComputedStyle(dot).animationName !== "none");
  }, { timeout: 15000, polling: 50 }).catch(async () => { throw new Error(`${label}: no starting line on the task:\n${(await pageText(page)).slice(0, 1500)}`); });
  return Date.now() - from;
}

test("an agent started on the open task shows Starting… with its spinner at once, then the conversation", { timeout: 300000 }, async (t) => {
  const w = await agentWorld(t);
  const page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });

  // SEND TO AGENT, pressed somewhere else (the dispatch door every start shares)
  const made = await w.api("/api/tasks", { Title: "Compare payroll vendors", Summary: "Compare three payroll vendors on price for Northwind", Kind: "general" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  await page.waitForFunction(() => /Compare payroll vendors/.test(document.querySelector("[data-tq-task-page]")?.innerText || ""), { timeout: 30000 });
  await new Promise((r) => setTimeout(r, 2500));       // at rest: whatever polls there are have slowed to their idle pace
  assert.equal(await startingShown(page), false, "nothing is starting yet");
  let at = Date.now();
  await w.api(`/api/tasks/${made.taskId}/dispatch`, { kind: "general" });
  const dispatched = await seeStarting(page, at, "dispatch");
  console.log(`# dispatch: Starting… shown after ${dispatched} ms`);
  assert.ok(dispatched < 1500, `Starting… took ${dispatched} ms after the start`);
  await page.waitForFunction(() => /Payworth is cheapest/.test(document.querySelector("[data-tq-task-page]")?.innerText || ""), { timeout: 60000 });
  assert.equal(await page.$("[data-tq-task-page] [data-tq-starting-line]"), null, "the starting line gives way to the conversation");

  // CONTINUE, from elsewhere, on a task whose agent was stopped
  await w.api(`/api/tasks/${made.taskId}/pause`, {});
  await page.waitForFunction(() => !document.querySelector("[data-tq-task-page] [data-tq-agent-room='live']"), { timeout: 30000 });
  await new Promise((r) => setTimeout(r, 2500));
  at = Date.now();
  await w.api(`/api/tasks/${made.taskId}/continue-work`, { note: "and the south office?" });
  const continued = await seeStarting(page, at, "continue");
  console.log(`# continue: Starting… shown after ${continued} ms`);
  assert.ok(continued < 1500, `Starting… took ${continued} ms after Continue`);
  await page.waitForFunction(() => !document.querySelector("[data-tq-task-page] [data-tq-starting-line]"), { timeout: 60000 });

  // TRIAGE: a quick look that holds the task for seconds with no session, then needs the agent (quickwork.escalate) - the owner's case
  const next = await w.api("/api/tasks", { Title: "Check the training renewal", Summary: "Check what the Trainly renewal costs for Northwind", Kind: "general" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, next.taskId);
  await page.waitForFunction(() => /Check the training renewal/.test(document.querySelector("[data-tq-task-page]")?.innerText || ""), { timeout: 30000 });
  await new Promise((r) => setTimeout(r, 2500));
  at = Date.now();
  await w.api("/api/fixture/general/start", { taskId: next.taskId, hold: 4 });
  const triaged = await seeStarting(page, at, "triage");
  console.log(`# triage: Starting… shown after ${triaged} ms`);
  assert.ok(triaged < 1500, `Starting… took ${triaged} ms after triage started it`);
  await page.waitForFunction(() => /Payworth is cheapest/.test(document.querySelector("[data-tq-task-page]")?.innerText || ""), { timeout: 60000 });
  assert.equal(await page.$("[data-tq-task-page] [data-tq-starting-line]"), null, "the starting line gives way to the conversation");

  // QUEUED behind full agent slots: "Waiting its turn", not Starting…
  const third = await w.api("/api/tasks", { Title: "Sort the vendor invoices", Summary: "Sort the Spendly invoices by month", Kind: "general" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, third.taskId);
  await page.waitForFunction(() => /Sort the vendor invoices/.test(document.querySelector("[data-tq-task-page]")?.innerText || ""), { timeout: 30000 });
  await new Promise((r) => setTimeout(r, 2500));
  at = Date.now();
  const q = await w.api("/api/fixture/general/start", { taskId: third.taskId, queue: true });
  await page.waitForFunction(() => /waiting its turn/i.test(document.querySelector("[data-tq-task-page]")?.innerText || ""), { timeout: 15000, polling: 50 })
    .catch(async () => { throw new Error(`no Waiting its turn (${JSON.stringify(q)}):
${(await pageText(page)).slice(0, 1500)}
${JSON.stringify((await w.api(`/api/tasks/${third.taskId}`)).queued)}`); });
  const queued = Date.now() - at;
  console.log(`# queued: Waiting its turn shown after ${queued} ms`);
  assert.ok(queued < 1500, `Waiting its turn took ${queued} ms`);
  assert.equal(await startingShown(page), false, "a queued start is not Starting…");
  await w.api(`/api/tasks/${third.taskId}/dispatch`, null, "DELETE");
  assert.deepEqual(errors, []);
});
