import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, doVerb, findRow, pressNext, ringed, sleep, type } from "./walkdriver.mjs";

/* A CLOSED TASK OPENED BY NAME WALKS ON FROM ITS ROW (the 2026-10-25 navigation sweep, N10): Mark done on the first task, then "open TQ-0001",
   then Next - the page draws the closed task under Tasks, where it was, but the walk's place was keyed by its lane (fyi), so Next skipped
   every task and report below it and brought up the fyi batch. */
test("Next from a closed task opened by its ref goes to the task below it, not the fyi batch", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t);
  await clickRow(page, await findRow(page, /Month-end close/)); await sleep(3000);
  assert.ok(await doVerb(page, "done")); await sleep(5000);
  await type(page, "open TQ-0001"); await sleep(7000);
  assert.match(await ringed(page), /Month-end close/, "the closed task did not come back on the table");
  assert.ok(await pressNext(page)); await sleep(5000);
  const at = await ringed(page), last = await page.evaluate(() => [...document.querySelectorAll(".tq-msg")].at(-1)?.innerText.replace(/\s+/g, " ") || "");
  assert.ok(!/NOTHING TO DECIDE/i.test(last), `Next jumped to the fyi batch: ${last.slice(0, 80)}`);
  assert.match(at, /New starter on Monday/, `Next from TQ-0001 landed on ${at}`);
  assert.deepEqual(errors, []);
});
