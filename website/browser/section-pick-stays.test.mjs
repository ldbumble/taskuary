import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, findRow, sleep } from "./walkdriver.mjs";

/* A SECTION OPENED BY HAND OPENS IN THE VIEW IT IS IN (the overnight walk, 2026-10-27): on a draft waiting for Send, Agent work clicked
   open made the page's stage "to start" - the view flipped to the task, both drawers shut, and neither the agent the owner asked for nor
   the draft was on screen. The stage is where the task is up to; a pick only opens its section. */
const state = (page) => page.evaluate(() => {
  const b = document.querySelector("[data-tq-canvas-item] [data-tq-task-body]");
  const box = [...document.querySelectorAll("[data-tq-canvas-item] textarea")].find((x) => /What should it do/.test(x.placeholder || ""));
  const co = document.querySelector("[data-tq-canvas-item] [data-tq-closeout]");
  return { main: b?.getAttribute("data-tq-main"), stage: b?.getAttribute("data-tq-stage"), agent: !!box && box.getBoundingClientRect().width > 0,
    closeout: !!co && co.getBoundingClientRect().width > 0 };
});

test("Agent work opened over a draft waiting for Send: the work view stays, the agent opens and Close out folds under it", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1600, height: 810 });
  await clickRow(page, await findRow(page, /Invoice 88213/));
  await page.waitForSelector("[data-tq-canvas-item] [data-tq-closeout] textarea", { timeout: 20000 }); await sleep(1500);
  assert.deepEqual(await state(page), { main: "work", stage: "close_out", agent: false, closeout: true });
  assert.ok(await page.evaluate(() => {
    const h = [...document.querySelectorAll("[data-tq-canvas-item] button, [data-tq-canvas-item] [role=button]")].find((b) => /^Agent work/.test(b.textContent.trim()));
    h?.click(); return !!h;
  }), "no Agent work heading to open");
  await sleep(1200);
  assert.deepEqual(await state(page), { main: "work", stage: "close_out", agent: true, closeout: true }, "the pick flipped the view");
  assert.deepEqual(errors, []);
});
