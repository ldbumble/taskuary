import assert from "node:assert/strict";
import test from "node:test";
import { boot, rail, pressNext, sleep } from "./walkdriver.mjs";

/* THE WALK FLOWS (the 2026-10-28 flow walk), at a laptop and a phone: Walk me through my tasks, then Next from the first task to the end -
   every task once, in its rail order, then the reports, then the fyi a batch at a time under "All read, next" with the band's count going
   down by the batch, and the walk's own button again at the end. Then Back from the top of the fyi down to the first task: each step the
   one before it, the ring on what the table shows, and no Back on the first. Invented Northwind world (the demo). */
const ringed = async (page) => (await rail(page)).find((r) => r.cur) || null;
const table = (page) => page.evaluate(() => [...document.querySelectorAll("[data-tq-canvas-item]")].filter((e) => e.getBoundingClientRect().height > 0).pop()
  ?.getAttribute("data-tq-canvas-item") || "");
const row = (page) => page.evaluate(() => (document.querySelector("[data-tq-row]")?.innerText || "").replace(/\s+/g, " "));
const fyiMore = (page) => page.evaluate(() => [...document.querySelectorAll(".tq-pile-more")].filter((e) => e.getBoundingClientRect().height > 0 && /fyi/.test(e.textContent))
  .map((e) => Number((e.textContent.match(/\d+/) || [0])[0]))[0] ?? 0);
const back = (page) => page.evaluate(() => { const b = document.querySelector("[data-tq-row] button[data-tq-walk-back]");
  if (b && !b.disabled) { b.click(); return true; } return false; });

for (const [width, height] of [[1440, 900], [390, 844]]) {
  test(`at ${width}px Next walks every task once, then the reports, then the fyi by the batch; Back walks it back`, { timeout: 300000 }, async (t) => {
    const { page, errors } = await boot(t, { width, height });
    const tasks = (await rail(page)).map((r) => r.key);
    await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => /Walk me through my tasks/.test(b.innerText))?.click());
    await page.waitForFunction(() => !!document.querySelector(".tq-pile-row.current"), { timeout: 20000 });
    await sleep(1500);
    // Back first, over the tasks: twelve Nexts down, twelve Backs up - each the row before, the ring on what the table shows
    const fwd = [];
    for (let i = 0; i < 12; i++) { fwd.push((await ringed(page)).key); assert.ok(await pressNext(page)); await sleep(1800); }
    const bk = [];
    for (let i = 0; i < 12; i++) {
      assert.ok(await back(page), `Back is on the row ${i + 1} steps up`); await sleep(1800);
      const r = await ringed(page); bk.push(r?.key); assert.equal(await table(page), r?.key, "Back's ring and table agree");
    }
    assert.deepEqual(bk, fwd.slice().reverse(), "Back walks the same rows back, one at a time");
    assert.equal(await back(page), false, "the first task offers no Back");

    // ...then Next from the first task to the end
    const seen = [];
    for (let i = 0; i < 40; i++) {
      const r = await ringed(page);
      if (!r) break;                                                   // the fyi batches ring no single row
      assert.ok(!seen.includes(r.key), `Next came back to ${r.text} - it walks each item once: ${JSON.stringify(seen)}`);
      if (/TQ-\d+/.test(r.text)) assert.equal(await table(page), r.key, `the ring and the table name one item: ${r.text}`);
      seen.push(r.key);
      assert.ok(await pressNext(page), `Next is on the row at ${r.text}`);
      await sleep(1800);
    }
    // the rows the rail drew at the start, in its order - none skipped, none out of turn - and the folded reports after them
    const order = tasks.filter((k) => seen.includes(k));
    assert.deepEqual(seen.slice(0, order.length), order, "Next takes the rows in their rail order");
    assert.ok(seen.length >= 15, `the walk went through the tasks and the reports: ${seen.length}`);
    // the fyi, a batch at a time: "All read, next", and the band's count down by what each batch read
    const counts = [];
    for (let b = 0; b < 6 && /All read, next/.test(await row(page)); b++) { counts.push(await fyiMore(page)); assert.ok(await pressNext(page)); await sleep(2500); }
    assert.ok(counts.length >= 2, `the fyi came in batches under All read, next: ${JSON.stringify(counts)}`);
    for (let i = 1; i < counts.length; i++) assert.ok(counts[i] < counts[i - 1] || counts[i] === 0, `the fyi count goes down batch by batch: ${JSON.stringify(counts)}`);
    assert.match(await row(page), /Walk me through my tasks/, "the end of the walk offers to walk again");
    assert.deepEqual(errors, []);
  });
}
