import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

/* A PAGE LOADS ITS DATA ONCE (the owner, 2026-10-26: "things don't load twice, if you click a button twice it won't reload [double
   work]"). The overnight setup walk counted the GETs each open fires in the demo world: every start asked for the first-run state, the
   build and today's meetings twice each, and Settings > Docs read all nine documents to draw a list that shows none of their words. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const gets = (page) => {
  const seen = [];
  page.on("request", (r) => { const u = new URL(r.url()); if (r.method() === "GET" && u.pathname.startsWith("/api/")) seen.push(u.pathname); });
  return { since: (i) => seen.slice(i), get n() { return seen.length; } };
};
const count = (list, path) => list.filter((p) => p === path).length;
const ONCE = [];

test("a start reads the first-run state, the build and today's meetings once each; Settings > Docs draws its list without the documents",
  { timeout: 180000 }, async (t) => {
  const h = await startHarness(); t.after(() => h.close());
  const page = await h.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  const g = gets(page);
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 60000 });
  await sleep(2500);
  const boot = g.since(0);
  for (const p of ONCE) assert.equal(count(boot, p), 1, `${p} read ${count(boot, p)} times at the start`);

  await page.evaluate(() => document.querySelector('[data-tq-nav="settings"]').click());
  await page.waitForSelector('[data-tq-browse="settings"] [data-tq-browse-chip]');
  const at = g.n;
  await page.evaluate(() => [...document.querySelectorAll('[data-tq-browse="settings"] [data-tq-browse-chip]')].find((c) => c.innerText.trim() === "Docs").click());
  await page.waitForFunction(() => [...document.querySelectorAll('[data-tq-browse="settings"] [data-tq-browse-card]')].some((c) => /LEARNED\.md/.test(c.innerText)), { timeout: 20000 });
  await sleep(1500);
  const docs = g.since(at).filter((p) => p.startsWith("/api/doc/"));
  assert.deepEqual(docs, [], "the list of documents reads none of them");
  // ...and a document opened from it is still read and drawn
  await page.evaluate(() => [...document.querySelectorAll('[data-tq-browse="settings"] [data-tq-browse-card]')].find((c) => /JOB\.md/.test(c.innerText)).click());
  await page.waitForFunction(() => document.querySelector('[data-tq-browse="settings"] [data-tq-browse-one] textarea')?.value.length > 0, { timeout: 20000 });
  assert.deepEqual(errors, []);
});
