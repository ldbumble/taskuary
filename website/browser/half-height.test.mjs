import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* HALF, THEN WHOLE (the owner, 2026-10-30: "it should be half size when full and make full size when half"): on a desk a task on the canvas
   takes the canvas; its arrow beside the X halves it with its top where it was, and the same arrow makes it whole again. Demo world only. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("the task's arrow halves it, top kept, and makes it whole again", { timeout: 200000 }, async (t) => {
  const hz = await startHarness();
  t.after(() => hz.close());
  const page = await hz.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  await page.goto(hz.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const tasks = (await (await fetch(`${hz.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": hz.token } })).json()).data;
  const id = tasks.find((x) => /^Invoice 88213/.test(x.Title))?.TaskId;
  const CUR = `[data-tq-canvas-item]:has([data-tq-task-page="${id}"])`;
  await page.evaluate((id) => { location.hash = `task=${id}`; }, id);
  await page.waitForSelector(`${CUR} [data-tq-task-body][data-tq-sections]`, { timeout: 20000 });
  await sleep(1500);
  const box = () => page.evaluate((CUR) => { const r = document.querySelector(CUR).getBoundingClientRect(); return { top: Math.round(r.top), h: Math.round(r.height) }; }, CUR);
  const full = await box();
  await page.click(`${CUR} [data-tq-expand]`); await sleep(600);
  const half = await box();
  assert.ok(Math.abs(half.h - full.h / 2) < 40, `half the height ${JSON.stringify({ full, half })}`);
  assert.ok(Math.abs(half.top - full.top) <= 2, `its top where it was ${JSON.stringify({ full, half })}`);
  await page.click(`${CUR} [data-tq-expand]`); await sleep(600);
  assert.deepEqual(await box(), full, "whole again");
  assert.deepEqual(errors, []);
});
