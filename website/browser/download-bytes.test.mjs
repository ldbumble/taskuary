import assert from "node:assert/strict";
import { execFile, execFileSync } from "node:child_process";
import { mkdir, readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import { startHarness } from "./harness.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const python = process.env.TASKUARY_TEST_PYTHON || (process.platform === "win32" ? "python" : "python3");
const run = promisify(execFile);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// "download button not working when generating artifacts (i thought we stress tested this and it's not working still)" (the owner,
// 2026-11-03). The stress run pressed Download in a plain browser and read the page; no test saved a file through the desktop window's
// road (Attachments.saveFile -> pywebview -> desktop.save_download) or looked at the bytes it left. Here a PDF, a workbook and a 12 MB
// ZIP an agent made are each saved BOTH ways - the browser's own download, and the window's road with the real Python save behind it -
// and each file on disk is compared with the agent's, byte for byte, beside the line the page shows.
test("every Download saves the agent's file itself, byte for byte, in the browser and through the desktop window's road", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const env = { ...process.env, TASKUARY_HOME: harness.home };
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  const made = await page.evaluate(async () => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    return (await fetch("/api/tasks", { method: "POST", headers, body: JSON.stringify({
      Title: "Quarter pack for Northwind", Summary: "Put the quarter's collections in a PDF, a workbook and one ZIP.", Kind: "general" }) })).json();
  });
  assert.ok(made.taskId, JSON.stringify(made));
  const folder = path.join(harness.home, "scratch", "outputs", `TQ-${String(made.taskId).padStart(4, "0")}`);
  execFileSync(python, ["-c", `
import os, sys, zipfile
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from openpyxl import Workbook
from taskuary import general
from taskuary.store import SQLiteStore
d, tid = Path(sys.argv[2]), int(sys.argv[3]); d.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(d / 'Quarter pack.zip', 'w', zipfile.ZIP_STORED) as z: z.writestr('scans.bin', os.urandom(12 << 20))
os.utime(d / 'Quarter pack.zip', (1790000300,) * 2)
wb = Workbook(); wb.active.append(['Payer', 'Paid']); wb.active.append(['Payworth', 1100]); wb.save(d / 'Collections by payer.xlsx')
os.utime(d / 'Collections by payer.xlsx', (1790000200,) * 2)
(d / 'Collections – Q3.pdf').write_bytes(b'%PDF-1.4\\n' + os.urandom(60000) + b'\\n%%EOF'); os.utime(d / 'Collections – Q3.pdf', (1790000100,) * 2)
s = SQLiteStore(str(Path(sys.argv[4]) / 'taskuary.db'))
s.add_comment(tid, 'owner', general.USER_TYPE, 'the quarter pack please')
s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The PDF, the workbook and the ZIP are ready.')
`, root, folder, String(made.taskId), harness.home], { env, stdio: "pipe" });
  const names = ["Quarter pack.zip", "Collections by payer.xlsx", "Collections – Q3.pdf"];
  const row = (name) => `[data-tq-result-made] [data-tq-output="${name}"]`;
  const same = async (file, name) => assert.ok((await readFile(file)).equals(await readFile(path.join(folder, name))), `${name}: not the agent's bytes`);

  // THE BROWSER'S OWN DOWNLOAD: the file lands whole (no .crdownload left, its full size) and is the agent's file
  const inBrowser = path.join(harness.home, "browser-downloads");
  await mkdir(inBrowser, { recursive: true });
  await (await page.createCDPSession()).send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: inBrowser });
  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector(row(names[0]), { timeout: 20000 });
  for (const name of names) {
    const size = (await stat(path.join(folder, name))).size;
    await page.$eval(`${row(name)} [data-tq-download]`, (b) => b.click());
    let done = false;
    for (let i = 0; i < 200 && !done; i++) {
      await sleep(100);
      const there = await readdir(inBrowser);
      done = there.includes(name) && !there.some((f) => f.endsWith(".crdownload")) && (await stat(path.join(inBrowser, name))).size === size;
    }
    assert.ok(done, `${name} was not saved whole by the browser: ${(await readdir(inBrowser)).join(", ")}`);
    await same(path.join(inBrowser, name), name);
  }

  // THE DESKTOP WINDOW'S ROAD: the page hands the address to pywebview's bridge, and the window's own save (desktop.save_download, run
  // here as the window runs it) fetches it from the server and writes it - the line names the whole folder and the file is the agent's
  const inWindow = path.join(harness.home, "Downloads");
  const win = await harness.newPage();
  win.on("pageerror", (e) => errors.push(e.message));
  await win.exposeFunction("__tqSaveDownload", async (url) => JSON.parse((await run(python, ["-c", `
import json, sys
sys.path.insert(0, sys.argv[1])
from taskuary import desktop
print(json.dumps(desktop.save_download(sys.argv[2], folder=sys.argv[3])))
`, root, url, inWindow], { env, maxBuffer: 1 << 20 })).stdout.trim().split("\n").pop()));
  await win.evaluateOnNewDocument(() => { window.pywebview = { api: { save_download: (url) => window.__tqSaveDownload(url) } }; });
  await win.goto(`${harness.ui}/#task=${made.taskId}`, { waitUntil: "domcontentloaded", timeout: 20000 });
  await win.waitForSelector(row(names[0]), { timeout: 20000 });
  for (const name of names) {
    await win.$eval(`${row(name)} [data-tq-download]`, (b) => b.click());
    await win.waitForSelector(`${row(name)} [data-tq-file-saved], ${row(name)} [data-tq-file-error]`, { timeout: 60000 });
    assert.equal(await win.$eval(`${row(name)} [data-tq-file-saved], ${row(name)} [data-tq-file-error]`, (e) => e.textContent), `Saved to ${inWindow} as ${name}`);
    await same(path.join(inWindow, name), name);
  }
  assert.deepEqual((await readdir(inWindow)).sort(), [...names].sort());
  assert.deepEqual(errors, []);
});
