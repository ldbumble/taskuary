import assert from "node:assert/strict";
import test from "node:test";
import { boot, rail, sleep } from "./walkdriver.mjs";

/* BACK FROM A PAGE PUTS IT DOWN (the 2026-10-25 navigation sweep, N17 and N19). Over a task, Back to the task's own #task=N was taken for a
   reload of the canvas's own address: the address changed, the Reports or Settings page stayed drawn, the task never came back and the Back
   arrow went. On the empty chat, Back left the page's folded header and a lone floor Next where the greeting, the day card and Walk me
   through my tasks had been. */
const state = (page) => page.evaluate(() => {
  const vis = (e) => e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().height > 0;
  return { hash: location.hash, items: [...document.querySelectorAll("[data-tq-canvas-item]")].filter(vis).map((e) => e.getAttribute("data-tq-canvas-item")),
    browse: [...document.querySelectorAll("[data-tq-browse]")].filter(vis).map((e) => e.getAttribute("data-tq-browse")),
    walk: [...document.querySelectorAll("button")].some((b) => vis(b) && b.textContent.trim() === "Walk me through my tasks"),
    floor: [...document.querySelectorAll("[data-tq-row] [data-tq-next]")].filter(vis).length };
});
const nav = (page, k) => page.evaluate((k) => { const n = document.querySelector(`[data-tq-nav="${k}"]`); n?.click(); return !!n; }, k);
const back = (page) => page.evaluate(() => { const b = document.querySelector('button[aria-label="Back"]'); b?.click(); return !!b; });

test("Back from Reports or Settings opened over a task brings the task back", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440 });
  const row = (await rail(page))[1].key;
  await page.evaluate((k) => document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"] .card`).click(), row); await sleep(3500);
  const was = await state(page);
  assert.match(was.hash, /^#task=\d+$/);
  for (const [area, how] of [["reports", "the header Back"], ["settings", "the browser's Back"]]) {
    assert.ok(await nav(page, area), area); await sleep(2500);
    if (how === "the header Back") assert.ok(await back(page), "no Back arrow over the page"); else await page.goBack();
    await sleep(3000);
    const now = await state(page);
    assert.equal(now.hash, was.hash, `${how}: the address`);
    assert.deepEqual(now.browse, [], `${how}: the ${area} page is still drawn`);
    assert.ok(now.items.includes(was.items[0]), `${how}: the task is not back on the canvas (${now.items})`);
  }
  assert.deepEqual(errors, []);
});

test("Back from a page on the empty chat brings the day card and its Walk button back", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440 });
  await sleep(1500);
  assert.ok((await state(page)).walk, "the landing has no Walk button");
  assert.ok(await nav(page, "reports")); await sleep(2500);
  assert.ok(await back(page), "no Back arrow over Reports"); await sleep(5000);
  const now = await state(page);
  assert.ok(now.walk, `the Walk button did not come back: ${JSON.stringify(now)}`);
  assert.equal(now.floor, 0, "a lone floor Next stood in the Walk button's place");
  assert.deepEqual(errors, []);
});
