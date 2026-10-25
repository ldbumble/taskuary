import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, pressNext, rail, sleep } from "./walkdriver.mjs";

/* TWO ROWS FILED IN THE SAME SECOND HAVE ONE ORDER (2026-10-25): the demo's two dashboards are filed by one run in one second, and the
   server broke that tie by a hashed key while the page put a row back by its arrival alone - they swapped, drawn over each other, as the
   rail moved (the dead-end walk's SWAP). The demo filed one a minute later to hide it; now the tie goes to the first filed, on the server
   and the page alike (funnel.place_id, funnelPile.placeId). Here: the rail the page draws is the server's order, a reload keeps it, and
   Next walks the tie down. */
const pile = (page) => page.evaluate(async () => (await (await fetch("/api/funnel/pile", { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json()).items
  .map((i) => ({ key: i.key, at: String(i.arrived_at || i.sort_at || i.since || i.when || "").slice(0, 19), tid: i.tid || null, title: i.title })));
// the rail draws a capped band's first rows and folds fyi into batches: what it draws must be the server's order, gaps and all
const drawn = async (page, keys) => (await rail(page)).map((r) => r.key).filter((k) => keys.includes(k));
const sameOrder = async (page, keys, why) => { const d = await drawn(page, keys); assert.deepEqual(d, keys.filter((k) => d.includes(k)), why); return d; };
const ringedKey = (page) => page.$eval("[data-tq-rail] .tq-pile-row.current", (e) => e.getAttribute("data-tq-key")).catch(() => null);

test("a same-second tie is drawn in the server's order, keeps it through a reload, and Next walks it down", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 2400 });   // tall enough that the capped Reports band draws them all
  const rows = await pile(page), keys = rows.map((r) => r.key);
  const shown = await sameOrder(page, keys, "the page draws the rail in another order than the server's");
  const twin = rows.findIndex((r, n) => n > 0 && r.at && r.at === rows[n - 1].at && !r.tid && !rows[n - 1].tid && shown.includes(r.key) && shown.includes(rows[n - 1].key));
  assert.ok(twin > 0, `the demo draws no two rows without a task filed in one second (its two dashboards): ${JSON.stringify(rows.map((r) => [r.at, r.title]))}`);
  const [first, second] = [rows[twin - 1], rows[twin]];
  t.diagnostic(`the tie: ${first.title} / ${second.title} at ${first.at}`);
  await page.reload({ waitUntil: "domcontentloaded" }); await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 40000 }); await sleep(2500);
  assert.deepEqual((await pile(page)).map((r) => r.key), keys, "the server's order changed across a reload");
  assert.deepEqual(await sameOrder(page, keys, "the page's order is not the server's after a reload"), shown, "the page's order changed across a reload");
  await clickRow(page, first.key);
  await page.waitForFunction((k) => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") === k, { timeout: 20000 }, first.key);
  await page.waitForFunction(() => !document.querySelector("[data-tq-row] [data-tq-next]")?.disabled, { timeout: 20000 });
  await sleep(1200);
  assert.ok(await pressNext(page), "no Next to press");
  await page.waitForFunction((k) => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") === k, { timeout: 20000 }, second.key)
    .catch(async () => assert.fail(`Next from ${first.title} went to ${await ringedKey(page)}, not its twin ${second.title}`));
  assert.deepEqual(errors, []);
});
