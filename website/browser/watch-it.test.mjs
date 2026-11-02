import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, doVerb, rail, sleep } from "./walkdriver.mjs";

/* WATCH IT (watch.py, the owner, 2026-11-01): a task that is not the owner's, kept open while somebody else handles it. The press sends
   nothing; the row moves under Watching at the foot of Tasks - still on the walk, which reaches it after Tasks (the owner, 2026-11-02) -
   and the walk goes on to the row that was below it. Opened again, the same button (Stop watching) ends the watch and the row is back
   under Tasks. */
const until = (page, f, arg, timeout = 20000) => page.waitForFunction(f, { timeout, polling: 100 }, arg).catch(() => {});
const under = (page, key) => page.evaluate((k) => document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"]`)?.closest("[data-tq-run]")?.getAttribute("data-tq-run") || null, key);

test("Watch it moves the task under Watching, the walk going on below it, and Stop watching brings it back to Tasks", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t);
  const tasks = await page.$$eval('[data-tq-run="task"] .tq-pile-row', (els) => els.map((e) => ({ key: e.getAttribute("data-tq-key"), text: e.innerText })));
  const pick = tasks.find((r) => /TQ-\d+/.test(r.text)) || tasks[0];
  assert.ok(pick, `the demo rail has no task: ${JSON.stringify(await rail(page))}`);
  await clickRow(page, pick.key);
  await until(page, (k) => document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") === k, pick.key);
  let pressed = null;                                   // ...the task's moves come with its card, a beat after the ring
  for (let i = 0; i < 20 && !(pressed = await doVerb(page, "watch")); i++) await sleep(500);
  assert.ok(pressed, "the task has no Watch it");
  await until(page, (k) => document.querySelector(`[data-tq-run="watching"] .tq-pile-row[data-tq-key="${k}"]`), pick.key);
  assert.equal(await under(page, pick.key), "watching", `the row did not move under Watching: ${JSON.stringify(await rail(page))}`);
  const heading = await page.evaluate(() => document.querySelector('[data-tq-run="watching"]')?.innerText || "");
  assert.match(heading, /watching/i, "the group has no Watching heading");
  await sleep(1500);
  const now = (await rail(page)).find((r) => r.cur);
  assert.notEqual(now?.key, pick.key, "the walk stayed on the watched row");
  // ...and opened again, its own button says Stop watching and ends the watch
  await clickRow(page, pick.key);
  await until(page, (k) => document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") === k, pick.key);
  // ...once the task as it now stands is drawn: its button reads Stop watching (the read held from before the watch said Watch it)
  const says = () => page.evaluate(() => [...document.querySelectorAll('[data-tq-verb="watch"]')].map((b) => b.textContent.trim()));
  for (let i = 0; i < 40 && !(await says()).includes("Stop watching"); i++) await sleep(250);
  assert.ok((await says()).includes("Stop watching"), `the watched task's button says ${JSON.stringify(await says())}`);
  pressed = null;
  for (let i = 0; i < 20 && !(pressed = await doVerb(page, "watch")); i++) await sleep(500);
  assert.ok(pressed, "the watched task has no Stop watching");
  // ...the row on the table keeps the band it was opened in (funnelPile.bandsOf's pin); off the table it is drawn where it now is
  for (let i = 0; i < 20 && (await says()).includes("Stop watching"); i++) await sleep(250);
  const other = tasks.find((r) => r.key !== pick.key);
  if (other) await clickRow(page, other.key);
  await until(page, (k) => document.querySelector(`[data-tq-run="task"] .tq-pile-row[data-tq-key="${k}"]`), pick.key);
  assert.equal(await under(page, pick.key), "task", "Stop watching left the row under Watching");
  assert.deepEqual(errors, []);
});
