import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, pressNext, sleep } from "./walkdriver.mjs";

/* NEXT AND BACK FROM A ROW YOU CLICKED, AND WHAT EACH READS (the owner, 2026-10-30: "if you click on task then hit back it should go to the one
   before it even if we did not start from the top. The only ones that disappear on read is reports and fyi, tasks never go away even if next
   until explicitly marked done", "i hit back on fyi it also marked them read ... if you click back it's not read only next"). On the demo
   world: a task clicked mid-list - Back is the row above, Next the row below, and a task Next passed is still on the rail; Back onto an FYI
   batch leaves it unread, and Next past it reads it off the rail. */
const until = async (f, ms = 15000) => { for (const t0 = Date.now(); Date.now() - t0 < ms; await sleep(200)) if (await f()) return true; return false; };
const pressBack = (page) => page.evaluate(() => { const b = document.querySelector(".tq-dock [data-tq-row] [data-tq-walk-back]"); if (b && !b.disabled) { b.click(); return true; } return false; });
const ring = (page) => page.evaluate(() => document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") || "");
const run = (page, sec) => page.$$eval(`[data-tq-run="${sec}"] .tq-pile-row[data-tq-key]`, (els) => els.map((e) => e.getAttribute("data-tq-key")));

test("a task clicked mid-list: Back is the row above, Next the row below, and tasks stay", { timeout: 300000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 900 });
  const tasks = await run(page, "task");
  assert.ok(tasks.length >= 4, `the demo has tasks: ${tasks}`);
  const at = 2;
  await clickRow(page, tasks[at]); await sleep(3000);
  assert.ok(await pressBack(page), "Back is offered on a task clicked mid-list");
  assert.ok(await until(async () => (await ring(page)) === tasks[at - 1]), `Back went to ${await ring(page)}, not the row above`);
  await sleep(2000);
  assert.ok(await pressNext(page));
  assert.ok(await until(async () => (await ring(page)) === tasks[at]), `Next from there went to ${await ring(page)}, not the row below`);
  await sleep(2000);
  assert.ok(await pressNext(page));
  assert.ok(await until(async () => (await ring(page)) === tasks[at + 1]), `Next went to ${await ring(page)}`);
  await sleep(2000);
  const now = await run(page, "task");
  for (const k of tasks.slice(at - 1, at + 1)) assert.ok(now.includes(k), `a task Next passed left the rail: ${k}`);
  assert.deepEqual(errors, []);
});

test("Back onto an FYI batch leaves it unread; Next past it reads it", { timeout: 300000 }, async (t) => {
  const { h, page, errors } = await boot(t, { width: 1440, height: 900 });
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET", headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" },
    ...(body ? { body: JSON.stringify(body) } : {}) }).then((r) => r.json());
  // the reports read, so the FYIs sit right under the last task
  for (const i of (await api("/api/funnel/pile")).items.filter((x) => x.lane === "report" || x.kind === "dashboard")) await api("/api/funnel/settle", { key: i.key, verb: "done" });
  await page.reload({ waitUntil: "domcontentloaded" }); await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 40000 }); await sleep(2500);
  const fyi = await run(page, "fyi");
  assert.ok(fyi.length, "the demo has FYIs");
  const unread = async (k) => (await api("/api/funnel/pile")).items.find((i) => i.key === k || (i.aliases || []).includes(k))?.unread;
  const tasks = await run(page, "task");
  await clickRow(page, tasks.at(-1)); await sleep(3000);
  assert.ok(await pressNext(page), "Next from the last task");                     // on to the FYI batch
  await sleep(4000);
  assert.ok(await pressBack(page), "Back from the FYI batch");                       // back up to the last task
  assert.ok(await until(async () => (await ring(page)) === tasks.at(-1)), `Back went to ${await ring(page)}`);
  await sleep(2500);
  assert.ok(await unread(fyi[0]), "Back from the FYI batch read it");
  assert.ok(await pressNext(page));                                                // on to the batch again
  await sleep(4000);
  assert.ok(await pressNext(page));                                                // Next past it reads it
  assert.ok(await until(async () => !(await unread(fyi[0])), 15000), "Next past the FYI batch did not read it");
  assert.deepEqual(errors, []);
});
