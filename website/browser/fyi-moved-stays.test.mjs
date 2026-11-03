import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickText, pressNext, sleep } from "./walkdriver.mjs";

/* SHOULD BE A TASK KEEPS THE FYI WHERE IT WAS (the owner, 2026-11-03: "i think we should keep it there but say was moved to task"). On a line
   of an FYI batch the press makes it a task under Tasks, and the line stays - in the FYI band and in the batch card - saying "Moved to Tasks
   · TQ-n". All read, next reads the rest and the moved row goes with the batch, never read twice: the task stays under Tasks, the walk still
   ends, and the line is never offered again. Its ref opens the task. Demo world at 1440, invented people only. */
const rows = (page) => page.$$eval("[data-tq-run] .tq-pile-row", (els) => els.map((e) => ({ run: e.closest("[data-tq-run]")?.dataset.tqRun, key: e.dataset.tqKey,
  cur: e.classList.contains("current"), moved: e.querySelector("[data-tq-moved]")?.dataset.tqMoved || "", text: e.innerText.replace(/\s+/g, " ") })));
const row = (page) => page.evaluate(() => document.querySelector("[data-tq-row]")?.innerText.replace(/\s+/g, " ") || "");
const until = (page, f, arg, timeout = 20000) => page.waitForFunction(f, { timeout, polling: 100 }, arg).catch(() => {});

async function pressOnBatch(t) {
  const { page, errors } = await boot(t, { width: 1440, height: 900 });
  await page.click('[data-tq-section-head="reports"] .fold'); await sleep(1500);
  await page.evaluate(() => [...document.querySelectorAll('[data-tq-run="reports"] .tq-pile-row[data-tq-key] .card')].at(-1).click()); await sleep(3500);
  assert.ok(await pressNext(page)); await sleep(3500);
  assert.match(await row(page), /All read, next/, "the first fyi batch is on the table");
  const key = await page.evaluate(() => { const m = document.querySelector("[data-tq-fyi-msg]"); m?.querySelector("button")?.click(); return m?.dataset.tqFyiMsg; });
  await sleep(1200);
  assert.equal(await clickText(page, /^Should be a task$/, "[data-tq-item-sections]"), "Should be a task");
  await until(page, (k) => !!document.querySelector(`[data-tq-run="fyi"] .tq-pile-row[data-tq-key="${k}"] [data-tq-moved]`)
    && !!document.querySelector(`[data-tq-run="task"] .tq-pile-row[data-tq-key="${k}"]`), key);
  return { page, errors, key };
}

test("Should be a task on a batch line keeps it in FYI, says where it went, and All read lets it go with the batch", { timeout: 240000 }, async (t) => {
  const { page, errors, key } = await pressOnBatch(t);
  const after = await rows(page), fyi = after.find((r) => r.run === "fyi" && r.key === key), task = after.find((r) => r.run === "task" && r.key === key);
  assert.match(fyi?.moved || "", /^TQ-\d+$/, `the FYI row stays, saying where it went: ${JSON.stringify(fyi)}`);
  assert.match(fyi.text, /Moved to Tasks · TQ-\d+/);
  assert.ok(task && !task.moved, "the new task is under Tasks as usual");
  const card = await page.evaluate((k) => document.querySelector(`[data-tq-fyi-msg="${k}"] [data-tq-moved]`)?.innerText || "", key);
  assert.equal(card, `Moved to Tasks · ${fyi.moved}`, "the batch card's line says it too");
  assert.match(await row(page), /All read, next/, "the batch is still on the table");
  // ...All read, next: the batch goes, the moved row with it, the task stays
  assert.ok(await pressNext(page)); await sleep(3000);
  const read = await rows(page);
  assert.ok(!read.some((r) => r.run === "fyi" && r.key === key), "the moved row left FYI with its batch");
  assert.ok(read.some((r) => r.run === "task" && r.key === key), "the task it became stays under Tasks - not read with the batch");
  // ...and the walk still ends, the moved row never offered again as FYI
  for (let b = 0; b < 8 && /All read, next/.test(await row(page)); b++) {
    assert.ok(!(await rows(page)).some((r) => r.run === "fyi" && r.key === key), "never offered again");
    assert.ok(await pressNext(page)); await sleep(2500);
  }
  assert.match(await row(page), /Walk me through my tasks/, "the end of the walk offers to walk again");
  assert.ok((await rows(page)).some((r) => r.run === "task" && r.key === key), "the task is still under Tasks at the walk's end");
  assert.deepEqual(errors, []);
});

test("the moved line's ref opens the task", { timeout: 240000 }, async (t) => {
  const { page, errors, key } = await pressOnBatch(t);
  const ref = await page.evaluate((k) => { const b = document.querySelector(`[data-tq-fyi-msg="${k}"] [data-tq-moved] button`); b?.click(); return b?.innerText; }, key);
  assert.match(ref || "", /^TQ-\d+$/);
  await until(page, (r) => (document.querySelector("[data-tq-task-page]")?.innerText || "").includes(r), ref);
  assert.ok((await page.evaluate(() => document.querySelector("[data-tq-task-page]")?.innerText || "")).includes(ref), `the task ${ref} is on the table`);
  assert.deepEqual(errors, []);
});
