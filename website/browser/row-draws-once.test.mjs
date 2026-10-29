import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE ROW DRAWS ONCE (the owner, 2026-10-27: "I reopened a task and there were no buttons on the bottom, then it reloaded the buttons and
   showed Next / Reopen task / Share. Why is it reloading and reflashing? ... not to load then reload"; earlier: "when you load a task the
   buttons load then go gray then reload"). Every frame and every mutation from the press, the dock's row as drawn - hidden or not, each
   button's label and whether it is off - through Reopen, Next, a rail click, a deep link, Mark done and a reload. The distinct states it
   goes through are the old row and the new one, nothing between: no empty or hidden row, no all-greyed one, no third set swapping in.
   The pressed button's own busy word ("Reopening…") is the press answering, and counts as the old row; a Next held steady (data-tq-steady,
   drawn as it was) is not off. */

const WATCH_MS = 3500;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const RECORD = () => {
  const log = [], t0 = performance.now();
  let last = null;
  const note = () => {
    const row = document.querySelector(".tq-dock [data-tq-row]");
    const hidden = !!row && getComputedStyle(row).visibility === "hidden";
    const btns = row ? [...row.querySelectorAll(".tq-arow-verbs button")].map((b) => `${b.textContent.trim()}${b.disabled && !b.hasAttribute("data-tq-steady") ? "[off]" : ""}`) : [];
    const s = !row ? "" : hidden ? `HIDDEN(${btns.join("|")})` : btns.join("|");
    if (s !== last) { last = s; log.push({ t: Math.round(performance.now() - t0), s }); }
  };
  note();
  const mo = new MutationObserver(note);
  mo.observe(document, { subtree: true, childList: true, attributes: true, characterData: true });
  let raf = 0; const tick = () => { note(); raf = requestAnimationFrame(tick); }; tick();
  window.__tqRowStop = () => { mo.disconnect(); cancelAnimationFrame(raf); note(); return log; };
};
const record = (page) => page.evaluate(RECORD);
const stop = (page) => page.evaluate(() => window.__tqRowStop());

// the states drawn, in order: the old row (and the pressed button's own busy word on it), then the new one - and that is all
const assertOnce = (log, what, { fromNothing = false } = {}) => {
  const msg = (why) => `${what}: ${why}: ${JSON.stringify(log)}`;
  // one row with a button turned to its busy word ("Reopen task" -> "Reopening…[off]") is the same row, answering
  const same = (a, b) => { const x = a.split("|"), y = b.split("|");
    return x.length === y.length && x.every((v, i) => v === y[i] || /…(\[off\])?$/.test(v) || /…(\[off\])?$/.test(y[i])); };
  const states = log.map((x) => x.s).filter((s, i, a) => i === 0 || !same(s, a[i - 1]));
  const drawn = fromNothing ? states.filter((s, i) => i > 0 || s) : states.slice(1);
  if (process.env.TQ_PROBE) console.log(what, JSON.stringify(log));
  for (const s of drawn) {
    assert.ok(s && !s.startsWith("HIDDEN"), msg("the row went empty or hidden"));
    assert.ok(s.split("|").some((b) => !b.endsWith("[off]")), msg("the row drew all greyed"));
  }
  assert.ok(drawn.length <= 1, msg(`the row drew ${drawn.length} sets after the old one: ${JSON.stringify(drawn)}`));
  return states.at(-1);
};

