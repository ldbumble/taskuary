import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, doVerb, folded, pressNext, rail, sleep } from "./walkdriver.mjs";

/* PUT IT ON MY LIST KEEPS THE NEW TASK AT THE REPORT'S PLACE, AND NEXT GOES ON DOWN THE LINE (the walk has one owner, 2026-10-30, spec 3.5
   W49 - railwalk.open(at=...)). The 2026-10-26 sweep found the walk going on from the new task's place under Tasks - back up the rail, the
   table blank for ~1.7 s. Now the table keeps the new task, and Next from it walks on from where the report or the FYI stood: to the row
   below it, never back up into Tasks, and the card it leaves wears its badge. */
const CASES = [
  { row: /Headcount by site/, below: /AP ageing over 30 days/ },
  { row: /Regional operations newsletter/, below: null },
];
const until = (page, f, arg, timeout = 20000) => page.waitForFunction(f, { timeout, polling: 100 }, arg).catch(() => {});
const ringedKey = (page) => page.evaluate(() => document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") || null);
for (const c of CASES) {
  test(`Put it on my list on ${c.row.source} keeps the new task on the table, and Next walks on below it`, { timeout: 180000 }, async (t) => {
    const { page, errors } = await boot(t);
    const before = await rail(page);
    const at = before.findIndex((r) => c.row.test(r.text));
    assert.ok(at >= 0, `the demo rail has ${c.row}: ${JSON.stringify(before.map((r) => r.text))}`);
    const tasks = new Set(await page.$$eval('[data-tq-run="task"] .tq-pile-row', (els) => els.map((e) => e.getAttribute("data-tq-key"))));
    assert.ok(tasks.size >= 3, "the rail's Tasks rows were not found");
    const key = before[at].key;
    await clickRow(page, key);
    await until(page, (k) => document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") === k, key);
    let pressed = null;                                   // ...its row's words come with its card, a beat after the ring
    for (let i = 0; i < 20 && !(pressed = await doVerb(page, "w:mine")); i++) await sleep(500);
    assert.ok(pressed, "the row has no Put it on my list");
    // ...the new task on the table, at the report's place: its row is the one ringed, now a task
    await until(page, (k) => /TQ-\d+/.test(document.querySelector(`[data-tq-rail] .tq-pile-row.current[data-tq-key="${k}"]`)?.innerText || ""), key);
    const kept = (await rail(page)).find((x) => x.cur);
    assert.equal(kept?.key, key, `the table did not keep the new task: ${JSON.stringify(kept)}`);
    assert.match(kept.text, /TQ-\d+/, "the row on the table is not the new task");
    let next = false;                                     // ...and its Next, once the new task's row is drawn
    for (let i = 0; i < 20 && !(next = await pressNext(page)); i++) await sleep(500);
    assert.ok(next, "no Next on the new task");
    await until(page, (k) => (document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") || k) !== k, key);
    await sleep(1500);
    const now = await ringedKey(page), landed = (await rail(page)).find((x) => x.cur)?.text || "";
    assert.ok(!tasks.has(now), `Next went back up into Tasks: ${landed}`);
    if (c.below) assert.match(landed, c.below, `Next did not go on to the row below: ${landed}`);
    const card = (await folded(page)).find((f) => c.row.test(f.title));
    assert.ok(card?.badge, `the card Next left wears no badge: ${JSON.stringify(await folded(page))}`);
    assert.deepEqual(errors, []);
  });
}
