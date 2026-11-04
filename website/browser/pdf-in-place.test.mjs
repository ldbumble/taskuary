import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdir, readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PY = process.env.TASKUARY_TEST_PYTHON || (process.platform === "win32" ? "python" : "python3");
// a one-page PDF, small and valid enough for the viewer
const PDF = "b'%PDF-1.4\\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/Parent 2 0 R"
  + "/MediaBox[0 0 200 200]>>endobj\\ntrailer<</Root 1 0 R>>\\n%%EOF'";

// the page saves into `dir` from here on; [] until something lands there
const saves = async (page, dir) => {
  await mkdir(dir, { recursive: true });
  await (await page.createCDPSession()).send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: dir });
};
const landed = async (dir, name) => {
  let got = [];
  for (let i = 0; i < 100 && !got.includes(name); i++) { await sleep(100); got = await readdir(dir); }
  return got;
};
// the viewer drew the PDF in place: a frame on the PDF's own bytes, never the window sent anywhere
const viewer = (page, sel) => page.waitForFunction((s) => {
  const f = document.querySelector(`${s} iframe`);
  return f && /^blob:/.test(f.src) && f.getBoundingClientRect().height > 100;
}, { timeout: 30000 }, sel);

/* A PDF IS READ WHERE YOU ARE (the owner, 2026-11-04: "When clicking a pdf link in Came from or the agent, it should display the pdf
   inline if it's what we are working on, instead of downloading"). The invoice a mail carried, opened from Came from's "1 attachment":
   its chip draws it in place, nothing is saved by the press, and its Download still saves the file itself. Invented sender. */
test("a mail's PDF opens in place from Came from, and Download still saves it", { timeout: 240000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const page = await h.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const out = execFileSync(PY, ["-c", `
import sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from taskuary.artifacts import attachment_dir
from taskuary.store import SQLiteStore
s = SQLiteStore(str(Path(sys.argv[2]) / 'taskuary.db'))
tid = s.create_task({'Title': 'October invoice from Payworth', 'Kind': 'task', 'Status': 'open', 'Source': 'email',
                     'Summary': 'Payworth sent the October invoice to approve.'}, 'router')
mid = s.add_message({'TaskId': tid, 'Channel': 'email', 'ExternalId': f'fixture-pdf-{tid}', 'FromName': 'Billing at Payworth',
                     'FromEmail': 'billing@vendor.example', 'Subject': 'October invoice', 'BodyText': 'The October invoice is attached.', 'Status': 'routed'})
pdf = ${PDF}
f = attachment_dir(mid) / '0-invoice-october.pdf'; f.write_bytes(pdf)
s.add_attachment({'MessageId': mid, 'ExternalId': f'fixture-pdf-att-{tid}', 'Name': 'invoice-october.pdf', 'ContentType': 'application/pdf',
                  'Size': len(pdf), 'Inline': 0, 'Path': str(f)})
print(tid, f)
`, root, h.home], { env: { ...process.env, TASKUARY_HOME: h.home }, encoding: "utf8" }).trim();
  const [tid, file] = [Number(out.split(" ")[0]), out.slice(out.indexOf(" ") + 1)];
  const CUR = `[data-tq-canvas-item]:has([data-tq-task-page="${tid}"])`, FROM = `${CUR} [data-tq-from]`;
  await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, tid);
  await page.waitForSelector(`${CUR} [data-tq-task-body][data-tq-sections]`, { timeout: 20000 });
  await sleep(1200);
  if (await page.$(`${CUR} [data-tq-section-tab=from]`)) { await page.click(`${CUR} [data-tq-section-tab=from] [data-tq-tab-arrow]`); await sleep(800); }
  const dir = path.join(h.home, "downloads");
  await saves(page, dir);
  const where = await page.evaluate(() => location.href);

  await page.$eval(`${FROM} [data-tq-files-pill]`, (b) => b.click());
  const chip = `${FROM} [data-tq-att="invoice-october.pdf"]`;
  await page.waitForSelector(chip, { visible: true, timeout: 10000 });
  await page.$eval(chip, (b) => b.click());
  await viewer(page, `${FROM} [data-tq-pdf-view]`);
  assert.equal(await page.$eval(`${FROM} [data-tq-pdf-view]`, (v) => v.dataset.tqPdfView), "invoice-october.pdf");
  await sleep(1200);
  assert.deepEqual(await readdir(dir), [], "the press drew it - it saved nothing");
  assert.equal(await page.evaluate(() => location.href), where);

  await page.$eval(`${FROM} [data-tq-pdf-view] [data-tq-download]`, (b) => b.click());
  assert.ok((await landed(dir, "invoice-october.pdf")).includes("invoice-october.pdf"), "Download saves it");
  assert.deepEqual(await readFile(path.join(dir, "invoice-october.pdf")), await readFile(file));
  assert.equal(await page.evaluate(() => location.href), where);

  // the chip again puts it away
  await page.$eval(chip, (b) => b.click());
  await page.waitForFunction((s) => !document.querySelector(`${s} [data-tq-pdf-view]`), { timeout: 5000 }, FROM);
  assert.deepEqual(errors, []);
});

