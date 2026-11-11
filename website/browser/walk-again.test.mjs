import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* THE WAY TO WALK AGAIN IS ON THE BAR (the owner, 2026-11-10, on the desk after a walk went through everything with one task still open: "where
   is the button to start over?" - the bar held only Back). The demo world: walk it from the day card to its end by the bar's Next, then read
   the bar - the walk's again beside Back while the rail holds anything, never Back alone (rules part 4: no dead ends). Recorded. */
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "n17");
const barButtons = (page) => page.evaluate(() => [...document.querySelectorAll("[data-tq-row] button")]
  .filter((b) => b.getBoundingClientRect().width > 0 && getComputedStyle(b).visibility !== "hidden").map((b) => ({ text: b.innerText.trim(), off: b.disabled })));
const press = (page, re) => page.evaluate((src) => { const b = [...document.querySelectorAll("button")].find((x) => new RegExp(src).test(x.innerText.trim()) && !x.disabled
  && x.getBoundingClientRect().width > 0); b?.click(); return !!b; }, re);

test("at the end of a walk with tasks still open, the bar offers the walk again beside Back", { timeout: 600000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const page = await h.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  const name = process.env.N17_NAME || "walk-again", dir = path.join(out, "video", name); await mkdir(dir, { recursive: true });
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => /^Walk me through my tasks/.test(b.innerText.trim())), { timeout: 60000 });
  assert.ok(await press(page, "^Walk me through my tasks"), "the day card's walk");
  let rec = null, bar = [], end = false;
  for (let i = 0; i < 80 && !end; i++) {
    await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-row] button")].some((b) => /^(Next|All read, next)/.test(b.innerText.trim()) && !b.disabled)
      || /you're clear|1 to go|to go, then/.test(document.body.innerText), { timeout: 20000, polling: 200 }).catch(() => {});
    await new Promise((r) => setTimeout(r, 400));
    bar = await barButtons(page);
    if (!bar.some((b) => /^(Next|All read, next)/.test(b.text) && !b.off)) { end = true; break; }
    if (!rec && i > 0) rec = await record(page, dir);
    await press(page, "^(Next|All read, next)");
  }
  if (!rec) rec = await record(page, dir);
  await new Promise((r) => setTimeout(r, 2500));
  bar = await barButtons(page);
  const rail = await page.evaluate(() => (/(\d+) to go/.exec(document.body.innerText) || [])[1] || "");
  await page.screenshot({ path: path.join(out, `${name}.png`) });
  await rec.stop();
  const again = bar.some((b) => /^Walk me through my tasks/.test(b.text) && !b.off);
  await note(dir, { done: "The demo world: the day card's walk, then the bar's Next until it is gone - the walk at its end, tasks still on the rail.",
    expect: "On the bar: Back and the way to walk again (Walk me through my tasks) - never Back alone.",
    saw: `rail: ${rail || "?"} to go; bar: ${bar.map((b) => b.text).join(" | ") || "nothing"}`, verdict: end && again ? "PASS" : "FAIL" });
  assert.ok(end, "the walk reached its end");
  assert.ok(again, `the bar offers the walk again: ${JSON.stringify(bar)} (rail ${rail} to go)`);
  // ...and it walks again: the first item on the table, its Next on the bar
  await press(page, "^Walk me through my tasks");
  await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-row] button")].some((b) => /^(Next|All read, next)/.test(b.innerText.trim()) && !b.disabled),
    { timeout: 30000, polling: 200 });
  assert.deepEqual(errors, []);
});
