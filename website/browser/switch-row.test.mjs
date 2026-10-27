import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* SWITCHING TASKS, THE ROW GOES STRAIGHT ACROSS (the owner, 2026-10-26: "fix switching tasks thing of course"). A rail click or Next put
   another item on the table, and the row still wore the old one's buttons after it was up, Next went grey for the ~300 ms the pull took,
   and only then did the new one's buttons settle. Since 2026-10-27 (row-draws-once) the old row may stand whole until the new one is
   ready, and is then replaced in one step - never mixed with it. Sampled every frame and every mutation from the press: the row's buttons
   (data-tq-for) are all the old item's or all the new one's, the old never back after the new, Next is never greyed - not disabled at all on a rail
   click, and on its own press held but drawn as it was - and the new item's own buttons come up. */

const WATCH_MS = 3000;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// the item on the table, the items the row's buttons were registered for, and its buttons: [off] disabled, [grey] drawn as off
const record = (page) => page.evaluate(() => {
  const log = [], t0 = performance.now();
  let last = "";
  const note = () => {
    const table = [...document.querySelectorAll(".tq-canvas-live [data-tq-canvas-item]")].filter((x) => x.getBoundingClientRect().height > 0).pop();
    const row = document.querySelector(".tq-dock [data-tq-row]");
    const grey = (b) => { const s = getComputedStyle(b); return Number(s.opacity) < 1 || s.backgroundColor === "rgb(185, 193, 200)"; };
    const btns = row ? [...row.querySelectorAll(".tq-arow-verbs button")].map((b) => `${b.textContent.trim()}${b.disabled ? "[off]" : ""}${grey(b) ? "[grey]" : ""}`) : [];
    const s = { table: table?.getAttribute("data-tq-canvas-item") || null, for: [...new Set([...(row?.querySelectorAll(".tq-arow-verbs [data-tq-for]") || [])]
      .map((b) => b.getAttribute("data-tq-for")))].join(","), btns: btns.join("|") };
    const sig = JSON.stringify(s);
    if (sig !== last) { last = sig; log.push({ t: Math.round(performance.now() - t0), ...s }); }
  };
  note();
  const mo = new MutationObserver(note);
  mo.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true });
  let raf = 0; const tick = () => { note(); raf = requestAnimationFrame(tick); }; tick();
  window.__tqPress = () => { note(); log.push({ t: Math.round(performance.now() - t0), press: true }); };   // the owner's press, in the log
  window.__tqStop = () => { mo.disconnect(); cancelAnimationFrame(raf); note(); return log; };
});

const nextOf = (s) => s.btns.split("|").find((b) => b.startsWith("Next")) || "";
// from the press on: nothing on the row is A's - while A is still up for the pull, and once B is - and Next never looks off (on a rail
// click it is never off at all); B comes up and stays
const assertStraight = (rec, what, rail) => {
  const msg = (why) => `${what}: ${why}: ${JSON.stringify(rec)}`, p = rec.findIndex((s) => s.press), log = rec.filter((s) => !s.press);
  assert.ok(p > 0, msg("the press is in the log"));
  const a = log[0].table, at = log.findIndex((s) => s.table && s.table !== a);
  assert.ok(a && at > 0, msg("another item came up"));
  const b = log[at].table, after = log.slice(at);
  assert.ok(after.every((s) => s.table === b), msg("the table stayed on B"));
  assert.ok(log[0].for === a, msg("A's buttons were drawn for A"));
  // ...THE ROW DRAWS ONCE (the owner, 2026-10-27: "not to load then reload"): A's row may stand, as it was, until B's is whole - then B's,
  // in one step. Never the two mixed, never a lone Next between them, and A's never back once B's is up
  const fors = rec.slice(p).filter((s) => !s.press).map((s) => s.for);
  assert.ok(fors.every((f) => f === a || f === b), msg("the row mixed the two items' buttons, or drew neither's"));
  assert.ok(fors.indexOf(b) < 0 || fors.slice(fors.indexOf(b)).every((f) => f === b), msg("the old item's buttons came back after the new one's"));
  assert.ok(log.every((s) => nextOf(s) && !nextOf(s).includes("[grey]")), msg("Next greyed or left the row during the switch"));
  if (rail) assert.ok(log.every((s) => !nextOf(s).includes("[off]")), msg("Next was disabled by a rail click"));
  const end = log[log.length - 1];
  assert.ok(end.for === b && end.btns.split("|").length > 1 && nextOf(end) === "Next", msg("B's own buttons came up"));
};

