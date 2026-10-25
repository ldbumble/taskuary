import assert from "node:assert/strict";
import test from "node:test";
import { boot, sleep } from "./walkdriver.mjs";

/* THE FYI COUNT GOES STRAIGHT FROM ONE BATCH TO THE NEXT (the 2026-10-25 navigation sweep, N15): "All read, next" lands the settled rail a
   moment before the next batch is on the table, and for that moment the band fell to its floor - "8 more fyi" -> "6 more fyi" -> "4 more
   fyi", and "2 more fyi" before none - a count that was neither the one before nor the one after, on every press. Sampled every frame. */
test("between two fyi batches the rail never draws a count that is neither the old one nor the new one", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t);
  const press = () => page.evaluate(() => { const b = document.querySelector("[data-tq-row] [data-tq-next]"); b?.click(); return b?.textContent.trim() || null; });
  await page.click('[data-tq-section-head="reports"] .fold'); await sleep(1500);
  await page.evaluate(() => [...document.querySelectorAll('[data-tq-run="reports"] .tq-pile-row[data-tq-key] .card')].at(-1).click()); await sleep(3500);
  await press(); await sleep(3500);                                    // the first fyi batch is on the table
  await page.evaluate(() => {
    window.__f = []; let last = null;
    const tick = () => {
      const more = [...document.querySelectorAll(".tq-pile-more")].filter((e) => e.getBoundingClientRect().height > 0 && /fyi/.test(e.textContent)).map((e) => e.textContent.trim())[0] || "";
      if (more !== last) { last = more; window.__f.push(more); }
      requestAnimationFrame(tick);
    }; tick();
  });
  const runs = [];
  for (let b = 0; b < 2; b++) {
    const was = await page.evaluate(() => window.__f.length);
    assert.equal(await press(), "All read, next", "no fyi batch on the table"); await sleep(3000);
    runs.push(await page.evaluate((n) => window.__f.slice(Math.max(0, n - 1)), was));
  }
  for (const r of runs) assert.deepEqual(r.filter((x, i) => i > 0 && i < r.length - 1), [], `a stray count between ${r[0] || "(none)"} and ${r.at(-1) || "(none)"}: ${JSON.stringify(r)}`);
  assert.deepEqual(errors, []);
});
