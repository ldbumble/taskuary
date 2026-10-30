import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, doVerb, pressNext, sleep } from "./walkdriver.mjs";

/* A NEW WALK FORGETS WHAT THE LAST ONE LEFT (the owner, 2026-10-30: "i was on a task hit send then it skipped the next task in list straight
   to fyi"). The page keeps the rows it left in a walk and puts down unseen any the server offers again - and only the walk button cleared
   that list. A task passed with Next, then a new chat (a new walk on the server), then the task above it closed: the server offered the
   passed task, rightly, and the page put it down unseen and walked on. On the demo world: the second task comes up after the first closes. */
const until = async (f, ms = 15000) => { for (const t0 = Date.now(); Date.now() - t0 < ms; await sleep(200)) if (await f()) return true; return false; };

test("after a new chat, closing the task above one passed in the old walk brings that task up", { timeout: 300000 }, async (t) => {
  const { h, page, errors } = await boot(t, { width: 1440, height: 900 });
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET", headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" },
    ...(body ? { body: JSON.stringify(body) } : {}) }).then((r) => r.json());
  const tasks = await page.$$eval('[data-tq-run="task"] .tq-pile-row[data-tq-key]', (els) => els.map((e) => e.getAttribute("data-tq-key")));
  const [first, second] = tasks;
  const ring = () => page.evaluate(() => document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") || "");

  await clickRow(page, second); await sleep(3500);
  assert.ok(await pressNext(page), "the second task has a Next");
  assert.ok(await until(async () => (await ring()) !== second), "Next left the second task");
  await sleep(2000);

  await api("/api/assistant/dock/new", {});                   // a new chat on the server: a new walk - the page is NOT reloaded, as the owner's wasn't
  await sleep(2500);

  await clickRow(page, first); await sleep(3500);
  doVerb(page, "done").catch(() => {});
  assert.ok(await until(async () => (await ring()) === second, 20000), `after the close the walk took ${await ring()}, not the second task`);
  assert.deepEqual(errors, []);
});
