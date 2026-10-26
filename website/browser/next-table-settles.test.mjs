import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* ONE PRESS WALKS ON (the owner, 2026-10-26: Next said "The list moved while that was loading - press it again" - "the list changed while
   you pressed next should be fixed as well"). A row clicked puts its task on the table and the rail is read again for it; Next pressed
   before that read lands waits on it. Here the task closed somewhere else meanwhile, so the read says the table's item is gone and clears
   the table under the press - which then stopped, its scope moved, and asked for another press. One press must reach the server and
   walk on to the row below, with no "press it again" line. */

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rail = (page) => page.$$eval("[data-tq-rail] .tq-pile-row", (els) => els
  .map((r) => ({ key: r.getAttribute("data-tq-key"), level: r.closest("[data-tq-run]")?.getAttribute("data-tq-run") })).filter((r) => r.key));
const post = (page, path, body) => page.evaluate(async (p, b) => {
  const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
  const r = await fetch(p, { method: "POST", headers, body: JSON.stringify(b) });
  return { status: r.status, body: await r.json() };
}, path, body);

test("Next pressed while the rail read clears the table under it walks on in one press", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [], held = [], streams = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let hold = false;
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (req) => {
    const u = new URL(req.url());
    if (req.method() === "POST" && u.pathname === "/api/concierge/stream") streams.push(req.postData() || "");
    if (hold && req.method() === "GET" && u.pathname === "/api/funnel/pile") { held.push(req); return; }
    page.fixtureRequestGuard(req);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const before = await rail(page), tasks = before.filter((r) => r.level === "task");
  assert.ok(tasks.length >= 2, `the demo rail has two tasks: ${JSON.stringify(before)}`);
  const first = tasks[0].key, below = tasks[1].key;
  const tid = await page.evaluate(async (k) => {
    const d = await (await fetch("/api/funnel/pile", { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json();
    return d.items.find((i) => i.key === k)?.tid;
  }, first);
  assert.ok(Number.isInteger(tid), `the first task row names its task: ${tid}`);

  // the rail's reads are held from here: the click's own re-read is the one Next will wait on
  hold = true;
  await page.evaluate((k) => document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"] .card`).click(), first);
  await page.waitForFunction((k) => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") === k, { timeout: 20000 }, first);
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((n) => n.textContent.trim() === "Next" && !n.disabled), { timeout: 30000 });
  for (let i = 0; i < 50 && !held.length; i += 1) await sleep(100);
  assert.ok(held.length >= 1, "the click asked the rail again");
  // ...the task closes somewhere else (the phone, the Tasks page): it leaves the rail
  const closed = await post(page, "/api/fixture/task/closed-elsewhere", { task_id: tid });
  assert.equal(closed.status, 200, JSON.stringify(closed));
  const pressedAt = streams.length;
  await page.evaluate(() => [...document.querySelectorAll("button")].find((n) => n.textContent.trim() === "Next" && !n.disabled).click());
  await sleep(800);
  assert.equal(streams.length, pressedAt, "the press waits on the rail read before it is sent");

  // the held read lands saying the table's item is gone, as the server does for an item that left (funnel.next_item -> null)
  hold = false;
  for (const req of held.splice(0)) {
    const u = new URL(req.url());
    if (u.searchParams.get("current") !== first) { page.fixtureRequestGuard(req); continue; }
    const headers = Object.fromEntries(Object.entries(req.headers()).filter(([k]) => /^x-taskuary-token$|^accept$/i.test(k)));
    const data = await (await fetch(req.url(), { headers })).json();
    await req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ...data, current: null }) });
  }
  await page.waitForFunction((k) => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") === k, { timeout: 20000 }, below)
    .catch(() => {});
  await sleep(1500);
  const ring = await page.evaluate(() => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") || null);
  const body = await page.evaluate(() => document.body.innerText);
  assert.ok(!/list moved while that was loading|press it again|press Next again/i.test(body), `the press was refused: ${body.slice(-600)}`);
  assert.equal(streams.length, pressedAt + 1, "one press, one navigation");
  assert.equal(ring, below, "Next walked on to the row below the task that closed");
  assert.deepEqual(errors, []);
});
