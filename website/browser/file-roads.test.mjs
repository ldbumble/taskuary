import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdir, readdir, readFile, rm } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

// "this did not work - both preview and download?" (the owner, 2026-10-28). What it made - a workbook named with a '%', a CSV, a PDF,
// a write-up and a Word document - each opens in place from the Result's What it made and each Download saves the file itself, without
// the page going anywhere; and a file deleted from disk since says so on its row, the page still where it was.
test("every file an agent made opens in place and downloads; a gone one says so", { timeout: 240000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  const made = await page.evaluate(async () => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    return (await fetch("/api/tasks", { method: "POST", headers, body: JSON.stringify({
      Title: "Collections by payer", Summary: "Put what each payer paid in a workbook, with a short write-up.", Kind: "general" }) })).json();
  });
  assert.ok(made.taskId, JSON.stringify(made));
  const folder = path.join(harness.home, "scratch", "outputs", `TQ-${String(made.taskId).padStart(4, "0")}`);
  execFileSync(process.env.TASKUARY_TEST_PYTHON || (process.platform === "win32" ? "python" : "python3"), ["-c", `
import os, sys, zipfile
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from openpyxl import Workbook
from taskuary import general
from taskuary.store import SQLiteStore
d, tid = Path(sys.argv[2]), int(sys.argv[3]); d.mkdir(parents=True, exist_ok=True)
def stamp(p, n): os.utime(p, (1790000000 + n * 60,) * 2)
wb = Workbook(); ws = wb.active; ws.title = 'Collected'
for r in (['Payer', 'Billed', 'Collected'], ['Payworth', 1200, 1100], ['Trainly', 480, 480]): ws.append(r)
wb.save(d / 'TQ-0012 % Collected all-in-one.xlsx'); stamp(d / 'TQ-0012 % Collected all-in-one.xlsx', 5)
(d / 'Q3 #2 rates.csv').write_text('Payer,Rate\\nSpendly,0.9\\n', encoding='utf-8'); stamp(d / 'Q3 #2 rates.csv', 4)
pdf = b'%PDF-1.4\\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\\ntrailer<</Root 1 0 R>>\\n%%EOF'
(d / 'summary.pdf').write_bytes(pdf); stamp(d / 'summary.pdf', 3)
(d / 'Résumé – findings.md').write_text('# Findings\\n\\nPayworth paid **92%** of what was billed.', encoding='utf-8'); stamp(d / 'Résumé – findings.md', 2)
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
with zipfile.ZipFile(d / 'review.docx', 'w') as z:
    z.writestr('word/document.xml', f'<w:document xmlns:w="{W}"><w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Payer review</w:t></w:r></w:p>'
               '<w:p><w:r><w:t>Trainly paid in full.</w:t></w:r></w:p></w:body></w:document>')
stamp(d / 'review.docx', 1)
s = SQLiteStore(str(Path(sys.argv[4]) / 'taskuary.db'))
s.add_comment(tid, 'owner', general.USER_TYPE, 'put the collections in a workbook')
s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The workbook and a short write-up are ready.')
`, root, folder, String(made.taskId), harness.home], { env: { ...process.env, TASKUARY_HOME: harness.home }, stdio: "pipe" });

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  const list = "[data-tq-result-made]";
  const row = (name) => `${list} [data-tq-output="${name}"]`;
  const names = ["TQ-0012 % Collected all-in-one.xlsx", "Q3 #2 rates.csv", "summary.pdf", "Résumé – findings.md", "review.docx"];
  await page.waitForSelector(row(names[0]), { timeout: 20000 });
  assert.deepEqual(await page.$$eval(`${list} [data-tq-output]`, (els) => els.map((e) => e.dataset.tqOutput)), names);
  const where = await page.evaluate(() => location.href);

  // OPEN: each previews in place by what it is
  const open = async (name) => page.$eval(`${row(name)} [data-tq-open]`, (b) => b.click());
  const shows = async (name, sel, text) => page.waitForFunction((r, s, x) => {
    const el = document.querySelector(`${r} ${s}`);
    return el && (!x || el.textContent.includes(x));
  }, { timeout: 15000 }, row(name), sel, text);
  await open(names[0]); await shows(names[0], "[data-tq-sheet-preview] table", "Payworth");
  await open(names[1]); await shows(names[1], ".tq-published-table table", "Spendly");
  await open(names[2]); await shows(names[2], "iframe.tq-published-frame");
  assert.match(await page.$eval(`${row(names[2])} iframe`, (f) => f.src), /^blob:/);
  await open(names[3]); await shows(names[3], ".tq-published-md strong", "92%");
  await open(names[4]); await shows(names[4], "[data-tq-doc-preview] h3", "Payer review");
  assert.equal(await page.$$eval(`${list} .tq-published-note`, (els) => els.filter((e) => /could not|moved or deleted/.test(e.textContent)).length), 0);

  // DOWNLOAD: each saves the file itself under its own name, and the page stays where it is
  const saved = path.join(harness.home, "downloads");
  await mkdir(saved, { recursive: true });
  const cdp = await page.createCDPSession();
  await cdp.send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: saved });
  for (const name of names) {
    await page.$eval(`${row(name)} [data-tq-download]`, (b) => b.click());
    let got = [];
    for (let i = 0; i < 100 && !got.includes(name); i++) { await new Promise((r) => setTimeout(r, 100)); got = await readdir(saved); }
    assert.ok(got.includes(name), `${name} was not saved: ${got.join(", ")}`);
    assert.deepEqual(await readFile(path.join(saved, name)), await readFile(path.join(folder, name)), name);
  }
  assert.equal(await page.evaluate(() => location.href), where);

  // GONE: deleted on disk since the list was drawn - Download says so on its row and saves nothing; Open says so too
  await rm(path.join(folder, "summary.pdf"));
  await rm(path.join(saved, "summary.pdf"));
  await page.$eval(`${row("summary.pdf")} [data-tq-download]`, (b) => b.click());
  await page.waitForSelector(`${row("summary.pdf")} [data-tq-file-error]`, { timeout: 10000 });
  const why = await page.$eval(`${row("summary.pdf")} [data-tq-file-error]`, (e) => e.textContent);
  assert.match(why, /summary\.pdf was moved or deleted/);
  assert.match(why, /TQ-\d{4}/);
  await new Promise((r) => setTimeout(r, 500));
  assert.ok(!(await readdir(saved)).includes("summary.pdf"));
  assert.equal(await page.evaluate(() => location.href), where);
  await open("summary.pdf"); await open("summary.pdf");                      // hide, then open again: the preview reads it afresh
  await shows("summary.pdf", ".tq-published-note", "moved or deleted");
  assert.deepEqual(errors, []);
});
