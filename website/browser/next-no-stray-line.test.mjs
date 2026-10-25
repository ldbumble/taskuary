import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

/* NEXT BRINGS A CARD, NEVER ITS SENTENCE ALONE (the owner, 2026-10-25: "saw a stray text showing next 4 fyi every once in a while"):
   a prepared answer drawn ahead of its press (drawAhead, `held`) held its card back and said "Next up: 4 FYI." as a bare bubble
   until the press answered. The whole demo walk is pressed through, every frame watched for such a line. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const press = (page) => page.evaluate(() => {
  const b = [...document.querySelectorAll("button")].find((n) => /^(Next|All read, next)$/.test(n.textContent.trim()) && !n.disabled);
  if (b) b.click(); return !!b;
});

test("a walk of Nexts never shows a 'Next up' line without its card", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  await page.evaluate(() => {
    window.__said = [];
    const look = () => { for (const p of document.querySelectorAll(".tq-msg:not(.you) .body > p"))
      if (/^\s*(Next up|Opened)\b/.test(p.textContent) && p.getBoundingClientRect().height) window.__said.push(p.textContent.slice(0, 80)); };
    new MutationObserver(look).observe(document.body, { subtree: true, childList: true, characterData: true });
  });
  await page.evaluate(() => document.querySelector("[data-tq-rail] .tq-pile-row .card").click());
  await sleep(2500);
  let n = 0;
  for (let misses = 0; n < 40 && misses < 3; n += 1) { misses = (await press(page)) ? 0 : misses + 1; await sleep(1500); }
  const badges = await page.$$eval("[data-tq-folded] [data-tq-pressed]", (els) => els.map((e) => e.getAttribute("data-tq-pressed")));
  assert.ok(badges.includes("All read, next"), `the walk reached an fyi batch in ${n} presses: ${JSON.stringify(badges)}`);
  assert.deepEqual([...new Set(await page.evaluate(() => window.__said))], [], "a Next showed its sentence without its card");
});
