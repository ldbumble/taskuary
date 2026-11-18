import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* THE PAGE'S OWN BUTTONS, OUTSIDE A TASK (the hammer round, 2026-11-18: "pressed once, twice, fast: instant, does what it says, no jump, no blank
   beat"). Each press is watched frame by frame from the click - what the canvas says at every committed change - and recorded. */
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "nav-presses");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const center = (page, sel) => page.evaluate((s) => { const b = document.querySelector(s); if (!b || !b.getBoundingClientRect().width) return null;
  const q = b.getBoundingClientRect(); return { x: q.x + q.width / 2, y: q.y + q.height / 2 }; }, sel);
// every change of `read` (a function's source, run in the page) from the click on, for `ms`
async function watchPress(page, sel, read, ms = 2500) {
  const at = await center(page, sel);
  assert.ok(at, `no ${sel} on the page`);
  await page.evaluate((src) => {
    const f = new Function(`return (${src})`)(), seen = [];
    let last = JSON.stringify(f());
    const w = { t0: performance.now(), seen };
    const tick = () => { const now = JSON.stringify(f()); if (now !== last) { seen.push({ at: Math.round(performance.now() - w.t0), v: JSON.parse(now) }); last = now; } w.raf = requestAnimationFrame(tick); };
    w.raf = requestAnimationFrame(tick);
    window.__tqPress = w;
  }, read.toString());
  await page.mouse.click(at.x, at.y);
  await sleep(ms);
  return page.evaluate(() => { const w = window.__tqPress; cancelAnimationFrame(w.raf); window.__tqPress = null; return w.seen; });
}

async function demo(t) {
  const h = await startHarness();
  t.after(() => h.close());
  const page = await h.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => /^Walk me through my tasks/.test(b.innerText.trim()) && !b.disabled), { timeout: 90000 });
  return { h, page, errors };
}

// THE DAY CARD COMES BACK COUNTED. Back on the feed by the logo from a page, the card's heading read "What's open", then "Counting…" for a
// beat, then "What's open" again: the digest under it (SinceBlock) was drawn anew with nothing read, and said the day was still being counted
// until its own read came back - every trip home
test("the logo back from a page draws the day card as it was, never Counting… for a beat", { timeout: 300000 }, async (t) => {
  const { page, errors } = await demo(t);
  const head = () => document.querySelector(".tq-day-wait .tq-day-h")?.innerText || null;
  await page.waitForFunction((src) => /what's open/i.test(new Function(`return (${src})`)()() || ""), { timeout: 30000 }, head.toString());
  const dir = path.join(out, "home-counting"); await mkdir(dir, { recursive: true });
  const rec = await record(page, dir), seen = [];
  try {
    for (let i = 0; i < 2; i += 1) {
      await watchPress(page, "[data-tq-nav=reports]", head, 1500);
      seen.push(...(await watchPress(page, "[data-tq-home]", head, 2500)).map((x) => ({ trip: i, ...x })));
    }
  } finally {
    await rec.stop();
    await writeFile(path.join(dir, "seen.json"), JSON.stringify(seen, null, 1));
    const counting = seen.filter((x) => /counting/i.test(x.v || ""));
    await note(dir, { done: "The demo world; the day card counted. Reports, then the Taskuary logo home - twice.",
      expect: "The day card is back saying What's open from its first frame; never Counting… in between.",
      saw: counting.length ? JSON.stringify(seen) : "as expected", verdict: counting.length ? "FAIL" : "PASS" });
  }
  assert.ok(seen.some((x) => /what's open/i.test(x.v || "")), `the day card never came back: ${JSON.stringify(seen)}`);
  assert.deepEqual(seen.filter((x) => /counting/i.test(x.v || "")), [], `the day card said Counting… on the way home: ${JSON.stringify(seen)}`);
  assert.deepEqual(errors, []);
});
