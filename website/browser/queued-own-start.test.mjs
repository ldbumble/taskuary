import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* A START QUEUED BEHIND A FULL HOUSE, THEN THE OWNER'S OWN LINE (the stress round on refused starts, 2026-11-18). A mail's assistant start
   waits for a free slot; the owner types on the task, which never waits on the cap. The page reads every state from the press: the queued
   line goes once his turn takes the task and never comes back, and the task's row carries no queued start under the working agent (it did
   until the turn ended and the drain found the task occupied). Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "queued-own-start");

test("the owner's own line over a queued start: the queued line goes and stays gone", { timeout: 300000 }, async (t) => {
  await mkdir(out, { recursive: true });
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${path.join(repo, "tests", "fake_claude.py")} %*\r\n` : `#!/bin/sh\nexec "${py}" "${path.join(repo, "tests", "fake_claude.py")}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify([{ when: "go ahead", anywhere: true, first: "Reviewed the tool - notes are below.", wait: 15 }]));
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "1" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  const made = await api("/api/fixture/mail-task", { owed: true });
  assert.ok((await api("/api/fixture/general/start", { taskId: made.taskId, queue: true })).queued);
  const page = await h.newPage(), errors = [];
  await page.setViewport({ width: 1600, height: 900 });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector("[data-tq-task-page] [data-tq-queued-line]", { visible: true, timeout: 60000 });
  const rec = await record(page, out);
  let seen = []; const rowStates = [];
  try {
    await page.evaluate(() => {
      window.__seen = []; const t0 = performance.now();
      const read = () => { const q = !!document.querySelector("[data-tq-task-page] [data-tq-queued-line]"), last = window.__seen.at(-1);
        if (last?.q !== q) window.__seen.push({ at: Math.round(performance.now() - t0), q }); };
      new MutationObserver(read).observe(document.body, { subtree: true, childList: true }); read();
      document.querySelector("[data-tq-task-page] .tq-aui-input")?.focus();
    });
    await page.keyboard.type("please go ahead"); await page.keyboard.press("Enter");
    // ...and while his turn runs, the task's own row: never "queued" over the agent at work
    for (let i = 0; i < 6; i++) {
      await new Promise((r) => setTimeout(r, 1500));
      const rows = (await api("/api/tasks?active=1")).data || [];
      const row = rows.find((r) => r.TaskId === made.taskId);
      rowStates.push(`${row?.State || "none"}${row?.Queued ? "+Q" : ""}`);
    }
    await page.waitForFunction(() => /notes are below/.test(document.querySelector("[data-tq-task-page]")?.innerText || ""), { timeout: 90000 });
    await new Promise((r) => setTimeout(r, 6000));
    seen = await page.evaluate(() => window.__seen);
    await page.screenshot({ path: path.join(out, "after.png") });
  } finally {
    await rec.stop();
    await writeFile(path.join(out, "server.log"), h.backend.output());
  }
  const detail = await api(`/api/tasks/${made.taskId}`);
  const back = seen.findIndex((x, i) => x.q && seen.slice(0, i).some((y) => !y.q));
  await note(out, { done: "A mail's assistant start queued behind a full house; the owner types on the task.", expect: "The queued line goes and never comes back; the task is not queued.",
    saw: JSON.stringify({ seen, rowStates, queued: detail?.queued }), verdict: back < 0 && !detail?.queued && !rowStates.some((x) => /queued|\+Q/.test(x)) ? "PASS" : "FAIL" });
  assert.ok(!rowStates.some((x) => /queued|\+Q/.test(x)), `the row was still queued while his turn ran: ${JSON.stringify(rowStates)}`);
  assert.equal(back, -1, `the queued line came back: ${JSON.stringify(seen)}`);
  assert.ok(!detail?.queued, `still queued: ${JSON.stringify(detail?.queued)}`);
  assert.deepEqual(errors, []);
});
