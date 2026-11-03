import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
/* FYI FITS AS MANY AS THE SCREEN HOLDS (the owner, 2026-11-02: "on FYI we should fit as many as can fit on the screen. In mine it's probably
   8 at a time or so"). The demo's 14 tasks already fill a 900px rail, so the capped bands were held at two rows each - "10 more fyi" - to
   save a scrollbar the tasks had put there anyway. Now, scrolled to, the FYI band shows a screenful; a shorter window shows fewer, and the
   rows keep their order. */
test("the fyi band shows as many rows as one screen of the rail holds, fewer on a short window", { timeout: 180000 }, async (t) => {
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
  assert.ok(tall.total >= 10, `the demo has a band of fyi to fit - ${JSON.stringify(tall)}`);
  assert.ok(tall.fyi.length >= 8, `1440x900: at least 8 fyi rows - ${JSON.stringify(tall)}`);
  assert.ok(tall.bandH <= tall.rail, `...and the band fits one screen of the rail - ${JSON.stringify(tall)}`);
  const short = await at(700);
  assert.ok(short.fyi.length < tall.fyi.length && short.fyi.length >= 2, `a short window shows fewer, never under two - ${JSON.stringify(short)}`);
  assert.ok(short.bandH <= short.rail, `...still one screen - ${JSON.stringify(short)}`);
  assert.match(short.more, new RegExp(`^${short.total - short.fyi.length} more`), `the rest stay behind "N more" - ${JSON.stringify(short)}`);
  assert.deepEqual(short.fyi, tall.fyi.slice(0, short.fyi.length), "the rows keep their order: the short window draws the first of the same rows");
  const back = await at(900);
  assert.deepEqual(back.fyi, tall.fyi, "tall again: the room comes back");
  assert.deepEqual(errors, []);
});
