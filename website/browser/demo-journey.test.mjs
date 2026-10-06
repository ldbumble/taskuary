import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { launch } from "../browser.mjs";

const website = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));

test("the default static demo completes one reviewed request and never calls a live API", { timeout: 60000 }, async () => {
  const port = await new Promise((resolve, reject) => {
    const server = net.createServer(); server.once("error", reject);
    server.listen(0, "127.0.0.1", () => { const port = server.address().port; server.close(() => resolve(port)); });
  });
  assert.ok(![7787, 7790].includes(port));
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
    const page = await browser.newPage(), errors = [], apiRequests = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.setRequestInterception(true);
    page.on("request", request => {
      const url = new URL(request.url());
      if (url.origin === origin && url.pathname.startsWith("/api/")) apiRequests.push(url.pathname);
      if (["http:", "https:"].includes(url.protocol) && url.origin !== origin) request.abort();
      else request.continue();
    });
    await page.setViewport({ width: 1440, height: 950 });
    await page.goto(`${origin}/?demo=guided`, { waitUntil: "networkidle0" });
    await page.waitForSelector('[data-tq-demo-journey="request"]');
    const start = await page.$('[data-tq-demo-journey] button');
    assert.ok((await start.boundingBox()).y < 950, "the first action is visible without scrolling");
    const initial = await page.evaluate(async () => {
      const { default: api } = await import("/src/api.js");
      const pile = (await api.get("/api/funnel/pile")).data;
      return { pile, feed: (await api.get("/api/feed")).data.data,
        age: Date.now() - new Date(pile.items[0].when.replace(" ", "T")).getTime() };
    });
    assert.equal(initial.pile.items.length, 1); assert.equal(initial.feed.length, 1);
    assert.ok(initial.age >= 0 && initial.age < 90000, "the request arrived one minute before this visit");
    await start.click();
    await page.waitForSelector('[data-tq-demo-journey="working"]');
    const duplicate = await page.evaluate(async () => {
      const { default: api } = await import("/src/api.js");
      return (await api.post("/api/tasks/18/dispatch", { agent: "analyst" })).data;
    });
    assert.equal(duplicate.existing, true, "a second start reuses the running demo agent");
    await page.waitForSelector('[data-tq-demo-journey="review"]');
    const result = await page.$eval('[data-tq-demo-result]', node => node.innerText);
    assert.match(result, /192,600/); assert.match(result, /posted vendor invoices/); assert.match(result, /excluded/);
    await page.setViewport({ width: 390, height: 844 });
    await delay(200);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "the review fits a narrow screen");
    const draft = '[data-tq-demo-review] textarea:not([aria-hidden="true"])';
    await page.click(draft); await page.keyboard.down("Control"); await page.keyboard.press("KeyA"); await page.keyboard.up("Control");
    const edited = "Hi Ruth, August vendor spend is $192,600. I checked the three categories; open purchase orders are excluded. Demo edit.";
    await page.type(draft, edited);
    const approve = await page.$('[data-tq-demo-review] button[title="Complete this temporary demo; no email is sent"]');
    assert.equal(await approve.evaluate(node => node.innerText), "Simulate approval");
    await approve.click();
    await page.waitForSelector('[data-tq-demo-journey="complete"]');
    await page.waitForFunction(() => document.body.innerText.includes("Nothing is waiting on you"));
    assert.match(await page.$eval('[data-tq-demo-outcome]', node => node.innerText), /No email was sent/);
    const finished = await page.evaluate(async () => {
      const { default: api } = await import("/src/api.js");
      const { demoJourneySnapshot } = await import("/src/demoApi.js");
      return { detail: (await api.get("/api/tasks/18")).data, pile: (await api.get("/api/funnel/pile")).data, journey: demoJourneySnapshot() };
    });
    assert.equal(finished.detail.task.Status, "done"); assert.equal(finished.pile.items.length, 0);
    assert.equal(finished.journey.review.FinalText, edited, "approval keeps the visitor's edit");
    await page.reload({ waitUntil: "networkidle0" });
    await page.waitForSelector('[data-tq-demo-journey="request"]');
    await page.click('button[title^="A walk through every part of Taskuary"]');
    await page.waitForFunction(() => document.body.innerText.includes("Set up Taskuary on your own machine"));
    assert.ok(await page.$('a[href="https://taskuary.com/docs/"]'), "the setup action provides a working installation destination");
    await page.goto(`${origin}/?demo=explore`, { waitUntil: "networkidle0" });
    assert.equal(await page.$('[data-tq-demo-journey]'), null);
    assert.deepEqual(apiRequests, [], "the static workflow never calls a live API or sends a message");
    assert.deepEqual(errors, []);
  } finally {
    await browser?.close();
    if (vite.exitCode === null) {
      const closed = new Promise(resolve => vite.once("exit", resolve));
      vite.kill(); await Promise.race([closed, delay(3000)]);
      if (vite.exitCode === null) vite.kill("SIGKILL");
    }
  }
});
