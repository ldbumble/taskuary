import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, pressNext, sleep } from "./walkdriver.mjs";

/* ONE NEXT ON A REPORT TAKES ITS ROW OFF THE RAIL IN THE FRAME THE TABLE MOVES (the owner, 2026-11-02: "on a report if you press Next, the
   canvas shrinks the report right away and 'on the table' moves to the next item right away, but the prior report stays on the work rail for
   an extra second before it leaves"). The ring moving is not the row leaving: each frame after the press is sampled for the passed report's
   row in the DOM (drawn, with height), and for the ring. With the walk's answer held 2.5 s the row can only leave by the page's own word. */
const SOON = 150;
const run = (page, sec) => page.$$eval(`[data-tq-run="${sec}"] .tq-pile-row[data-tq-key]`, (els) => els.map((e) => e.getAttribute("data-tq-key")));
const ring = (page) => page.evaluate(() => document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") || "");
const until = async (f, ms = 15000) => { for (const t0 = Date.now(); Date.now() - t0 < ms; await sleep(50)) if (await f()) return true; return false; };
// every frame from the press: when the ring left `from`, and when `from`'s row stopped being drawn on the rail
const pressAndSample = (page, from) => page.evaluate((k) => new Promise((done) => {
  const b = document.querySelector("[data-tq-row] [data-tq-next]");
  if (!b || b.disabled) { done(null); return; }
  const shown = () => [...document.querySelectorAll(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"]`)].some((e) => e.getBoundingClientRect().height > 0 && getComputedStyle(e).display !== "none");
  const ringOn = () => document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") || "";
  const t0 = performance.now(); let ringAt = -1, goneAt = -1;
  const tick = () => { const t = Math.round(performance.now() - t0);
    if (ringAt < 0 && ringOn() !== k) ringAt = t;
    if (shown()) goneAt = -1; else if (goneAt < 0) goneAt = t;
    if (t > 4000) done({ ringAt, goneAt }); else requestAnimationFrame(tick); };
  b.click(); requestAnimationFrame(tick);
}), from);

async function onReport(t, slow, arrive) {
  const { page, errors } = await boot(t, { width: 1440, height: 900, ...(slow ? { slow, slowOn: "/api/walk/" } : {}) });
  const tasks = await run(page, "task"), reports = await run(page, "reports");
  assert.ok(tasks.length && reports.length >= 2, `the demo has tasks and reports: ${tasks} / ${reports}`);
  const r0 = reports[0];
  if (arrive === "click") await clickRow(page, r0);
  else { await clickRow(page, tasks.at(-1)); await until(async () => (await ring(page)) === tasks.at(-1)); await sleep(slow + 2500); assert.ok(await pressNext(page), "Next from the last task"); }
  assert.ok(await until(async () => (await ring(page)) === r0), `the report is on the table: the ring is on ${await ring(page)}`);
  await sleep(slow + 3000);
  const m = await pressAndSample(page, r0);
  assert.ok(m, "Next is pressable on the report");
  assert.ok(m.ringAt >= 0 && m.ringAt <= SOON, `the ring stayed on the report ${m.ringAt} ms`);
  assert.ok(m.goneAt >= 0 && m.goneAt <= SOON, `the report's row stayed on the rail ${m.goneAt} ms after Next (the ring moved at ${m.ringAt} ms)`);
  await sleep(slow + 2000);
  assert.ok(!(await run(page, "reports")).includes(r0), "the report came back on the rail");
  assert.deepEqual(errors, []);
}

test("Next on a report reached by Next takes its row off the rail at the press", { timeout: 300000 }, (t) => onReport(t, 0, "next"));
test("...with the walk's answer held", { timeout: 300000 }, (t) => onReport(t, 2500, "next"));
test("Next on a report clicked takes its row off the rail at the press", { timeout: 300000 }, (t) => onReport(t, 0, "click"));
test("...clicked, with the walk's answer held", { timeout: 300000 }, (t) => onReport(t, 2500, "click"));
