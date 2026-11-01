import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* WHICH WORKSTREAM, ON THE TASK (the owner, 2026-11-01: "the workstream is changeable on the task itself, the way dev tasks have their
   GitHub repo picker"). Alex runs Northwind finance systems by day and the Ledger app with friends; Omar's bug report is placed in the
   Ledger app by his address. The task's "What triage made of it" shows that in its picker; choosing Northwind moves it, and the task
   reads it back. At 1440x900, invented people only. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("the task shows its workstream in a picker, and choosing another moves it", { timeout: 300000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const page = await h.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const made = await (await fetch(`${h.fixtureApi}/api/fixture/task/workstreams`, { method: "POST",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: "{}" })).json();
  assert.equal(made.workstream, "ledger-app", JSON.stringify(made));
  const CUR = `[data-tq-canvas-item]:has([data-tq-task-page="${made.taskId}"])`;
  await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector(`${CUR} [data-tq-task-body][data-tq-sections]`, { timeout: 20000 });
  await sleep(1500);
  if (await page.$(`${CUR} [data-tq-section-tab=from]`)) { await page.click(`${CUR} [data-tq-section-tab=from] [data-tq-tab-arrow]`); await sleep(800); }
  // ...and its rail row wears the workstream as a small label after the title (the owner, 2026-11-01)
  await page.waitForFunction((t) => [...document.querySelectorAll("[data-tq-rail] .tq-pile-row")].some((r) => r.innerText.includes(t)
    && r.querySelector("[data-tq-workstream]")?.innerText.includes("Ledger app")), { timeout: 15000 }, "Export button greyed");
  const sel = `${CUR} [data-tq-workstream-picker] select`;
  await page.waitForSelector(sel, { visible: true, timeout: 10000 });
  const before = await page.$eval(sel, (s) => ({ value: s.value, options: [...s.options].map((o) => o.textContent) }));
  assert.equal(before.value, "ledger-app");
  assert.deepEqual(before.options, ["Northwind finance systems", "Ledger app", "Personal (personal)"]);
  await page.select(sel, "northwind-finance-systems");
  await sleep(1500);
  const got = await (await fetch(`${h.fixtureApi}/api/tasks/${made.taskId}`, { headers: { "X-Taskuary-Token": h.token } })).json();
  assert.equal(got.workstream?.slug, "northwind-finance-systems", JSON.stringify(got.workstream));
  assert.equal(await page.$eval(sel, (s) => s.value), "northwind-finance-systems");
  assert.deepEqual(errors, []);
});
