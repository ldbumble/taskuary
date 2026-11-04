import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, doVerb, sleep } from "./walkdriver.mjs";

/* A WATCHED ROW CLICKED HAS ITS NAV AT ONCE (the owner, 2026-11-04: "i clicked a watching task and there is no next/back thing yet? took a
   long time to light up why? watching is not much to generate?"). A row under Watching is on the walk (watch.py) and has nothing to draft:
   clicked, it draws at once and Back and Next are pressable within about a second. They stand greyed until the click's walk move lands
   (rulings 2026-11-03), and that answer built the whole rail first - its own read of the row had emptied the cache - so on a big rail the
   bar stayed grey for as long as the build took (server.walk_open). */
const until = (page, f, arg, timeout = 20000) => page.waitForFunction(f, { timeout, polling: 100 }, arg).catch(() => {});
const ringed = (page, k) => until(page, (k) => document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") === k, k);
const nav = (page) => page.evaluate(() => {
  const n = document.querySelector("[data-tq-row] [data-tq-next]"), b = document.querySelector("[data-tq-row] [data-tq-walk-back]");
  return { next: !!n && !n.disabled, back: !!b && !b.disabled };
});
// the click, and how long until Back and Next are both there and pressable
async function lit(page, key) {
  const t0 = Date.now();
  await clickRow(page, key);
  let seen = null;
  for (; Date.now() - t0 < 15000; await sleep(25)) if ((seen = await nav(page)).next && seen.back) break;
  return { ms: Date.now() - t0, ...seen };
}
const LIT_MS = 1200;

test("a row under Watching, clicked, has Back and Next lit within a second", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t);
  const tasks = await page.$$eval('[data-tq-run="task"] .tq-pile-row', (els) => els.map((e) => e.getAttribute("data-tq-key")));
  assert.ok(tasks.length >= 3, "the demo rail has tasks");
  const pick = tasks[1];
  await clickRow(page, pick); await ringed(page, pick);
  let pressed = null;
  for (let i = 0; i < 20 && !(pressed = await doVerb(page, "watch")); i++) await sleep(500);
  assert.ok(pressed, "the task has no Watch it");
  await until(page, (k) => document.querySelector(`[data-tq-run="watching"] .tq-pile-row[data-tq-key="${k}"]`), pick);
  await sleep(2500);
  // ...from another task, the way the owner came to it: the rail, not the walk
  await clickRow(page, tasks[0]); await ringed(page, tasks[0]); await sleep(2500);
  const got = await lit(page, pick);
  console.log(`watched row on the demo rail: Back and Next lit after ${got.ms} ms`);
  assert.ok(got.next && got.back, `the watched row's bar: ${JSON.stringify(got)}`);
  assert.ok(got.ms <= LIT_MS, `Back and Next lit after ${got.ms} ms`);
  assert.deepEqual(errors, []);
});

// ...and on a rail the size of a working inbox, a task triage put under Watching itself (its watch verdict, 2026-11-03), never opened
const call = (h) => async (method, url, body) => (await fetch(`${h.fixtureApi}${url}`, { method,
  headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined })).json();
test("on a big rail, a task watched before it was ever opened, clicked, has Back and Next lit within a second", { timeout: 300000 }, async (t) => {
  const { h, page, errors } = await boot(t), api = call(h);
  await api("POST", "/api/fixture/walk/big", { tasks: 200, reports: 50, fyi: 200 });
  const pile = (await api("GET", "/api/funnel/pile")).items, tasks = pile.filter((i) => i.tid && i.lane !== "fyi");
  const pick = tasks[5], op = await api("POST", "/api/operations", { kind: "task.watching", target: pick.tid, params: {} });
  assert.equal((await api("POST", `/api/operations/${op.id}/execute`, { version: op.version })).status, "done", "Watch it ran");
  await page.reload({ waitUntil: "domcontentloaded" });
  await until(page, (k) => document.querySelector(`[data-tq-run="watching"] .tq-pile-row[data-tq-key="${k}"]`), pick.key, 60000);
  await clickRow(page, tasks[0].key); await ringed(page, tasks[0].key); await sleep(3000);
  const got = await lit(page, pick.key);
  console.log(`watched row on a ${pile.length}-row rail: Back and Next lit after ${got.ms} ms`);
  assert.ok(got.next && got.back, `the watched row's bar: ${JSON.stringify(got)}`);
  assert.ok(got.ms <= LIT_MS, `Back and Next lit after ${got.ms} ms`);
  assert.deepEqual(errors, []);
});
