import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { launch } from "../browser.mjs";

const website = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

// The New sheet, drawn in the demo (no mailbox, nothing can send): every tab draws, and none of them loops
test("New > Send something with no mailbox draws, and offers the mailbox", { timeout: 60000 }, async () => {
  const port = await new Promise((resolve, reject) => {
    const server = net.createServer(); server.once("error", reject);
    server.listen(0, "127.0.0.1", () => { const port = server.address().port; server.close(() => resolve(port)); });
  });
  const origin = `http://127.0.0.1:${port}`;
  const vite = spawn(process.execPath, ["node_modules/vite/bin/vite.js", "--mode", "demo", "--host", "127.0.0.1", "--port", String(port), "--strictPort"],
    { cwd: website, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
  let log = ""; vite.stdout.on("data", c => { log += c; }); vite.stderr.on("data", c => { log += c; });
  let browser;
  try {
    let ready = false;
    for (let n = 0; n < 100; n++) {
      if (vite.exitCode !== null) throw new Error(`Demo Vite exited: ${log}`);
      try { if ((await fetch(origin)).ok) { ready = true; break; } } catch { /* starting */ }
      await delay(100);
    }
    assert.ok(ready, `Demo Vite did not start: ${log}`);
    browser = await launch();
    const page = await browser.newPage(), errors = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
    await page.setRequestInterception(true);
    page.on("request", request => {
      const url = new URL(request.url());
      if (["http:", "https:"].includes(url.protocol) && url.origin !== origin) request.abort(); else request.continue();
    });
    await page.setViewport({ width: 1366, height: 900 });
    await page.goto(`${origin}/#new-task`, { waitUntil: "networkidle0" });
    await page.waitForSelector("[data-tq-new] [role=tab]", { timeout: 20000 });
    const tab = async (word) => page.$$eval("[data-tq-new] [role=tab]", (tabs, word) => tabs.find(t => t.textContent.includes(word))?.click(), word);
    await tab("Send something");
    await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-new] [role=tab]")]
      .some(t => t.textContent.includes("Send something") && t.getAttribute("aria-selected") === "true"), { timeout: 5000 });
    await delay(1500);
    const text = await page.evaluate(() => document.body.innerText);
    assert.doesNotMatch(text, /failed to draw/i);
    assert.match(text, /Nothing here can send yet/);
    assert.ok(await page.$$eval("button", bs => bs.some(b => b.textContent.trim() === "Connect a mailbox")), "the mailbox is offered on the row");
    assert.deepEqual(errors.filter(e => /#185|Maximum update depth/i.test(e)), []);
    // ...and every tab is a keyboard stop: Tab reaches the next one, Enter opens it (the UI audit, 2026-10-21: the six tabs were mouse-only)
    await page.$$eval("[data-tq-new] [role=tab]", tabs => tabs.find(t => t.getAttribute("aria-selected") === "true").focus());
    await page.keyboard.press("Tab"); await page.keyboard.press("Enter");
    await page.waitForFunction(() => { const tabs = [...document.querySelectorAll("[data-tq-new] [role=tab]")], i = tabs.findIndex(t => t.textContent.includes("Send something"));
      return tabs[i + 1]?.getAttribute("aria-selected") === "true"; }, { timeout: 5000 });
  } finally {
    await browser?.close();
    if (vite.exitCode === null) { vite.kill(); await Promise.race([new Promise(resolve => vite.once("exit", resolve)), delay(3000)]); }
  }
});
