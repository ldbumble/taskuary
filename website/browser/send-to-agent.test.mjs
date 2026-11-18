import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* SEND TO AGENT ON A REPORT (the owner, 2026-11-16/17: "report or dashboard or fyi they should all work the same ... it requires user prompt on what
   they want to know about it"; "it shows as pill on left side you type on it and it goes to blank canvas"). A report run lands; he opens it and
   presses Send to agent: a blank Agent canvas, the report a chip on the box, Send unlit until he types. His words start the agent; the task
   opens with his line carrying the report's name as a pill and the agent's turn under it. Recorded. Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "send-to-agent");

async function world(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify([{ when: "over 90 days", anywhere: true, first: "One invoice is over 90 days: Payworth, 1,200." }]));
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "1" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api };
}

for (const kind of (process.env.STA_KINDS || "report,dashboard").split(",")) test(`Send to agent on a ${kind}: blank canvas, chip on the box, his words start it`, { timeout: 300000 }, async (t) => {
  const w = await world(t), page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  const r = await w.api("/api/fixture/report", { title: kind === "dashboard" ? "Receivables board" : "Weekly AR aging", dashboard: kind === "dashboard" });
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((mid) => { location.hash = `msg=${mid}`; }, r.messageId);
  await page.waitForSelector("[data-tq-item-sections]", { visible: true, timeout: 60000 });
  await new Promise((res) => setTimeout(res, 1500));
  const dir = path.join(out, kind); const rec = await record(page, dir);
  const look = () => page.evaluate(() => {
    const vis = (e) => e && e.getBoundingClientRect().width > 0;
    const box = document.querySelector("[data-tq-item-ask]"), send = document.querySelector("[data-tq-item-send]");
    return { open: document.querySelector("[data-tq-item-body]")?.dataset.tqMain, ask: box?.dataset.tqItemAsk, chips: [...document.querySelectorAll("[data-tq-item-chip]")].filter(vis).map((c) => c.innerText.trim()),
      came: [...document.querySelectorAll("[data-tq-came-chip]")].filter(vis).map((c) => c.innerText.trim()), send: send ? (send.disabled ? "off" : "lit") : "none",
      place: document.querySelector("[data-tq-item-ask] textarea")?.placeholder || "", reading: document.querySelectorAll("[data-tq-item-reading]").length,
      task: !!document.querySelector("[data-tq-task-page]"), buttons: [...document.querySelectorAll("button")].filter(vis).map((b) => b.innerText.trim()).filter((x) => /agent/i.test(x)) };
  });
  const before = await look();
  // Send to agent - the item's own button, wherever it is laid
  const pressed = await page.evaluate(() => { const b = [...document.querySelectorAll("button")].find((x) => /^Send to agent/.test(x.innerText.trim()) && x.getBoundingClientRect().width > 0); b?.click(); return !!b; });
  assert.ok(pressed, `no Send to agent: ${JSON.stringify(before)}`);
  await page.waitForSelector("[data-tq-item-chip]", { visible: true, timeout: 10000 });
  await new Promise((res) => setTimeout(res, 600));
  const handed = await look();
  // ...an empty press does nothing, and says nothing wrong
  await page.evaluate(() => document.querySelector("[data-tq-item-send]")?.click());
  await new Promise((res) => setTimeout(res, 400));
  const empty = await look();
  await page.type("[data-tq-item-ask] textarea", "Which invoices are over 90 days?");
  const typed = await look();
  await page.evaluate(() => document.querySelector("[data-tq-item-send]")?.click());
  await page.waitForSelector("[data-tq-task-page]", { visible: true, timeout: 30000 });
  await page.waitForFunction(() => /Payworth, 1,200/.test(document.querySelector("[data-tq-task-page]")?.innerText || ""), { timeout: 60000 }).catch(() => {});
  await new Promise((res) => setTimeout(res, 1500));
  const after = await page.evaluate(() => {
    const tp = document.querySelector("[data-tq-task-page]");
    return { text: (tp?.innerText || "").replace(/\s+/g, " ").slice(0, 900), came: [...(tp?.querySelectorAll("[data-tq-line-came]") || [])].map((e) => e.innerText.trim()) };
  });
  await rec.stop();
  const saw = { before, handed, empty, typed, after, errors };
  await writeFile(path.join(dir, "states.json"), JSON.stringify(saw, null, 1));
  await note(dir, { done: `A ${kind} run lands; he opens it, presses Send to agent, presses Send empty, types, Send.`, expect: "Blank Agent canvas with the item a chip; Send unlit until words; the task opens with his line under the report's pill and the agent's answer.",
    saw: JSON.stringify(saw), verdict: "see assertions" });
  console.log(JSON.stringify(saw, null, 1));
  assert.equal(handed.open, "agent"); assert.equal(handed.reading, 0);
  assert.equal(handed.send, "off"); assert.equal(empty.send, "off"); assert.equal(typed.send, "lit");
  assert.ok(after.came.some((c) => c.includes(kind === "dashboard" ? "Receivables board" : "Weekly AR aging")), JSON.stringify(after));
  assert.match(after.text, /Which invoices are over 90 days\?/);
  assert.deepEqual(errors, []);
});
