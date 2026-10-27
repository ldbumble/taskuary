import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* NO STRIP AT ALL (the owner, 2026-10-26: "maybe keep the box but remove the advisor? not sure the advisor is really useful"). The
   Advisor's band over the row went - first when silent (the same day: "remove it when it's not doing anything"), now always: its pick is
   the row's one dark button, and the few lines that warned stand in the task beside what they are about (advice.taskNote). Walked across
   the rail at 1600x810: the dock is the one line of the row and the box on every item, and a decided item still has its button lit. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("the dock never draws the Advisor's strip: one line on every item, and the Advisor's pick still lit", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const keys = await page.$$eval("[data-tq-rail] .tq-pile-row[data-tq-key]", (els) => els.map((r) => r.getAttribute("data-tq-key")));
  const seen = [];
  for (const k of keys.slice(0, 14)) {
    await page.evaluate((k) => document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"] .card`)?.click(), k);
    await page.waitForFunction((k) => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") === k, { timeout: 20000 }, k).catch(() => {});
    await sleep(2500);                                  // its reads and its advice land
    seen.push({ k, ...(await page.evaluate(() => {
      const dock = document.querySelector(".tq-dock"), bar = dock?.querySelector(".tq-dock-line");
      const h = (e) => (e ? Math.round(e.getBoundingClientRect().height) : null);
      return { dock: h(dock), bar: h(bar), strip: document.querySelectorAll("[data-tq-strip], .tq-dock .tq-next").length,
        other: [...(dock?.children || [])].filter((e) => e !== bar && e.getBoundingClientRect().height > 0).map((e) => e.className).join(","),
        // ...counted by label: the row draws a hidden measuring copy of itself (ActionRow's ghost)
        decided: !!document.querySelector("[data-tq-advice-verb]"), lit: new Set([...document.querySelectorAll("[data-tq-row] .tq-ab.p:not(:disabled)")].map((b) => b.textContent.trim())).size, litWords: [...document.querySelectorAll("[data-tq-row] .tq-ab.p:not(:disabled)")].map((b) => b.textContent.trim()).join("|") };
    })) });
  }
  if (process.env.TQ_PROBE) console.log(JSON.stringify(seen, null, 1));
  for (const s of seen) {
    assert.equal(s.strip, 0, `no strip and no line over the row: ${JSON.stringify(s)}`);
    assert.equal(s.other, "", `nothing but the one line in the dock: ${JSON.stringify(s)}`);
    assert.ok(Math.abs(s.dock - (s.bar + 2)) <= 2, `the dock is the one line of the row and the box: ${JSON.stringify(s)}`);
  }
  // ...the box keeps its size: the dock is as tall as it was with a silent strip (44px at 1600x810, the one-row chat bar's)
  assert.ok(seen.every((s) => s.dock <= 48), `one line, never a band over it: ${JSON.stringify(seen.map((s) => s.dock))}`);
  // ...and the Advisor still decides: a decided item lights one button
  const decided = seen.filter((s) => s.decided);
  assert.ok(decided.length, `a decided item was met: ${JSON.stringify(seen)}`);
  for (const s of decided) assert.ok(s.lit <= 1, `one dark button at most: ${JSON.stringify(s)}`);
  assert.ok(decided.some((s) => s.lit === 1), `the Advisor's pick is lit on the row: ${JSON.stringify(decided)}`);
  assert.deepEqual(errors, []);
});
