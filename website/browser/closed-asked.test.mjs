import assert from "node:assert/strict";
import test from "node:test";
import { boot, findRow, sleep } from "./walkdriver.mjs";

/* A QUESTION ON A CLOSED TASK BRINGS IT BACK (the owner, 2026-10-25: "new message came in but it did not reopen task?"). A colleague asked
   the owner something on a finished thread; triage read it as a reply to send, and the task stayed done with no row. The fixture ingests
   the question through the real door with triage scripted; the task is back on the rail under Tasks, by its new title. */
test("a question to the owner on a closed task's thread puts the task back on the rail", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t);
  assert.equal(await findRow(page, /what separates the 4100 accounts/), null, "no such row before the question");
  const made = await page.evaluate(async () => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    return (await fetch("/api/fixture/task/closed-asked", { method: "POST", headers, body: "{}" })).json();
  });
  assert.equal(made.status, "open", `the task was not reopened: ${JSON.stringify(made)}`);
  let key = null;
  for (let i = 0; i < 30 && !key; i++) { await sleep(1000); key = await findRow(page, /what separates the 4100 accounts/); }
  assert.ok(key, "the reopened task has no row on the rail");
  const level = await page.evaluate((k) => document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"]`)?.closest("[data-tq-run]")?.getAttribute("data-tq-run"), key);
  assert.equal(level, "task", "it is back under Tasks");
  assert.deepEqual(errors, []);
});
