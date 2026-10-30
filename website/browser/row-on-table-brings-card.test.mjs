import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, rail, sleep } from "./walkdriver.mjs";

/* A CLICK ON THE ROW ALREADY ON THE TABLE BRINGS ITS TASK BACK (TQ-1251): after an update's relaunch the rail ringed a task while the
   canvas showed the morning greeting with no card of it, and a click on its row did nothing at all ("I should be able to click on the
   task itself"). The row on the table was treated as already in view. */
const cards = (page) => page.$$eval(".tq-canvas-live, .tq-live-card", (els) => els.map((e) => e.innerText.replace(/\s+/g, " ").slice(0, 60)));
test("a click on the ringed row whose card is gone opens the task again", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t);
  const row = (await rail(page))[0];
  assert.ok(await clickRow(page, row.key)); await sleep(3500);
  assert.equal((await rail(page)).find((r) => r.cur)?.key, row.key, "the first row did not go on the table");
  const ref = (await cards(page)).pop()?.match(/TQ-\d+/)?.[0];
  assert.ok(ref, "no card for the row on the table");
  // the canvas as it stood: the row ringed, no card of it in the chat
  await page.$$eval(".tq-canvas-live, .tq-live-card", (els) => els.forEach((e) => e.classList.remove("tq-canvas-live", "tq-live-card")));
  assert.deepEqual(await cards(page), []);
  assert.ok(await clickRow(page, row.key)); await sleep(3500);
  assert.ok((await cards(page)).some((c) => c.includes(ref)), "a click on the row on the table did not bring its task up");
  assert.equal((await rail(page)).find((r) => r.cur)?.key, row.key, "the click moved the table off the row");
  assert.deepEqual(errors, []);
});
