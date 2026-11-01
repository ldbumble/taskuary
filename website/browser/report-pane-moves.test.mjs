import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, doVerb, findRow, sleep } from "./walkdriver.mjs";

/* A REPORT'S MOVES RIDE ITS PANE (the owner, 2026-10-31, a report on the table: "i thought we moved all buttons to the agent canvas?? report
   should be white with buttons on it??"): as a task's left the bar for its panes, the open Report wears the task's white strip with Put it on my
   list, Send to agent, Pause this report and Share on it; folded, the same four stand on its spine; the bar is Back and Next. A dashboard and an
   FYI the same, on the pane each is about. A phone keeps its row. On the demo world, invented people only. */
const seen = (page, sel) => page.$$eval(sel, (bs) => bs.filter((b) => b.offsetParent && b.getBoundingClientRect().width > 0)
  .map((b) => b.textContent.trim() || b.getAttribute("aria-label")));
const bar = (page) => seen(page, "[data-tq-row] button");
const MOVES = ["Put it on my list", "Send to agent", "Pause this report", "Share"];
const tab = (page, k) => page.evaluate((k) => document.querySelector(`[data-tq-item-sections] [data-tq-section-tab="${k}"]`)?.click(), k);
const openReports = (page) => page.evaluate(() => document.querySelector('[data-tq-section-head="reports"] .fold')?.click());

for (const [w, h] of [[1366, 768], [1920, 1080]]) test(`at ${w}x${h} a report's moves are on its white strip and its spine, none on the bar`, { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: w, height: h });
  assert.ok(await clickRow(page, await findRow(page, /Headcount by site/)));
  await page.waitForSelector('[data-tq-item-sections="report"] [data-tq-pane-strip="report"] [data-tq-pane-moves] button', { timeout: 20000 }); await sleep(1200);
  const strip = await page.evaluate(() => { const s = document.querySelector('[data-tq-item-sections] [data-tq-pane-strip="report"]'), r = s.getBoundingClientRect();
    const bs = [...s.querySelectorAll("[data-tq-pane-moves] button")];
    return { bg: getComputedStyle(s).backgroundColor, name: s.querySelector("p")?.textContent.trim(), tops: [...new Set(bs.map((b) => Math.round(b.getBoundingClientRect().top)))],
      inside: bs.every((b) => b.getBoundingClientRect().right <= r.right + 0.5), head: !!document.querySelector('[data-tq-slot="report"] [data-tq-section-head]') }; });
  assert.equal(strip.bg, "rgb(255, 255, 255)", "the open pane's strip is white, as a task's");
  assert.equal(strip.name, "Report");
  assert.ok(!strip.head, "the strip says its name: no second heading under it");
  assert.deepEqual(await seen(page, '[data-tq-pane-strip="report"] [data-tq-pane-moves] button'), MOVES, "the four moves, in the bar's old order");
  assert.equal(strip.tops.length, 1, `one line: ${strip.tops}`);
  assert.ok(strip.inside, "nothing runs past the strip");
  assert.deepEqual(await bar(page), ["Back", "Next"], "the bar is Back and Next");
  // ...Pause this report and Share the quiet pair after the moves, as the Change pill set them apart
  assert.deepEqual(await page.$$eval('[data-tq-pane-strip="report"] [data-tq-pane-moves] button', (bs) => bs.map((b) => b.classList.contains("task"))), [false, false, true, true]);

  // folded, on its spine
  await tab(page, "from"); await sleep(800);
  assert.deepEqual(await seen(page, '[data-tq-section-tab="report"] [data-tq-spine-moves] button'), MOVES, "folded, the same four on its spine");
  assert.deepEqual(await bar(page), ["Back", "Next"]);
  // ...and the strip's fold arrow opens the report again
  await page.click('[data-tq-pane-strip="from"] [data-tq-strip-fold]'); await sleep(800);
  assert.equal(await page.$eval("[data-tq-item-sections] [data-tq-sections]", (e) => e.dataset.tqMain), "report");

  // a press from the strip does what the bar's did: the demo pauses no report and says so, and the moves stay
  assert.equal(await doVerb(page, "w:report_off"), "pane");
  await page.waitForFunction(() => /switched off/.test(document.body.innerText), { timeout: 20000 }); await sleep(1200);
  assert.deepEqual(await seen(page, '[data-tq-pane-strip="report"] [data-tq-pane-moves] button'), MOVES, "the refusal leaves the strip whole");
  assert.deepEqual(errors, []);
});

test("a dashboard and an FYI lay their moves on the pane each is about; Close out says where", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 900 });
  await openReports(page); await sleep(1200);
  assert.ok(await clickRow(page, await findRow(page, /Northwind desk/)));
  await page.waitForSelector('[data-tq-item-sections="dashboard"] [data-tq-pane-strip="report"] [data-tq-pane-moves] button', { timeout: 20000 }); await sleep(1200);
  assert.deepEqual(await seen(page, '[data-tq-pane-strip="report"] [data-tq-pane-moves] button'), MOVES);
  assert.deepEqual(await bar(page), ["Back", "Next"]);
  await tab(page, "close"); await sleep(800);
  assert.match(await page.$eval("[data-tq-dash-close] [data-tq-row-moves]", (e) => e.innerText), /^What happens next is at the top of the dashboard, and Next on the row below/);

  assert.ok(await clickRow(page, await findRow(page, /Regional operations newsletter/)));
  await page.waitForSelector('[data-tq-item-sections="fyi"] [data-tq-pane-strip="from"] [data-tq-pane-moves] button', { timeout: 20000 }); await sleep(1200);
  const fyi = await seen(page, '[data-tq-pane-strip="from"] [data-tq-pane-moves] button');
  assert.ok(fyi.includes("Should be a task") && !fyi.includes("Send to agent"), `Came from's strip: ${fyi}`);
  assert.deepEqual(await bar(page), ["Back", "Next"]);
  // ...and Send to agent, a stage move, on the folded Agent's spine as on a task's (the owner, 2026-10-31) - its press opens Agent
  assert.deepEqual(await seen(page, '[data-tq-section-tab="agent"] [data-tq-spine-moves] button'), ["Send to agent"], "the Agent spine carries Send to agent");
  assert.equal(await page.$eval('[data-tq-slot="agent"]', (e) => Math.round(e.getBoundingClientRect().width)), 156, "a full spine, as a task's");
  await page.click('[data-tq-section-tab="agent"] [data-tq-spine-moves] button'); await sleep(1500);
  assert.equal(await page.$eval("[data-tq-item-sections] [data-tq-sections]", (e) => e.dataset.tqMain), "agent", "the press opened Agent");
  await page.keyboard.press("Escape"); await sleep(300);
  assert.deepEqual(errors, []);
});

test("on a phone a report keeps its moves on the row", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 390, height: 844 });
  assert.ok(await clickRow(page, await findRow(page, /Headcount by site/)));
  await page.waitForSelector('[data-tq-item-sections="report"][data-tq-item-sections]', { timeout: 20000 }); await sleep(2000);
  assert.equal(await page.$$eval("[data-tq-item-sections] [data-tq-pane-strip]", (s) => s.length), 0, "stacked sections wear no strip");
  const row = await page.$$eval("[data-tq-row] button[data-tq-verb]", (bs) => bs.map((b) => b.dataset.tqVerb));
  assert.ok(row.includes("w:mine") || (await page.$("[data-tq-row] [data-tq-more]")), `the row holds the report's moves: ${row}`);
  assert.deepEqual(errors, []);
});
