import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* THE AGENT HANDS ITS BROWSER TO THE OWNER AND TAKES IT BACK (the overnight walk, 2026-11-11). The stand-in opens a portal and ends its turn handing
   over the sign-in ([[TASKUARY-YOURTURN: ...]]); its browser is said open on the page (/api/fixture/browser-page - no agent-browser here). Expected:
   ONE card in the chat; the browser pane shows while it is his step and says why; after his Done the agent goes on UNDER the card; nothing
   spins above it. Recorded, rows read at each state. Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "n17", "video", process.env.N17_NAME || "hand-over");

test("the agent hands its browser over for a sign-in and goes on under the card once he is done", { timeout: 600000 }, async (t) => {
  await mkdir(out, { recursive: true });
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${path.join(repo, "tests", "fake_claude.py")} %*\r\n` : `#!/bin/sh\nexec "${py}" "${path.join(repo, "tests", "fake_claude.py")}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify([
    { when: "pressed I'm done", anywhere: true, first: "Signed in - the price list is on the portal: Payworth 4 a head." },
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
  const page = await h.newPage(), errors = [], states = [];
  await page.setViewport({ width: 1600, height: 900 });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, task.taskId);
  await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 });
  const rec = await record(page, out);
  const look = async (label) => {
    const s = await page.evaluate(() => {
      const tp = document.querySelector("[data-tq-task-page]"), vp = tp?.querySelector(".tq-aui-viewport");
      const rows = vp ? [...vp.querySelectorAll(".tq-aui-message, [data-tq-asking], .tq-aui-ask")].filter((e) => e.getBoundingClientRect().height > 0)
        .map((e) => `${e.className || e.tagName}${e.querySelector("[data-tq-run-clock]") ? " CLOCK" : ""}${e.querySelector(".tq-aui-thinking") ? " SPIN" : ""} :: ${(e.innerText || "").replace(/\s+/g, " ").slice(0, 110)}`) : [];
      const pane = [...document.querySelectorAll("[data-tq-browser], .tq-browser, [class*=browser]")].filter((e) => e.getBoundingClientRect().width > 80).map((e) => `${e.className}`.slice(0, 60) + " :: " + (e.innerText || "").replace(/\s+/g, " ").slice(0, 120));
      const done = [...(tp?.querySelectorAll("button") || [])].filter((b) => /^(Done|I.m done)$/.test(b.innerText.trim()) && b.getBoundingClientRect().width > 0).length;
      // ...the line that says why the pane went, and the chip that brings a folded one back
      const closed = (document.querySelector("[data-tq-browser-closed]")?.innerText || "").trim();
      const chip = [...(tp?.querySelectorAll("button") || [])].map((b) => b.innerText.trim()).filter((x) => /^browser ·/.test(x));
      return { rows: rows.slice(-6), pane: pane.slice(0, 4), done, closed, chip };
    });
    states.push({ label, ...s }); await page.screenshot({ path: path.join(out, `${states.length}-${label}.png`) });
    return s;
  };
  try {
    await page.evaluate(() => document.querySelector("[data-tq-task-page] .tq-aui-input")?.focus());
    await page.keyboard.type("open the vendor portal and get the price list"); await page.keyboard.press("Enter");
    await page.waitForFunction(() => /sign in to the vendor portal|wants a sign-in/i.test(document.querySelector("[data-tq-task-page]")?.innerText || ""), { timeout: 60000 });
    await new Promise((r) => setTimeout(r, 4000)); await look("handed-over");
    // ...he puts the pane away in the middle of his step: there must be a way back to it
    const folded = await page.evaluate(() => { const b = [...document.querySelectorAll("[data-tq-task-page] button")].find((x) => /fold the browser away/.test(x.title || "")); b?.click(); return !!b; });
    states.push({ label: "fold pressed", folded });
    await new Promise((r) => setTimeout(r, 1500)); await look("folded-mid-step");
    const back = await page.evaluate(() => { const b = [...document.querySelectorAll("[data-tq-task-page] button")].find((x) => /^browser ·/.test(x.innerText.trim())); b?.click(); return b?.innerText.trim() || ""; });
    states.push({ label: "way back pressed", back });
    await new Promise((r) => setTimeout(r, 1500)); await look("unfolded");
    const pressed = await page.evaluate(() => { const b = [...document.querySelectorAll("button")].filter((x) => /^(Done|I.m done)$/.test(x.innerText.trim()) && !x.disabled && x.getBoundingClientRect().width > 0).pop(); b?.click(); return !!b; });
    states.push({ label: "done pressed", pressed });
    await new Promise((r) => setTimeout(r, 400)); await look("after-done-0.4s");
    await page.waitForFunction(() => /Signed in - the price list/.test(document.querySelector("[data-tq-task-page]")?.innerText || ""), { timeout: 60000 }).catch(() => states.push({ label: "no answer after Done within 60 s" }));
    await new Promise((r) => setTimeout(r, 3000)); await look("answered");
    await page.reload({ waitUntil: "domcontentloaded" }); await new Promise((r) => setTimeout(r, 5000)); await look("reloaded");
  } finally {
    await rec.stop();
    await writeFile(path.join(out, "states.json"), JSON.stringify(states, null, 1));
    await writeFile(path.join(out, "server.log"), h.backend.output());
    await note(out, { done: "The stand-in hands the sign-in over on its (said) open page; the owner presses Done; the agent answers.",
      expect: "One card; the pane while it is his step; the answer under the card; nothing spinning above it.", saw: "see states.json", verdict: "RECORDED" });
  }
  assert.deepEqual(errors, []);
});
