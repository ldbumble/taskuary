import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE ANSWER STANDS UNDER THE VIEW IT TALKS ABOUT (the overnight walk, 2026-10-26). The invoice's view ends ~170 px above the dock, and the
   pop-up still rose to 45% of the canvas: "reply saying Thursday works" was answered over the right half of the draft it was about. With
   room under the view the pop-up fits in it; the newest words are the ones in view. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rect = (page, sel) => page.$eval(sel, (e) => { const r = e.getBoundingClientRect(); return { top: Math.round(r.top), bottom: Math.round(r.bottom) }; });

test("the chat pop-up fits in the room under a short task view", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const inv = tasks.find((x) => /^Invoice 88213/.test(x.Title));
  await page.evaluate((id) => { location.hash = `task=${id}`; }, inv.TaskId);
  await page.waitForSelector(`[data-tq-task-page="${inv.TaskId}"]`, { timeout: 20000 });
  await page.waitForSelector(".tq-dock [data-tq-row] [data-tq-next]", { timeout: 20000 });
  await sleep(2500);

  for (const line of ["what is this about?", "reply saying Thursday works"]) {
    await page.click(".tq-compose-box textarea");
    await page.keyboard.type(line);
    await page.keyboard.press("Enter");
    await page.waitForSelector("[data-tq-chat-pop]:not([hidden])", { timeout: 20000 });
    await page.waitForFunction(() => !document.querySelector("[data-tq-chat-pop] .tq-pending"), { timeout: 30000 });
    await sleep(400);
    const view = await rect(page, "[data-tq-canvas-item]"), pop = await rect(page, "[data-tq-chat-pop]");
    const say = JSON.stringify({ line, view, pop });
    assert.ok(pop.top >= view.bottom, `the pop-up stands under the view, not over it ${say}`);
    assert.ok(pop.bottom - pop.top >= 140, `...and is still tall enough to read ${say}`);
    // the newest answer is the one in view: the pop-up's body is scrolled to its end
    assert.ok(await page.$eval("[data-tq-chat-pop] .tq-chat-pop-body", (b) => b.scrollHeight - b.scrollTop - b.clientHeight <= 2), `the newest words in view ${say}`);
    await page.keyboard.press("Escape");
  }
  assert.deepEqual(errors, []);
});
