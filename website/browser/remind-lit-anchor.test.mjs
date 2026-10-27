import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE LIT REMIND ME OPENS ITS PICKER BY THE ROW (the overnight walk, 2026-10-26). "remind me Monday" lights the row's Remind me - a move from
   the folded ▾, drawn on the row only while it is lit. Pressing it clears the light, the button folds back into its ▾, and the picker it had
   just opened lost its anchor: MUI drew it at the screen's top-left corner, over the rail, with "The anchor element should be part of the
   document layout" in the console. It opens where the button stood. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("a typed remind lights Remind me, one press opens its picker, by the row", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error" && /anchor/i.test(m.text())) errors.push(m.text().slice(0, 200)); });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const inv = tasks.find((x) => /^Invoice 88213/.test(x.Title));
  await page.evaluate((id) => { location.hash = `task=${id}`; }, inv.TaskId);
  await page.waitForSelector(`[data-tq-task-page="${inv.TaskId}"]`, { timeout: 20000 });
  await page.waitForSelector(".tq-dock [data-tq-row] [data-tq-next]", { timeout: 20000 });
  await sleep(2000);

  await page.click(".tq-compose-box textarea");
  await page.keyboard.type("remind me Monday");
  await page.keyboard.press("Enter");
  const lit = '.tq-arow-verbs button.tq-ab.p[data-tq-verb$="remind"]';
  await page.waitForSelector(lit, { visible: true, timeout: 20000 });
  const btn = await page.$eval(lit, (b) => { const r = b.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width }; });
  assert.ok(await page.$(".tq-compose-box[data-tq-open]"), "the box is still wide when the button lights - the case that slid it");
  // a real press, down then up where the button was drawn while the box was wide: the press is what takes the focus from the box
  await page.mouse.click(btn.x + btn.w / 2, btn.y + 12, { delay: 120 });
  await page.waitForFunction(() => [...document.querySelectorAll(".MuiPopover-paper")].some((p) => p.innerText.includes("Bring it back on")), { timeout: 10000 });
  await sleep(400);
  const paper = await page.evaluate(() => { const p = [...document.querySelectorAll(".MuiPopover-paper")].find((x) => x.innerText.includes("Bring it back on")).getBoundingClientRect();
    return { x: p.left, y: p.top, h: p.height }; });
  const say = JSON.stringify({ btn, paper });
  assert.ok(Math.abs(paper.x - btn.x) < 120, `the picker opens over the button's column, not at the screen's edge ${say}`);
  assert.ok(paper.y + paper.h > 810 * 0.5, `...and down by the row it was pressed on ${say}`);
  assert.deepEqual(errors, []);
});
