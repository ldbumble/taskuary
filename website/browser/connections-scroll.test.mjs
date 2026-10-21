import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { launch } from "../browser.mjs";

const website = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

// A PRESS INSIDE AN OPEN CARD KEEPS THE PLACE (the UI audit, 2026-10-21): every Connections step header snapped the card back to its
// top - the table's pin held the card's head while the owner worked a screen below it
test("pressing a Connections step header leaves the page where it was, and a mailbox must be an address", { timeout: 90000 }, async () => {
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
    await page.setRequestInterception(true);
    page.on("request", request => {
      const url = new URL(request.url());
      if (["http:", "https:"].includes(url.protocol) && url.origin !== origin) request.abort(); else request.continue();
    });
    await page.setViewport({ width: 1366, height: 768 });
    await page.goto(`${origin}/#connector=outlook`, { waitUntil: "networkidle0" });
    await page.waitForFunction(() => document.querySelector("[data-tq-browse=connections]")?.innerText.includes("Mailboxes"), { timeout: 20000 });
    await delay(1500);
    const top = () => page.evaluate(() => Math.round(document.querySelector(".tq-chat-body").scrollTop));
    for (const word of ["3 Mailboxes", "2 Test"]) {
      const el = (await page.evaluateHandle((word) => [...document.querySelectorAll("[data-tq-browse=connections] [role=button], [data-tq-browse=connections] button")]
        .find(e => (e.innerText || "").replace(/\s+/g, " ").trim() === word), word)).asElement();
      assert.ok(el, `${word} is on the card`);
      await el.evaluate(e => e.scrollIntoView({ block: "center" })); await delay(400);
      const before = await top();
      assert.ok(before > 100, "the step sits below the card's head");
      await el.click(); await delay(1200);
      assert.ok(Math.abs((await top()) - before) < 40, `${word}: the page stayed (${before} -> ${await top()})`);
    }
    // ...and a mailbox is an address: "not an address" was added and ticked green (the UI audit, 2026-10-21)
    const open = (await page.evaluateHandle(() => [...document.querySelectorAll("[data-tq-browse=connections] [role=button], [data-tq-browse=connections] button")]
      .find(e => (e.innerText || "").replace(/\s+/g, " ").trim() === "3 Mailboxes"))).asElement();
    await open.click(); await delay(800);
    const box = await page.waitForSelector('[data-tq-browse=connections] input[placeholder="someone@yourdomain.com"]', { timeout: 5000 });
    await box.type("not an address"); await page.keyboard.press("Enter"); await delay(500);
    assert.match(await page.$eval("[data-tq-browse=connections]", e => e.innerText), /That isn't an email address/);
    assert.deepEqual(errors, []);
  } finally {
    await browser?.close();
    if (vite.exitCode === null) { vite.kill(); await Promise.race([new Promise(resolve => vite.once("exit", resolve)), delay(3000)]); }
  }
});
