import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdir, readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

// A researcher on Codex built a workbook in its task's outputs folder, cited it with a raw `:codex-file-citation{...}` marker and,
// asked to send it, linked http://127.0.0.1:7787/outputs/TQ-n/<file> - a route the server never had, so the click was a 404.
// On the canvas both are now one file: its name, a Preview of its sheets and a Download that works.
test("a workbook the agent made previews in the chat and downloads", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());

  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  const made = await page.evaluate(async () => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    const r = await fetch("/api/tasks", { method: "POST", headers, body: JSON.stringify({
      Title: "Compare training vendors", Summary: "Put the vendor comparison in a spreadsheet.", Kind: "general" }) });
    return r.json();
  });
  assert.ok(made.taskId, `task not created: ${JSON.stringify(made)}`);

  // the agent's turn as it happened: the workbook in the task's folder, and an answer naming it both broken ways
  const ref = `TQ-${String(made.taskId).padStart(4, "0")}`;
  const folder = path.join(harness.home, "scratch", "outputs", ref);
  const book = path.join(folder, "vendor comparison.xlsx").replace(/\\/g, "/");
  execFileSync(process.env.TASKUARY_TEST_PYTHON || (process.platform === "win32" ? "python" : "python3"), ["-c", `
import sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from openpyxl import Workbook
from taskuary import general
from taskuary.store import SQLiteStore
book, tid = Path(sys.argv[2]), int(sys.argv[3])
wb = Workbook(); ws = wb.active; ws.title = 'Vendors'
for r in (['Vendor', 'Contact', 'Annual cost'], ['Payworth', 'Gail Moreno', 1200], ['Trainly', 'Ray Colton', 480]): ws.append(r)
wb.create_sheet('Notes').append(['Checked by Alex Doyle'])
book.parent.mkdir(parents=True, exist_ok=True); wb.save(book)
(book.parent / 'raw costs.csv').write_text('Vendor,Cost\\nSpendly,300\\n', encoding='utf-8')
s =SQLiteStore(str(Path(sys.argv[4]) / 'taskuary.db'))
s.add_comment(tid, 'owner', general.USER_TYPE, 'can you send the file here, as a spreadsheet?')
s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The comparison is ready.\\n\\n'
    + ':codex-file-citation{path="' + str(book).replace('\\\\', '/') + '" artifact_kind="workbook" purpose="output"}\\n\\n'
    + '[Download the spreadsheet](http://127.0.0.1:7787/outputs/' + book.parent.name + '/vendor%20comparison.xlsx)')
`, root, book, String(made.taskId), harness.home], { env: { ...process.env, TASKUARY_HOME: harness.home }, stdio: "pipe" });

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  const chip = '.tq-aui-agent [data-tq-output="vendor comparison.xlsx"]';
  // the finished agent's Result rests on its summary and lists the workbook with its Open; its heading unfolds the chat (2026-10-27)
  await page.waitForSelector('[data-tq-result-made] [data-tq-output="vendor comparison.xlsx"] [data-tq-open]', { timeout: 20000 });
  await page.$eval('[data-tq-work] [data-tq-step="2"]', (dot) => dot.parentElement.click());
  await page.waitForSelector(chip, { visible: true, timeout: 20000 });

  // the marker and the dead address are gone from the words; the file sits under them, once
  const answer = await page.$eval(".tq-aui-agent", (el) => ({ text: el.innerText, dead: el.querySelectorAll('a[href*="/outputs/"]').length,
    chips: el.querySelectorAll("[data-tq-output]").length }));
  assert.doesNotMatch(answer.text, /codex-file-citation|artifact_kind|7787/);
  assert.match(answer.text, /Download the spreadsheet/);
  assert.equal(answer.dead, 0);
  assert.equal(answer.chips, 1);

  // Preview: the first sheet as a table, a tab for the other
  const button = (label) => page.evaluateHandle((sel, l) => [...document.querySelector(sel).querySelectorAll("button, a")]
    .find((b) => b.textContent.trim() === l), chip, label);
  await (await button("Preview")).click();
  await page.waitForFunction((sel) => document.querySelector(`${sel} [data-tq-sheet-preview] table`)?.innerText.includes("Payworth"), { timeout: 15000 }, chip);
  const table = await page.$eval(`${chip} [data-tq-sheet-preview]`, (el) => el.innerText);
  assert.match(table, /Vendor\s+Contact\s+Annual cost/);
  assert.match(table, /Gail Moreno/);
  await page.evaluate((sel) => [...document.querySelectorAll(`${sel} [role=tab]`)].find((b) => b.textContent === "Notes").click(), chip);
  await page.waitForFunction((sel) => document.querySelector(`${sel} [data-tq-sheet-preview] table`)?.innerText.includes("Checked by Alex Doyle"), { timeout: 15000 }, chip);

  // Download: the link is the real route, and clicking it saves the workbook itself
  const href = await page.evaluate((sel) => [...document.querySelector(sel).querySelectorAll("a")].find((a) => a.textContent.trim() === "Download").getAttribute("href"), chip);
  assert.match(href, new RegExp(`^/api/task-outputs/${made.taskId}/vendor%20comparison\\.xlsx\\?download=true&token=`));
  const saved = path.join(harness.home, "downloads");
  await mkdir(saved, { recursive: true });
  const cdp = await page.createCDPSession();
  await cdp.send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: saved });
  await (await button("Download")).click();
  let got = [];
  for (let i = 0; i < 100 && !got.some((f) => f === "vendor comparison.xlsx"); i++) {
    await new Promise((r) => setTimeout(r, 100));
    got = await readdir(saved);
  }
  assert.deepEqual(got, ["vendor comparison.xlsx"]);
  assert.deepEqual(await readFile(path.join(saved, got[0])), await readFile(book));

  // ...and a file in the folder that no answer names is on the task too, at the foot of the conversation - the cited one is not
  // drawn there a second time
  const foot = await page.$$eval(".tq-aui-viewport [data-tq-output]", (els) => els.filter((e) => !e.closest(".tq-aui-agent")).map((e) => e.dataset.tqOutput));
  assert.deepEqual(foot, ["raw costs.csv"]);
  const csv = '[data-tq-output="raw costs.csv"]';
  await page.evaluate((sel) => [...document.querySelector(sel).querySelectorAll("button")].find((b) => b.textContent.trim() === "Preview").click(), csv);
  await page.waitForFunction((sel) => document.querySelector(`${sel} table`)?.innerText.includes("Spendly"), { timeout: 15000 }, csv);
  assert.deepEqual(errors, []);
});
