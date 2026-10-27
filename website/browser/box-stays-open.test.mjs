import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* ONCE OPEN, THE CHAT BOX STAYS OPEN (the owner, 2026-10-27: "it gets smaller and bigger at random times when you are in there ... when you
   click in, it stays open until you do X or something"; "it should not hover over the buttons but over the canvas"; "typing is above where
   attachments, emojis and voice note is - looks weird"). Opened: over the canvas, above the dock - never over the row; one row - the tools,
   the words and send on one line; open through a click elsewhere, a look away and an answer; shut by its × or Esc. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("the chat box stays open over the canvas until its × or Esc, in one row, never over the buttons", { timeout: 300000 }, async (t) => {
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
  await page.waitForSelector(".tq-dock [data-tq-row] [data-tq-next]", { timeout: 20000 });
  await sleep(2000);
  const open = () => page.$(".tq-compose-box[data-tq-open]").then(Boolean);
  const shape = () => page.evaluate(() => {
    const box = document.querySelector(".tq-compose-box"), dock = document.querySelector(".tq-dock"), r = box.getBoundingClientRect();
    const mid = (e) => { const q = e.getBoundingClientRect(); return q.top + q.height / 2; };
    const ta = box.querySelector("textarea"), tools = [...box.querySelectorAll(".tq-compose-tools button")].filter((b) => b.offsetParent);
    return { clear: Math.round(dock.getBoundingClientRect().top - r.bottom), oneRow: tools.every((b) => Math.abs(mid(b) - mid(ta)) <= 12),
      toolsLeft: tools.every((b) => b.getBoundingClientRect().right <= ta.getBoundingClientRect().left + 1), tools: tools.length };
  });

  await page.click(".tq-compose-box textarea");
  await page.waitForSelector(".tq-compose-box[data-tq-open]", { timeout: 5000 });
  await sleep(300);
  const s = await shape();
  assert.ok(s.clear >= 0, `the open box stands above the dock, never over the buttons ${JSON.stringify(s)}`);
  assert.ok(s.tools >= 2 && s.oneRow && s.toolsLeft, `one row: the tools on the left of the words, on their line ${JSON.stringify(s)}`);

  // a click on the canvas, a look away: still open
  await page.mouse.click(400, 300); await sleep(600);
  assert.ok(await open(), "a click elsewhere leaves it open");
  await page.evaluate(() => document.activeElement?.blur()); await sleep(600);
  assert.ok(await open(), "a look away leaves it open");

  // a line sent and answered: still open, the same size
  const before = await page.$eval(".tq-compose-box", (e) => Math.round(e.getBoundingClientRect().width));
  await page.click(".tq-compose-box textarea");
  await page.keyboard.type("what does Tom want from us?");
  await page.keyboard.press("Enter");
  await page.waitForSelector("[data-tq-chat-pop]:not([hidden])", { timeout: 20000 });
  await page.waitForFunction(() => !document.querySelector("[data-tq-chat-pop] .tq-pending"), { timeout: 30000 });
  await sleep(500);
  assert.ok(await open(), "an answer coming up leaves it open");
  assert.equal(await page.$eval(".tq-compose-box", (e) => Math.round(e.getBoundingClientRect().width)), before, "...at the same size");

  // its ×: shut
  await page.click("[data-tq-box-close]"); await sleep(400);
  assert.equal(await open(), false, "the × shuts it");
  // Esc too
  await page.click(".tq-compose-box textarea"); await page.waitForSelector(".tq-compose-box[data-tq-open]", { timeout: 5000 });
  // ...the first Esc shuts an answer that is up, the next the box
  const popUp = !!(await page.$("[data-tq-chat-pop]:not([hidden])"));
  await page.keyboard.press("Escape"); await sleep(200);
  if (popUp) { await page.keyboard.press("Escape"); await sleep(200); }
  assert.equal(await open(), false, "Esc shuts it");
  assert.deepEqual(errors, []);
});
