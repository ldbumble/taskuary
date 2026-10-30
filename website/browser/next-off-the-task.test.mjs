import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, clickText, rail, sleep } from "./walkdriver.mjs";

/* NEXT FROM A PAGE OVER A TASK (the owner, 2026-10-29): on Reports, with a task under it ("under this page" on the rail), the bar wore the
   task's moves beside Back and Next - Put it on my list, Reply, Mark done, Send to agent, Remind me / Not ours - and Next did nothing. A line
   said after the task (an answer carries the table's own words) lent them to the bar, which the task page's bar never shows; and what Next
   brought without a card (the walk's end, a failure) landed in the shut chat window and under the page, so nothing moved. Next from a page
   walks on as it does from the task page - to the row below the table's task - and takes the page down with it. */
const state = (page) => page.evaluate(() => {
  const vis = (e) => e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().height > 0;
  return { hash: location.hash, items: [...document.querySelectorAll("[data-tq-canvas-item]")].filter(vis).map((e) => e.getAttribute("data-tq-canvas-item")),
    browse: [...document.querySelectorAll("[data-tq-browse]")].filter(vis).map((e) => e.getAttribute("data-tq-browse")),
    bar: [...document.querySelectorAll("[data-tq-row] button")].filter(vis).map((b) => b.textContent.trim()),
    board: [...document.querySelectorAll("[data-tq-board-task]")].some(vis),
    err: [...document.querySelectorAll("[data-tq-err-line]")].filter(vis).map((e) => e.textContent),
    ring: [...document.querySelectorAll("[data-tq-rail] .tq-pile-row.current")].map((e) => e.getAttribute("data-tq-key")) };
});
const nav = (page, k) => page.evaluate((k) => { const n = document.querySelector(`[data-tq-nav="${k}"]`); n?.click(); return !!n; }, k);
const next = (page) => page.evaluate(() => { const b = document.querySelector("[data-tq-row] [data-tq-next]"); if (b && !b.disabled) { b.click(); return true; } return false; });
const ask = async (page, text) => { await page.click(".tq-compose-box textarea"); await sleep(300); await page.keyboard.type(text); await page.keyboard.press("Enter"); await sleep(5000); };
// a task on the table and a line said about it after it - the shape that lent the bar its words
async function taskUnder(t) {
  const { page, errors } = await boot(t, { width: 1440 });
  const rows = await rail(page), at = 2;
  assert.ok(await clickRow(page, rows[at].key)); await sleep(3500);
  assert.match((await state(page)).hash, /^#task=\d+$/, "the row did not open its task");
  await ask(page, "what is this one about?");
  return { page, errors, row: rows[at].key, below: rows[at + 1].key };
}

test("Next on Reports over a task opens the row below it, and the bar there is Back and Next", { timeout: 240000 }, async (t) => {
  const { page, errors, row, below } = await taskUnder(t);
  for (const area of ["reports", "new", "settings"]) {
    assert.ok(await nav(page, area)); await sleep(2500);
    const s = await state(page);
    assert.deepEqual(s.browse, [area], `${area} did not open`);
    assert.deepEqual(s.ring, [row], `${area}: the task is not the one under the page`);
    assert.deepEqual(s.bar, ["Back", "Next"], `${area}: the bar carries the task's moves`);
    // ...greyed under Settings, which has its own ← back to your tasks at the top (the owner, 2026-10-29); Reports and New keep them
    const bar = await page.evaluate(() => [...document.querySelectorAll("[data-tq-row] [data-tq-next], [data-tq-row] [data-tq-walk-back]")].map((b) => ({ off: b.disabled, title: b.title })));
    if (area === "settings") assert.ok(bar.length && bar.every((b) => b.off && /Back to your tasks with ← at the top/.test(b.title)), `settings: ${JSON.stringify(bar)}`);
    else assert.ok(bar.some((b) => !b.off), `${area}: Back and Next are greyed ${JSON.stringify(bar)}`);
  }
  assert.ok(await nav(page, "reports")); await sleep(2500);
  assert.ok(await next(page), "no Next on the bar over Reports"); await sleep(4000);
  const now = await state(page);
  assert.deepEqual(now.browse, [], "Reports is still drawn after Next");
  assert.deepEqual(now.ring, [below], "Next did not walk to the row below the task");
  assert.equal(now.items.length, 1, `the next item is not on the canvas ${JSON.stringify(now)}`);
  // ...and the Board, a view of its own, carries none of the table's moves either
  assert.ok(await clickText(page, /^Board$/)); await sleep(2500);
  const b = await state(page);
  assert.ok(b.board, "the Board did not open");
  assert.ok(b.bar.every((x) => ["Back", "Next"].includes(x)), `Board: the bar carries the task's moves ${b.bar}`);
  assert.deepEqual(errors, []);
});

test("a Next over Reports that brings no item is still seen: the page goes and the canvas says what happened", { timeout: 240000 }, async (t) => {
  const { page, errors, row } = await taskUnder(t);
  assert.ok(await nav(page, "reports")); await sleep(2500);
  const guard = page.fixtureRequestGuard;
  page.off("request", guard); page.on("request", (r) => (/\/api\/concierge\/(next|stream)/.test(r.url()) ? r.abort() : guard(r)));
  assert.ok(await next(page)); await sleep(4000);
  const now = await state(page);
  assert.deepEqual(now.browse, [], "Reports is still drawn over a Next that failed");
  assert.deepEqual(now.ring, [row], "the task Next could not leave is not back on the table");
  assert.ok(now.err.length, `the failure is said nowhere in view ${JSON.stringify(now)}`);
  assert.deepEqual(errors, []);
});
