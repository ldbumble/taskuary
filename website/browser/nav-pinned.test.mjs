import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, pressNext, rail, sleep } from "./walkdriver.mjs";

/* NEXT STAYS UNDER THE CURSOR (the owner, 2026-10-28, from the demo sweep): the dock's row was centred, so the Nav pill moved with each
   item's buttons - Next stood at 519, then 704, then 615 px - and walking meant chasing it. Nav holds the row's start now; the item's
   own types centre in what is left. On the demo world at a laptop's 1366: the first task and Next down two more, Next's x the same on
   each - the first one too, where there is no Back and its room is kept. */
const until = async (f, ms = 15000) => { for (const t0 = Date.now(); Date.now() - t0 < ms; await sleep(200)) if (await f()) return true; return false; };
const on = (page) => page.evaluate(() => document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") || "");
const nextAt = (page) => page.evaluate(() => {
  const b = document.querySelector(".tq-dock [data-tq-row] [data-tq-next]"), r = b?.getBoundingClientRect();
  const verbs = [...document.querySelectorAll(".tq-dock [data-tq-row] .tq-arow-verbs button[data-tq-verb]")].map((x) => x.textContent.trim());
  return r ? { x: Math.round(r.left), w: Math.round(r.width), verbs } : null;
});

test("Next stands at the same x on three tasks in a row", { timeout: 300000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1366, height: 768 });
  const tasks = (await rail(page)).filter((r) => r.key).map((r) => r.key);
  const run = await page.$$eval("[data-tq-run=task] .tq-pile-row", (els) => els.map((e) => e.getAttribute("data-tq-key")));
  assert.ok(run.length >= 3, `the demo rail has three tasks: ${JSON.stringify(tasks)}`);
  await clickRow(page, run[0]);
  await until(async () => (await on(page)) === run[0] && !!(await nextAt(page))); await sleep(2500);
  const seen = [await nextAt(page)];
  for (const k of run.slice(1, 3)) {
    assert.ok(await pressNext(page), "Next is pressable");
    assert.ok(await until(async () => (await on(page)) === k), `Next walks down to ${k}`);
    await sleep(2500);
    seen.push(await nextAt(page));
  }
  // ...the items' own rows differ, so the test means something: a centred row would have moved Next between them - or, on a desk where the
  // bar is Back and Next alone (the owner, 2026-10-29), nothing else is on it to move them
  assert.ok(new Set(seen.map((s) => s.verbs.join("|"))).size > 1 || seen.every((s) => !s.verbs.length), `three items with different buttons: ${JSON.stringify(seen)}`);
  // ...from the second task on, with Back beside it; the first has no Back and no empty room kept for one (the owner, 2026-10-28: it looked weird)
  const withBack = seen.slice(1);
  assert.ok(withBack.every((s) => Math.abs(s.x - withBack[0].x) <= 1), `Next's x once Back is there: ${JSON.stringify(seen.map((s) => s.x))}`);
  assert.deepEqual(errors, []);
});

/* ...AND CENTRED WHEN IT IS ALL THE ROW HAS (the owner, 2026-10-28: "nav should be in middle if nothing else") - until the bar became only as
   wide as what it holds, Back and Next then the ask bar (the owner, 2026-10-29): on a desk Nav stands at the bar's start, a task's and an FYI
   batch's alike, with no empty stretch around it. */
const navBox = (page) => page.evaluate(() => {
  const row = document.querySelector(".tq-dock [data-tq-row] .tq-arow-verbs"), nav = row?.querySelector(".tq-cl-next");
  if (!row || !nav) return null;
  const r = row.getBoundingClientRect(), n = nav.getBoundingClientRect();
  return { groups: row.querySelectorAll(":scope > .tq-cl").length, left: Math.round(n.left - r.left), right: Math.round(r.right - n.right),
    next: nav.querySelector("[data-tq-next]")?.textContent.trim() || "" };
});
test("on a desk the bar is Nav alone, at its start, for a task and an FYI batch", { timeout: 300000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1366, height: 768 });
  const run = await page.$$eval("[data-tq-run=task] .tq-pile-row", (els) => els.map((e) => e.getAttribute("data-tq-key")));
  await clickRow(page, run[0]);
  await until(async () => (await on(page)) === run[0] && !!(await navBox(page))); await sleep(2500);
  const task = await navBox(page);
  assert.ok(task.groups === 1 && task.left <= 2 && task.right <= 12, `a task's bar: Nav alone, no empty stretch ${JSON.stringify(task)}`);
  // the first FYI batch, the way fyi-count-between-batches gets there: the last report, then Next
  await page.evaluate(() => document.querySelector('[data-tq-section-head="reports"] .fold').click()); await sleep(1500);
  await page.evaluate(() => [...document.querySelectorAll('[data-tq-run="reports"] .tq-pile-row[data-tq-key] .card')].at(-1).click()); await sleep(3500);
  await pressNext(page);
  assert.ok(await until(async () => (await navBox(page))?.next === "All read, next"), "an FYI batch is on the table");
  await sleep(1500);
  const fyi = await navBox(page);
  assert.equal(fyi.groups, 1, `the batch's row is Nav alone ${JSON.stringify(fyi)}`);
  assert.ok(fyi.left <= 2 && fyi.right <= 12, `Nav alone, the bar as wide as it ${JSON.stringify(fyi)}`);
  assert.deepEqual(errors, []);
});
