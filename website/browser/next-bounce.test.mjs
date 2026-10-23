import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* NEXT NEVER BOUNCES BACK (the owner, 2026-10-23: "i hit next on this, it goes to [the row below] then jumps back to [the task]"). A task on
   the table, Next draws the row below it at once - and a row arriving while the press is being made (after its admission, before its
   commit check) refused the press as stale: the whole rail had moved though the pick had not, and the page took the drawn row down and
   put the task it left back up. Here: the first task on the table, a task armed to land inside the press, Next, the rail's reads slowed -
   the table goes to the row below and stays there, every frame, through the answer, the arrival and the rail that follows. */

const WATCH_MS = 7000;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rail = (page) => page.$$eval("[data-tq-rail] .tq-pile-row", (els) => els
  .map((r) => ({ key: r.getAttribute("data-tq-key"), level: r.closest("[data-tq-run]")?.getAttribute("data-tq-run") })).filter((r) => r.key));
const clickRow = (page, key) => page.evaluate((k) => document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"] .card`).click(), key);
const nextEnabled = (page) => page.waitForFunction(() => [...document.querySelectorAll("button")].some((n) => n.textContent.trim() === "Next" && !n.disabled), { timeout: 30000 });
const clickNext = (page) => page.evaluate(() => {
  const b = [...document.querySelectorAll("button")].find((n) => n.textContent.trim() === "Next" && !n.disabled);
  if (!b) throw new Error("Next must be enabled for this owner gesture");
  b.click();
});
// every frame: the rail's ringed row and the card on the table
const record = (page) => page.evaluate(() => {
  const log = [], t0 = performance.now(); let last = "";
  const note = () => {
    const card = [...document.querySelectorAll(".tq-canvas-live [data-tq-canvas-item]")].filter((x) => x.getBoundingClientRect().height > 0).pop();
    const s = { ring: document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") || null, card: card?.getAttribute("data-tq-canvas-item") || null };
    const sig = JSON.stringify(s);
    if (sig !== last) { last = sig; log.push({ t: Math.round(performance.now() - t0), ...s }); }
  };
  const mo = new MutationObserver(note); mo.observe(document.body, { subtree: true, childList: true, attributes: true });
  let raf = 0; const tick = () => { note(); raf = requestAnimationFrame(tick); }; tick();
  window.__tqStop = () => { mo.disconnect(); cancelAnimationFrame(raf); note(); return log; };
});

test("Next to the row below stays there while a row lands inside the press and the rail reloads", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  // the rail's reads slowed: the reload after the answer lands well after the card
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (req) => {
    const slow = req.method() === "GET" && new URL(req.url()).pathname === "/api/funnel/pile";
    if (slow) setTimeout(() => page.fixtureRequestGuard(req), 1500); else page.fixtureRequestGuard(req);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });

  const before = await rail(page);
  const tasks = before.filter((r) => r.level === "task");
  assert.ok(tasks.length >= 2, `the demo rail has two tasks: ${JSON.stringify(before)}`);
  const first = tasks[0].key, below = tasks[1].key;
  await clickRow(page, first);
  await page.waitForFunction((k) => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") === k, { timeout: 20000 }, first);
  await nextEnabled(page);
  await sleep(1500);                                         // what is on the table settles first

  const armed = await page.evaluate(async () => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    return (await fetch("/api/fixture/processing/arrive-during-next", { method: "POST", headers, body: "{}" })).json();
  });
  assert.equal(armed.armed, true, JSON.stringify(armed));
  await record(page);
  await clickNext(page);
  await sleep(WATCH_MS);
  const log = await page.evaluate(() => window.__tqStop());
  const msg = (why) => `${why}: ${JSON.stringify(log)}`;
  const at = log.findIndex((s) => s.ring === below);
  assert.ok(at >= 0, msg(`Next did not go to the row below (${below})`));
  // from the moment the row below is up, nothing but a press may move the table: never back to the task it left
  assert.ok(log.slice(at).every((s) => s.ring === below), msg("the rail's ring left the row below"));
  assert.ok(log.slice(at).every((s) => s.card !== first), msg("the task Next left came back onto the table"));
  assert.equal(log.at(-1).card, below, msg("the table is not on the row below"));
  const body = await page.evaluate(() => document.body.innerText);
  assert.ok(!/list changed while you pressed Next|press Next again/i.test(body), "the press was refused");
  // ...and the row that arrived is on the rail, below - it moved nothing
  const after = await rail(page);
  assert.ok(after.length > before.length, `the arrival reached the rail: ${JSON.stringify(after)}`);
  assert.deepEqual(after.filter((r) => before.some((b) => b.key === r.key)).map((r) => r.key), before.filter((b) => after.some((r) => r.key === b.key)).map((r) => r.key));
  assert.deepEqual(errors, []);
});
