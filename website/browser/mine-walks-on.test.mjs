import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, doVerb, findRow, folded, rail, sleep } from "./walkdriver.mjs";

/* PUT IT ON MY LIST WALKS ON DOWN THE LINE (the 2026-10-26 sweep; rail-order-is-fixed-next-walks-down): on a report or an FYI the new task
   kept the report's key in Tasks, and the walk went on from THERE - the table blank for ~1.7 s, then a task in the middle of Tasks (from
   the FYI, the first task at the top), with the folded card's "Put it on my list" badge wiped on the way. The walk goes on to the row below
   the report or the FYI, never back up, and the card keeps its badge. */
const CASES = [
  { row: /Headcount by site/, below: /AP ageing over 30 days/, badge: "Put it on my list" },
  { row: /Regional operations newsletter/, below: null, badge: "Should be a task" },   // an FYI says it as the correction it is (2026-10-29)
];
for (const c of CASES) {
  test(`Put it on my list on ${c.row.source} walks on below it and keeps its badge`, { timeout: 180000 }, async (t) => {
    const { page, errors } = await boot(t);
    const before = await rail(page);
    const at = before.findIndex((r) => c.row.test(r.text));
    assert.ok(at >= 0, `the demo rail has ${c.row}: ${JSON.stringify(before.map((r) => r.text))}`);
    const tasks = new Set(await page.$$eval('[data-tq-run="task"] .tq-pile-row', (els) => els.map((e) => e.getAttribute("data-tq-key"))));
    assert.ok(tasks.size >= 3, "the rail's Tasks rows were not found");
    await clickRow(page, before[at].key); await sleep(3000);
    assert.ok(await doVerb(page, "w:mine"), "the row has no Put it on my list");
    const seen = [];
    for (let n = 0; n < 14; n++) { await sleep(500); const r = (await rail(page)).find((x) => x.cur); seen.push(r ? { key: r.key, text: r.text } : null); }
    const landed = seen.filter(Boolean).pop()?.text || "";
    const up = seen.filter((s) => s && tasks.has(s.key)).map((s) => s.text);
    assert.deepEqual(up, [], `the walk went back up into Tasks: ${JSON.stringify(seen)}`);
    if (c.below) assert.match(landed, c.below, `the walk did not go on to the row below: ${JSON.stringify(seen)}`);
    const card = (await folded(page)).find((f) => c.row.test(f.title));
    assert.equal(card?.badge, c.badge, `the folded card lost its badge: ${JSON.stringify(await folded(page))}`);
    assert.deepEqual(errors, []);
  });
}
