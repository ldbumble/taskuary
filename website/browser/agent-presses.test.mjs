import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";

/* THE THREE AGENT PRESSES, FOR BOTH KINDS, ON AN OPEN TASK (the owner, 2026-10-27: "did you ensure new agent / Continue works on an open
   task, both coding and regular agent, both buttons, before pushing it all?"). On a real start - a stand-in claude on PATH
   (tests/fake_claude.py: stream-json for the regular agent, its interactive mode in a pty for the coding one), the real server - and on
   the canvas, as the owner uses it:
   (a) Send to agent starts an agent: its pane shows it working and the owner's ask, then the answer;
   (b) Continue on a stopped agent, a note typed and sent: the note at once, the pane working, the new answer in the same conversation;
   (c) Run another agent on a stopped agent: a second, separate run starts and is shown, the first one kept apart from it.
   Invented task and people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const SCRIPT = [
  { when: "south office", first: "Starting with the south office: two sites, both already on Payworth." },
  { when: "north office", first: "Fresh look from the north office: Trainly runs there today." },
  // a coding seed is the whole prompt (the task's words in it too): the run's own ask is matched before the task's
  { when: "rerun the importer", first: "Reran the importer: 412 rows, no errors." },
  { when: "second pass", first: "Second pass on the export: the totals now match." },
  { when: "export", first: "Found the export bug: the date column was read as text." },
  { when: ".", first: "Compared three vendors: Payworth is cheapest at 4 a head, Trainly 6, Spendly 7." }];

async function agentWorld(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify(SCRIPT));
  // a think long enough to see the pane working between the press and the answer
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "2" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body, method) => fetch(`${h.fixtureApi}${p}`, { method: method || (body ? "POST" : "GET"),
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const pageText = (page) => page.evaluate(() => document.querySelector("[data-tq-task-page]")?.innerText || "");
const termText = (page) => page.evaluate(() => [...document.querySelectorAll("[data-tq-task-page] .xterm-rows")].map((n) => n.textContent).join("\n"));
const inTask = (page, re, timeout = 30000) => page.waitForFunction((src) => new RegExp(src).test(document.querySelector("[data-tq-task-page]")?.innerText || ""),
  { timeout, polling: 50 }, re.source).catch(async () => { throw new Error(`no ${re} on the task:\n${(await pageText(page)).slice(-2000)}`); });
const inTerm = (page, re, timeout = 30000) => page.waitForFunction((src) => new RegExp(src).test([...document.querySelectorAll("[data-tq-task-page] .xterm-rows")]
  .map((n) => n.textContent).join("\n")), { timeout, polling: 100 }, re.source)
  .catch(async () => { throw new Error(`no ${re} in the agent's terminal:\n${(await termText(page)).slice(-1500)}\n--- page:\n${(await pageText(page)).slice(-1200)}`); });
const visible = (page, label, within = "body", timeout = 30000) => page.waitForFunction((label, within) => [...document.querySelectorAll(`${within} button`)]
  .some((b) => !b.disabled && b.textContent.trim() === label && b.offsetParent), { timeout }, label, within)
  .catch(async () => { throw new Error(`no ${label} to press in ${within}: ${(await page.evaluate(() => [...document.querySelectorAll("button")]
    .filter((b) => b.offsetParent).map((b) => b.textContent.trim()).filter(Boolean).join(" | ")))}`); });
const click = (page, label, within = "body") => page.evaluate((label, within) => {
  const b = [...document.querySelectorAll(`${within} button`)].find((x) => !x.disabled && x.textContent.trim() === label && x.offsetParent);
  if (!b) throw new Error(`no ${label} to press`); b.click();
}, label, within);
const press = async (page, label, within) => { await visible(page, label, within); await click(page, label, within); };
// the row's verb, on the row or in one of its ▾
async function rowVerb(page, id) {
  // the row is up once it has its verbs - not its Next: a task that is the last item has none (the nav pill, 37de8d86)
  await page.waitForSelector('[data-tq-row] [data-tq-next], [data-tq-row] [data-tq-back], [data-tq-row] button[data-tq-verb]', { timeout: 20000 });
  // ...on the row once its write-up has settled (it is greyed while Stop and save writes up)
  // ...or, a stage move, in the open Agent pane's heading or on its spine (the owner, 2026-10-29: they left the bar)
  let at = await page.waitForSelector([`[data-tq-row] button[data-tq-verb$="${id}"]:not([disabled])`, `[data-tq-pane-moves] button[data-tq-verb$="${id}"]:not([disabled])`,
    `[data-tq-spine-moves] button[data-tq-verb$="${id}"]:not([disabled])`, `[data-tq-head-moves] button[data-tq-verb$="${id}"]:not([disabled])`,
    `[data-tq-pane-strip] button[data-tq-verb$="${id}"]:not([disabled])`].join(", "), { timeout: id === "continue" ? 20000 : 3000 }).catch(() => null);
  for (const more of await page.$$("[data-tq-row] [data-tq-more]")) {
    if (at) break;
    await more.click();
    at = await page.waitForSelector(`[role=menuitem][data-tq-verb$="${id}"]`, { timeout: 1500 }).catch(() => null);
    if (!at) { await page.keyboard.press("Escape"); await sleep(400); }
  }
  if (!at) throw new Error(`no ${id} on the row: ${await page.evaluate(() => [...document.querySelectorAll("[data-tq-row] button, [role=menuitem]")]
    .map((b) => `${b.getAttribute("data-tq-verb")}=${b.innerText}`).join(", "))}`);
  await sleep(300);           // a menu still opening
  await at.evaluate((b) => b.click());
}
// the pane says the agent is on it
const working = (page) => page.evaluate(() => {
  const pane = document.querySelector("[data-tq-task-page]");
  return !!pane && (/working|thinking|Starting|Continuing…/i.test(pane.innerText) || !!pane.querySelector(".tq-typing, [data-tq-starting], .xterm-rows"));
});
// the box under Send to agent / Run another agent: the ask typed, then its own start
async function startFromBox(page, ask, kind) {
  await page.waitForSelector("[data-tq-run-form] textarea", { visible: true, timeout: 15000 });
  await page.type("[data-tq-run-form] textarea", ask);
  const start = `[data-tq-run-form] [data-tq-agent-start=${kind}]:not([disabled])`;
  await page.waitForSelector(start, { timeout: 20000 })
    .catch(async () => assert.fail(`no ${kind} start in the box: ${await page.evaluate(() => document.querySelector("[data-tq-run-form]")?.innerText)}`));
  await page.$eval(start, (b) => b.click());
}
// ...and its write-up done: while it runs the page holds the Agent pane, and its end puts the page where the task is up to (TaskPage mainKey)
// - Close out opened under it went back to Agent a few seconds later
const writtenUp = (page) => page.waitForFunction(() => !document.querySelector("[data-tq-writeup=pending]"), { timeout: 30000 });
// CONTINUE OPENS IN THE AGENT PANE (the owner, 2026-10-29: "both should open in the agent window, both for coding and general agent. Continue
// box should be inside the canvas always"): pressed on Agent's spine and in the open pane's heading, its card stands in the Agent pane, where
// Run another agent's box does - never under the canvas
async function continueInsideAgent(page) {
  for (const from of ["spine", "pane"]) {
    const key = from === "spine" ? "close" : "agent";
    if (!(await page.$(`[data-tq-slot=${key}][data-tq-open]`))) {
      await page.click(`[data-tq-section-tab=${key}] [data-tq-tab-name]`);
      await page.waitForSelector(`[data-tq-slot=${key}][data-tq-open]`, { timeout: 5000 });
    }
    const btn = `[data-tq-${from}-moves=agent] button[data-tq-verb$="continue"]:not([disabled])`;
    await page.waitForSelector(btn, { timeout: 20000 })
      .catch(async () => assert.fail(`no Continue on the Agent ${from}: ${await page.evaluate(() => [...document.querySelectorAll("[data-tq-spine-moves] button, [data-tq-pane-moves] button")]
        .map((b) => { const sp = b.closest("[data-tq-spine-moves]"), at = sp ? `spine:${sp.dataset.tqSpineMoves}` : `pane:${b.closest("[data-tq-pane-moves]")?.dataset.tqPaneMoves}`;
          return `${b.textContent}=${b.dataset.tqVerb}${b.disabled ? " (greyed)" : ""} on ${at}`; }).join(" | "))}`));
    await page.$eval(btn, (b) => b.click());
    await page.waitForSelector("[data-tq-slot=agent][data-tq-open] [data-tq-continue-pane] [data-tq-continue-card] textarea", { visible: true, timeout: 5000 })
      .catch(async () => assert.fail(`Continue from the ${from} did not open in the Agent pane: ${await page.evaluate(() => [...document.querySelectorAll("[data-tq-continue-card]")]
        .map((c) => c.closest("[data-tq-slot]")?.dataset.tqSlot || "outside the canvas").join(", "))}`));
    assert.equal(await page.evaluate(() => [...document.querySelectorAll("[data-tq-continue-card]")].filter((c) => !c.closest("[data-tq-slot=agent]")).length), 0,
      `no Continue card outside the Agent pane (${from})`);
    // ...FIRST in it (the owner, 2026-10-29): the new step's box under the strip, the last run's report below it, its words box taking the cursor
    const at = await page.evaluate(() => { const slot = document.querySelector("[data-tq-slot=agent]"), card = slot.querySelector("[data-tq-continue-card]");
      const report = slot.querySelector("[data-tq-result-summary], [data-tq-agent-record], [data-tq-earlier-run], [data-tq-full-result]");
      return { card: card.getBoundingClientRect().top, report: report ? report.getBoundingClientRect().top : null, focus: !!document.activeElement?.closest("[data-tq-continue-card]") }; });
    assert.ok(at.report === null || at.card < at.report, `the Continue box above the last run's report (${from}) ${JSON.stringify(at)}`);
    assert.ok(at.focus, `its field takes the cursor (${from})`);
    await click(page, "Cancel", "[data-tq-continue-card]");
    await page.waitForFunction(() => !document.querySelector("[data-tq-continue-card]"), { timeout: 5000 });
  }
}
async function continueWith(page, note, log = null) {
  await rowVerb(page, "continue");
  await page.waitForSelector("[data-tq-continue-card] textarea", { visible: true, timeout: 15000 });
  await page.type("[data-tq-continue-card] textarea", note);
  await click(page, "Continue", "[data-tq-continue-card]");
  const at = Date.now();
  // the card goes once the server has taken it; one that stays says why
  await page.waitForFunction(() => !document.querySelector("[data-tq-continue-card]"), { timeout: 15000 })
    .catch(async () => assert.fail(`Continue did not go through: ${await page.evaluate(() => document.querySelector("[data-tq-continue-card]")?.innerText)}`
      + `\n--- server:\n${(log?.() || "").slice(-2500)}`));
  return at;
}

async function openTask(t, kind) {
  const w = await agentWorld(t);
  const page = await w.newPage();
  await page.setViewport({ width: 1600, height: 810 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  const made = kind === "general"
    ? await w.api("/api/tasks", { Title: "Compare payroll vendors", Summary: "Compare three payroll vendors on price for Northwind", Kind: "general" })
    : await w.api("/api/tasks", { Title: "Fix the vendor export", Summary: "The vendor export drops the date column for Northwind", Kind: "coding" });
  // the coding task's checkout: an empty folder, pinned on the task, so the box has its code chosen
  if (kind === "coding") {
    const dir = await mkdtemp(path.join(os.tmpdir(), "taskuary-ledger-"));
    t.after(() => rm(dir, { recursive: true, force: true }).catch(() => {}));
    const put = await w.api(`/api/tasks/${made.taskId}/repo`, { repo: "northwind/ledger", path: dir }, "PUT");
    assert.ok(!put.detail, `the checkout was not taken: ${JSON.stringify(put)}`);
  }
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  return { w, page, errors, tid: made.taskId };
}

test("a regular agent on an open task: Send to agent, Continue, Run another agent", { timeout: 300000 }, async (t) => {
  const { page, errors } = await openTask(t, "general");

  await t.test("(a) Send to agent starts it: the ask, working, the answer", async () => {
    await press(page, "Send to agent");
    await startFromBox(page, "compare them on price per head", "general");
    await inTask(page, /compare them on price per head/, 5000);
    assert.ok(await working(page), `nothing says it works:\n${(await pageText(page)).slice(-600)}`);
    await inTask(page, /Payworth is cheapest/);
  });

  await t.test("(b) Continue on the stopped agent: the note at once, working, the answer in the same conversation", async () => {
    await press(page, "Stop and save");
    await page.waitForSelector("[data-tq-result-summary], [data-tq-full-result]", { timeout: 30000 });   // resting on its summary, one press from its record (2026-10-27)
    await writtenUp(page);
    await continueInsideAgent(page);
    const pressed = await continueWith(page, "look at the south office first");
    await inTask(page, /look at the south office first/, 1500);
    assert.ok(Date.now() - pressed < 1500, "the note shows with the press's answer");
    assert.ok(await working(page), `nothing says it works:\n${(await pageText(page)).slice(-600)}`);
    await inTask(page, /Starting with the south office/);
    const text = await pageText(page);
    assert.ok(text.includes("Payworth is cheapest") && text.indexOf("Payworth is cheapest") < text.indexOf("Starting with the south office"),
      "the new answer is under the first, in the same conversation");
  });

  await t.test("(c) Run another agent on the stopped agent: a second run, shown apart from the first", async () => {
    await press(page, "Stop and save");
    await page.waitForSelector("[data-tq-result-summary], [data-tq-full-result]", { timeout: 30000 });   // resting on its summary, one press from its record (2026-10-27)
    await writtenUp(page);
    await rowVerb(page, "run-another");
    await startFromBox(page, "take a fresh look from the north office", "general");
    await page.waitForSelector("[data-tq-earlier-run]", { timeout: 30000 })
      .catch(async () => assert.fail(`the new run was not drawn apart:\n${(await pageText(page)).slice(-1500)}`));
    // ...its own thread: the owner's ask for it, then its answer under it
    await page.waitForFunction(() => {
      const turns = [...document.querySelectorAll(".tq-aui-thread .tq-aui-agent, .tq-aui-thread .tq-aui-user")];
      const at = turns.findIndex((m) => m.matches(".tq-aui-user") && /take a fresh look from the north office/.test(m.innerText));
      return at >= 0 && turns.slice(at + 1).some((m) => m.matches(".tq-aui-agent") && m.innerText.trim());
    }, { timeout: 30000 }).catch(async () => assert.fail(`the second run's ask and answer are not on its thread:\n${(await pageText(page)).slice(-1500)}`));
    const seen = await page.evaluate(() => ({
      thread: [...document.querySelectorAll(".tq-aui-thread .tq-aui-agent, .tq-aui-thread .tq-aui-user")].map((m) => m.innerText).join("\n"),
      folded: document.querySelector("[data-tq-earlier-run]")?.textContent || "" }));
    assert.ok(!seen.thread.includes("Starting with the south office"), `the first agent's chat is still the thread: ${seen.thread}`);
    assert.ok(seen.folded.includes("Starting with the south office"), "the first agent's conversation is kept, folded");
  });
  assert.deepEqual(errors, []);
});

test("a coding agent on an open task: Send to agent, Continue, Run another agent", { timeout: 300000 }, async (t) => {
  const { w, page, errors, tid } = await openTask(t, "coding");

  await t.test("(a) Send to agent starts it: the ask, working, the answer", async () => {
    await press(page, "Send to agent");
    await startFromBox(page, "find the export bug", "coding");
    await page.waitForSelector("[data-tq-task-page] .xterm-rows", { timeout: 30000 })
      .catch(async () => assert.fail(`no agent pane:\n${(await pageText(page)).slice(-1500)}\n--- server:\n${w.backend.output().slice(-3000)}`));
    assert.ok(await working(page));
    await inTerm(page, /find the export bug|Found the export bug/);
    await inTerm(page, /Found the export bug/);
  });

  await t.test("(b) Continue on the stopped agent: the note at once, working, the answer in the same conversation", async () => {
    await press(page, "Stop and save");
    await page.waitForSelector("[data-tq-result-summary], [data-tq-full-result]", { timeout: 30000 });   // resting on its summary, one press from its record (2026-10-27)
    await writtenUp(page);
    await continueInsideAgent(page);
    await continueWith(page, "now rerun the importer", () => w.backend.output()).catch(async (e) => { throw new Error(`${e.message}
--- terminals: ${JSON.stringify(await w.api("/api/terminals")).slice(0, 3000)}`); });
    await page.waitForSelector("[data-tq-task-page] .xterm-rows", { timeout: 15000 });
    await inTerm(page, /now rerun the importer/, 10000);
    assert.ok(await working(page));
    await inTerm(page, /Reran the importer/);
  });

  await t.test("(c) Run another agent on the stopped agent: a second run, shown apart from the first", async () => {
    await press(page, "Stop and save");
    await page.waitForSelector("[data-tq-result-summary], [data-tq-full-result]", { timeout: 30000 });   // resting on its summary, one press from its record (2026-10-27)
    await writtenUp(page);
    const before = await w.api(`/api/terminals`);
    await rowVerb(page, "run-another");
    await startFromBox(page, "a second pass on the export", "coding");
    await page.waitForSelector("[data-tq-task-page] .xterm-rows", { timeout: 30000 })
      .catch(async () => assert.fail(`no agent pane:\n${(await pageText(page)).slice(-1500)}\n--- server:\n${w.backend.output().slice(-2500)}`));
    await inTerm(page, /Second pass on the export/);
    const term = await termText(page);
    assert.ok(!/Reran the importer/.test(term), `the first agent's session is the pane again:\n${term.slice(-800)}`);
    const after = await w.api(`/api/terminals`);
    const sids = (r) => (r.data || []).filter((s) => Number(s.taskId ?? s.task_id) === Number(tid)).map((s) => s.sid);
    assert.ok(sids(after).some((s) => !sids(before).includes(s)), `no new session: before ${JSON.stringify(sids(before))}, after ${JSON.stringify(sids(after))}`);
  });
  assert.deepEqual(errors, []);
});
