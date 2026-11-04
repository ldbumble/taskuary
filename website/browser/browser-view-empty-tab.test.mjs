import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* AN EMPTY TAB IS NOT A PAGE (the owner, 2026-11-03): a general task marked as needing a browser was answered without one, and half its
   canvas was the agent's Chrome on about:blank - "an empty tab, live" - with "your turn - the agent is waiting on you; click the page and
   type" over it, while what the agent waited on was a question asked in words. The view folds to its chip until the agent opens a page;
   the chip still opens it. A real backend whose agent-browser session has no Chrome (fixture_changes.browser_view). Invented people only. */
test("a browser on an empty tab folds to its chip, and a question in words is no turn on the page", { timeout: 120000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  const made = await page.evaluate(async () => (await fetch("/api/fixture/browser/view", { method: "POST", body: JSON.stringify({ step: "blank" }),
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json());
  assert.ok(made.taskId, JSON.stringify(made));
  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  // the agent's room is drawn, with its answer and question in it
  await page.waitForFunction(() => document.body.innerText.includes("First month free, or a price now?")
    && document.querySelector("[data-tq-browser-layout]")
    || (document.querySelector("[data-tq-section-tab=agent]")?.click(), false), { timeout: 30000, polling: 500 });
  // ...and polled a few times: the browser state is read every 3 s, so the fold is checked after the first reads are in
  await new Promise((r) => setTimeout(r, 4000));
  const at = await page.evaluate(() => ({ layout: document.querySelector("[data-tq-browser-layout]")?.dataset.tqBrowserLayout,
    text: document.body.innerText, view: !!document.querySelector("[data-tq-browser-view]") }));
  assert.equal(at.layout, "folded", `the empty tab is a chip, not half the canvas: ${at.layout}`);
  assert.ok(!at.view && !/an empty tab, live/.test(at.text), "no view of the empty tab is drawn");
  assert.ok(!/your turn/i.test(at.text), "a question asked in words is not the owner's turn on the page");
  assert.ok(/browser · an empty tab - show it/.test(at.text), "the chip says what is there");
  // the owner asks for it: the chip opens the view
  await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => /an empty tab - show it/.test(b.textContent))?.click());
  await page.waitForFunction(() => ["stack", "split"].includes(document.querySelector("[data-tq-browser-layout]")?.dataset.tqBrowserLayout), { timeout: 10000 });
  assert.deepEqual(errors, []);
});