test("switching tasks: the old item's buttons leave at the switch and Next stays as it was", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const keys = await page.$$eval("[data-tq-rail] .tq-pile-row", (els) => els.filter((r) => r.closest("[data-tq-run]")?.getAttribute("data-tq-run") === "task")
    .map((r) => r.getAttribute("data-tq-key")).filter(Boolean));
  assert.ok(keys.length >= 4, `the demo rail has tasks: ${keys}`);
  const clickRow = (k) => page.evaluate((k) => { window.__tqPress?.(); document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"] .card`).click(); }, k);
  const settled = async (k) => {
    await page.waitForFunction((k) => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") === k
      && document.querySelectorAll(".tq-dock [data-tq-row] .tq-arow-verbs button").length > 1, { timeout: 20000 }, k);
    await sleep(1500);                                  // its reads, its advice and the rail behind it land
  };

  for (const [i, [ka, kb]] of [[keys[0], keys[1]], [keys[2], keys[3]], [keys[1], keys[0]]].entries()) await t.test(`rail click ${i + 1}`, async () => {
    await clickRow(ka); await settled(ka);
    await record(page);
    await clickRow(kb);
    await sleep(WATCH_MS);
    const log = await page.evaluate(() => window.__tqStop());
    if (process.env.TQ_PROBE) console.log(`rail ${i + 1}`, JSON.stringify(log));
    assertStraight(log, `rail ${i + 1}`, true);
  });

  // ...and between two tasks opened by name (a link, Search, the Assistant's Open): the task view's own verbs - a draft's Send and
  // Redraft among them - are the ones that stood over the next task
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data || [];
  const open = tasks.filter((x) => !["done", "dropped"].includes(x.Status)).map((x) => x.TaskId).slice(0, 4);
  assert.ok(open.length >= 4, `the demo has open tasks: ${open}`);
  const openTask = (id) => page.evaluate((id) => { window.__tqPress?.(); location.hash = `task=${id}`; }, id);
  for (const [i, [a, b]] of [[open[0], open[1]], [open[2], open[3]]].entries()) await t.test(`task link ${i + 1}`, async () => {
    await openTask(a);
    await page.waitForFunction((id) => {
      const item = document.querySelector(`.tq-canvas-live [data-tq-task-page="${id}"]`)?.closest("[data-tq-canvas-item]")?.getAttribute("data-tq-canvas-item");
      return !!item && !!document.querySelector(`.tq-dock [data-tq-row] [data-tq-for="${item}"]`);
    }, { timeout: 20000 }, a).catch(async (e) => { throw new Error(`${e.message}: ${await page.evaluate(() => JSON.stringify({ hash: location.hash,
      items: [...document.querySelectorAll("[data-tq-canvas-item]")].map((x) => x.getAttribute("data-tq-canvas-item")),
      fors: [...document.querySelectorAll("[data-tq-for]")].map((x) => x.getAttribute("data-tq-for")) }))}`); });
    await sleep(1500);
    await record(page);
    await openTask(b);
    await sleep(WATCH_MS);
    const log = await page.evaluate(() => window.__tqStop());
    if (process.env.TQ_PROBE) console.log(`link ${i + 1}`, JSON.stringify(log));
    assertStraight(log, `link ${i + 1}`, true);
  });

  for (let i = 1; i <= 2; i += 1) await t.test(`Next ${i}`, async () => {
    await sleep(500);
    await record(page);
    await page.evaluate(() => { window.__tqPress(); document.querySelector(".tq-dock [data-tq-row] [data-tq-next]").click(); });
    await sleep(WATCH_MS);
    const log = await page.evaluate(() => window.__tqStop());
    if (process.env.TQ_PROBE) console.log(`next ${i}`, JSON.stringify(log));
    assertStraight(log, `next ${i}`, false);
  });
  assert.deepEqual(errors, []);
});
