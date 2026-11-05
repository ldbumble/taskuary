import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* TYPING INTO THE AGENT'S PAGE WORKS LIKE TYPING (the owner on a portal's sign-in, 2026-11-03: "i can't type into the userid box.. then i
   typed something went in but backspace did not work??"). Chrome edits a box by the key's Windows key code, and the view sent none, so
   Backspace, Delete and Ctrl+A did nothing. Here the page's focused box is kept the way Chrome's key input edits it (fixture_changes
   browser_view: text on a keyDown that carries it, Backspace only with its key code), and its value is what the test reads. Invented
   site and task only. */
test("keys typed on the view reach the page's box, Backspace and Ctrl+A included", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const painter = await harness.newPage();
  await painter.setViewport({ width: 1200, height: 760, deviceScaleFactor: 1 });
  await painter.setContent(`<body style="margin:0;background:#eef1f6;font:16px system-ui"><div style="margin:80px auto;width:360px;background:#fff;padding:24px">
    <label>User ID</label><div style="border:1px solid #9aa3b5;height:36px;margin-top:6px"></div></div></body>`);
  const frame = await painter.screenshot({ type: "jpeg", quality: 80, encoding: "base64" });
  await painter.close();

  const page = await harness.newPage();
  await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  const call = (url, body, method = "POST") => page.evaluate(async (url, body, method) => (await fetch(url, { method, ...(method === "POST" ? { body: JSON.stringify(body) } : {}),
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json(), url, body, method);
  const field = async () => (await call(`/api/fixture/browser/view/${made.taskId}`, null, "GET")).field;
  const until = async (want, what) => {
    let v;
    for (let i = 0; i < 40; i++) { v = await field(); if (v === want) return; await new Promise((r) => setTimeout(r, 150)); }
    assert.fail(`${what}: the page's box holds ${JSON.stringify(v)}, not ${JSON.stringify(want)}`);
  };

  const made = await call("/api/fixture/browser/view", { step: "open", frame });
  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForFunction(() => document.querySelector("[data-tq-browser-layout]")
    || (document.querySelector("[data-tq-section-tab=agent]")?.click(), false), { timeout: 30000, polling: 500 });
  // the agent hands the page over: it is the owner's to type on, no Take over first - and only now is the page drawn (a chat task's
  // browser shows only when the owner has a part on it, 2026-11-05)
  const turn = await call("/api/fixture/browser/view", { step: "turn", taskId: made.taskId });
  await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-browser-layout] p")].some((p) => p.textContent.trim() === "LIVE"),
    { timeout: 30000 });
  await page.waitForSelector(`[data-tq-browser-turn="${turn.requestId}"]`, { visible: true, timeout: 30000 });

  // ONE click on the box, and the keys go to the page from the first one
  const r = await (await page.$("[data-tq-browser-layout] canvas")).boundingBox();
  await page.mouse.click(r.x + r.width / 2, r.y + r.height * 0.25);
  await page.keyboard.type("alex.doyle");
  await until("alex.doyle", "typed after one click");
  await page.keyboard.press("Backspace"); await page.keyboard.press("Backspace");
  await until("alex.doy", "two Backspaces");
  await page.keyboard.down("Control"); await page.keyboard.press("KeyA"); await page.keyboard.up("Control");
  await page.keyboard.press("Backspace");
  await until("", "Ctrl+A then Backspace");
  await page.keyboard.type("adoyle");
  await until("adoyle", "typed again");
  // ...and the keys stayed on the page: nothing typed landed in the chat's box
  assert.ok(await page.evaluate(() => [...document.querySelectorAll("textarea")].every((x) => !x.value.includes("doyle"))), "no key went to the chat");
  assert.deepEqual(errors, []);
});
