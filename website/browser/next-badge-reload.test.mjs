import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

/* EVERY CARD THE WALK LEFT WEARS WHAT MOVED IT ON, AND KEEPS IT (the owner, 2026-10-24: "when you close a task or move on it shows mark
   done on the close task. If we hit next let's show that as well on the task on the canvas"). "All read, next" on an fyi batch walks on by
   the settle road, not Next's: its badge was drawn on the page and gone on the next read. Here: the whole demo walked with Next, reloaded. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const press = (page) => page.evaluate(() => {
  const b = [...document.querySelectorAll("button")].find((n) => /^(Next|All read, next)$/.test(n.textContent.trim()) && !n.disabled);
  if (b) b.click(); return !!b;
});
const folded = (page) => page.$$eval("[data-tq-folded]", (els) => els.map((e) => ({
  title: e.querySelector("b")?.textContent || "", badge: e.querySelector("[data-tq-pressed]")?.getAttribute("data-tq-pressed") || null })));

test("every card Next and All read, next walked past keeps its badge through a reload", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  await page.evaluate(() => document.querySelector("[data-tq-rail] .tq-pile-row .card").click());
  await sleep(2500);
  for (let i = 0, misses = 0; i < 40 && misses < 3; i += 1) { misses = (await press(page)) ? 0 : misses + 1; await sleep(1800); }
  await sleep(2000);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-folded]", { timeout: 30000 });
  await sleep(3000);
  const rows = await folded(page);
  assert.ok(rows.some((r) => r.badge === "All read, next"), `the walk reached an fyi batch: ${JSON.stringify(rows)}`);
  assert.deepEqual(rows.filter((r) => !r.badge), [], "a card the walk left lost its badge on reload");
  assert.deepEqual(errors, []);
});
