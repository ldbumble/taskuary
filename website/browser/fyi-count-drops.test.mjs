import assert from "node:assert/strict";
import test from "node:test";
import { boot, sleep } from "./walkdriver.mjs";

/* WHAT A WALK PRESS READS LEAVES THE RAIL AT THE PRESS (rule 4; the owner, 2026-11-01: "when you hit All read, next the fyi number on top
   is not going down", "why does it take 5 seconds until the one i hit next on disappears"). The rail held the read rows until the answer
   landed, and on a real home that answer takes seconds. Here every walk answer is held 3 s in the page: the passed report and the read
   batch must be off the rail, and off the FYI heading's count, long before it - and a reload must say the same. */
const SLOW = 3000;
const head = (page) => page.evaluate(() => Number(document.querySelector('[data-tq-section-head="fyi"] em')?.textContent ?? 0));
const onTable = (page) => page.evaluate(() => document.querySelectorAll("[data-tq-rail] .tq-pile-row.inbatch").length);
// how long after the press until `gone()` holds, sampled every frame (null: never, within 6 s)
const until = (page, gone) => page.evaluate((src) => new Promise((done) => {
  const f = new Function(`return (${src})()`), t0 = performance.now();
  const tick = () => { if (f()) done(Math.round(performance.now() - t0)); else if (performance.now() - t0 > 6000) done(null); else requestAnimationFrame(tick); };
  document.querySelector("[data-tq-row] [data-tq-next]").click(); tick();
}), gone.toString());

test("a walk press takes what it reads off the rail and the FYI heading at once, and a reload agrees", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t, { slow: SLOW, slowOn: "/api/walk/" });
  await page.click('[data-tq-section-head="reports"] .fold'); await sleep(1500);
  const report = await page.evaluate(() => { const r = document.querySelector('[data-tq-run="reports"] .tq-pile-row[data-tq-key]'); r.querySelector(".card").click(); return r.dataset.tqKey; });
  await sleep(SLOW + 1500);
  // Next on a report reads it: the row leaves with the press, while the report below is already on the table
  await page.evaluate((k) => { window.__k = k; }, report);
  const passed = await until(page, () => !document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${window.__k}"]`));
  console.log("passed report gone after", passed, "ms");
  assert.ok(passed !== null && passed < 1000, `the passed report stayed on the rail ${passed ?? "6000+"} ms after Next`);
  for (let i = 0; i < 8; i++) {                                       // on down the reports to the first fyi batch
    await sleep(SLOW + 1500);
    if (await page.evaluate(() => document.querySelector("[data-tq-row] [data-tq-next]")?.textContent.trim()) === "All read, next") break;
    await page.evaluate(() => document.querySelector("[data-tq-row] [data-tq-next]")?.click());
  }
  const was = await head(page), n = await onTable(page);
  assert.ok(n > 0, "no fyi batch on the table");
  assert.equal(await page.evaluate(() => document.querySelector("[data-tq-row] [data-tq-next]")?.textContent.trim()), "All read, next");
  await page.evaluate((w) => { window.__w = w; }, was - n);
  const dropped = await until(page, () => Number(document.querySelector('[data-tq-section-head="fyi"] em')?.textContent ?? 0) === window.__w);
  console.log("read batch off the FYI heading after", dropped, "ms");
  assert.ok(dropped !== null && dropped < 1000, `the FYI heading still counted the read batch ${dropped ?? "6000+"} ms after All read, next (${was} with ${n} read)`);
  await sleep(SLOW + 2000);
  assert.equal(await head(page), was - n, "the answer put the read batch back in the count");
  await page.reload({ waitUntil: "domcontentloaded" }); await page.waitForSelector("[data-tq-rail] .tq-pile-row"); await sleep(4000);
  assert.equal(await head(page), was - n, "a reload counts the read batch again");
  assert.deepEqual(errors, []);
});
