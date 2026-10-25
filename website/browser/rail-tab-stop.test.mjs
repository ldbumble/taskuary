import assert from "node:assert/strict";
import test from "node:test";
import { boot, rail, sleep } from "./walkdriver.mjs";

/* THE RAIL'S ONE TAB STOP IS THE ROW ON THE TABLE (owner-approved, 2026-10-20; the 2026-10-25 navigation sweep, N16): after a keyboard pick
   and then a mouse Next the stop stayed on the row the keyboard last reached, so Tab back in and Enter put the row the walk had left back on
   the table. */
test("after a keyboard pick and a mouse Next, the tab stop is the row Next put up", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t);
  const keys = (await rail(page)).map((r) => r.key), on = async () => (await rail(page)).find((r) => r.cur)?.key;
  const stop = () => page.$eval('[data-tq-rail] .card[tabindex="0"]', (e) => e.closest("[data-tq-key]").dataset.tqKey);
  await page.focus('[data-tq-rail] .card[tabindex="0"]');
  await page.keyboard.press("ArrowDown"); await page.keyboard.press("Enter"); await sleep(3500);
  assert.equal(await on(), keys[1], "Enter did not open the second row");
  const next = await page.$("[data-tq-row] [data-tq-next]");
  await next.click(); await sleep(3500);                     // a real mouse press: focus leaves the rail for the button
  assert.equal(await on(), keys[2], "Next did not bring the third row");
  assert.equal(await stop(), keys[2], "the tab stop stayed on the row the walk left");
  await page.focus('[data-tq-rail] .card[tabindex="0"]'); await page.keyboard.press("Enter"); await sleep(3000);
  assert.equal(await on(), keys[2], "Tab back in and Enter put the row the walk had left back on the table");
  assert.deepEqual(errors, []);
});