test("the action row draws once with the new item's buttons: Reopen, Next, rail, deep link, Mark done, reload", { timeout: 400000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const fixture = (path, body = {}) => page.evaluate(async (p, b) => (await fetch(p, { method: "POST", body: JSON.stringify(b),
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" } })).json(), path, body);
  const rowUp = () => page.waitForFunction(() => document.querySelectorAll(".tq-dock [data-tq-row] .tq-arow-verbs button, [data-tq-head-moves] button").length > 1, { timeout: 30000 });
  const settle = async () => { await rowUp(); await sleep(2000); };
  const watch = async (what, act, opts) => {
    await record(page); await act(); await sleep(WATCH_MS);
    return assertOnce(await stop(page), what, opts);
  };
  const keys = await page.$$eval("[data-tq-rail] .tq-pile-row", (els) => els.filter((r) => r.closest("[data-tq-run]")?.getAttribute("data-tq-run") === "task")
    .map((r) => r.getAttribute("data-tq-key")).filter(Boolean));
  assert.ok(keys.length >= 4, `the demo rail has tasks: ${keys}`);
  const clickRow = (k) => page.evaluate((k) => document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"] .card`).click(), k);
  await clickRow(keys[0]); await settle();

  for (const [i, k] of [keys[1], keys[2], keys[0]].entries()) await t.test(`rail click ${i + 1}`, async () => {
    await watch(`rail ${i + 1}`, () => clickRow(k)); await settle();
  });
  for (let i = 1; i <= 3; i += 1) await t.test(`Next ${i}`, async () => {
    await watch(`next ${i}`, () => page.evaluate(() => document.querySelector(".tq-dock [data-tq-row] [data-tq-next]").click())); await settle();
  });
  // ...and Back, the walk's step up the line (the owner, 2026-10-27): the same one draw
  for (let i = 1; i <= 2; i += 1) await t.test(`Back ${i}`, async () => {
    await watch(`back ${i}`, () => page.evaluate(() => document.querySelector(".tq-dock [data-tq-row] [data-tq-walk-back]").click())); await settle();
  });
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data || [];
  const open = tasks.filter((x) => !["done", "dropped"].includes(x.Status)).map((x) => x.TaskId);
  assert.ok(open.length >= 3, `the demo has open tasks: ${open}`);
  const link = (id) => page.evaluate((id) => { location.hash = `task=${id}`; }, id);
  for (const [i, id] of open.slice(0, 3).entries()) await t.test(`deep link ${i + 1}`, async () => {
    await watch(`link ${i + 1}`, () => link(id)); await settle();
  });

  await t.test("Reopen", async () => {
    const closed = await fixture("/api/fixture/task/agent-closed", { answer: "Re-added the missing secret; the re-run passed.", said: "the re-run passed" });
    assert.ok(closed.taskId, JSON.stringify(closed));
    await link(closed.taskId);
    await page.waitForSelector('.tq-dock [data-tq-row] [data-tq-verb="reopen"], [data-tq-head-moves] [data-tq-verb="reopen"]', { timeout: 30000 }); await sleep(2000);
    const end = await watch("reopen", () => page.evaluate(() => document.querySelector('.tq-dock [data-tq-row] [data-tq-verb="reopen"], [data-tq-head-moves] [data-tq-verb="reopen"]').click()));
    assert.ok(!/Reopen/.test(end), `the reopened task's row: ${end}`);
    await settle();
  });

  await t.test("Mark done", async () => {
    // a task on the walk whose row carries Mark done: its close puts the next one up
    const doneBtn = () => page.evaluate(() => !![...document.querySelectorAll(".tq-dock [data-tq-row] .tq-arow-verbs button, [data-tq-head-moves] button")].find((b) => b.textContent.trim() === "Mark done" && !b.disabled));
    const rows = await page.$$eval("[data-tq-rail] .tq-pile-row", (els) => els.filter((r) => r.closest("[data-tq-run]")?.getAttribute("data-tq-run") === "task")
      .map((r) => r.getAttribute("data-tq-key")).filter(Boolean));
    let found = false;
    for (const k of rows) { await clickRow(k); await settle(); if ((found = await doneBtn())) break; }
    assert.ok(found, "a task on the rail offers Mark done");
    await watch("mark done", () => page.evaluate(() => [...document.querySelectorAll(".tq-dock [data-tq-row] .tq-arow-verbs button, [data-tq-head-moves] button")].find((b) => b.textContent.trim() === "Mark done").click()));
    await settle();
  });

  await t.test("reload", async () => {
    await link(open[1]); await settle();
    await page.evaluateOnNewDocument(`(${RECORD.toString()})()`);
    await page.reload({ waitUntil: "domcontentloaded" });
    await sleep(WATCH_MS + 3000);
    assertOnce(await stop(page), "reload", { fromNothing: true });
  });
  assert.deepEqual(errors, []);
});
