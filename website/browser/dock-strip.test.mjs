import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* NO LINE, NO STRIP (the owner, 2026-10-26, the dock on a 1600x810 laptop: "for advisor we probably should remove it when it's not doing
   anything no? want to give laptops enough real estate to see the full task"). The Advisor's band over the row stood ~31px tall and empty
   whenever it was silent - the obvious move said by its lit button alone, an agent at work, a read on its way. Walked across the rail: a
   silent strip takes no room and the dock is that much shorter; a strip with a line shows it, its band as tall as before. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("the dock's Advisor strip takes no room while it is silent, and shows its line when it has one", { timeout: 300000 }, async (t) => {
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
    const m = await page.evaluate(() => {
      const dock = document.querySelector(".tq-dock"), strip = dock?.querySelector("[data-tq-strip]"), row = dock?.querySelector("[data-tq-row]");
      const h = (e) => (e ? Math.round(e.getBoundingClientRect().height) : null);
      const box = dock?.querySelector(".tq-compose-box");
      return { dock: h(dock), strip: strip ? h(strip) : null, row: h(row), box: h(box), line: strip?.querySelector(".tq-next")?.textContent || "",
        other: [...(dock?.children || [])].filter((e) => e !== strip && e !== row && e !== box && e.getBoundingClientRect().height > 0).map((e) => e.className).join(",") };
    });
    seen.push({ k, ...m });
  }
  if (process.env.TQ_PROBE) console.log(JSON.stringify(seen, null, 1));
  const silent = seen.filter((s) => s.strip !== null && !s.line && !s.other), said = seen.filter((s) => s.line && !s.other);
  assert.ok(silent.length, `a silent strip was met: ${JSON.stringify(seen)}`);
  for (const s of silent) {
    assert.equal(s.strip, 0, `a silent strip takes no room: ${JSON.stringify(s)}`);
    assert.ok(Math.abs(s.dock - (s.row + s.box + 2)) <= 2, `the dock is the row and the box: ${JSON.stringify(s)}`);
  }
  // ...and one with words shows them, in a band of its own: the dock is that band taller
  assert.ok(said.length, `a strip with a line was met: ${JSON.stringify(seen)}`);
  for (const s of said) {
    assert.ok(s.strip >= 30, `the line has its band: ${JSON.stringify(s)}`);
    assert.ok(Math.abs(s.dock - (s.row + s.box + s.strip + 2)) <= 2, `the dock is the strip, the row and the box: ${JSON.stringify(s)}`);
  }
  assert.deepEqual(errors, []);
});
