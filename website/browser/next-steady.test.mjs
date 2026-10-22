import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* WHAT NEXT DRAWS AT ONCE STAYS PUT (the owner, 0.3.9.26: "you click Next, it shows up right away, then reloads it a few seconds
   later... this is still bad"). After a press of Next the item put on the table first stays mounted and where it came to rest: the
   answer, the item's own reads, the Advisor and the rail that follows fill it in place - no remount, no spinner, no other key, and no
   slide up the screen when the answer lands. Recorded every frame for 8 s, plain and with the press's answer held 2.5 s the way a real
   brain takes it. What it caught: the "…" line under the card while the press was in flight took away the card's screen-high floor
   (assistantView.css), so the old card dropped at the press, the new one sat low, and the answer slid it up seconds later. */

const WATCH_MS = 8000, SETTLE_MS = 1200;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const nextEnabled = (page) => page.waitForFunction(() => [...document.querySelectorAll("button")].some((n) => n.textContent.trim() === "Next" && !n.disabled), { timeout: 30000 });
const clickNext = (page) => page.evaluate(() => {
  const b = [...document.querySelectorAll("button")].find((n) => n.textContent.trim() === "Next" && !n.disabled);
  if (!b) throw new Error("Next must be enabled for this owner gesture");
  b.click();
});
// every frame and every mutation: which element is the card on the table (its identity), its key, whether a loading state is up in
// it, and its box
const record = (page) => page.evaluate(() => {
  const ids = new WeakMap(); let n = 0;
  const idOf = (e) => { if (!ids.has(e)) ids.set(e, ++n); return ids.get(e); };
  const log = [], t0 = performance.now();
  let last = "";
  const note = () => {
    const e = [...document.querySelectorAll(".tq-canvas-live [data-tq-canvas-item]")].filter((x) => x.getBoundingClientRect().height > 0).pop() || null;
    const r = e?.getBoundingClientRect();
    const s = { el: e ? idOf(e) : 0, key: e?.getAttribute("data-tq-canvas-item") || null, page: e ? idOf(e.querySelector("[data-tq-task-page]") || e) : 0,
      spin: !!e && !!e.querySelector("[data-tq-task-loading], .MuiCircularProgress-root"), top: r ? Math.round(r.top) : null };
    const sig = JSON.stringify(s);
    if (sig !== last) { last = sig; log.push({ t: Math.round(performance.now() - t0), ...s }); }
  };
  note();
  const mo = new MutationObserver(note);
  mo.observe(document.body, { subtree: true, childList: true, attributes: true });
  let raf = 0; const tick = () => { note(); raf = requestAnimationFrame(tick); }; tick();
  window.__tqStop = () => { mo.disconnect(); cancelAnimationFrame(raf); note(); return log; };
});

const assertSteady = (log, what) => {
  const old = log[0], at = log.findIndex((s) => s.el && s.key !== old.key);
  const msg = (why) => `${what}: ${why}: ${JSON.stringify(log)}`;
  assert.ok(at > 0, msg("Next put another item on the table"));
  // the item put down stays where it stood until the next one is up - it dropped down the screen at the press
  assert.ok(log.slice(0, at).every((s) => s.key !== old.key || Math.abs(s.top - old.top) <= 2), msg("the card put down moved before the next came up"));
  const first = log[at], after = log.slice(at), filled = after.findIndex((s) => !s.spin);
  assert.ok(after.every((s) => s.el), msg("the table went empty"));
  assert.ok(after.every((s) => s.key === first.key), msg("the table's key changed"));
  assert.ok(after.every((s) => s.el === first.el && s.page === first.page), msg("the card remounted"));
  assert.ok(filled >= 0 && after.slice(filled).every((s) => !s.spin), msg("a loading state came back after the card filled"));
  // it comes to rest at once - the scroll that brings its top up is the press's own - and stays there whatever lands after
  const rest = after[after.length - 1].top, still = after.findIndex((s, i) => after.slice(i).every((x) => Math.abs(x.top - rest) <= 2));
  assert.ok(after[still].t - first.t <= SETTLE_MS, msg(`the card moved ${after[still].t - first.t} ms after it came up`));
};

test("the item Next draws at once stays mounted and in place while its answer, reads and rail land", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  // the harness's own guard, wrapped: a request the test slows is held, then handed to it as before
  const slow = [];
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (req) => {
    const rule = slow.find((s) => s.test(req.url(), req.method()));
    if (!rule) return page.fixtureRequestGuard(req);
    setTimeout(() => page.fixtureRequestGuard(req), rule.ms);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  // the walk starts on the rail's first row, clicked: Next goes on from there
  const first = await page.$eval("[data-tq-rail] .tq-pile-row[data-tq-key]", (e) => e.getAttribute("data-tq-key"));
  await page.evaluate((k) => document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"] .card`).click(), first);
  await page.waitForFunction((k) => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") === k, { timeout: 20000 }, first);

  const press = async (what) => {
    await nextEnabled(page);
    await sleep(1500);                                  // what is on the table settles first
    await record(page);
    await clickNext(page);
    await sleep(WATCH_MS);
    assertSteady(await page.evaluate(() => window.__tqStop()), what);
  };
  for (let i = 1; i <= 2; i += 1) await t.test(`plain Next ${i}`, () => press(`plain ${i}`));
  for (let i = 1; i <= 3; i += 1) await t.test(`Next whose answer takes 2.5 s ${i}`, async () => {
    slow.splice(0, slow.length, { test: (u, m) => m === "POST" && /\/api\/concierge\/(?:stream|next)$/.test(new URL(u).pathname), ms: 2500 });
    try { await press(`slow ${i}`); } finally { slow.length = 0; }
  });
  // ...and the rail's own reads, slow: the rail reload after a landing must not touch the card on the table
  await t.test("Next whose rail reads take 2.5 s", async () => {
    slow.splice(0, slow.length, { test: (u, m) => m === "GET" && new URL(u).pathname === "/api/funnel/pile", ms: 2500 });
    try { await press("slow rail"); } finally { slow.length = 0; }
  });
  assert.deepEqual(errors, []);
});
