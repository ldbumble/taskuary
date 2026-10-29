import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, findRow, sleep } from "./walkdriver.mjs";

/* SHOULD BE A TASK, ON AN FYI (the owner, 2026-10-29): a put-down's Not a task does not apply to what triage already filed, so in the same
   place - Came from, open on its head or folded on its spine - an FYI says the correction the other way, and the bar does not say it twice.
   A task's Came from keeps Not a task. On the demo world at 1440, invented people only. */
const words = (page, sel) => page.$$eval(sel, (bs) => bs.filter((b) => b.offsetParent).map((b) => b.textContent.trim()));

test("an FYI's Came from says Should be a task, a task's Not a task", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 900 });
  assert.ok(await clickRow(page, await findRow(page, /Regional operations newsletter/)));
  await page.waitForSelector('[data-tq-item-sections="fyi"]', { timeout: 20000 }); await sleep(1500);
  const head = await words(page, '[data-tq-item-sections] [data-tq-slot="from"] [data-tq-section-head] button');
  assert.deepEqual(head, ["Should be a task"], `Came from open: ${head}`);
  const bar = await words(page, "[data-tq-row] button");
  assert.ok(!bar.includes("Should be a task") && !bar.includes("Not a task"), `the bar says neither: ${bar}`);
  // ...and folded, on its spine
  await page.evaluate(() => document.querySelector('[data-tq-item-sections] [data-tq-section-tab="agent"]')?.click()); await sleep(800);
  const spine = await words(page, '[data-tq-item-sections] [data-tq-section-tab="from"] [data-tq-spine-moves] button');
  assert.deepEqual(spine, ["Should be a task"], `Came from folded: ${spine}`);
  const all = await words(page, "[data-tq-item-sections] button, [data-tq-row] button");
  assert.ok(!all.includes("Not a task"), `no Not a task on an FYI: ${all}`);

  // a task's Came from is where its Not a task stands
  assert.ok(await clickRow(page, await findRow(page, /Invoice 88213/)));
  await page.waitForSelector("[data-tq-task-page] [data-tq-section-tab=from] [data-tq-spine-moves] button", { timeout: 20000 }); await sleep(1000);
  const task = await words(page, "[data-tq-task-page] [data-tq-section-tab=from] [data-tq-spine-moves] button");
  assert.ok(task.includes("Not a task") && !task.includes("Should be a task"), `a task's Came from: ${task}`);
  assert.deepEqual(errors, []);
});
