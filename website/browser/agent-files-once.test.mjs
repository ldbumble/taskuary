import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

// ONE OF EACH THING IT MADE (the owner, 2026-10-28: "the attachments on the bottom of an agent - it looks like it created a million
// attachments"). An agent saved its workbook nine times, beside its helper script, its log and a temp file: What it made is the newest
// workbook and the PDF, the eight earlier versions behind one line, the working files behind another - and the chat's foot the same.
test("an agent's v1..v9 and scratch files list once, the rest folded", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  const made = await page.evaluate(async () => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    return (await fetch("/api/tasks", { method: "POST", headers, body: JSON.stringify({
      Title: "Vendor pricing review", Summary: "Compare what Payworth and Trainly charge.", Kind: "general" }) })).json();
  });
  assert.ok(made.taskId, JSON.stringify(made));
  const folder = path.join(harness.home, "scratch", "outputs", `TQ-${String(made.taskId).padStart(4, "0")}`);
  execFileSync(process.env.TASKUARY_TEST_PYTHON || (process.platform === "win32" ? "python" : "python3"), ["-c", `
import os, sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from taskuary import general
from taskuary.store import SQLiteStore
d, tid = Path(sys.argv[2]), int(sys.argv[3])
(d / 'tmp').mkdir(parents=True, exist_ok=True)
def put(name, n, body=b'x'):
    p = d / name; p.write_bytes(body); os.utime(p, (1790000000 + n * 60,) * 2)
for i in range(1, 10): put(f'pricing comparison v{i}.xlsx', i)
put('summary.pdf', 5, b'%PDF-1.4')
put('build_sheet.py', 20, b'print(1)'); put('run.log', 21, b'ok'); put('tmp/rates.csv', 22, b'a,b')
s = SQLiteStore(str(Path(sys.argv[4]) / 'taskuary.db'))
s.add_comment(tid, 'owner', general.USER_TYPE, 'put the pricing in a spreadsheet')
s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The comparison is ready, with a one-page summary.')
`, root, folder, String(made.taskId), harness.home], { env: { ...process.env, TASKUARY_HOME: harness.home }, stdio: "pipe" });

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  const list = "[data-tq-result-made] [data-tq-made-list]";
  await page.waitForSelector(`${list} [data-tq-output="pricing comparison v9.xlsx"]`, { timeout: 20000 });
  const rows = () => page.$$eval(`${list} [data-tq-output]`, (els) => els.map((e) => e.dataset.tqOutput));
  assert.deepEqual(await rows(), ["pricing comparison v9.xlsx", "summary.pdf"], "each thing it made once - no drafts, no scratch");
  const folds = await page.$$eval(`${list} [data-tq-fold] > button`, (els) => els.map((e) => e.textContent.trim()));
  assert.deepEqual(folds, ["▸ 8 earlier versions", "▸ 3 working files it used"]);

  // ...each still reachable: the earlier versions unfold under the workbook, newest first, and fold back
  await page.click(`${list} [data-tq-fold="earlier"] > button`);
  await page.waitForFunction((sel) => document.querySelectorAll(`${sel} [data-tq-fold="earlier"] [data-tq-output]`).length === 8, { timeout: 5000 }, list);
  assert.equal(await page.$eval(`${list} [data-tq-fold="earlier"] [data-tq-output]`, (e) => e.dataset.tqOutput), "pricing comparison v8.xlsx");
  await page.click(`${list} [data-tq-fold="working"] > button`);
  const working = await page.$$eval(`${list} [data-tq-fold="working"] [data-tq-output]`, (els) => els.map((e) => e.dataset.tqOutput).sort());
  assert.deepEqual(working, ["build_sheet.py", "run.log", "tmp/rates.csv"]);

  // the conversation's foot lists them the same way
  await page.$eval("[data-tq-work]", (w) => (w.querySelector("[data-tq-full-result]") || w.querySelector('[data-tq-step="2"]').parentElement).click());
  await page.waitForSelector(".tq-aui-viewport [data-tq-made-list] [data-tq-output]", { timeout: 20000 });
  const foot = await page.$$eval(".tq-aui-viewport [data-tq-made-list] > .tq-published [data-tq-output]", (els) => els.map((e) => e.dataset.tqOutput));
  assert.deepEqual(foot, ["pricing comparison v9.xlsx", "summary.pdf"]);
  assert.deepEqual(errors, []);
});
