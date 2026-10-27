import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";

/* AN AGENT'S WHOLE ROAD, ON A REAL START (the agents walk, 2026-10-26). A fresh home with a stand-in claude on PATH (tests/fake_claude.py:
   claude's stream-json I/O, no network) so Send to agent, Stop and save, Continue and a turn that dies run through the real server.
   What the walk found, each pinned here: a double press on Send to agent, Stop and save or Continue posted twice; Continue's note and the
   agent's question never showed (the conversation had loaded before the session existed and stopped looking); a turn whose CLI died
   left "Agent is working" and Stop and save over a dead session, its Result saying "You stopped it"; a stopped agent's Result asked for
   its browser every 3 s and named its AI twice. Invented task and people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const SCRIPT = [{ when: "crash", exit: 3 },
  { when: "question", first: "Which site should I start with - the north office or the south one?" },
  { when: ".", first: "Compared three vendors: Payworth is cheapest at 4 a head, Trainly 6, Spendly 7." }];

async function agentWorld(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  // unquoted on Windows: cmd strips the first and last quote of a line that starts with one, and python then read `-p` as its own
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify(SCRIPT));
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "0.3" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api };
}

const inTask = (page, re, timeout = 30000) => page.waitForFunction((src) => new RegExp(src).test(document.querySelector("[data-tq-task-page]")?.innerText || ""),
  { timeout, polling: 100 }, re.source).catch(async () => { throw new Error(`no ${re} on the task:\n${(await page.evaluate(() => document.querySelector("[data-tq-task-page]")?.innerText || "")).slice(0, 1500)}`); });
const twice = (page, label, within = "body") => page.evaluate((label, within) => {
  const b = [...document.querySelectorAll(`${within} button`)].find((x) => !x.disabled && x.textContent.trim() === label && x.offsetParent);
  if (!b) return false; b.click(); b.click(); return true;
}, label, within);
const shown = (page) => page.evaluate(() => [...document.querySelectorAll("button")].filter((b) => b.offsetParent && b.getBoundingClientRect().width).map((b) => b.textContent.trim()));

test("an agent's road: each press runs once, Continue shows what it said, and a turn that dies reads Failed with Try again",
  { timeout: 300000 }, async (t) => {
  const w = await agentWorld(t);
  const page = await w.newPage();
  await page.setViewport({ width: 1600, height: 810 });
  const errors = [], posts = [], polls = [], chats = [];
  page.on("pageerror", (e) => errors.push(e.message));
  // ...and React's own complaint about what a component was handed (a portal straight under a Box, on every live agent)
  page.on("console", (m) => { if (m.type() === "error" && /Failed %s type|Failed prop type/.test(m.text())) errors.push(m.text().slice(0, 200)); });
  page.on("request", (r) => { const p = new URL(r.url()).pathname;
    if (r.method() === "POST") posts.push(p); if (/^\/api\/terminals\/[^/]+\/browser$/.test(p)) polls.push(Date.now());
    if (r.method() === "GET" && /^\/api\/tasks\/\d+\/assistant$/.test(p)) chats.push(Date.now()); });
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  const made = await w.api("/api/tasks", { Title: "Compare payroll vendors", Summary: "Compare three payroll vendors on price for Northwind", Kind: "general" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const count = (re) => posts.filter((p) => re.test(p)).length;

  // SEND TO AGENT, pressed twice in its box: one dispatch, and the agent's answer
  // ...the row's, in view: the box itself waits in the shut Agent drawer, so a press on nothing (the row not drawn yet) opened nothing
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.textContent.trim() === "Send to agent" && b.offsetParent), { timeout: 30000 });
  assert.ok(await page.evaluate(() => { const b = [...document.querySelectorAll("button")].find((x) => x.textContent.trim() === "Send to agent" && x.offsetParent); b.click(); return true; }));
  await page.waitForSelector("[data-tq-run-form] textarea", { timeout: 15000 });
  assert.ok(await twice(page, "Send to agent", "[data-tq-run-form]"), "the box's Send to agent");
  await inTask(page, /Payworth is cheapest/);
  assert.equal(count(/\/dispatch$/), 1, "one press, one dispatch");

  // STOP AND SAVE, pressed twice: one write-up, and the Result names its AI once
  assert.ok(await twice(page, "Stop and save"));
  await inTask(page, /Result/);
  await inTask(page, /You stopped it and its report is written/);
  assert.equal(count(/\/wrap$/), 1, "one press, one write-up");
  assert.equal(await page.evaluate(() => [...document.querySelectorAll("[data-tq-task-page] *")].some((e) => /^AI\s+claude$/i.test(e.textContent.trim()))), false,
    "the record line already names the AI - no pill saying it again");
  // ...and nothing asks after the browser of an agent that has stopped
  const quiet = Date.now(); await new Promise((r) => setTimeout(r, 7000));
  assert.equal(polls.filter((at) => at >= quiet).length, 0, "a stopped agent's browser is not polled");

  // CONTINUE, its card pressed twice: one continue, and the note and the agent's question show without a reload
  assert.ok(await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Continue" && b.offsetParent)?.click() ?? true));
  await page.waitForSelector("[data-tq-continue-card] textarea", { timeout: 15000 });
  await page.type("[data-tq-continue-card] textarea", "one question for me before you go on");
  assert.ok(await twice(page, "Continue", "[data-tq-continue-card]"));
  await inTask(page, /north office or the south one/, 20000);
  assert.equal(count(/\/continue-work$/), 1, "one press, one continue");

  // A TURN THAT DIES: Failed and its reason first, Try again lit, nothing left saying it works
  const box = await page.waitForSelector("[data-tq-task-page] textarea", { timeout: 15000 });
  await box.type("crash please"); const died = Date.now(); await page.keyboard.press("Enter");
  await inTask(page, /Result\s+Failed - /, 20000);
  // ...once: a task read from before the session ended put it back, and the view flipped between the live pane and the Result,
  // its conversation mounted again each time
  await new Promise((r) => setTimeout(r, 4000));
  assert.ok(chats.filter((at) => at >= died).length <= 2, `the conversation was read ${chats.filter((at) => at >= died).length} times as the turn died`);
  const row = await shown(page);
  assert.ok(row.includes("Try again"), `Try again on the row: ${row.join(" | ")}`);
  assert.ok(!row.includes("Stop and save"), `no Stop and save over a dead session: ${row.join(" | ")}`);
  assert.doesNotMatch(await page.evaluate(() => document.querySelector("[data-tq-task-page]").innerText), /Agent is working|You stopped it/);
  assert.deepEqual(errors, []);
});
