import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE RAIL IS ONE FIXED ORDER, AND NEXT WALKS DOWN IT (the owner, 2026-10-22): "If I click on the bottom one then hit Next it should go
   to Reports, not jump back to Tasks. It should always be in order." "On the table should never move them."
   On the demo world: the last task clicked, then Next - the first report is what opens, and the rail's order is the same before the
   click, with the task on the table, and after Next. */

const rail = (page) => page.$$eval("[data-tq-rail] .tq-pile-row", (els) => els
  .map((r) => ({ key: r.getAttribute("data-tq-key"), level: r.closest("[data-tq-run]")?.getAttribute("data-tq-run") }))
  .filter((r) => r.key));
const current = (page) => page.$eval(".tq-pile-row.current", (e) => e.getAttribute("data-tq-key")).catch(() => null);
const clickRow = (page, key) => page.evaluate((k) => document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"] .card`).click(), key);
const clickNext = (page) => page.evaluate(() => {
  const button = [...document.querySelectorAll("button")].find((n) => n.textContent.trim() === "Next" && !n.disabled);
  if (!button) throw new Error("Next must be enabled for this owner gesture");
  button.click();
});
// the rows both orders hold, in each one's order: a row may come or go (a batch read), but none may change place
const common = (a, b) => { const kb = new Set(b.map((r) => r.key)); return a.filter((r) => kb.has(r.key)).map((r) => r.key); };

test("Next from the clicked bottom task opens the first report, and no row moves", { timeout: 240000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((n) => n.textContent.trim() === "Next" || /walk/i.test(n.textContent)),
    { timeout: 30000 }).catch(() => {});

  const before = await rail(page);
  const tasks = before.filter((r) => r.level === "task"), reports = before.filter((r) => r.level === "reports");
  assert.ok(tasks.length >= 2, `the demo rail has tasks: ${JSON.stringify(before)}`);
  assert.ok(reports.length >= 1, `the demo rail has a report: ${JSON.stringify(before)}`);
  const bottom = tasks[tasks.length - 1].key, firstReport = reports[0].key;
  // the Tasks section comes before Reports, every task above every report
  assert.ok(before.findIndex((r) => r.key === firstReport) > before.findIndex((r) => r.key === bottom));

  await clickRow(page, bottom);
  await page.waitForFunction((k) => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") === k, { timeout: 20000 }, bottom);
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((n) => n.textContent.trim() === "Next" && !n.disabled), { timeout: 20000 });
  const onTable = await rail(page);
  assert.deepEqual(common(onTable, before), common(before, onTable), "putting the bottom task on the table moved a row");
  assert.equal(onTable.filter((r) => r.level === "task").at(-1)?.key, bottom, "the clicked task left the bottom of Tasks");

  await clickNext(page);
  await page.waitForFunction((k) => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") === k, { timeout: 20000 }, firstReport)
    .catch(async () => assert.fail(`Next went to ${await current(page)}, not the first report ${firstReport}`));
  await new Promise((r) => setTimeout(r, 1500));          // the rail that rides along with the answer lands
  assert.equal(await current(page), firstReport, "the table did not stay on the first report");
  const after = await rail(page);
  assert.deepEqual(common(after, before), common(before, after), "Next moved a row on the rail");
  // every task Next did not walk past stays in Tasks; the one it did stays too - or, a goal, goes to For later once its news is
  // walked past (the goal spec, 2026-10-12): leaving its section, never changing place inside one
  for (const r of tasks) {
    const now = after.find((x) => x.key === r.key);
    assert.ok(now && (now.level === "task" || (r.key === bottom && now.level === "later")), `task ${r.key} left Tasks on Next: ${JSON.stringify({ before, after })}`);
  }
  assert.deepEqual(errors, []);
});
