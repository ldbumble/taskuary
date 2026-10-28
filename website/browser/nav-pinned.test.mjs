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
  // ...the items' own rows differ, so the test means something: a centred row would have moved Next between them
  assert.ok(new Set(seen.map((s) => s.verbs.join("|"))).size > 1, `three items with different buttons: ${JSON.stringify(seen)}`);
  assert.ok(seen.every((s) => Math.abs(s.x - seen[0].x) <= 1), `Next's x on each of the three: ${JSON.stringify(seen.map((s) => s.x))}`);
  assert.deepEqual(errors, []);
});
