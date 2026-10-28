import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE CHAT IS A WINDOW (the owner, 2026-10-28, on 0.3.9.58: "why is it showing up in the actual canvas???? i thought we moved this to the side
   chat box like in support on most websites"): with a report on the table - drawn in a task's three sections - "what are my outstanding
   tasks?" and its whole answer were drawn in the canvas under the card, because the answer pop-up only held what was said while a TASK
   VIEW held the table. Now every turn goes into one support-style window at the canvas's bottom right: on a task and on a report, nothing
   new in the canvas, the window stays open, × shuts it, the pill opens it again on the same conversation; on a phone it is a bottom sheet. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rect = (page, sel) => page.$eval(sel, (e) => { const r = e.getBoundingClientRect(); return { l: r.left, r: r.right, t: r.top, b: r.bottom, w: r.width, h: r.height }; });
const Q = "what are my outstanding tasks?";
const inCanvas = (page) => page.$$eval(".tq-chat-body .tq-msg.you, .tq-chat-body .tq-msg.receipt, .tq-chat-body .tq-msg:not(.tq-live-card):not(.tq-welcome-msg) .body > p",
  (els) => els.map((e) => e.textContent.trim()).filter(Boolean));
const ask = async (page, q) => {
  await page.click(".tq-compose-box textarea");
  await page.waitForSelector("[data-tq-chat-win]:not([hidden])", { timeout: 5000 });
  await page.keyboard.type(q);
  await page.keyboard.press("Enter");
  await page.waitForFunction((q) => [...document.querySelectorAll("[data-tq-chat-win] .tq-msg.you")].some((e) => e.textContent.includes(q)), { timeout: 20000 }, q);
  await page.waitForFunction(() => !document.querySelector("[data-tq-chat-win] .tq-pending"), { timeout: 30000 });
  await sleep(400);
};
const openTask = async (page, harness, re) => {
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const t = tasks.find((x) => re.test(x.Title));
  assert.ok(t, `the demo's ${re}`);
  await page.evaluate((id) => { location.hash = `task=${id}`; }, t.TaskId);
  await page.waitForSelector(`[data-tq-task-page="${t.TaskId}"]`, { timeout: 20000 });
  await sleep(2000);
};

test("an answer goes into the chat window on a task and on a report, never into the canvas; × shuts it and the pill brings the same conversation back", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1366, height: 768, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });

  // ON A TASK
  await openTask(page, harness, /^Invoice 88213/);
  const before = await inCanvas(page), view = await rect(page, "[data-tq-canvas-item]");
  await ask(page, Q);
  const win = await rect(page, "[data-tq-chat-win]"), box = await rect(page, ".tq-compose-box"), dock = await rect(page, ".tq-dock"), body = await rect(page, ".tq-chat-body");
  const say = JSON.stringify({ win, box, dock, body });
  assert.deepEqual(await inCanvas(page), before, "nothing new is drawn in the canvas");
  assert.match(await page.$eval("[data-tq-chat-win] .tq-chat-pop-body", (e) => e.textContent), /outstanding tasks[\s\S]*scripted/, "the question and its answer are in the window");
  assert.equal(await page.$eval("[data-tq-chat-win] .tq-chat-pop-head b", (e) => e.textContent), "Taskuary");
  assert.ok(win.w >= 370 && win.w <= 381 && Math.abs(win.r - box.r) <= 1 && Math.abs(win.l - box.l) <= 1, `one ~380px panel, the box its floor ${say}`);
  assert.ok(Math.abs(win.b - box.t) <= 1, `...the conversation flush on the box ${say}`);
  assert.ok(box.b <= dock.t && dock.r - box.r < 40, `...at the bottom right, above the dock - never over the row ${say}`);
  assert.ok(win.t >= body.t && win.h + box.h <= 0.6 * 768 + 2, `...within the canvas, at most ~60% of the screen ${say}`);
  assert.deepEqual(await rect(page, "[data-tq-canvas-item]"), view, "the task view did not move");
  assert.ok(await page.$eval("[data-tq-chat-win] .tq-chat-pop-body", (b) => b.scrollHeight - b.scrollTop - b.clientHeight <= 2), "the newest words in view");
  // ...its own lines right, the answer left with the mark
  const sides = await page.$eval("[data-tq-chat-win] .tq-chat-pop-body", (b) => {
    const you = b.querySelector(".tq-msg.you .body").getBoundingClientRect(), it = [...b.querySelectorAll(".tq-msg:not(.you)")].pop(), r = b.getBoundingClientRect();
    return { youRight: r.right - you.right, itLeft: it.querySelector(".body").getBoundingClientRect().left - r.left, mark: !!it.querySelector(".avatar")?.children.length };
  });
  assert.ok(sides.youRight < 24 && sides.itLeft < 60 && sides.mark, `the owner's bubble right, Taskuary's answer left with its mark ${JSON.stringify(sides)}`);

  // ...it stays open (no auto-close, a click on the canvas leaves it), × shuts it, the pill opens it on the same conversation
  await sleep(3000);
  await page.click("[data-tq-task-head]");
  await sleep(300);
  assert.equal(await page.$eval("[data-tq-chat-win]", (e) => e.hidden), false, "it stays open until × or Esc");
  await page.click("[data-tq-chat-win] [aria-label='Close the chat']");
  await page.waitForSelector("[data-tq-chat-win][hidden]", { timeout: 5000 });
  await page.waitForFunction(() => !document.querySelector(".tq-compose-box[data-tq-open]"), { timeout: 5000 });
  await page.click(".tq-compose-box textarea");
  await page.waitForSelector("[data-tq-chat-win]:not([hidden])", { timeout: 5000 });
  assert.match(await page.$eval("[data-tq-chat-win] .tq-chat-pop-body", (e) => e.textContent), /outstanding tasks[\s\S]*scripted/, "reopened, the same conversation");
  await page.keyboard.press("Escape");
  await page.waitForSelector("[data-tq-chat-win][hidden]", { timeout: 5000 });

  // ON A REPORT (the owner's screenshot: the answer drawn under it, in the canvas)
  const rows = await page.$$("[data-tq-rail] .tq-pile-row");
  const at = await page.$$eval("[data-tq-rail] .tq-pile-row", (r) => r.findIndex((x) => /Headcount by site/.test(x.textContent)));
  assert.ok(at >= 0, "the demo's report on the rail");
  await rows[at].click();
  await page.waitForSelector("[data-tq-item-sections]", { timeout: 20000 });
  await sleep(1500);
  const onReport = await inCanvas(page);
  await ask(page, `${Q} (report)`);
  assert.deepEqual(await inCanvas(page), onReport, "nothing new in the canvas under the report");
  assert.equal(await page.$$eval("[data-tq-chat-win] .tq-msg.you", (els) => els.length), 2, "the window holds both turns");

  // A TASK NAMED IN AN ANSWER OPENS AS ITS RAIL ROW DOES (the owner, 2026-10-28: "it should hit the task and it should open ... like hitting a
  // task on the work rail"): "open TQ-0004" - the Assistant presses that row (a receipt in the window) - and later its name, pressed in the
  // answer, brings it back the same way: the task on the canvas, its rail row the selected one
  const onTable = () => page.evaluate(() => ({ hash: location.hash, sel: document.querySelector("[data-tq-rail] .tq-pile-row .card[aria-selected=true]")?.textContent || "",
    view: document.querySelector("[data-tq-task-page]")?.getAttribute("data-tq-task-page") || "" }));
  await ask(page, "open TQ-0004");
  await page.waitForFunction(() => document.querySelector("[data-tq-task-page]")?.getAttribute("data-tq-task-page") === "4", { timeout: 20000 });
  let at4 = await onTable();
  assert.match(at4.sel, /TQ-0004/, `the Assistant pressed TQ-0004's rail row ${JSON.stringify(at4)}`);
  assert.match(await page.$eval("[data-tq-chat-win] .tq-chat-pop-body", (e) => [...e.querySelectorAll(".tq-msg.receipt")].pop()?.textContent || ""), /Opened TQ-0004/,
    "...and said so in the window");
  const first = await page.$$("[data-tq-rail] .tq-pile-row .card");
  await first[0].click();
  await page.waitForFunction(() => document.querySelector("[data-tq-task-page]")?.getAttribute("data-tq-task-page") !== "4", { timeout: 20000 });
  await sleep(800);
  await page.click("[data-tq-chat-win] .tq-chat-pop-body [data-tq-task-link='4']");
  await page.waitForFunction(() => document.querySelector("[data-tq-task-page]")?.getAttribute("data-tq-task-page") === "4", { timeout: 20000 });
  await sleep(500);
  at4 = await onTable();
  assert.match(at4.sel, /TQ-0004/, `the name pressed in the answer selected its rail row ${JSON.stringify(at4)}`);
  assert.equal(at4.hash, "#task=4");
  assert.deepEqual(errors, []);
});

test("on a phone the chat window is a bottom sheet", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector(".tq-compose-box textarea", { timeout: 30000 });
  await openTask(page, harness, /^Invoice 88213/);
  const before = await inCanvas(page);
  await ask(page, Q);
  const win = await rect(page, "[data-tq-chat-win]"), box = await rect(page, ".tq-compose-box"), say = JSON.stringify({ win, box });
  assert.ok(win.l <= 0.5 && win.r >= 389.5 && box.l <= 0.5 && box.r >= 389.5, `the screen's width ${say}`);
  assert.ok(Math.abs(box.b - 844) <= 1 && Math.abs(win.b - box.t) <= 1, `...the box at the screen's foot, the conversation on it ${say}`);
  assert.deepEqual(await inCanvas(page), before, "nothing new in the canvas");
  await page.click("[data-tq-chat-win] [aria-label='Close the chat']");
  await page.waitForSelector("[data-tq-chat-win][hidden]", { timeout: 5000 });
  assert.deepEqual(errors, []);
});
