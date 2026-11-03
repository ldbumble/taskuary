import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { hit, sleep, where } from "./stress-buttons.mjs";

/* THE AGENT BUTTONS, PRESSED LIKE A HURRIED HAND (the owner, 2026-11-02: "click every button on every task ... clicking buttons fast/slow,
   multiple times"): Send to agent's start, Stop and save, Continue and Run another agent, each pressed twice fast with the mouse where the
   button stands, on a real start (tests/fake_claude.py on PATH, as agent-presses) - and each did its work once: one run started, one
   conversation turn, one write-up. Nothing on the page errs, and the Agent pane never folds away under the presses. Invented task only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const SCRIPT = [{ when: "north office", first: "Fresh look from the north office: Trainly runs there today." },
  { when: "south office", first: "Starting with the south office: two sites, both already on Payworth." },
  { when: "second pass", first: "Second pass on the export: the totals now match." },
  { when: "export", first: "Found the export bug: the date column was read as text." },
  { when: ".", first: "Compared three vendors: Payworth is cheapest at 4 a head, Trainly 6, Spendly 7." }];

async function world(t, kind) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify(SCRIPT));
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "2" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body, method) => fetch(`${h.fixtureApi}${p}`, { method: method || (body ? "POST" : "GET"),
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  if (kind === "coding") await api("/api/settings", { name: "developer_mode", value: "1" }, "PATCH");
  const page = await h.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error" || (m.type() === "warning" && /Warning:/.test(m.text()))) errors.push(m.text().slice(0, 300)); });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  const made = kind === "general"
    ? await api("/api/tasks", { Title: "Compare payroll vendors", Summary: "Compare three payroll vendors on price for Northwind", Kind: "general" })
    : await api("/api/tasks", { Title: "Fix the vendor export", Summary: "The vendor export drops the date column for Northwind", Kind: "coding" });
  if (kind === "coding") {
    const dir = await mkdtemp(path.join(os.tmpdir(), "taskuary-ledger-"));
    t.after(() => rm(dir, { recursive: true, force: true }).catch(() => {}));
    await api(`/api/tasks/${made.taskId}/repo`, { repo: "northwind/ledger", path: dir }, "PUT");
  }
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector(`[data-tq-task-page="${made.taskId}"]`, { timeout: 30000 });
  await sleep(1500);
  const tid = made.taskId;
  // every session this task has had, as the terminals list has shown them while the test watched
  const sids = new Set();
  const sessions = async () => { for (const s of (await api("/api/terminals")).data || []) if (Number(s.taskId ?? s.task_id) === tid) sids.add(s.sid); return sids.size; };
  const said = async (words) => ((await api(`/api/tasks/${tid}`)).comments || []).filter((c) => (c.Body || "").includes(words)).length;
  const reports = async () => ((await api(`/api/tasks/${tid}`)).comments || []).filter((c) => /AGENT REPORT/.test(c.Body || "")).length;
  return { h, api, page, errors, tid, sessions, said, reports };
}
const SHOTS = process.env.TQ_STRESS_SHOTS;
const inTask = (page, re, timeout = 30000) => page.waitForFunction((src) => new RegExp(src).test(document.querySelector("[data-tq-task-page]")?.innerText || ""),
  { timeout, polling: 100 }, re.source).catch(async (e) => {
    if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `agents-missing-${Date.now()}.png`) });
    throw new Error(`no ${re} on the task:\n${(await page.evaluate(() => document.querySelector("[data-tq-task-page]")?.innerText || "")).slice(-1500)}`, { cause: e }); });
const term = (page, re, timeout = 30000) => page.waitForFunction((src) => new RegExp(src).test([...document.querySelectorAll("[data-tq-task-page] .xterm-rows")].map((n) => n.textContent).join("\n")),
  { timeout, polling: 100 }, re.source);
const ready = async (page, spec, ms = 30000) => { for (const end = Date.now() + ms; Date.now() < end; await sleep(200)) if (await where(page, spec)) return true; return false; };
// a box's own start, twice fast: the words typed once, then the button pressed the way a double click lands
async function startTwice(page, words, kind) {
  await page.waitForSelector("[data-tq-run-form] textarea", { visible: true, timeout: 15000 });
  await page.type("[data-tq-run-form] textarea", words);
  const go = `[data-tq-run-form] [data-tq-agent-start=${kind}]:not([disabled])`;
  await page.waitForSelector(go, { timeout: 20000 });
  const r = await page.$eval(go, (b) => { b.scrollIntoView({ block: "nearest" }); const x = b.getBoundingClientRect(); return { x: x.x + x.width / 2, y: x.y + x.height / 2 }; });
  await page.mouse.click(r.x, r.y); await sleep(70); await page.mouse.click(r.x, r.y);
}
const stopTwice = async (page) => { assert.ok(await ready(page, "save-end"), "no Stop and save"); assert.ok(await hit(page, "save-end", 2, 70)); };
const writtenUp = (page) => page.waitForFunction(() => !document.querySelector("[data-tq-writeup=pending]"), { timeout: 40000 });

for (const kind of ["general", "coding"]) {
  test(`a ${kind} agent's buttons, each pressed twice fast, each run once`, { timeout: 420000 }, async (t) => {
    const w = await world(t, kind);
    const { page } = w;
    // Send to agent, its start pressed twice: one session, the ask said once
    assert.ok(await ready(page, kind === "general" ? "send-general" : "start-agent") || await ready(page, "start-agent"), "no Send to agent");
    await hit(page, (await where(page, "send-general")) ? "send-general" : "start-agent", 2, 70);
    const ask = kind === "general" ? "compare them on price per head" : "find the export bug";
    await startTwice(page, ask, kind);
    if (kind === "general") { await inTask(page, /Payworth is cheapest/); assert.equal(await w.said(ask), 1, "the ask was said once"); }
    else { await term(page, /Found the export bug/); assert.equal(await w.sessions(), 1, "one start made one session"); }
    // Stop and save twice: one write-up
    await stopTwice(page);
    await page.waitForSelector("[data-tq-result-summary], [data-tq-full-result]", { timeout: 40000 });
    await writtenUp(page); await sleep(2500);
    assert.ok((await w.reports()) <= 1, `one stop, one write-up: ${await w.reports()}`);
    // Continue, its own button pressed twice: the note once, one turn
    assert.ok(await ready(page, "continue"), "no Continue");
    await hit(page, "continue");
    await page.waitForSelector("[data-tq-continue-card] textarea", { visible: true, timeout: 15000 });
    const note = kind === "general" ? "look at the south office first" : "now look at the second pass";
    await page.type("[data-tq-continue-card] textarea", note);
    assert.ok(await hit(page, "text:^Continue$@[data-tq-continue-card]", 2, 70), "no Continue in its card");
    if (kind === "general") { await inTask(page, /Starting with the south office/); await sleep(1500); assert.equal(await w.said(note), 1, "the note was said once"); }
    else { await term(page, /Second pass on the export/); assert.ok((await w.sessions()) <= 2, `one Continue, at most one new session: ${await w.sessions()}`); }
    // Run another agent, its start pressed twice: exactly one more session
    await stopTwice(page);
    await page.waitForSelector("[data-tq-result-summary], [data-tq-full-result]", { timeout: 40000 });
    await writtenUp(page); await sleep(1500);
    assert.ok(await ready(page, "run-another"), "no Run another agent");
    const before = await w.sessions();
    await hit(page, "run-another");
    await startTwice(page, "take a fresh look from the north office", kind);
    const again = "take a fresh look from the north office";
    // ...its answer under its ask (a second run's prompt does not end on the owner's words, so the stand-in answers its catch-all)
    if (kind === "general") { await inTask(page, /take a fresh look from the north office\s+TASKUARY\s+\S/); await sleep(2000); assert.equal(await w.said(again), 1, "the second run's ask was said once"); }
    else { await term(page, /Fresh look from the north office|north office/); await sleep(2000); assert.equal(await w.sessions(), before + 1, "one Run another agent, one new session"); }
    assert.deepEqual(w.errors, []);
  });
}
