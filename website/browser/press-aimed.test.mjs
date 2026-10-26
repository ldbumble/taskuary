import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, doVerb, folded, pressNext, rail, sleep } from "./walkdriver.mjs";

/* A PRESS ACTS ON THE ITEM IT WAS AIMED AT (2026-10-25): a double-click on Mark done closed two tasks - the close drew the next task up at
   its press, and the second click landed on that task's own Mark done. And Next pressed on that next task while the close was still on its
   way left it with no "Next" badge after a reload (the owner's walk: the task after one closed with Mark done), and the walk on an empty
   table. One gesture is one press (actionRow.aimed); the close's late answer leaves a walk that went on alone (AssistantView advance). */
const api = (page, path) => page.evaluate(async (p) => (await fetch(p, { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json(), path);
const status = async (page, tid) => (await api(page, `/api/tasks/${tid}`)).task?.Status;
const ringedKey = (page) => page.$eval("[data-tq-rail] .tq-pile-row.current", (e) => e.getAttribute("data-tq-key")).catch(() => null);
const onTable = (page) => page.evaluate(() => [...document.querySelectorAll(".tq-canvas-live [data-tq-canvas-item]")]
  .filter((e) => e.getBoundingClientRect().height > 0 && !e.closest("[data-tq-folded]")).map((e) => e.getAttribute("data-tq-canvas-item")).pop() || null);
// the walk's first three tasks, in the rail's order, and the first one on the table
async function start(t, opts) {
  const { page, errors } = await boot(t, opts);
  const tasks = (await api(page, "/api/funnel/pile")).items.filter((i) => i.tid && i.lane !== "fyi").slice(0, 3);
  await clickRow(page, tasks[0].key);
  await page.waitForFunction((k) => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") === k, { timeout: 20000 }, tasks[0].key);
  await page.waitForFunction(() => document.querySelector("[data-tq-row] [data-tq-next]") && !document.querySelector("[data-tq-row] [data-tq-next]").disabled, { timeout: 20000 });
  await sleep(2500);                                       // the next task's read is held, so a close draws it at the press
  return { page, errors, tasks };
}
// a double-click as a hand makes one: the second click GAP ms after the first, where the first was - on whatever is drawn there by then.
// Slower than the row's wait for the next item's first decision (HOLD_MS, 400: the row is hidden till then) and inside the double-click
// time Windows gives by default (500), so the browser counts it as the second click of one
const GAP = +(process.env.TASKUARY_DOUBLE_GAP || 450);
// ...and the close answered as the demo answers it, quickly: the next task's row is live under the second click (TASKUARY_SLOW_CLOSE
// holds the answer back, as a close over a live agent does)
const SLOW = +(process.env.TASKUARY_SLOW_CLOSE || 0);
async function dblAt(page, el) {
  const b = await el.boundingBox(), x = b.x + b.width / 2, y = b.y + b.height / 2;
  await page.mouse.click(x, y); await sleep(GAP);
  await page.mouse.down({ clickCount: 2 }); await page.mouse.up({ clickCount: 2 });
}
const dbl = async (page, sel) => dblAt(page, await page.waitForSelector(sel, { visible: true, timeout: 10000 }));
// exactly the first task acted on, the second on the table and open, its rail row ringed
async function oneActed(page, tasks, acted) {
  await sleep(5000);
  assert.equal(await ringedKey(page), tasks[1].key, "the rail does not ring the next task");
  assert.equal(await onTable(page), tasks[1].key, "the next task is not the view on the table");
  assert.ok(acted(await status(page, tasks[0].tid)), `the pressed task was not acted on: ${await status(page, tasks[0].tid)}`);
  assert.equal(await status(page, tasks[1].tid), "open", "the second click acted on the next task");
  assert.ok(!(await folded(page)).some((f) => f.badge && tasks[1].title.startsWith(f.title.slice(0, 20))), "the next task wears a press");
}

test("a double-click on Mark done closes one task and leaves the next open on the table", { timeout: 180000 }, async (t) => {
  // ...on a screen wide enough for Mark done to stand on the row: at 1440 the one-row chat bar's box (2026-10-26) takes the room CLOSE stood
  // in, and it folds into the ▾ - a menu item, not the button a hand double-clicks
  const { page, errors, tasks } = await start(t, { slow: SLOW, width: 1920 });
  await dbl(page, '[data-tq-row] button[data-tq-verb="done"]');
  await oneActed(page, tasks, (s) => s === "done");
  assert.deepEqual(errors, []);
});

test("a double-click on Next walks past one task, not two", { timeout: 180000 }, async (t) => {
  const { page, errors, tasks } = await start(t, { slow: SLOW });
  await dbl(page, "[data-tq-row] [data-tq-next]");
  await oneActed(page, tasks, (s) => s === "open");
  assert.ok((await folded(page)).some((f) => f.badge === "Next" && tasks[0].title.startsWith(f.title.slice(0, 20))), "the task walked past wears no Next");
  assert.deepEqual(errors, []);
});

test("a double-click on Remind me's day puts one task away", { timeout: 180000 }, async (t) => {
  const { page, errors, tasks } = await start(t, { slow: SLOW });
  assert.ok(await doVerb(page, "remind")); await sleep(700);
  const day = await page.waitForFunction(() => [...document.querySelectorAll(".MuiPopover-paper button")].find((n) => /^Tomorrow/.test(n.textContent.trim())), { timeout: 10000 });
  await dblAt(page, day.asElement());
  await oneActed(page, tasks, (s) => s === "open");
  const away = await api(page, `/api/tasks/${tasks[0].tid}`), next = await api(page, `/api/tasks/${tasks[1].tid}`);
  assert.ok(away.task?.RemindAt, "the pressed task was not put away");
  assert.ok(!next.task?.RemindAt, "the second click put the next task away too");
  assert.deepEqual(errors, []);
});

test("a double-click on Close with a note closes one task", { timeout: 180000 }, async (t) => {
  const { page, errors, tasks } = await start(t, { slow: SLOW });
  assert.ok(await doVerb(page, "close-note")); await sleep(800);
  await page.keyboard.type("Handled by Paula Vance on the phone");
  const b = await page.evaluateHandle(() => [...document.querySelectorAll("[data-tq-close-note-card] button")].find((n) => n.textContent.trim() === "Close with a note"));
  await dblAt(page, b.asElement());
  await oneActed(page, tasks, (s) => s === "done");
  assert.deepEqual(errors, []);
});

test("Next on the task a slow Mark done drew up walks on, and the task keeps its Next badge through a reload", { timeout: 180000 }, async (t) => {
  const { page, errors, tasks } = await start(t, { slow: 2500 });
  assert.ok(await doVerb(page, "done"));
  await page.waitForFunction((k) => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") === k, { timeout: 5000 }, tasks[1].key);
  await sleep(600);                                        // past one press, and long before the close answers
  assert.equal(await onTable(page), tasks[1].key, "the close's receipt took the next task off the table before its answer");
  assert.ok(await pressNext(page), "no Next on the task the close drew up");
  await page.waitForFunction((k) => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") === k, { timeout: 15000 }, tasks[2].key)
    .catch(async () => assert.fail(`Next went to ${await ringedKey(page)}, not the third task`));
  await sleep(4000);                                       // the close has answered by now: the walk stays where Next took it
  assert.equal(await ringedKey(page), tasks[2].key, "the close's late answer moved the walk");
  assert.equal(await onTable(page), tasks[2].key);
  const worn = async () => Object.fromEntries((await folded(page)).filter((f) => f.badge).map((f) => [f.title.slice(0, 20), f.badge]));
  const before = await worn();
  assert.equal(before[tasks[0].title.slice(0, 20)], "Mark done");
  assert.equal(before[tasks[1].title.slice(0, 20)], "Next");
  await page.reload({ waitUntil: "domcontentloaded" }); await page.waitForSelector("[data-tq-folded]", { timeout: 30000 }); await sleep(4000);
  assert.deepEqual(await worn(), before, "a badge was lost on reload");
  assert.equal(await status(page, tasks[0].tid), "done");
  assert.equal(await status(page, tasks[1].tid), "open");
  assert.deepEqual(errors, []);
});
