import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, rail, sleep } from "./walkdriver.mjs";

/* A PRESS OF NEXT READS EACH THING ONCE (the overnight walk, 2026-10-26; the owner: "things don't load twice, if you click a button twice it
   won't reload"). Counted per press, every request the page made: the Advisor was asked about the item being LEFT and twice about the one
   arriving, the sync caption's status was read once per write and live event (the press's own record among them), a draft's To and Cc
   rows each read everyone Taskuary has seen, and a double-click on an FYI batch's "All read, next" posted two settles of one batch. */
const count = (reqs, t0, re, m = "GET") => reqs.filter((r) => r.t >= t0 && r.m === m && re.test(r.p)).length;

test("each press of Next asks the Advisor once, about the item it brings, and the status and the people at most once", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1600, height: 810 });
  const reqs = [];
  page.on("request", (r) => { const u = new URL(r.url()); if (u.pathname.startsWith("/api/")) reqs.push({ t: Date.now(), m: r.method(), p: u.pathname + decodeURIComponent(u.search) }); });
  await clickRow(page, (await rail(page))[0].key); await sleep(4000);
  const start = Date.now();
  for (let i = 0; i < 5; i++) {
    const left = await page.$eval("[data-tq-rail] .tq-pile-row.current", (e) => e.getAttribute("data-tq-key"));
    const t0 = Date.now();
    await page.evaluate(() => document.querySelector("[data-tq-row] [data-tq-next]").click());
    await sleep(3500);
    const now = await page.$eval("[data-tq-rail] .tq-pile-row.current", (e) => e.getAttribute("data-tq-key"));
    const at = `press ${i}: ${left} -> ${now}`;
    assert.notEqual(now, left, `${at}: Next did not move`);
    assert.equal(reqs.filter((r) => r.t >= t0 && r.p === `/api/advice?key=${left}`).length, 0, `${at}: the Advisor was asked about the item put down`);
    assert.ok(count(reqs, t0, /^\/api\/advice\?/) <= 2, `${at}: ${count(reqs, t0, /^\/api\/advice\?/)} Advisor reads`);
    assert.ok(count(reqs, t0, /^\/api\/people$/) <= 1, `${at}: ${count(reqs, t0, /^\/api\/people$/)} reads of everyone`);
  }
  // the status: once a press, and the caption's own poll may fall inside the walk once (it was two a press, and three after a close)
  assert.ok(count(reqs, start, /^\/api\/ingest\/status$/) <= 6, `${count(reqs, start, /^\/api\/ingest\/status$/)} status reads in five presses`);
  assert.deepEqual(errors, []);
});

test("a double-click on All read, next settles the batch once and walks on one batch", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1600, height: 810 });
  const reqs = [];
  page.on("request", (r) => { const u = new URL(r.url()); if (u.pathname.startsWith("/api/")) reqs.push({ t: Date.now(), m: r.method(), p: u.pathname }); });
  await page.click('[data-tq-section-head="reports"] .fold'); await sleep(1500);
  await page.evaluate(() => [...document.querySelectorAll('[data-tq-run="reports"] .tq-pile-row[data-tq-key] .card')].at(-1).click()); await sleep(3500);
  await page.evaluate(() => document.querySelector("[data-tq-row] [data-tq-next]").click()); await sleep(3500);
  const label = () => page.$eval("[data-tq-row] [data-tq-next]", (b) => b.textContent.trim()).catch(() => "");
  const fyi = () => page.$eval('[data-tq-section-head="fyi"]', (e) => e.innerText.replace(/\s+/g, " ")).catch(() => "");
  assert.equal(await label(), "All read, next", "no fyi batch on the table");
  // ...a batch is as many as this screen reads together (fyiBatch.js: six at 1600x810), counted off the card on the table
  const size = await page.$$eval('[data-tq-item-sections="fyis"] [data-tq-fyi-msg]', (e) => e.length);
  assert.equal(size, 6, "a 1600x810 screen reads six together");
  const was = await fyi(), t0 = Date.now();
  await page.evaluate(() => { const b = document.querySelector("[data-tq-row] [data-tq-next]"); b.click(); b.click(); });
  await sleep(5000);
  assert.equal(count(reqs, t0, /^\/api\/funnel\/settle$/, "POST"), 1, "the batch was settled twice");
  const n = (s) => +(/(\d+)/.exec(s)?.[1] || 0);
  assert.equal(n(was) - n(await fyi()), size, `one batch read: ${was} -> ${await fyi()}`);
  assert.deepEqual(errors, []);
});
