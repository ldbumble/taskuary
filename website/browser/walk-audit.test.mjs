import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* THE WALK, ROW BY ROW, AS THE OWNER PRESSES IT (the owner, 2026-11-10: "keep on doing audits of the next/triage walk through"). The demo world,
   walked from the day card by the bar's Next to its end. At every press: Next greys at once until the move lands; the row it lands on is the one
   the rail marked next (never a skip); the rail's rows keep their order; once settled the bar holds navigation only (the owner, 2026-11-10: "on
   bottom the only buttons should be nav") and nothing greyed is left standing beside it. Then Back once, from the middle. Recorded. */
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "n17");
const NAV = /^(Back|Next|All read, next|Walk me through my tasks)$/;
const read = (page) => page.evaluate(() => {
  const rows = [...document.querySelectorAll("[data-tq-rail] .tq-pile-row[data-tq-key]")].filter((e) => !e.classList.contains("settling"));
  const bar = [...document.querySelectorAll("[data-tq-row] button")].filter((b) => b.getBoundingClientRect().width > 0 && getComputedStyle(b).visibility !== "hidden")
    .map((b) => ({ text: b.innerText.trim(), off: b.disabled }));
  return { keys: rows.map((e) => e.getAttribute("data-tq-key")), on: rows.filter((e) => /\b(current|inbatch)\b/.test(e.className)).map((e) => e.getAttribute("data-tq-key")),
    next: rows.find((e) => /\bnext\b/.test(e.className))?.getAttribute("data-tq-key") || null, bar };
});
const press = (page, re) => page.evaluate((src) => { const b = [...document.querySelectorAll("[data-tq-row] button")].find((x) => new RegExp(src).test(x.innerText.trim()) && !x.disabled
  && x.getBoundingClientRect().width > 0); b?.click(); return !!b; }, re);
const settle = async (page, before) => {
  const t0 = Date.now(); let s;
  do { await new Promise((r) => setTimeout(r, 150)); s = await read(page); } while (Date.now() - t0 < 15000 && (JSON.stringify(s.on) === JSON.stringify(before.on) || s.bar.some((b) => b.off && /^(Next|All read, next)$/.test(b.text))));
  await new Promise((r) => setTimeout(r, 1500));
  return read(page);
};

test("the walk, row by row: Next greys until it lands, lands on the row marked next, the rows keep their order, the bar is navigation only", { timeout: 900000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const page = await h.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  const name = process.env.N17_NAME || "walk-audit", dir = path.join(out, "video", name); await mkdir(dir, { recursive: true });
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => /^Walk me through my tasks/.test(b.innerText.trim())), { timeout: 60000 });
  const rec = await record(page, dir), steps = [], bad = [];
  try {
    await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => /^Walk me through my tasks/.test(b.innerText.trim()))?.click());
    let s = await settle(page, { on: [] }), order = s.keys.slice(), backed = false;
    for (let n = 0; n < 60; n++) {
      const step = { n, on: s.on, next: s.next, bar: s.bar.map((b) => b.text + (b.off ? " (off)" : "")).join(" | ") };
      steps.push(step);
      const stray = s.bar.filter((b) => !NAV.test(b.text));
      if (stray.length) bad.push(`${n} ${s.on.join(",")}: the bar holds more than navigation: ${stray.map((b) => b.text).join(", ")}`);
      const greyed = s.bar.filter((b) => b.off && b.text !== "Back");
      if (greyed.length) bad.push(`${n} ${s.on.join(",")}: greyed and left standing: ${greyed.map((b) => b.text).join(", ")}`);
      // ...the rows that stay keep their order: a row never moves
      const kept = order.filter((k) => s.keys.includes(k)), now = s.keys.filter((k) => order.includes(k));
      if (JSON.stringify(kept) !== JSON.stringify(now)) bad.push(`${n}: the rail's rows moved: ${JSON.stringify(now.slice(0, 8))}`);
      order = s.keys.slice();
      const go = s.bar.find((b) => /^(Next|All read, next)$/.test(b.text) && !b.off);
      if (!go) break;
      // ...BACK ONCE, from the middle: the row above, then Next again lands back here
      if (!backed && n === 3) {
        backed = true;
        const here = s.on, above = await press(page, "^Back$");
        if (above) { const b = await settle(page, s); if (JSON.stringify(b.on) === JSON.stringify(here)) bad.push(`${n}: Back moved nothing`);
          await press(page, "^(Next|All read, next)$"); const f = await settle(page, b);
          if (JSON.stringify(f.on) !== JSON.stringify(here)) bad.push(`${n}: Back then Next landed on ${f.on.join(",")}, not ${here.join(",")}`); s = f; continue; }
      }
      const want = s.next, before = s;
      await press(page, `^${go.text}$`);
      // ...greyed at once, until the move lands (the owner, 2026-11-03: one move at a time)
      await new Promise((r) => setTimeout(r, 120));
      const mid = await read(page);
      if (JSON.stringify(mid.on) === JSON.stringify(before.on) && mid.bar.some((b) => b.text === go.text && !b.off)) bad.push(`${n}: ${go.text} still pressable 120 ms after the press, the move not landed`);
      s = await settle(page, before);
      if (want && !s.on.includes(want) && s.on.length) bad.push(`${n}: landed on ${s.on.join(",")}, the rail marked ${want} next`);
    }
    steps.push({ end: true, bar: s.bar.map((b) => b.text + (b.off ? " (off)" : "")).join(" | ") });
  } finally {
    await page.screenshot({ path: path.join(out, `${name}.png`) });
    await rec.stop();
    await writeFile(path.join(dir, "steps.json"), JSON.stringify(steps, null, 1));
    await note(dir, { done: "The demo world walked from the day card by the bar's Next to its end, Back once at the fourth row.",
      expect: "Next greys at once and lands on the row the rail marked next; rows never move; the bar is navigation only, nothing greyed left beside it.",
      saw: bad.length ? bad.slice(0, 12).join("\n") : `as expected over ${steps.length} rows`, verdict: bad.length ? "FAIL" : "PASS" });
  }
  assert.deepEqual(bad.slice(0, 12), []);
  assert.deepEqual(errors, []);
});
