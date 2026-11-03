import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, pressNext, sleep } from "./walkdriver.mjs";

/* BACK MOVES AT ITS PRESS, AS NEXT DOES (the owner, 2026-11-02: "the Back button takes way too long, not like the Next button which works
   well"). Next drew the row below at its press; Back waited for the server's whole answer before the table moved. Every walk answer is held
   2 s here, as a real home's can be: Back draws the row above at once, and when every answer is in the walk stands where the page does. A
   second press while the first is out finds Back and Next greyed (the owner, 2026-11-03: one move at a time); once it lands, it too moves at
   its press - Back twice, Next after a Back, Back after a Next. */
const HOLD = 2000, AT_ONCE = 300;
const ring = (page) => page.evaluate(() => document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") || "");
const table = (page) => page.evaluate(() => [...document.querySelectorAll(".tq-canvas-live [data-tq-canvas-item]")].filter((x) => x.getBoundingClientRect().height > 0).pop()?.getAttribute("data-tq-canvas-item") || "");
const run = (page, sec) => page.$$eval(`[data-tq-run="${sec}"] .tq-pile-row[data-tq-key]`, (els) => els.map((e) => e.getAttribute("data-tq-key")));
const pressBack = (page) => page.evaluate(() => { const b = document.querySelector(".tq-dock [data-tq-row] [data-tq-walk-back]"); if (b && !b.disabled) { b.click(); return true; } return false; });
const walkOn = (page) => page.evaluate(() => fetch("/api/funnel/pile", { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } }).then((r) => r.json()).then((p) => p.walk?.on));
const until = async (f, ms) => { for (const t0 = Date.now(); Date.now() - t0 < ms; await sleep(25)) if (await f()) return Date.now() - t0; return -1; };
const on = async (page, key, what) => {
  const took = await until(async () => (await ring(page)) === key && (await table(page)) === key, AT_ONCE);
  assert.ok(took >= 0, `${what}: ring ${await ring(page)}, table ${await table(page)}, not ${key}, ${AT_ONCE} ms after the press`);
  return took;
};
async function at(t, n) {
  const { page, errors } = await boot(t, { width: 1440, height: 900, slow: HOLD, slowOn: "/api/walk/" });
  const tasks = await run(page, "task");
  assert.ok(tasks.length > n + 1, `the demo has tasks: ${tasks}`);
  await clickRow(page, tasks[n]); assert.ok(await until(async () => (await ring(page)) === tasks[n], 15000) >= 0, `the click opened ${tasks[n]}`);
  await sleep(HOLD + 1500);
  return { page, errors, tasks };
}
// ...the second press: refused while the first is out, both buttons greyed - then taken once it lands, and drawn at its press
const greyedThen = async (page, press, key, what) => {
  assert.equal(await press(page), false, `${what}: taken while the move before it was out`);
  assert.equal(await pressNext(page) || await pressBack(page), false, `${what}: Next or Back live while a move was out`);
  assert.ok(await until(() => press(page), HOLD + 3000) >= 0, `${what}: never live again`);
  return on(page, key, what);
};
const settled = async (page, key) => {
  await sleep(2 * HOLD + 1500);
  assert.equal(await ring(page), key, "every answer in: the ring stayed on the row the last press drew");
  assert.equal(await table(page), key, "every answer in: the table stayed on the row the last press drew");
  assert.equal(await walkOn(page), key, "the walk stands where the page does");
};

test("Back draws the row above at its press", { timeout: 300000 }, async (t) => {
  const { page, errors, tasks } = await at(t, 2);
  assert.ok(await pressBack(page), "Back is offered");
  console.log(`Back alone: ${await on(page, tasks[1], "Back")} ms`);
  await settled(page, tasks[1]);
  assert.deepEqual(errors, []);
});

test("Back pressed twice: greyed while the first is out, then up again at its press", { timeout: 300000 }, async (t) => {
  const { page, errors, tasks } = await at(t, 3);
  assert.ok(await pressBack(page), "the first Back");
  await on(page, tasks[2], "the first Back");
  console.log(`second Back: ${await greyedThen(page, pressBack, tasks[1], "the second Back")} ms`);
  await settled(page, tasks[1]);
  assert.deepEqual(errors, []);
});

test("Next after a Back: greyed while the Back is out, then back down at its press", { timeout: 300000 }, async (t) => {
  const { page, errors, tasks } = await at(t, 2);
  assert.ok(await pressBack(page), "Back");
  await on(page, tasks[1], "Back");
  console.log(`Next after a Back: ${await greyedThen(page, pressNext, tasks[2], "Next after a Back")} ms`);
  await settled(page, tasks[2]);
  assert.deepEqual(errors, []);
});

test("Back after a Next: greyed while the Next is out, then back up at its press", { timeout: 300000 }, async (t) => {
  const { page, errors, tasks } = await at(t, 2);
  assert.ok(await pressNext(page), "Next");
  assert.ok(await until(async () => (await ring(page)) === tasks[3], AT_ONCE) >= 0, `Next drew ${await ring(page)}, not ${tasks[3]}`);
  console.log(`Back after a Next: ${await greyedThen(page, pressBack, tasks[2], "Back after a Next")} ms`);
  await settled(page, tasks[2]);
  assert.deepEqual(errors, []);
});
