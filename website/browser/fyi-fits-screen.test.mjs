import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
/* FYI SHOWS A FIXED COUNT (the owner, 2026-11-02: "6 on big and 4 on small"): a window 900px tall or more draws 6 fyi rows, a shorter one
   4, the rest behind "N more", in the same order, and a resize recomputes it. */
test("the fyi band shows 6 rows on a big window and 4 on a short one", { timeout: 180000 }, async (t) => {
  const h = await startHarness(); t.after(() => h.close());
  const page = await h.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  await page.goto(h.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 40000 });
  await sleep(2500);
  const state = () => page.evaluate(() => {
    const sc = document.querySelector("[data-tq-rail]"), band = (l) => document.querySelector(`[data-tq-run="${l}"]`);
    const keys = (l) => [...(band(l)?.querySelectorAll(".tq-pile-row[data-tq-key]") || [])].map((e) => e.dataset.tqKey);
    const fyi = band("fyi"), head = fyi?.querySelector("[data-tq-section-head]");
    return { rail: sc.clientHeight, fyi: keys("fyi"), tasks: keys("task").length, total: Number(head?.querySelector("em")?.textContent),
      bandH: fyi ? Math.round(fyi.getBoundingClientRect().height) : 0, more: fyi?.querySelector(".tq-pile-more")?.textContent.trim() || "" };
  });
  const at = async (height) => { await page.setViewport({ width: 1440, height, deviceScaleFactor: 1 }); await sleep(2000); return state(); };
  const tall = await at(900);
  assert.ok(tall.total >= 10, `the demo has a band of fyi - ${JSON.stringify(tall)}`);
  assert.equal(tall.fyi.length, 6, `1440x900: 6 fyi rows - ${JSON.stringify(tall)}`);
  assert.match(tall.more, new RegExp(`^${tall.total - 6} more`), `the rest stay behind "N more" - ${JSON.stringify(tall)}`);
  await page.setViewport({ width: 1280, height: 700, deviceScaleFactor: 1 }); await sleep(2000);
  const short = await state();
  assert.equal(short.fyi.length, 4, `1280x700: 4 fyi rows - ${JSON.stringify(short)}`);
  assert.match(short.more, new RegExp(`^${short.total - 4} more`), `the rest stay behind "N more" - ${JSON.stringify(short)}`);
  assert.deepEqual(short.fyi, tall.fyi.slice(0, 4), "the rows keep their order");
  const back = await at(900);
  assert.deepEqual(back.fyi, tall.fyi, "tall again: the room comes back");
  assert.deepEqual(errors, []);
});