/* ...and a PDF the agent made or showed: the one it SHOWED is drawn under its answer, and the one its answer LINKS opens in place under
   the link - neither saved by the press, each with a Download that saves the file. */
test("an agent's PDF opens in place - shown under the answer and from a link in it", { timeout: 240000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const page = await h.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(h.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  const made = await page.evaluate(async () => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    return (await fetch("/api/tasks", { method: "POST", headers, body: JSON.stringify({
      Title: "Trainly renewal summary", Summary: "Write up the Trainly renewal as a PDF.", Kind: "general" }) })).json();
  });
  assert.ok(made.taskId, JSON.stringify(made));
  const tid = made.taskId, folder = path.join(h.home, "scratch", "outputs", `TQ-${String(tid).padStart(4, "0")}`);
  execFileSync(PY, ["-c", `
import sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from taskuary import general, session_artifacts
from taskuary.store import SQLiteStore
d, tid = Path(sys.argv[2]), int(sys.argv[3]); d.mkdir(parents=True, exist_ok=True)
pdf = ${PDF}
(d / 'renewal.pdf').write_bytes(pdf); (d / 'terms.pdf').write_bytes(pdf)
s = SQLiteStore(str(Path(sys.argv[4]) / 'taskuary.db'))
s.add_comment(tid, 'owner', general.USER_TYPE, 'write up the renewal')
s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, f'The renewal is written up, and [the terms](/api/task-outputs/{tid}/terms.pdf) are beside it.')
session_artifacts.shown(s, tid, d / 'renewal.pdf', 'assistant')
`, root, folder, String(tid), h.home], { env: { ...process.env, TASKUARY_HOME: h.home }, stdio: "pipe" });

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, tid);
  await page.waitForSelector("[data-tq-work]", { timeout: 20000 });
  await page.$eval("[data-tq-work]", (w) => (w.querySelector("[data-tq-full-result]") || w.querySelector('[data-tq-step="2"]').parentElement).click());
  const CHAT = ".tq-aui-viewport";
  await page.waitForSelector(`${CHAT} [data-tq-file-link]`, { timeout: 20000 });
  const dir = path.join(h.home, "downloads");
  await saves(page, dir);
  const where = await page.evaluate(() => location.href);

  // SHOWN: drawn open under the answer, as the agent chose
  const SHOWN = `${CHAT} [data-tq-pdf]`;
  await page.waitForSelector(SHOWN, { timeout: 15000 });
  await viewer(page, SHOWN);

  // LINKED: the press draws it under the link and saves nothing
  await page.$eval(`${CHAT} [data-tq-file-link]`, (a) => a.click());
  const LINKED = `${CHAT} [data-tq-file-link-view]`;
  await viewer(page, `${LINKED} [data-tq-pdf-view]`);
  await sleep(1200);
  assert.deepEqual(await readdir(dir), [], "the press drew it - it saved nothing");
  assert.equal(await page.evaluate(() => location.href), where);
  await page.$eval(`${LINKED} [data-tq-pdf-view] [data-tq-download]`, (b) => b.click());
  assert.ok((await landed(dir, "terms.pdf")).includes("terms.pdf"), "Download saves the linked one");
  assert.deepEqual(await readFile(path.join(dir, "terms.pdf")), await readFile(path.join(folder, "terms.pdf")));

  await page.$eval(`${SHOWN} [data-tq-download]`, (b) => b.click());
  const got = await landed(dir, "renewal.pdf");
  assert.ok(got.some((n) => /\.pdf$/.test(n) && n !== "terms.pdf"), `Download saves the shown one: ${got.join(", ")}`);
  assert.equal(await page.evaluate(() => location.href), where);
  assert.deepEqual(errors, []);
});
