import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, pressNext, sleep } from "./walkdriver.mjs";

/* NEXT ON THE ROW A PRESS DREW, WHILE THAT PRESS IS STILL OUT (the owner, 2026-11-02: "still when you hit next the one you are on, task or
   report, does not disappear right away"). Next draws the row below at its press, but a second Next on that row was held until the first
   answer landed - the row sat on the table, ringed (and a report on the rail), for as long as the server took. Every walk answer is held
   2.5 s here, as a real home's can be: the second press puts its row down and draws the one after at once, a report leaves the rail at
   once, and when both answers are in the walk stands where the page does. */
const HOLD = 2500, AT_ONCE = 300;
const ring = (page) => page.evaluate(() => document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") || "");
const table = (page) => page.evaluate(() => [...document.querySelectorAll(".tq-canvas-live [data-tq-canvas-item]")].filter((x) => x.getBoundingClientRect().height > 0).pop()?.getAttribute("data-tq-canvas-item") || "");
const run = (page, sec) => page.$$eval(`[data-tq-run="${sec}"] .tq-pile-row[data-tq-key]`, (els) => els.map((e) => e.getAttribute("data-tq-key")));
const walkOn = (page) => page.evaluate(() => fetch("/api/funnel/pile", { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } }).then((r) => r.json()).then((p) => p.walk?.on));
const until = async (f, ms) => { for (const t0 = Date.now(); Date.now() - t0 < ms; await sleep(25)) if (await f()) return Date.now() - t0; return -1; };

async function twoNexts(t, pick) {
  const { page, errors } = await boot(t, { width: 1440, height: 900, slow: HOLD, slowOn: "/api/walk/next" });
  const tasks = await run(page, "task"), reports = await run(page, "reports");
  const [from, line] = pick(tasks, reports);
  await clickRow(page, from); await until(async () => (await ring(page)) === from, 15000); await sleep(2500);
  assert.ok(await pressNext(page), "the first Next");
  assert.ok(await until(async () => (await ring(page)) === line[0], AT_ONCE) >= 0, `the first Next drew ${await ring(page)}, not ${line[0]}`);
  await sleep(400);
  assert.ok(await pressNext(page), "a second Next, the first still out");
  const took = await until(async () => (await ring(page)) === line[1], AT_ONCE);
  assert.ok(took >= 0, `the row passed stayed: the ring is on ${await ring(page)}, not ${line[1]}, ${AT_ONCE} ms after the second Next`);
  assert.notEqual(await table(page), line[0], "the row passed is still on the table");
  return { page, errors };
}

test("a second Next on a task the first drew moves on at its press", { timeout: 300000 }, async (t) => {
  const { page, errors } = await twoNexts(t, (tasks) => [tasks.at(-4), tasks.slice(-3)]);
  await sleep(2 * HOLD + 1500);
  const tasks = await run(page, "task");
  assert.equal(await ring(page), tasks.at(-2), "both answers in: the ring stayed on the row the second press drew");
  assert.equal(await walkOn(page), tasks.at(-2), "the walk stands where the page does");
  assert.ok(tasks.includes(tasks.at(-3)), "a task Next passed stays on the rail (rule 4)");
  assert.deepEqual(errors, []);
});

test("a second Next on a report the first drew takes it off the rail at its press", { timeout: 300000 }, async (t) => {
  let r0 = null;
  const { page, errors } = await twoNexts(t, (tasks, reports) => { r0 = reports[0]; return [tasks.at(-1), reports.slice(0, 2)]; });
  assert.ok(!(await run(page, "reports")).includes(r0), "the report passed is still on the rail");
  await sleep(2 * HOLD + 1500);
  assert.ok(!(await run(page, "reports")).includes(r0), "the report passed came back on the rail");
  assert.equal(await walkOn(page), await ring(page), "the walk stands where the page does");
  assert.deepEqual(errors, []);
});
